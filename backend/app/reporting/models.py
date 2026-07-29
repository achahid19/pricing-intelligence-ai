from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class CompetitorReport(Base):
    """
    A generated snapshot of the workspace's confirmed ProductMatch data,
    synthesized into a price-comparison table, deterministic alerts (MAP
    violations, price anomalies), and an AI-written executive summary +
    recommendations. Aggregates across every saved competitor/reseller in
    the workspace — not scoped to one DiscoveryRun, since there isn't a
    single run a report is "about".

    `content` (JSONB) holds the actual report — schema_version,
    summary_stats, price_comparison, alerts, executive_summary,
    recommendations (see reporting/schemas.py for the typed shape). Numbers
    and alert flags in it are always Python-computed; only
    executive_summary/recommendations are AI-authored text (see
    CLAUDE.md's "AI narrates on top of deterministic data" rule).

    A narrative-generation failure doesn't discard the (already-correct,
    already-expensive-to-compute) deterministic work — status="failed"
    still persists price_comparison/alerts/summary_stats, just with
    executive_summary=null and recommendations=[].
    """
    __tablename__ = "competitor_reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # User-assigned label (e.g. "Q3 competitor check-in"). Null means the
    # frontend falls back to displaying generated_at — a report is always
    # identifiable by its timestamp, this is purely an optional convenience.
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SET NULL, not CASCADE — deleting an old report shouldn't cascade into
    # deleting a newer one that references it for "since last time" framing.
    fed_forward_from_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitor_reports.id", ondelete="SET NULL"), nullable=True
    )

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    trigger_source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")  # manual|scheduled
    ai_provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="completed")  # completed|failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
