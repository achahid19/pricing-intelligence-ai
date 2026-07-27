from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class DiscoveryRun(Base):
    """
    One AI-driven attempt to find competitor sites for a workspace.
    `context_snapshot` records exactly what business context was sent (the
    objectives/country/market/catalog summary actually used to build the
    prompt) — not for display, but so a run's results stay explainable
    after the workspace's own context has since changed.
    """
    __tablename__ = "discovery_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    ai_provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    context_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")  # running|completed|failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    sites: Mapped[list["CompetitorSite"]] = relationship(
        back_populates="discovery_run", cascade="all, delete-orphan"
    )


class CompetitorSite(Base):
    """
    A candidate competitor domain proposed by a DiscoveryRun. `status`
    starts "candidate" — the user reviews and either "saves" (tracked going
    forward, the seed for Phase 2's product-level discovery) or "dismisses"
    it. Confidence/rationale come straight from the AI's own JSON output,
    never recomputed — this is a proposal, not a verified fact.
    """
    __tablename__ = "competitor_sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    discovery_run_id: Mapped[int] = mapped_column(
        ForeignKey("discovery_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )

    domain: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_product_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate")  # candidate|saved|dismissed

    discovery_run: Mapped["DiscoveryRun"] = relationship(back_populates="sites")
