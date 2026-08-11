from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Product(Base):
    """
    Workspace-owned catalog item. name is the only truly required field
    (see docs/PROJECT.md Step 2) — everything else, including image, is
    optional so plain manual/CSV entry is never blocked by a missing field.
    price is nullable: not every source has one upfront (a website-import
    candidate from a site that doesn't publish prices, e.g. a B2B or brand
    site) — a priceless product can still be cataloged, matched, and edited
    later once a real price is known. It's simply excluded from anything
    that fundamentally needs a number (report price-comparison/ranking,
    own-price-change alerts) until then — see reporting/service.py.

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
    price: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
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
    # The exact page a website-imported product was found on (see
    # catalog/router.py's confirm_website_import) — lets the catalog link
    # straight back to the source for verification. Null for every other
    # import_source. Editable via PATCH (ProductDialog's "Source URL"
    # field) — a discovered page can turn out generic/wrong, and the user
    # may know the real one even when the AI didn't.
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Whether source_url is actually confirmed real — see
    # ai_client._url_is_cited / url_check for what "confirmed" means at
    # discovery time. Three states, not two: True (confirmed at discovery,
    # or the user just typed/corrected it themselves — see update_product),
    # False (positively known bad — e.g. url_check.find_generic_urls caught
    # several different products sharing one non-specific page), and NULL
    # (no signal either way — every non-website_ai product, and any
    # website_ai row created before this field existed). NULL is
    # deliberately NOT treated as "bad" in the UI — it just means no
    # verification was ever attempted, not that verification failed.
    source_url_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

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
