from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price: Decimal = Field(gt=0)
    currency: str = Field(default="USD", min_length=3, max_length=3)
    min_price: Optional[Decimal] = Field(default=None, gt=0)
    image_url: Optional[str] = Field(default=None, max_length=1000)
    description: Optional[str] = Field(default=None, max_length=5000)
    sku: Optional[str] = Field(default=None, max_length=100)
    brand: Optional[str] = Field(default=None, max_length=200)
    category: Optional[str] = Field(default=None, max_length=200)
    barcode: Optional[str] = Field(default=None, max_length=100)


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    price: Optional[Decimal] = Field(default=None, gt=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    min_price: Optional[Decimal] = Field(default=None, gt=0)
    image_url: Optional[str] = Field(default=None, max_length=1000)
    description: Optional[str] = Field(default=None, max_length=5000)
    sku: Optional[str] = Field(default=None, max_length=100)
    brand: Optional[str] = Field(default=None, max_length=200)
    category: Optional[str] = Field(default=None, max_length=200)
    barcode: Optional[str] = Field(default=None, max_length=100)
    # Editable, unlike import_source — a website-import's discovered page
    # can turn out generic/wrong (see docs/PROGRESS.md's url_verified work)
    # and the user may know the real product page even when the AI didn't.
    source_url: Optional[str] = Field(default=None, max_length=1000)


class ProductOut(BaseModel):
    id: int
    name: str
    price: Optional[Decimal]
    currency: str
    min_price: Optional[Decimal]
    image_url: Optional[str]
    description: Optional[str]
    sku: Optional[str]
    brand: Optional[str]
    category: Optional[str]
    barcode: Optional[str]
    import_source: str
    source_url: Optional[str]
    source_url_verified: Optional[bool]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ImportResultOut(BaseModel):
    created: int
    skipped: list[str] = []
    errors: list[str] = []


class BulkDeleteResultOut(BaseModel):
    deleted: int


class AiDescribeOut(BaseModel):
    title: str
    description: str
    category: Optional[str] = None
    image_url: str


class WebsiteImportDiscoverIn(BaseModel):
    # Optional override — when omitted, the workspace's own `website` field
    # (captured at onboarding/Settings) is used.
    url: Optional[str] = Field(default=None, max_length=500)
    max_products: int = Field(default=15, ge=1, le=25)


class WebsiteImportCandidate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    # Optional, and genuinely allowed to stay null all the way into the
    # catalog: not every business site publishes a price (B2B, quote-based,
    # brand sites that route to retailers). Product.price is nullable for
    # exactly this reason — a priceless product can be cataloged now and
    # priced later via the normal edit flow, rather than forcing a price
    # before it can be imported at all.
    price: Optional[Decimal] = Field(default=None, gt=0)
    currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    url: str = Field(max_length=1000)
    # True when `url` was actually cited by the AI provider's web search
    # tool (a real page it visited), not just a string the model wrote
    # into its own JSON output — see ai_client._url_is_cited(). Defaults
    # True so a manually-submitted /confirm candidate (no discover step,
    # e.g. a direct API call) isn't flagged as unverified for no reason;
    # the discover response always sets this explicitly either way.
    url_verified: bool = True
    # Generously bounded, not "1-2 sentences" — the discovery prompt now
    # asks for a full, thorough description, so this needs real headroom
    # rather than truncating a genuinely detailed one.
    description: Optional[str] = Field(default=None, max_length=20000)
    stock_status: Optional[str] = Field(default=None, max_length=500)
    additional_info: Optional[str] = Field(default=None, max_length=1000)


class WebsiteImportDiscoverOut(BaseModel):
    domain: str
    candidates: list[WebsiteImportCandidate]
    # Informational only — these candidates are still included in
    # `candidates` (with price=None), not excluded. Lets the review screen
    # say "N of these need a price added" instead of silently dropping them.
    no_price_count: int
    # Unlike no_price_count, these ARE excluded from `candidates` — a
    # product whose name already exists in the catalog would just be
    # skipped as a duplicate at /confirm anyway, so re-running discovery
    # only surfaces genuinely new products, not the same ones every time.
    already_imported_count: int


class WebsiteImportConfirmIn(BaseModel):
    products: list[WebsiteImportCandidate] = Field(min_length=1, max_length=100)
