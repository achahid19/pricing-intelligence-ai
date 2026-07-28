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
    price_comparison: list[PriceComparisonRow]
    alerts: list[AlertItem]
    executive_summary: Optional[str]
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
