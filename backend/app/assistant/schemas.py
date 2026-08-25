from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class ChatMessage(BaseModel):
    """Client-side chat history entry — see assistant/service.py's module
    docstring for why this is deliberately just plain user/assistant text
    turns, never the individual native tool-call/tool-result turns a
    provider needs mid-loop (those are rebuilt fresh, server-side, on
    every call)."""

    role: Literal["user", "assistant"]
    content: str


class SendMessageIn(BaseModel):
    messages: list[ChatMessage]


class ToolCallActionIn(BaseModel):
    action: Literal["approve", "dismiss"]


class ToolCallOut(BaseModel):
    id: int
    tool_name: str
    status: str
    display: dict
    tier: str
    result_summary: Optional[dict]
    error_message: Optional[str]
    created_at: datetime
    executed_at: Optional[datetime]

    model_config = {"from_attributes": True}
