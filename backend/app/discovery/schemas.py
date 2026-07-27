from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DiscoveryRunCreate(BaseModel):
    # Upper bound is a hard safety cap, not just a UI suggestion — more
    # candidates means more AI reasoning/search cost with no cost-estimate
    # system in place yet (see docs/DECISIONS.md).
    max_candidates: int = Field(default=10, ge=1, le=25)


class CompetitorSiteOut(BaseModel):
    id: int
    workspace_id: int
    discovery_run_id: Optional[int]
    domain: str
    name: Optional[str]
    confidence_score: Optional[int]
    rationale: Optional[str]
    estimated_product_count: Optional[int]
    status: str

    model_config = {"from_attributes": True}


class CompetitorSiteCreate(BaseModel):
    """Manually add a known competitor, skipping AI discovery entirely —
    trusted as-is, saved directly rather than starting as a candidate."""

    domain: str = Field(min_length=1, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)


class DiscoveryRunOut(BaseModel):
    id: int
    workspace_id: int
    triggered_at: datetime
    ai_provider: str
    model: str
    status: str
    error_message: Optional[str]
    search_count: Optional[int] = None
    skipped_known_count: Optional[int] = None
    context_snapshot: dict
    sites: list[CompetitorSiteOut] = []

    model_config = {"from_attributes": True}


class CompetitorSiteUpdate(BaseModel):
    status: Literal["saved", "dismissed"]
