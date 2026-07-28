"""
Plain (non-HTTP) query functions shared between the discovery router and
other domains that need the same data — currently `reporting`, which reads
tracked matches to build a report but must not depend on the router module
itself (that would couple it to the HTTP layer and invert the intended
one-way dependency: reporting depends on discovery, never the reverse).
"""
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product
from app.discovery.models import CompetitorProduct, CompetitorSite, ProductMatch

# Same "hard safety cap" convention as ai_client._MAX_SAMPLE_PRODUCTS /
# _MAX_MATCH_OWN_PRODUCTS — bounds prompt size regardless of how large a
# competitor's real discovered catalog gets.
_MAX_UNMATCHED_SAMPLE_PER_SITE = 10


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


async def fetch_market_coverage(db: AsyncSession, workspace_id: int) -> dict:
    """Full-catalog market-coverage data for reporting — deliberately not
    scoped to matched products (that's fetch_tracked_matches's job). This
    is what lets a report say "this competitor carries N products you
    have no match for", not just compare the handful already paired up.
    Aggregation is SQL-side (GROUP BY counts, LIMIT-capped samples) rather
    than fetching every CompetitorProduct row into Python — cost stays
    bounded regardless of how large a competitor's real catalog gets."""
    own_catalog_size = await db.scalar(
        select(func.count(Product.id)).where(Product.workspace_id == workspace_id)
    )
    own_products_with_match = await db.scalar(
        select(func.count(func.distinct(ProductMatch.product_id))).where(
            ProductMatch.workspace_id == workspace_id, ProductMatch.status == "confirmed"
        )
    )

    totals_result = await db.execute(
        select(CompetitorProduct.competitor_site_id, func.count(CompetitorProduct.id))
        .where(CompetitorProduct.workspace_id == workspace_id)
        .group_by(CompetitorProduct.competitor_site_id)
    )
    totals_by_site = dict(totals_result.all())

    matched_result = await db.execute(
        select(CompetitorProduct.competitor_site_id, func.count(func.distinct(CompetitorProduct.id)))
        .join(ProductMatch, ProductMatch.competitor_product_id == CompetitorProduct.id)
        .where(CompetitorProduct.workspace_id == workspace_id, ProductMatch.status == "confirmed")
        .group_by(CompetitorProduct.competitor_site_id)
    )
    matched_by_site = dict(matched_result.all())

    sites_result = await db.execute(
        select(CompetitorSite)
        .where(CompetitorSite.workspace_id == workspace_id, CompetitorSite.status == "saved")
        .order_by(CompetitorSite.domain)
    )
    sites = sites_result.scalars().all()

    # Same-status subquery reused per site below — a product is "unmatched"
    # if it has no confirmed ProductMatch row at all.
    matched_competitor_product_ids = select(ProductMatch.competitor_product_id).where(
        ProductMatch.status == "confirmed"
    )

    site_entries = []
    for site in sites:
        sample_result = await db.execute(
            select(CompetitorProduct)
            .where(
                CompetitorProduct.competitor_site_id == site.id,
                CompetitorProduct.id.not_in(matched_competitor_product_ids),
            )
            .order_by(CompetitorProduct.discovered_at.desc())
            .limit(_MAX_UNMATCHED_SAMPLE_PER_SITE)
        )
        site_entries.append(
            {
                "competitor_site_id": site.id,
                "competitor_site_domain": site.domain,
                "competitor_site_name": site.name,
                "relationship_type": site.relationship_type,
                "total_products_discovered": totals_by_site.get(site.id, 0),
                "matched_products_count": matched_by_site.get(site.id, 0),
                "unmatched_sample": [
                    {
                        "competitor_product_id": p.id,
                        "title": p.title,
                        "price": float(p.price) if p.price is not None else None,
                        "currency": p.currency,
                        "description": p.description,
                    }
                    for p in sample_result.scalars().all()
                ],
            }
        )

    return {
        "own_catalog_size": own_catalog_size or 0,
        "own_products_with_confirmed_match": own_products_with_match or 0,
        "total_competitor_products_discovered": sum(totals_by_site.values()),
        "sites": site_entries,
    }
