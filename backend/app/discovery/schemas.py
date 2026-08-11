from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, Field


class DiscoveryRunCreate(BaseModel):
    # Upper bound is a hard safety cap, not just a UI suggestion — more
    # candidates means more AI reasoning/search cost with no cost-estimate
    # system in place yet (see docs/DECISIONS.md).
    max_candidates: int = Field(default=10, ge=1, le=25)
    # "competitor" finds rival businesses (own-brand, resellers excluded);
    # "reseller" finds businesses that advertise/sell THIS workspace's own
    # products, for MAP-compliance monitoring — the inverse inclusion rule,
    # only relevant to workspaces that selected that objective.
    mode: Literal["competitor", "reseller"] = "competitor"


class CompetitorSiteOut(BaseModel):
    id: int
    workspace_id: int
    discovery_run_id: Optional[int]
    domain: str
    name: Optional[str]
    relationship_type: str
    confidence_score: Optional[int]
    rationale: Optional[str]
    estimated_product_count: Optional[int]
    status: str

    model_config = {"from_attributes": True}


class CompetitorSiteCreate(BaseModel):
    """Manually add a known competitor or reseller, skipping AI discovery
    entirely — trusted as-is, saved directly rather than starting as a
    candidate."""

    domain: str = Field(min_length=1, max_length=255)
    name: Optional[str] = Field(default=None, max_length=255)
    relationship_type: Literal["competitor", "reseller"] = "competitor"


class DiscoveryRunOut(BaseModel):
    id: int
    workspace_id: int
    triggered_at: datetime
    ai_provider: str
    model: str
    mode: str
    status: str
    error_message: Optional[str]
    search_count: Optional[int] = None
    skipped_known_count: Optional[int] = None
    context_snapshot: dict
    sites: list[CompetitorSiteOut] = []

    model_config = {"from_attributes": True}


class CompetitorSiteUpdate(BaseModel):
    # "candidate" is included so a dismissed site can be restored back into
    # the review queue — a dismissal isn't otherwise reachable anywhere in
    # the UI once made, which is the whole reason this needed to be undoable.
    status: Literal["candidate", "saved", "dismissed"]


class CompetitorProductOut(BaseModel):
    id: int
    workspace_id: int
    competitor_site_id: int
    title: str
    price: Optional[Decimal]
    currency: Optional[str]
    url: str
    image_url: Optional[str]
    description: Optional[str]
    stock_status: Optional[str]
    additional_info: Optional[str]
    is_trackable: bool
    is_url_verified: bool
    is_dismissed: bool
    discovered_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CompetitorProductUpdate(BaseModel):
    is_dismissed: bool


class ProductDiscoveryCreate(BaseModel):
    # Same reasoning as DiscoveryRunCreate.max_candidates — a hard safety
    # cap, not just a UI suggestion.
    max_products: int = Field(default=15, ge=1, le=25)


class ProductMatchOut(BaseModel):
    id: int
    workspace_id: int
    product_id: int
    competitor_product_id: int
    match_method: str
    confidence: Optional[int]
    rationale: Optional[str]
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ProductMatchCreate(BaseModel):
    """Manual match, created directly as confirmed — no AI judgment to
    review, same as a manually-added CompetitorSite."""

    product_id: int
    competitor_product_id: int


class ProductMatchUpdate(BaseModel):
    status: Literal["confirmed", "dismissed"]


class TrackedMatchOut(BaseModel):
    """Flat, denormalized view of one ProductMatch for the workspace-wide
    Tracked page — joins in just enough from Product/CompetitorProduct/
    CompetitorSite that the frontend can render a full comparison row
    without a second round of per-id lookups."""

    id: int
    status: str
    match_method: str
    confidence: Optional[int]
    rationale: Optional[str]
    created_at: datetime

    product_id: int
    product_name: str
    # Nullable: Product.price is optional (e.g. a website-imported product
    # from a site with no published price) — a priceless product can still
    # be matched and tracked here, just with no delta/MAP verdict possible
    # until a real price is added.
    product_price: Optional[Decimal]
    product_currency: str
    product_min_price: Optional[Decimal]

    competitor_product_id: int
    competitor_product_title: str
    competitor_product_price: Optional[Decimal]
    competitor_product_currency: Optional[str]
    competitor_product_is_trackable: bool
    competitor_product_updated_at: datetime

    competitor_site_id: int
    competitor_site_domain: str
    competitor_site_name: Optional[str]
    competitor_site_relationship_type: str

    model_config = {"from_attributes": True}
