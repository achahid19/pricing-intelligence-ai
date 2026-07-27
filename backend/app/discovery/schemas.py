from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class CompetitorSiteOut(BaseModel):
    id: int
    discovery_run_id: int
    domain: str
    name: Optional[str]
    confidence_score: int
    rationale: str
    estimated_product_count: Optional[int]
    status: str

    model_config = {"from_attributes": True}


class DiscoveryRunOut(BaseModel):
    id: int
    workspace_id: int
    triggered_at: datetime
    ai_provider: str
    model: str
    status: str
    error_message: Optional[str]
    search_count: Optional[int] = None
    sites: list[CompetitorSiteOut] = []

    model_config = {"from_attributes": True}


class CompetitorSiteUpdate(BaseModel):
    status: Literal["saved", "dismissed"]
