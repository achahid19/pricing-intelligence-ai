import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_workspace
from app.catalog.models import Product
from app.discovery.models import (
    CompetitorProduct,
    CompetitorSite,
    DiscoveryRun,
    ProductMatch,
)
from app.discovery.schemas import (
    CompetitorProductOut,
    CompetitorProductUpdate,
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
from app.discovery import service as discovery_service
from app.services import ai_client
from app.services.cooldown import check_cooldown
from app.services.text import normalize_domain
from app.workspace.models import Workspace

logger = logging.getLogger(__name__)

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

    try:
        run, search_count, skipped_known = await discovery_service.run_site_discovery(
            db, workspace, mode, max_candidates=max_candidates
        )
    except ai_client.NoActiveProviderError:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="No active AI provider configured for this workspace. Set one up in Settings first.",
        )
    except Exception:
        # discovery_service.run_site_discovery already logged the full
        # traceback and persisted a truncated error_message on the row
        # before re-raising — this is just the HTTP-layer translation.
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider couldn't complete discovery. Try again in a moment.",
        )

    return _to_run_out(run, search_count=search_count, skipped_known_count=skipped_known)


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


@router.delete("/sites/{site_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_competitor_site(
    site_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Delete a competitor/reseller site outright — mainly for clearing out
    old dismissed candidates that just accumulate forever otherwise (a
    dismissed site is never re-suggested, but until now was never
    removable either). Cascades to any CompetitorProduct discovered under
    it, and in turn their ProductMatch/CompetitorProductSnapshot rows
    (ondelete="CASCADE" throughout, see discovery/models.py) — same
    reasoning as delete_competitor_product. Not status-restricted: works
    on a candidate/saved/dismissed site alike, though the UI only exposes
    this for dismissed ones today."""
    result = await db.execute(
        select(CompetitorSite).where(CompetitorSite.id == site_id, CompetitorSite.workspace_id == workspace.id)
    )
    site = result.scalars().first()
    if site is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Competitor site not found")
    await db.delete(site)
    await db.commit()


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
    domain = normalize_domain(payload.domain)
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
        return await discovery_service.run_site_product_discovery(
            db, workspace.id, site, max_products=payload.max_products
        )
    except Exception as exc:
        logger.exception("product discovery failed for site %s, workspace %s", site.id, workspace.id)
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"The AI provider couldn't complete product discovery: {str(exc)[:300]}",
        )


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


@router.patch("/products/{product_id}", response_model=CompetitorProductOut)
async def update_competitor_product(
    product_id: int,
    payload: CompetitorProductUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Dismiss ("not interested" — excluded from matching, market coverage,
    and reports; see discovery/service.py) or restore a competitor product.
    Unlike delete, this keeps the row and its price history intact, and a
    future discovery re-run leaves the flag alone rather than reviving it."""
    result = await db.execute(
        select(CompetitorProduct).where(
            CompetitorProduct.id == product_id, CompetitorProduct.workspace_id == workspace.id
        )
    )
    product = result.scalars().first()
    if product is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Product not found")
    product.is_dismissed = payload.is_dismissed
    await db.commit()
    await db.refresh(product)
    return product


@router.delete("/products/{product_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_competitor_product(
    product_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Delete one discovered competitor product outright — e.g. a
    genuinely wrong or duplicate entry. Cascades to its
    CompetitorProductSnapshot history and any ProductMatch against it
    (ondelete="CASCADE" on both, see discovery/models.py) — deleting a
    competitor's product removes any confirmed match against your own
    catalog too, which is correct: there's nothing left to track once the
    competitor-side row is gone. Unlike a discovery re-run (which only
    ever upserts, never removes a row no longer found on the site), this
    is a direct, permanent removal the user asked for."""
    result = await db.execute(
        select(CompetitorProduct).where(
            CompetitorProduct.id == product_id, CompetitorProduct.workspace_id == workspace.id
        )
    )
    product = result.scalars().first()
    if product is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Product not found")
    await db.delete(product)
    await db.commit()


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

    try:
        return await discovery_service.run_site_auto_match(db, workspace.id, site)
    except discovery_service.NoCompetitorProductsError as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except discovery_service.EmptyCatalogError as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except Exception as exc:
        logger.exception("auto-match failed for site %s, workspace %s", site.id, workspace.id)
        raise HTTPException(
            status_code=http_status.HTTP_502_BAD_GATEWAY,
            detail=f"The AI provider couldn't complete matching: {str(exc)[:300]}",
        )


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
    rows = await discovery_service.fetch_tracked_matches(db, workspace.id, status_filter)
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
