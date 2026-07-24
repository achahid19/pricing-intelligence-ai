from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_workspace
from app.db.database import get_db
from app.workspace.encryption import encrypt_key
from app.workspace.models import AiProviderConfig, Workspace
from app.workspace.schemas import (
    AiProviderConfigCreate,
    AiProviderConfigOut,
    WorkspaceContextUpdate,
    WorkspaceOut,
)

router = APIRouter()


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

    encrypted = encrypt_key(payload.api_key)
    target = next((c for c in existing_configs if c.provider == payload.provider), None)

    for config in existing_configs:
        config.is_active = config is target

    if target is not None:
        target.encrypted_api_key = encrypted
        target.model_override = payload.model_override
        target.is_active = True
    else:
        target = AiProviderConfig(
            workspace_id=workspace.id,
            provider=payload.provider,
            encrypted_api_key=encrypted,
            model_override=payload.model_override,
            is_active=True,
        )
        db.add(target)

    await db.commit()
    await db.refresh(target)
    return target
