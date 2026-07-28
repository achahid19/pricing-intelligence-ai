import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_workspace
from app.catalog.models import Product
from app.discovery.models import (
    CompetitorProduct,
    CompetitorProductSnapshot,
    CompetitorSite,
    DiscoveryRun,
    ProductMatch,
)
from app.discovery.schemas import (
    CompetitorProductOut,
    CompetitorSiteCreate,
    CompetitorSiteOut,
    CompetitorSiteUpdate,
    DiscoveryRunCreate,
    DiscoveryRunOut,
    ProductDiscoveryCreate,
    ProductMatchCreate,
    ProductMatchOut,
    ProductMatchUpdate,
    TrackedMatchOut,
)
from app.db.database import get_db
from app.discovery.service import fetch_tracked_matches
from app.services import ai_client
from app.services.cooldown import check_cooldown
from app.services.model_catalog import default_model_for
from app.workspace.models import AiProviderConfig, Workspace

router = APIRouter()

# No queue/rate-limit middleware in this app yet — this is the cheapest
# possible guard against a stuck retry loop or an impatient double-click
# burning real AI-provider cost with zero server-side protection. Shared
# across every AI-cost action in this module (discovery runs, per-site
# product discovery, auto-match) — same guard, same reasoning, not a
# separate tunable per action.
DISCOVERY_COOLDOWN_SECONDS = 30


def _check_cooldown(last_at: Optional[datetime]) -> None:
    check_cooldown(last_at, DISCOVERY_COOLDOWN_SECONDS)


_MARKDOWN_CITATION_RE = re.compile(r"\s*\(\[[^\]]+\]\(https?://[^)]+\)\)")


def _strip_citations(text: Optional[str]) -> Optional[str]:
    """Web-search-enabled responses sometimes embed an inline markdown
    citation like "([genious.ma](https://...))" right in a text field —
    it renders as literal text, not a link, wherever we just display the
    field as plain text, so strip it before storing rather than leaving
    visual noise in the data for every future consumer (matching, reports)."""
    if not text:
        return text
    return _MARKDOWN_CITATION_RE.sub("", text).strip() or None


def _normalize_domain(raw: str) -> str:
    """Strip scheme, a leading www., and any trailing path/slash — so
    "https://www.example.com/" and "example.com" are recognized as the same
    competitor rather than creating a duplicate row. Also cuts at the first
    whitespace/parenthesis: the AI sometimes appends a trailing annotation
    after the bare domain (e.g. "genious.ma (genious communications)") — a
    valid domain never contains either, so this is safe to cut on."""
    domain = raw.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
    domain = domain.split("/")[0]
    return re.split(r"[\s(]", domain, maxsplit=1)[0]


async def _get_saved_site(db: AsyncSession, site_id: int, workspace_id: int) -> CompetitorSite:
    result = await db.execute(
        select(CompetitorSite).where(CompetitorSite.id == site_id, CompetitorSite.workspace_id == workspace_id)
    )
    site = result.scalars().first()
    if site is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Competitor site not found")
    if site.status != "saved":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Save this competitor before discovering its products.",
        )
    return site


def _to_run_out(
    run: DiscoveryRun, search_count: Optional[int] = None, skipped_known_count: Optional[int] = None
) -> DiscoveryRunOut:
    return DiscoveryRunOut(
        id=run.id,
        workspace_id=run.workspace_id,
        triggered_at=run.triggered_at,
        ai_provider=run.ai_provider,
        model=run.model,
        mode=run.mode,
        status=run.status,
        error_message=run.error_message,
        search_count=search_count,
        skipped_known_count=skipped_known_count,
        context_snapshot=run.context_snapshot,
        sites=[CompetitorSiteOut.model_validate(s) for s in run.sites],
    )


@router.post("/runs", response_model=DiscoveryRunOut)
async def create_discovery_run(
    payload: DiscoveryRunCreate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Trigger a discovery run: the workspace's active AI provider
    researches the web (its own native search tool) and proposes up to
    payload.max_candidates sites with confidence + rationale — either
    competitors (rival businesses, mode="competitor") or resellers of this
    workspace's own products (mode="reseller", for MAP-compliance
    monitoring). Synchronous — a single web-search-enabled AI call, may
    take 10-30s."""
    max_candidates = payload.max_candidates
    mode = payload.mode

    last_run_result = await db.execute(
        select(DiscoveryRun.triggered_at)
        .where(DiscoveryRun.workspace_id == workspace.id, DiscoveryRun.mode == mode)
        .order_by(DiscoveryRun.triggered_at.desc())
        .limit(1)
    )
    _check_cooldown(last_run_result.scalars().first())

    active_result = await db.execute(
        select(AiProviderConfig).where(
            AiProviderConfig.workspace_id == workspace.id,
            AiProviderConfig.is_active.is_(True),
        )
    )
    active_config = active_result.scalars().first()
    if active_config is None:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="No active AI provider configured for this workspace. Set one up in Settings first.",
        )
    model = active_config.model_override or default_model_for(active_config.provider)

    products_result = await db.execute(select(Product).where(Product.workspace_id == workspace.id))
    products = products_result.scalars().all()
    context = ai_client.build_discovery_context(workspace, products)

    # Domains already known for this workspace (any status, any prior run)
    # — re-running discovery shouldn't re-suggest a competitor the user has
    # already saved, dismissed, or is still sitting on from an earlier run.
    known_result = await db.execute(
        select(CompetitorSite.domain).where(CompetitorSite.workspace_id == workspace.id)
    )
    known_domains = {_normalize_domain(d) for d in known_result.scalars().all()}

    run = DiscoveryRun(
        workspace_id=workspace.id,
        ai_provider=active_config.provider,
        model=model,
        mode=mode,
        context_snapshot={"context": context, "max_candidates": max_candidates},
        status="running",
    )
    db.add(run)
    await db.flush()

    discover_fn = ai_client.discover_reseller_sites if mode == "reseller" else ai_client.discover_competitor_sites
    try:
        result, search_count = await discover_fn(db, workspace.id, context, max_candidates=max_candidates)
    except Exception as exc:
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        await db.commit()
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider couldn't complete discovery. Try again in a moment.",
        )

    skipped_known = 0
    for candidate in result.get("candidates", [])[:max_candidates]:
        domain = _normalize_domain(candidate.get("domain") or "")
        if not domain:
            continue
        if domain in known_domains:
            skipped_known += 1
            continue
        known_domains.add(domain)  # a run can propose the same domain twice; don't double-add within one run either
        try:
            confidence = max(0, min(100, int(candidate.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0
        db.add(
            CompetitorSite(
                workspace_id=workspace.id,
                discovery_run_id=run.id,
                domain=domain,
                name=candidate.get("name"),
                relationship_type=mode,
                confidence_score=confidence,
                rationale=_strip_citations(candidate.get("rationale")) or "",
                estimated_product_count=candidate.get("estimated_product_count"),
                status="candidate",
            )
        )

    run.status = "completed"
    await db.commit()

    refreshed = await db.execute(
        select(DiscoveryRun).where(DiscoveryRun.id == run.id).options(selectinload(DiscoveryRun.sites))
    )
    return _to_run_out(refreshed.scalars().one(), search_count=search_count, skipped_known_count=skipped_known)


@router.get("/runs", response_model=list[DiscoveryRunOut])
async def list_discovery_runs(
    mode: Optional[str] = None,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    query = select(DiscoveryRun).where(DiscoveryRun.workspace_id == workspace.id)
    if mode:
        query = query.where(DiscoveryRun.mode == mode)
    result = await db.execute(query.options(selectinload(DiscoveryRun.sites)).order_by(DiscoveryRun.triggered_at.desc()))
    return [_to_run_out(run) for run in result.scalars().all()]


@router.get("/runs/{run_id}", response_model=DiscoveryRunOut)
async def get_discovery_run(
    run_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DiscoveryRun).where(DiscoveryRun.id == run_id).options(selectinload(DiscoveryRun.sites))
    )
    run = result.scalars().first()
    if run is None or run.workspace_id != workspace.id:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Discovery run not found")
    return _to_run_out(run)


@router.patch("/sites/{site_id}", response_model=CompetitorSiteOut)
async def update_competitor_site(
    site_id: int,
    payload: CompetitorSiteUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompetitorSite).where(CompetitorSite.id == site_id, CompetitorSite.workspace_id == workspace.id)
    )
    site = result.scalars().first()
    if site is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Competitor site not found")
    site.status = payload.status
    await db.commit()
    await db.refresh(site)
    return site


@router.post("/sites", response_model=CompetitorSiteOut, status_code=http_status.HTTP_201_CREATED)
async def create_competitor_site_manually(
    payload: CompetitorSiteCreate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Add a known competitor or reseller directly, skipping AI discovery —
    for when the owner already knows one discovery didn't (or hasn't been
    run at all yet). Saved immediately, no confidence/rationale since
    there's no AI judgment involved; if the domain is already known for
    this workspace, that existing row is marked saved (and its
    relationship_type updated, since a manual add is a deliberate,
    trusted correction) instead of creating a duplicate."""
    domain = _normalize_domain(payload.domain)
    if not domain:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Enter a domain.")

    existing_result = await db.execute(
        select(CompetitorSite).where(CompetitorSite.workspace_id == workspace.id, CompetitorSite.domain == domain)
    )
    existing = existing_result.scalars().first()
    if existing is not None:
        existing.status = "saved"
        existing.relationship_type = payload.relationship_type
        if payload.name:
            existing.name = payload.name
        await db.commit()
        await db.refresh(existing)
        return existing

    site = CompetitorSite(
        workspace_id=workspace.id,
        discovery_run_id=None,
        domain=domain,
        name=payload.name,
        relationship_type=payload.relationship_type,
        confidence_score=None,
        rationale=None,
        estimated_product_count=None,
        status="saved",
    )
    db.add(site)
    await db.commit()
    await db.refresh(site)
    return site


@router.get("/sites", response_model=list[CompetitorSiteOut])
async def list_competitor_sites(
    site_status: Optional[str] = None,
    relationship_type: Optional[str] = None,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    query = select(CompetitorSite).where(CompetitorSite.workspace_id == workspace.id)
    if site_status:
        query = query.where(CompetitorSite.status == site_status)
    if relationship_type:
        query = query.where(CompetitorSite.relationship_type == relationship_type)
    result = await db.execute(query.order_by(CompetitorSite.confidence_score.desc()))
    return result.scalars().all()


@router.get("/sites/{site_id}", response_model=CompetitorSiteOut)
async def get_competitor_site(
    site_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompetitorSite).where(CompetitorSite.id == site_id, CompetitorSite.workspace_id == workspace.id)
    )
    site = result.scalars().first()
    if site is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Competitor site not found")
    return site


@router.post("/sites/{site_id}/products", response_model=list[CompetitorProductOut])
async def discover_products_for_site(
    site_id: int,
    payload: ProductDiscoveryCreate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Ask the workspace's active AI provider to browse this saved
    competitor's site and list real products it found. Upserts by
    (competitor_site_id, url) — re-running updates existing rows rather
    than duplicating, and never deletes rows no longer found."""
    site = await _get_saved_site(db, site_id, workspace.id)
    _check_cooldown(site.products_discovered_at)

    try:
        result, _search_count = await ai_client.discover_competitor_products(
            db,
            workspace.id,
            site.domain,
            site.name,
            max_products=payload.max_products,
            relationship_type=site.relationship_type,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"The AI provider couldn't complete product discovery: {str(exc)[:300]}",
        )

    existing_result = await db.execute(
        select(CompetitorProduct).where(CompetitorProduct.competitor_site_id == site.id)
    )
    # Keyed on (url, title), not url alone — a single pricing/listing page
    # legitimately lists several distinct products under the same URL when
    # they don't each have their own page, so url alone would silently
    # collapse multiple real products onto one row within the same run.
    existing_by_key = {(p.url, p.title): p for p in existing_result.scalars().all()}

    for candidate in result.get("products", [])[: payload.max_products]:
        title = (candidate.get("title") or "").strip()
        url = (candidate.get("url") or "").strip()
        if not title or not url:
            continue
        try:
            price = candidate.get("price")
            price = round(float(price), 2) if price is not None else None
        except (TypeError, ValueError):
            price = None

        description = _strip_citations(candidate.get("description"))
        additional_info = _strip_citations(candidate.get("additional_info"))

        stock_status = candidate.get("stock_status")
        is_trackable = price is not None

        key = (url, title)
        existing = existing_by_key.get(key)
        if existing is not None:
            existing.price = price
            existing.currency = candidate.get("currency")
            existing.description = description
            existing.stock_status = stock_status
            existing.additional_info = additional_info
            existing.is_trackable = is_trackable
            product = existing
        else:
            product = CompetitorProduct(
                workspace_id=workspace.id,
                competitor_site_id=site.id,
                title=title,
                price=price,
                currency=candidate.get("currency"),
                url=url,
                description=description,
                stock_status=stock_status,
                additional_info=additional_info,
                is_trackable=is_trackable,
            )
            db.add(product)
            existing_by_key[key] = product

        # A price/stock reading for every product touched this run — the
        # CompetitorProduct row above only ever holds the latest state, so
        # without this the previous value would be silently overwritten and
        # lost the moment this run commits. Appending via the relationship
        # (rather than setting competitor_product_id directly) lets
        # SQLAlchemy resolve the FK at flush time even for a brand-new,
        # not-yet-committed product.
        product.snapshots.append(
            CompetitorProductSnapshot(workspace_id=workspace.id, price=price, stock_status=stock_status)
        )

    site.products_discovered_at = datetime.now(timezone.utc)
    await db.commit()

    refreshed = await db.execute(
        select(CompetitorProduct)
        .where(CompetitorProduct.competitor_site_id == site.id)
        .order_by(CompetitorProduct.discovered_at.desc())
    )
    return refreshed.scalars().all()


@router.get("/sites/{site_id}/products", response_model=list[CompetitorProductOut])
async def list_products_for_site(
    site_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    # Existence/ownership check only — a site doesn't need to be "saved"
    # to list whatever products it may already have.
    site_result = await db.execute(
        select(CompetitorSite).where(CompetitorSite.id == site_id, CompetitorSite.workspace_id == workspace.id)
    )
    if site_result.scalars().first() is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Competitor site not found")

    result = await db.execute(
        select(CompetitorProduct)
        .where(CompetitorProduct.competitor_site_id == site_id)
        .order_by(CompetitorProduct.discovered_at.desc())
    )
    return result.scalars().all()


@router.post("/sites/{site_id}/auto-match", response_model=list[ProductMatchOut])
async def auto_match_site_products(
    site_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Propose matches between this competitor's discovered products and
    the workspace's own catalog. Writes ProductMatch rows as "candidate"
    for the user to confirm/dismiss — mirrors CompetitorSite's own
    candidate review flow."""
    site = await _get_saved_site(db, site_id, workspace.id)
    _check_cooldown(site.last_auto_match_at)

    competitor_products_result = await db.execute(
        select(CompetitorProduct).where(CompetitorProduct.competitor_site_id == site.id)
    )
    competitor_products = competitor_products_result.scalars().all()
    if not competitor_products:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Discover this competitor's products before running auto-match.",
        )

    own_products_result = await db.execute(select(Product).where(Product.workspace_id == workspace.id))
    own_products = own_products_result.scalars().all()
    if not own_products:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Your catalog is empty.")

    try:
        result, _search_count = await ai_client.match_products(db, workspace.id, own_products, competitor_products)
    except Exception as exc:
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"The AI provider couldn't complete matching: {str(exc)[:300]}",
        )

    existing_result = await db.execute(
        select(ProductMatch).where(ProductMatch.competitor_product_id.in_([p.id for p in competitor_products]))
    )
    existing_by_pair = {(m.product_id, m.competitor_product_id): m for m in existing_result.scalars().all()}

    for match in result.get("matches", []):
        try:
            comp_idx = int(match["competitor_product_index"])
            prod_idx = int(match["product_index"])
            confidence = max(0, min(100, int(match.get("confidence", 0))))
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= comp_idx < len(competitor_products)) or not (0 <= prod_idx < len(own_products)):
            continue
        competitor_product = competitor_products[comp_idx]
        product = own_products[prod_idx]
        rationale = match.get("rationale") or ""

        pair_key = (product.id, competitor_product.id)
        existing = existing_by_pair.get(pair_key)
        if existing is not None:
            if existing.status == "candidate":
                existing.confidence = confidence
                existing.rationale = rationale
            # A confirmed or dismissed pair is left alone — a fresh AI
            # proposal shouldn't silently overwrite a decision already made.
            continue
        new_match = ProductMatch(
            workspace_id=workspace.id,
            product_id=product.id,
            competitor_product_id=competitor_product.id,
            match_method="ai_auto",
            confidence=confidence,
            rationale=rationale,
            status="candidate",
        )
        db.add(new_match)
        existing_by_pair[pair_key] = new_match

    site.last_auto_match_at = datetime.now(timezone.utc)
    await db.commit()

    refreshed = await db.execute(
        select(ProductMatch)
        .join(CompetitorProduct, ProductMatch.competitor_product_id == CompetitorProduct.id)
        .where(CompetitorProduct.competitor_site_id == site.id)
    )
    return refreshed.scalars().all()


@router.get("/matches", response_model=list[TrackedMatchOut])
async def list_tracked_matches(
    status_filter: str = "confirmed",
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Workspace-wide view of matches across every competitor — unlike
    /sites/{site_id}/matches (scoped to one competitor, used for review),
    this is what a "your catalog vs. every tracked competitor" page reads
    from, so it joins in enough from Product/CompetitorProduct/
    CompetitorSite that the frontend needs no further per-id lookups."""
    rows = await fetch_tracked_matches(db, workspace.id, status_filter)
    return [
        TrackedMatchOut(
            id=match.id,
            status=match.status,
            match_method=match.match_method,
            confidence=match.confidence,
            rationale=match.rationale,
            created_at=match.created_at,
            product_id=product.id,
            product_name=product.name,
            product_price=product.price,
            product_currency=product.currency,
            product_min_price=product.min_price,
            competitor_product_id=cproduct.id,
            competitor_product_title=cproduct.title,
            competitor_product_price=cproduct.price,
            competitor_product_currency=cproduct.currency,
            competitor_product_is_trackable=cproduct.is_trackable,
            competitor_product_updated_at=cproduct.updated_at,
            competitor_site_id=site.id,
            competitor_site_domain=site.domain,
            competitor_site_name=site.name,
            competitor_site_relationship_type=site.relationship_type,
        )
        for match, product, cproduct, site in rows
    ]


@router.get("/sites/{site_id}/matches", response_model=list[ProductMatchOut])
async def list_matches_for_site(
    site_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    site_result = await db.execute(
        select(CompetitorSite).where(CompetitorSite.id == site_id, CompetitorSite.workspace_id == workspace.id)
    )
    if site_result.scalars().first() is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Competitor site not found")

    result = await db.execute(
        select(ProductMatch)
        .join(CompetitorProduct, ProductMatch.competitor_product_id == CompetitorProduct.id)
        .where(CompetitorProduct.competitor_site_id == site_id)
    )
    return result.scalars().all()


@router.post("/matches", response_model=ProductMatchOut, status_code=http_status.HTTP_201_CREATED)
async def create_manual_match(
    payload: ProductMatchCreate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Manually pair one of the workspace's own products with a competitor
    product (drag-and-drop drop target calls this) — created directly as
    "confirmed", no AI judgment to review, same as a manually-added
    CompetitorSite."""
    product_result = await db.execute(
        select(Product).where(Product.id == payload.product_id, Product.workspace_id == workspace.id)
    )
    if product_result.scalars().first() is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Product not found")

    competitor_product_result = await db.execute(
        select(CompetitorProduct).where(
            CompetitorProduct.id == payload.competitor_product_id,
            CompetitorProduct.workspace_id == workspace.id,
        )
    )
    if competitor_product_result.scalars().first() is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Competitor product not found")

    existing_result = await db.execute(
        select(ProductMatch).where(
            ProductMatch.product_id == payload.product_id,
            ProductMatch.competitor_product_id == payload.competitor_product_id,
        )
    )
    existing = existing_result.scalars().first()
    if existing is not None:
        existing.status = "confirmed"
        existing.match_method = "manual"
        await db.commit()
        await db.refresh(existing)
        return existing

    match = ProductMatch(
        workspace_id=workspace.id,
        product_id=payload.product_id,
        competitor_product_id=payload.competitor_product_id,
        match_method="manual",
        status="confirmed",
    )
    db.add(match)
    await db.commit()
    await db.refresh(match)
    return match


@router.patch("/matches/{match_id}", response_model=ProductMatchOut)
async def update_match(
    match_id: int,
    payload: ProductMatchUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(ProductMatch).where(ProductMatch.id == match_id, ProductMatch.workspace_id == workspace.id)
    )
    match = result.scalars().first()
    if match is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Match not found")
    match.status = payload.status
    await db.commit()
    await db.refresh(match)
    return match
