from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_workspace
from app.catalog.models import Product
from app.discovery.models import CompetitorSite, DiscoveryRun
from app.discovery.schemas import (
    CompetitorSiteCreate,
    CompetitorSiteOut,
    CompetitorSiteUpdate,
    DiscoveryRunCreate,
    DiscoveryRunOut,
)
from app.db.database import get_db
from app.services import ai_client
from app.services.model_catalog import default_model_for
from app.workspace.models import AiProviderConfig, Workspace

router = APIRouter()

# No queue/rate-limit middleware in this app yet — this is the cheapest
# possible guard against a stuck retry loop or an impatient double-click
# burning real AI-provider cost with zero server-side protection.
DISCOVERY_COOLDOWN_SECONDS = 30


def _normalize_domain(raw: str) -> str:
    """Strip scheme, a leading www., and any trailing path/slash — so
    "https://www.example.com/" and "example.com" are recognized as the same
    competitor rather than creating a duplicate row."""
    domain = raw.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
    return domain.split("/")[0]


def _to_run_out(
    run: DiscoveryRun, search_count: Optional[int] = None, skipped_known_count: Optional[int] = None
) -> DiscoveryRunOut:
    return DiscoveryRunOut(
        id=run.id,
        workspace_id=run.workspace_id,
        triggered_at=run.triggered_at,
        ai_provider=run.ai_provider,
        model=run.model,
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
    """Trigger a competitor-discovery run: the workspace's active AI
    provider researches the web (its own native search tool) and proposes
    up to payload.max_candidates competitor sites with confidence + rationale.
    Synchronous — a single web-search-enabled AI call, may take 10-30s."""
    max_candidates = payload.max_candidates

    last_run_result = await db.execute(
        select(DiscoveryRun.triggered_at)
        .where(DiscoveryRun.workspace_id == workspace.id)
        .order_by(DiscoveryRun.triggered_at.desc())
        .limit(1)
    )
    last_triggered_at = last_run_result.scalars().first()
    if last_triggered_at is not None:
        elapsed = (datetime.now(timezone.utc) - last_triggered_at).total_seconds()
        if elapsed < DISCOVERY_COOLDOWN_SECONDS:
            wait_seconds = int(DISCOVERY_COOLDOWN_SECONDS - elapsed) + 1
            raise HTTPException(
                status_code=http_status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Please wait {wait_seconds}s before running discovery again.",
            )

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
        context_snapshot={"context": context, "max_candidates": max_candidates},
        status="running",
    )
    db.add(run)
    await db.flush()

    try:
        result, search_count = await ai_client.discover_competitor_sites(
            db, workspace.id, context, max_candidates=max_candidates
        )
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
                confidence_score=confidence,
                rationale=candidate.get("rationale") or "",
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
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(DiscoveryRun)
        .where(DiscoveryRun.workspace_id == workspace.id)
        .options(selectinload(DiscoveryRun.sites))
        .order_by(DiscoveryRun.triggered_at.desc())
    )
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
    """Add a known competitor directly, skipping AI discovery — for when
    the owner already knows a competitor discovery didn't (or hasn't been
    run at all yet). Saved immediately, no confidence/rationale since
    there's no AI judgment involved; if the domain is already known for
    this workspace, that existing row is marked saved instead of creating
    a duplicate."""
    domain = _normalize_domain(payload.domain)
    if not domain:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail="Enter a domain.")

    existing_result = await db.execute(
        select(CompetitorSite).where(CompetitorSite.workspace_id == workspace.id, CompetitorSite.domain == domain)
    )
    existing = existing_result.scalars().first()
    if existing is not None:
        existing.status = "saved"
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
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    query = select(CompetitorSite).where(CompetitorSite.workspace_id == workspace.id)
    if site_status:
        query = query.where(CompetitorSite.status == site_status)
    result = await db.execute(query.order_by(CompetitorSite.confidence_score.desc()))
    return result.scalars().all()
