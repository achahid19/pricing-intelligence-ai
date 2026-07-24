from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Provider = Literal["openai", "google", "anthropic"]


class WorkspaceOut(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AiProviderConfigCreate(BaseModel):
    provider: Provider
    api_key: str = Field(min_length=1)
    model_override: Optional[str] = None


class AiProviderConfigOut(BaseModel):
    """Never includes the raw or encrypted key — only enough to show the
    user what's configured."""
    id: int
    provider: Provider
    model_override: Optional[str]
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
