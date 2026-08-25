from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant import service as assistant_service
from app.assistant.schemas import SendMessageIn, ToolCallActionIn, ToolCallOut
from app.auth.dependencies import get_current_workspace
from app.db.database import get_db
from app.services import ai_client
from app.workspace.models import Workspace

router = APIRouter()


@router.post("/messages")
async def send_message(
    payload: SendMessageIn,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Runs one assistant turn. Returns either `{"type": "message", "text"}`
    for a plain reply, or `{"type": "tool_proposal", "call_id", "tool_name",
    "display", "tier"}` when the model wants to take a write action —
    approve/dismiss it via PATCH /assistant/tool-calls/{call_id}. No
    request-body arguments beyond the conversation history: `messages` is
    the client's own flat history (see assistant/schemas.py's ChatMessage)."""
    try:
        return await assistant_service.send_message(
            db, workspace, [m.model_dump() for m in payload.messages]
        )
    except ai_client.NoActiveProviderError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active AI provider configured for this workspace. Set one up in Settings first.",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI provider couldn't complete that. Try again in a moment.",
        )


@router.patch("/tool-calls/{call_id}", response_model=ToolCallOut)
async def act_on_tool_call(
    call_id: int,
    payload: ToolCallActionIn,
    background_tasks: BackgroundTasks,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Deliberately takes ONLY an action ("approve"|"dismiss") — no
    arguments field exists here at all, so a tampered request has no
    channel to substitute different arguments than what was actually
    proposed and shown to the user; approval always executes against
    whatever was already stored on the row at propose time (see
    assistant/service.py's approve_tool_call)."""
    if payload.action == "dismiss":
        call = await assistant_service.dismiss_tool_call(db, workspace, call_id)
    else:
        call = await assistant_service.approve_tool_call(db, background_tasks, workspace, call_id)
    return call
