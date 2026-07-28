from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class DiscoveryRun(Base):
    """
    One AI-driven attempt to find competitor OR reseller sites for a
    workspace — `mode` distinguishes the two, since they're fundamentally
    different research questions with opposite inclusion rules (see
    CompetitorSite.relationship_type). `context_snapshot` records exactly
    what business context was sent (the objectives/country/market/catalog
    summary actually used to build the prompt) — not for display, but so a
    run's results stay explainable after the workspace's own context has
    since changed.
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
    mode: Mapped[str] = mapped_column(Text, nullable=False, default="competitor")  # competitor|reseller
    context_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="running")  # running|completed|failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    sites: Mapped[list["CompetitorSite"]] = relationship(
        back_populates="discovery_run", cascade="all, delete-orphan"
    )


class CompetitorSite(Base):
    """
    A competitor OR reseller domain — either proposed by a DiscoveryRun
    (AI-sourced, `discovery_run_id` set, confidence/rationale come from the
    AI) or added directly by the user (`discovery_run_id` NULL, confidence/
    rationale absent — a manual entry is trusted as-is, not a proposal to
    review). `workspace_id` is denormalized here (not just reachable via
    the run) specifically so manually-added sites — which have no run at
    all — can still be scoped and deduplicated per workspace.

    `relationship_type` distinguishes two fundamentally different research
    questions sharing one table/review workflow: "competitor" (another
    business with its own rival product/brand — resellers/retailers are
    explicitly excluded, see ai_client._DISCOVER_PROMPT_TEMPLATE) vs.
    "reseller" (a business that advertises/sells THIS workspace's own
    product — the inverse inclusion rule, needed for MAP-compliance
    monitoring: checking whether resellers are advertising below the
    minimum price set in Product.min_price). Default "competitor" so
    existing rows and the common case need no extra decision.

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
    relationship_type: Mapped[str] = mapped_column(Text, nullable=False, default="competitor")  # competitor|reseller
    confidence_score: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100, AI-sourced only
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)  # AI-sourced only
    estimated_product_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate")  # candidate|saved|dismissed

    # Cooldown timestamps for the two per-site AI actions Phase 2 adds —
    # same "cheapest guard against a double-click burning real cost" logic
    # as DISCOVERY_COOLDOWN_SECONDS, just scoped per-site instead of
    # per-workspace since these actions operate on one site at a time.
    products_discovered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_auto_match_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    discovery_run: Mapped["DiscoveryRun | None"] = relationship(back_populates="sites")
    products: Mapped[list["CompetitorProduct"]] = relationship(
        back_populates="competitor_site", cascade="all, delete-orphan"
    )


class CompetitorProduct(Base):
    """
    A product observed on a saved competitor's site via
    ai_client.discover_competitor_products(). Unlike CompetitorSite, there's
    no candidate/saved/dismissed review status here — these are just
    observed facts to browse and match against, not proposals to accept or
    reject. workspace_id is denormalized for the same reason as
    CompetitorSite: simple per-workspace queries without joining through
    the site. Re-running discovery upserts by (competitor_site_id, url)
    rather than duplicating, and never deletes rows no longer found — a
    product temporarily unlisted isn't necessarily discontinued.
    """
    __tablename__ = "competitor_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competitor_site_id: Mapped[int] = mapped_column(
        ForeignKey("competitor_sites.id", ondelete="CASCADE"), nullable=False, index=True
    )

    title: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Best-effort, AI-observed — not a real inventory feed, just whatever
    # availability signal (or lack of one) was visible on the page.
    stock_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Free-text catch-all for whatever else was actually useful on the page
    # (specs, capacity, contract terms, included features) — deliberately
    # not a fixed set of structured attribute columns, since what's worth
    # capturing varies enormously by product type.
    additional_info: Mapped[str | None] = mapped_column(Text, nullable=True)

    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    competitor_site: Mapped["CompetitorSite"] = relationship(back_populates="products")
    matches: Mapped[list["ProductMatch"]] = relationship(
        back_populates="competitor_product", cascade="all, delete-orphan"
    )


class ProductMatch(Base):
    """
    A pairing between one of the workspace's own products and a
    CompetitorProduct. `status` mirrors CompetitorSite's candidate/saved/
    dismissed vocabulary (as "candidate"/"confirmed"/"dismissed") rather
    than a flatter active/dismissed — an ai_auto proposal needs a pending
    state distinct from user-confirmed, same reasoning that already
    justified CompetitorSite.status. Manual matches (drag-and-drop) are
    created directly as "confirmed" — there's no AI judgment to review,
    same as a manually-added CompetitorSite skipping the candidate stage.
    """
    __tablename__ = "product_matches"
    __table_args__ = (UniqueConstraint("product_id", "competitor_product_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )
    competitor_product_id: Mapped[int] = mapped_column(
        ForeignKey("competitor_products.id", ondelete="CASCADE"), nullable=False, index=True
    )

    match_method: Mapped[str] = mapped_column(Text, nullable=False)  # manual|ai_auto
    confidence: Mapped[int | None] = mapped_column(Integer, nullable=True)  # 0-100, ai_auto only
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)  # ai_auto only
    status: Mapped[str] = mapped_column(Text, nullable=False, default="candidate")  # candidate|confirmed|dismissed

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    competitor_product: Mapped["CompetitorProduct"] = relationship(back_populates="matches")
