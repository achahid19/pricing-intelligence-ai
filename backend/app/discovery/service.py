"""
Plain (non-HTTP) query functions shared between the discovery router and
other domains that need the same data — currently `reporting`, which reads
tracked matches to build a report but must not depend on the router module
itself (that would couple it to the HTTP layer and invert the intended
one-way dependency: reporting depends on discovery, never the reverse).
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.discovery.models import CompetitorProduct, CompetitorSite, ProductMatch


async def fetch_tracked_matches(
    db: AsyncSession, workspace_id: int, status_filter: str = "confirmed"
) -> list[tuple[ProductMatch, Product, CompetitorProduct, CompetitorSite]]:
    """The same join `GET /discovery/matches` (list_tracked_matches) renders
    into TrackedMatchOut — extracted here so it has exactly one
    implementation rather than being reimplemented per consumer."""
    result = await db.execute(
        select(ProductMatch, Product, CompetitorProduct, CompetitorSite)
        .join(Product, ProductMatch.product_id == Product.id)
        .join(CompetitorProduct, ProductMatch.competitor_product_id == CompetitorProduct.id)
        .join(CompetitorSite, CompetitorProduct.competitor_site_id == CompetitorSite.id)
        .where(ProductMatch.workspace_id == workspace_id, ProductMatch.status == status_filter)
        .order_by(Product.name)
    )
    return result.all()
