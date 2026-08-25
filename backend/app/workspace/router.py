from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_workspace
from app.db.database import get_db
from app.services import ai_client
from app.services.model_catalog import MODEL_CATALOG
from app.workspace.encryption import encrypt_key
from app.workspace.models import AiProviderConfig, Workspace
from app.workspace.schemas import (
    AiProviderConfigCreate,
    AiProviderConfigOut,
    ContextReview,
    WorkspaceContextUpdate,
    WorkspaceOut,
)

router = APIRouter()


@router.get("/models")
async def list_model_catalog():
    """Curated, cost-tiered model list per provider — single source of truth
    so the frontend never hardcodes a model list that can drift from
    ai_client.py's actual defaults. No auth needed; not workspace-specific."""
    return MODEL_CATALOG


@router.get("/me", response_model=WorkspaceOut)
async def get_my_workspace(workspace: Workspace = Depends(get_current_workspace)):
    return workspace


@router.patch("/me", response_model=WorkspaceOut)
async def update_my_workspace(
    payload: WorkspaceContextUpdate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(workspace, field, value)
    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.post("/review-context", response_model=ContextReview)
async def review_context(
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Reviews the workspace's OWN already-stored objectives_note/market
    free-text fields — no request body, matching the "review what was just
    saved" framing (see frontend/app/(app)/settings/page.tsx's two trigger
    points: right after the first AI key is saved, and right after
    business context is edited). A gentle nudge, not a hard gate — the
    frontend decides whether/how to surface a false in_scope, this
    endpoint just reports it."""
    try:
        review = await ai_client.review_business_context(
            db, workspace.id, workspace.objectives_note, workspace.market
        )
    except ai_client.NoActiveProviderError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active AI provider configured for this workspace. Set one up in Settings first.",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider couldn't complete the review. Try again in a moment.",
        )
    if review is None:
        return ContextReview(in_scope=True, note=None)
    return ContextReview(**review)


@router.post("/product-tour-complete", response_model=WorkspaceOut)
async def complete_product_tour(
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Marks the interactive first-run tour as seen — called on finishing
    the last step OR explicitly skipping (both count; see frontend/lib/
    productTour.tsx). The timestamp is server-set, not client-sent, same
    reasoning as every other one-shot flag on this model. Idempotent: a
    second call just overwrites with a fresher timestamp, no error."""
    workspace.product_tour_completed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(workspace)
    return workspace


@router.get("/ai-provider", response_model=list[AiProviderConfigOut])
async def list_ai_providers(
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(AiProviderConfig).where(AiProviderConfig.workspace_id == workspace.id)
    )
    return result.scalars().all()


@router.post("/ai-provider", response_model=AiProviderConfigOut)
async def set_ai_provider(
    payload: AiProviderConfigCreate,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    # Only one provider config is active at a time — this is the one
    # ai_client.py will use. Setting a new/updated one deactivates the rest.
    result = await db.execute(
        select(AiProviderConfig).where(AiProviderConfig.workspace_id == workspace.id)
    )
    existing_configs = result.scalars().all()
    target = next((c for c in existing_configs if c.provider == payload.provider), None)

    if target is None and not payload.api_key:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An API key is required the first time you configure this provider.",
        )

    for config in existing_configs:
        config.is_active = config is target

    if target is not None:
        if payload.api_key:
            target.encrypted_api_key = encrypt_key(payload.api_key)
        target.model_override = payload.model_override
        target.is_active = True
    else:
        target = AiProviderConfig(
            workspace_id=workspace.id,
            provider=payload.provider,
            encrypted_api_key=encrypt_key(payload.api_key),
            model_override=payload.model_override,
            is_active=True,
        )
        db.add(target)

    await db.commit()
    await db.refresh(target)
    return target
