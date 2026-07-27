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
    A competitor domain — either proposed by a DiscoveryRun (AI-sourced,
    `discovery_run_id` set, confidence/rationale come from the AI) or added
    directly by the user (`discovery_run_id` NULL, confidence/rationale
    absent — a manual entry is trusted as-is, not a proposal to review).
    `workspace_id` is denormalized here (not just reachable via the run)
    specifically so manually-added sites — which have no run at all — can
    still be scoped and deduplicated per workspace.

    `status` starts "candidate" for AI proposals — the user reviews and
    either "saves" (tracked going forward, the seed for Phase 2's
    product-level discovery) or "dismisses" it. Manual entries start
    "saved" directly, skipping review of your own deliberate input.
    """
    __tablename__ = "competitor_sites"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    discovery_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("discovery_runs.id", ondelete="CASCADE"), nullable=True, index=True
    )

    domain: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100, AI-sourced only
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)  # AI-sourced only
    estimated_product_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate")  # candidate|saved|dismissed

    discovery_run: Mapped["DiscoveryRun | None"] = relationship(back_populates="sites")
