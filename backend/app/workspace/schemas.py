from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Provider = Literal["openai", "google", "anthropic"]

# Known checkbox options shown at onboarding — deliberately not a hard
# enum, "anything else" is captured in objectives_note instead of forcing
# a code change to add a new one. See DECISIONS.md.
# "map_compliance" (not "product_fit") on purpose — brands monitoring
# reseller MAP violations is a real, already-validated use case from the
# prior platform and one of this product's three named target segments;
# "product-fit validation" was a weaker match for what Discovery/Reporting
# actually deliver.
KNOWN_OBJECTIVES = ["market_research", "price_alignment", "map_compliance"]


class PipelineSubstep(BaseModel):
    id: str
    label: str
    status: Literal["pending", "done", "error", "cancelled"]


class WorkspaceOut(BaseModel):
    id: int
    name: str
    objectives_selected: Optional[list[str]]
    objectives_note: Optional[str]
    country: Optional[str]
    market: Optional[str]
    website: Optional[str]
    report_interval_hours: Optional[int]
    refresh_before_report: Optional[bool]
    onboarding_pipeline_triggered_at: Optional[datetime]
    pipeline_status: Optional[str]
    pipeline_trigger_source: Optional[str]
    pipeline_started_at: Optional[datetime]
    pipeline_finished_at: Optional[datetime]
    pipeline_error_message: Optional[str]
    pipeline_report_id: Optional[int]
    pipeline_substeps: Optional[list[PipelineSubstep]]
    # True the instant a cancel request has been recorded, until the
    # running pipeline actually reaches its next checkpoint and stops —
    # lets the frontend show a transient "Stopping…" state rather than
    # nothing happening for up to several seconds.
    pipeline_cancel_requested: bool
    product_tour_completed_at: Optional[datetime]
    onboarding_completed: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkspaceContextUpdate(BaseModel):
    objectives_selected: Optional[list[str]] = Field(default=None, max_length=20)
    objectives_note: Optional[str] = Field(default=None, max_length=2000)
    country: Optional[str] = Field(default=None, max_length=100)
    market: Optional[str] = Field(default=None, max_length=200)
    # Plain string, not a strict URL type — a bare domain ("acme.com") is a
    # valid, common thing to type here and shouldn't be rejected. Normalize
    # (add https://, etc.) at the point this is actually crawled, not here.
    website: Optional[str] = Field(default=None, max_length=300)
    report_interval_hours: Optional[int] = Field(default=None, ge=1, le=168)
    refresh_before_report: Optional[bool] = Field(default=None)


class AiProviderConfigCreate(BaseModel):
    """Also used to update an existing provider config (e.g. changing just
    the model). `api_key` is optional: omit it to keep the already-stored
    key when this provider already has a config — required only the first
    time a provider is configured."""

    provider: Provider
    api_key: Optional[str] = Field(default=None, min_length=1)
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
