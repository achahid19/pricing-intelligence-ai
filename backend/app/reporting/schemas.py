from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class TrendInfo(BaseModel):
    previous_price: float
    previous_checked_at: datetime
    direction: Literal["up", "down", "same"]
    delta_pct: float
    is_anomaly: bool


class PriceComparisonRow(BaseModel):
    match_id: int
    match_method: str
    confidence: Optional[int]
    rationale: Optional[str]
    product_id: int
    product_name: str
    product_price: float
    product_currency: str
    product_min_price: Optional[float]
    competitor_product_id: int
    competitor_product_title: str
    competitor_product_price: Optional[float]
    competitor_product_currency: Optional[str]
    competitor_product_is_trackable: bool
    # Free-text, AI-observed (see discovery/models.py's CompetitorProduct.
    # stock_status docstring) — ambient display only, never null-checked
    # for a "trackable" determination the way price/currency are.
    competitor_product_stock_status: Optional[str] = None
    competitor_site_id: int
    competitor_site_domain: str
    competitor_site_name: Optional[str]
    competitor_site_relationship_type: str
    same_currency: bool
    price_delta_pct: Optional[float]
    below_map: bool
    trend: Optional[TrendInfo]


class AlertItem(BaseModel):
    """Not every alert is about one specific confirmed match, or even about
    a competitor at all: map_violation and price_anomaly are match-scoped
    (all PriceComparisonRow fields below are set, same full row context as
    before so the frontend never has to look anything up); new_competitor_
    product is scoped to a competitor SITE's whole catalog (none of your
    own products involved); own_price_change is scoped to one of YOUR OWN
    products with no competitor involved at all — competitor_site_id/
    domain/name are null for that type, which is why they're optional
    here rather than always-present like the earlier alert-only design."""

    type: Literal[
        "map_violation", "price_anomaly", "new_competitor_product", "own_price_change", "stock_status_change"
    ]
    severity: Literal["high", "medium"]
    message: str

    # map_violation / price_anomaly / new_competitor_product only — every
    # alert about a competitor has these; own_price_change has none.
    competitor_site_id: Optional[int] = None
    competitor_site_domain: Optional[str] = None
    competitor_site_name: Optional[str] = None

    # map_violation / price_anomaly only
    match_id: Optional[int] = None
    match_method: Optional[str] = None
    confidence: Optional[int] = None
    rationale: Optional[str] = None
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    product_price: Optional[float] = None
    product_currency: Optional[str] = None
    product_min_price: Optional[float] = None
    competitor_product_id: Optional[int] = None
    competitor_product_title: Optional[str] = None
    competitor_product_price: Optional[float] = None
    competitor_product_currency: Optional[str] = None
    competitor_product_is_trackable: Optional[bool] = None
    competitor_site_relationship_type: Optional[str] = None
    same_currency: Optional[bool] = None
    price_delta_pct: Optional[float] = None
    below_map: Optional[bool] = None
    # price_anomaly (a competitor's own price vs. its history) and
    # own_price_change (this workspace's own price vs. its history) share
    # this same field — both are exactly a TrendInfo, just about a
    # different price series; product_id/name/price/currency above are
    # also shared and populated for own_price_change.
    trend: Optional[TrendInfo] = None

    # new_competitor_product only
    new_product_count: Optional[int] = None
    new_product_titles: Optional[list[str]] = None

    # stock_status_change only — free-text, whatever the discovery AI
    # observed on the page each time, not a fixed vocabulary.
    previous_stock_status: Optional[str] = None
    current_stock_status: Optional[str] = None


class ProductMetrics(BaseModel):
    """Same-currency-gated comparison metrics for one product — see
    reporting/metrics.py (ported from ai_crafters_pfa's validated
    metrics.py, adapted since this app has no currency conversion).
    price_rank/price_index/etc. are null when zero same-currency
    competitor prices exist; total_competitors_compared still reflects
    the real any-currency match count. "N of total" must always use
    same_currency_competitors_count + 1 as the denominator, never
    total_competitors_compared + 1 — the two differ whenever any match is
    cross-currency."""

    price_rank: Optional[int]
    total_competitors_compared: int
    same_currency_competitors_count: int
    sellers_cheaper: int
    price_index: Optional[float]
    # Plain-English rendering of price_rank/price_index for business
    # reading — the primary way a product's price standing should be
    # shown; price_rank/price_index above are analytics detail, kept for
    # anyone who wants the raw numbers, never shown as a labeled
    # statistic ("Rank #3", "Index 112.34") in the UI or PDF.
    # `= None` default (unlike its siblings above) is deliberate, not an
    # oversight: this field was added after real reports already existed
    # in the DB, and their stored JSONB content genuinely has no such key
    # at all (not even a null value) — without a default, Pydantic
    # response validation 500s on every historical report the instant it's
    # listed/fetched. Confirmed live: GET /reporting/reports broke outright
    # for a real workspace with pre-existing reports before this fix.
    price_position_summary: Optional[str] = None
    cheapest_competitor_name: Optional[str]
    cheapest_competitor_price: Optional[float]
    cheapest_competitor_site_id: Optional[int] = None


class ProductComparisonGroup(BaseModel):
    product_id: int
    product_name: str
    product_price: float
    product_currency: str
    product_min_price: Optional[float]
    # Your own price's trend since the previous report — a product-level
    # property (not per-match, unlike everything in `matches`), computed
    # once from ProductSnapshot regardless of how many competitors it's
    # matched against. None on a first report or when unchanged.
    own_trend: Optional[TrendInfo] = None
    metrics: ProductMetrics
    matches: list[PriceComparisonRow]


class UnmatchedCompetitorProduct(BaseModel):
    competitor_product_id: int
    title: str
    price: Optional[float]
    currency: Optional[str]
    description: Optional[str]


class SiteCoverage(BaseModel):
    competitor_site_id: int
    competitor_site_domain: str
    competitor_site_name: Optional[str]
    relationship_type: str
    total_products_discovered: int
    matched_products_count: int
    unmatched_sample: list[UnmatchedCompetitorProduct]


class MarketCoverage(BaseModel):
    """Full discovered catalogs of every saved site, not just matched
    products — see discovery/service.py's fetch_market_coverage(). This is
    what lets a report talk about assortment/whitespace, not only price."""

    own_catalog_size: int
    own_products_with_confirmed_match: int
    total_competitor_products_discovered: int
    sites: list[SiteCoverage]


class SummaryStats(BaseModel):
    """price_increases/price_decreases count competitors whose own price
    rose/fell since the previous report (from `trend`, a real time
    comparison) — never how many are currently pricier/cheaper than you
    (that's a snapshot comparison with no time dimension, see
    reporting/service.py's _build_summary_stats). Both are 0 whenever
    there's no previous report to compare against yet."""

    matches_tracked: int
    alerts_count: int
    map_violations_count: int
    price_anomalies_count: int
    price_increases: int
    price_decreases: int
    no_price_count: int


class RecommendationItem(BaseModel):
    objective: str
    text: str


class ReportContent(BaseModel):
    schema_version: int
    summary_stats: SummaryStats
    price_comparison: list[ProductComparisonGroup]
    market_coverage: MarketCoverage
    alerts: list[AlertItem]
    executive_summary: Optional[str]
    market_position: Optional[str]
    competitive_gaps: Optional[str]
    recommendations: list[RecommendationItem]


class CompetitorReportOut(BaseModel):
    id: int
    workspace_id: int
    fed_forward_from_report_id: Optional[int]
    name: Optional[str]
    generated_at: datetime
    trigger_source: str
    ai_provider: str
    model: str
    status: str
    error_message: Optional[str]
    content: ReportContent

    model_config = {"from_attributes": True}


class ReportRename(BaseModel):
    # Empty/whitespace-only clears back to null — the frontend then falls
    # back to displaying generated_at, same as a report that was never named.
    name: str = ""


class PipelineStartedOut(BaseModel):
    """POST /reports' response now that it kicks off the full pipeline in
    the background instead of generating synchronously (see reporting/
    service.py's run_full_pipeline) — there's no report id yet at request
    time. Workspace.pipeline_status/pipeline_substeps (already polled by
    the frontend for the other two trigger points) is what actually
    carries progress and the eventual report id forward."""
    detail: str = "Report generation started."


class PipelineCancelOut(BaseModel):
    """POST /reporting/pipeline/cancel's response — the run doesn't stop
    immediately (see run_full_pipeline's cooperative cancellation
    checkpoints), so this just confirms the request was recorded; the
    poller picks up pipeline_status flipping to "cancelled" from there."""
    detail: str = "Cancellation requested."
