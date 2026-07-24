from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Provider = Literal["openai", "google", "anthropic"]

# Known checkbox options shown at onboarding — deliberately not a hard
# enum, "anything else" is captured in objectives_note instead of forcing
# a code change to add a new one. See DECISIONS.md.
KNOWN_OBJECTIVES = ["market_research", "price_alignment", "product_fit"]


class WorkspaceOut(BaseModel):
    id: int
    name: str
    objectives_selected: Optional[list[str]]
    objectives_note: Optional[str]
    country: Optional[str]
    market: Optional[str]
    report_interval_hours: Optional[int]
    onboarding_completed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceContextUpdate(BaseModel):
    objectives_selected: Optional[list[str]] = Field(default=None, max_length=20)
    objectives_note: Optional[str] = Field(default=None, max_length=2000)
    country: Optional[str] = Field(default=None, max_length=100)
    market: Optional[str] = Field(default=None, max_length=200)
    report_interval_hours: Optional[int] = Field(default=None, ge=1, le=168)


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
