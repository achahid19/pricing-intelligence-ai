from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.dependencies import get_current_workspace
from app.catalog.models import Product
from app.discovery.models import CompetitorSite, DiscoveryRun
from app.discovery.schemas import CompetitorSiteOut, CompetitorSiteUpdate, DiscoveryRunCreate, DiscoveryRunOut
from app.db.database import get_db
from app.services import ai_client
from app.services.model_catalog import default_model_for
from app.workspace.models import AiProviderConfig, Workspace

router = APIRouter()


def _to_run_out(run: DiscoveryRun, search_count: Optional[int] = None) -> DiscoveryRunOut:
    return DiscoveryRunOut(
        id=run.id,
        workspace_id=run.workspace_id,
        triggered_at=run.triggered_at,
        ai_provider=run.ai_provider,
        model=run.model,
        status=run.status,
        error_message=run.error_message,
        search_count=search_count,
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

    for candidate in result.get("candidates", [])[:max_candidates]:
        domain = (candidate.get("domain") or "").strip().lower()
        if not domain:
            continue
        try:
            confidence = max(0, min(100, int(candidate.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0
        db.add(
            CompetitorSite(
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
    return _to_run_out(refreshed.scalars().one(), search_count=search_count)


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
        select(CompetitorSite)
        .join(DiscoveryRun, CompetitorSite.discovery_run_id == DiscoveryRun.id)
        .where(CompetitorSite.id == site_id, DiscoveryRun.workspace_id == workspace.id)
    )
    site = result.scalars().first()
    if site is None:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Competitor site not found")
    site.status = payload.status
    await db.commit()
    await db.refresh(site)
    return site


@router.get("/sites", response_model=list[CompetitorSiteOut])
async def list_competitor_sites(
    site_status: Optional[str] = None,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    query = (
        select(CompetitorSite)
        .join(DiscoveryRun, CompetitorSite.discovery_run_id == DiscoveryRun.id)
        .where(DiscoveryRun.workspace_id == workspace.id)
    )
    if site_status:
        query = query.where(CompetitorSite.status == site_status)
    result = await db.execute(query.order_by(CompetitorSite.confidence_score.desc()))
    return result.scalars().all()
