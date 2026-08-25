from datetime import datetime, timezone

from fastapi import BackgroundTasks
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product, ProductSnapshot
from app.catalog.schemas import ProductCreate
from app.reporting import service as reporting_service
from app.workspace.models import Workspace


async def maybe_start_onboarding_pipeline(
    db: AsyncSession, background_tasks: BackgroundTasks, workspace: Workspace
) -> None:
    """The "0 -> >0" trigger: the very first time a workspace's catalog
    goes from empty to non-empty (via any product-creation path — manual
    add, website import, or CSV/XLSX import), kick off the automated
    discover-match-report pipeline (reporting/service.py's
    run_full_pipeline) in the background, once, ever. Guarded by
    Workspace.onboarding_pipeline_triggered_at — set (and committed) here
    before enqueueing, not after the pipeline finishes, so a second product
    landing while the first pipeline is still running can't double-trigger
    it. Lives here rather than in discovery/service.py to avoid a circular
    import: reporting/service.py already imports discovery/service.py, so
    the reverse would be circular, and this helper needs both."""
    if workspace.onboarding_pipeline_triggered_at is not None:
        return
    count = await db.scalar(select(func.count(Product.id)).where(Product.workspace_id == workspace.id))
    if not count:
        return
    workspace.onboarding_pipeline_triggered_at = datetime.now(timezone.utc)
    await db.commit()
    background_tasks.add_task(reporting_service.run_full_pipeline_background, workspace.id, "onboarding")


async def create_product(
    db: AsyncSession,
    background_tasks: BackgroundTasks,
    workspace: Workspace,
    payload: ProductCreate,
) -> Product:
    """Single source of truth for the manual "Add Product" path — shared by
    catalog/router.py's POST / and the assistant's create_product tool
    executor, so the two never drift on the snapshot/onboarding-pipeline
    side effects below."""
    product = Product(workspace_id=workspace.id, import_source="manual", **payload.model_dump())
    # A starting-price snapshot, same reasoning as every other creation
    # path — without one, a price edited before the first report has no
    # baseline to diff against, even though the product clearly existed.
    product.snapshots.append(ProductSnapshot(workspace_id=workspace.id, price=product.price))
    db.add(product)
    await db.commit()
    await db.refresh(product)
    await maybe_start_onboarding_pipeline(db, background_tasks, workspace)
    return product
