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
    competitor_site_id: int
    competitor_site_domain: str
    competitor_site_name: Optional[str]
    competitor_site_relationship_type: str
    same_currency: bool
    price_delta_pct: Optional[float]
    below_map: bool
    trend: Optional[TrendInfo]


class AlertItem(PriceComparisonRow):
    """Every field a PriceComparisonRow has, plus the alert-specific ones —
    an alert is always about a specific row, so it carries the row's full
    context rather than a bare match_id the frontend would have to look up."""

    type: Literal["map_violation", "price_anomaly"]
    severity: Literal["high", "medium"]
    message: str


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
    cheapest_competitor_name: Optional[str]
    cheapest_competitor_price: Optional[float]


class ProductComparisonGroup(BaseModel):
    product_id: int
    product_name: str
    product_price: float
    product_currency: str
    product_min_price: Optional[float]
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
    generated_at: datetime
    trigger_source: str
    ai_provider: str
    model: str
    status: str
    error_message: Optional[str]
    content: ReportContent

    model_config = {"from_attributes": True}
