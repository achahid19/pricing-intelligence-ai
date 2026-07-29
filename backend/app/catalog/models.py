from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Product(Base):
    """
    Workspace-owned catalog item. name/price are the only required fields
    (see docs/PROJECT.md Step 2) — everything else, including image, is
    optional so plain manual/CSV entry is never blocked by a missing field.

    `import_source` records how this row was created (manual|csv|url|
    image_ai|website_ai) — purely observational/debugging, no behavior
    depends on it today.
    """
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(Text, nullable=False)
    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(Text, nullable=False, default="USD")
    # MAP floor — the lowest price resellers are allowed to *advertise* this
    # product at. Optional and independent of `price`: not every workspace
    # enforces MAP, and where it does apply there's no fixed relationship
    # to the workspace's own listed price (that's a per-business policy
    # call, not something to validate here).
    min_price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)

    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sku: Mapped[str | None] = mapped_column(Text, nullable=True)
    brand: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    barcode: Mapped[str | None] = mapped_column(Text, nullable=True)

    import_source: Mapped[str] = mapped_column(Text, nullable=False, default="manual")

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    snapshots: Mapped[list["ProductSnapshot"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


class ProductSnapshot(Base):
    """
    A price reading for one of the workspace's own Products — mirrors
    CompetitorProductSnapshot's role (see discovery/models.py), but the
    write trigger is different: a competitor's price is re-observed by
    discovery re-runs regardless of whether it actually changed, so that
    table gets a row on every touch; a workspace's own price only ever
    changes through an explicit edit made through this app, so a row here
    is written only when the price is set (on creation) or genuinely
    changes (on edit) — never a snapshot storm from re-saving the same
    value. Without this, reporting/service.py's _compute_own_trend has no
    way to recover "what was this priced at, as of the previous report"
    once a price has been overwritten.
    """
    __tablename__ = "product_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True
    )

    price: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True
    )

    product: Mapped["Product"] = relationship(back_populates="snapshots")
