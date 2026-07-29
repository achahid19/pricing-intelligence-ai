"""
Deterministic report aggregation — this is where CLAUDE.md's "AI narrates
on top of deterministic data" boundary actually lives. Every number and
flag in a report's price_comparison/alerts is computed here from real DB
rows; only executive_summary/recommendations (produced by
ai_client.generate_report_narrative) are AI-authored text. The AI is never
asked to compute or judge a comparison, only to write about one already
computed.
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.discovery.models import CompetitorProductSnapshot
from app.discovery.service import fetch_market_coverage, fetch_new_competitor_products, fetch_tracked_matches
from app.reporting.metrics import group_comparison_rows
from app.reporting.models import CompetitorReport
from app.services import ai_client
from app.services.model_catalog import default_model_for
from app.workspace.models import AiProviderConfig, Workspace

# A swing of at least this magnitude since the previous report is flagged
# as a price anomaly — a named threshold, not a magic number, same
# reasoning as this codebase's other tunable constants (DISCOVERY_COOLDOWN_SECONDS,
# _MAX_MATCH_OWN_PRODUCTS).
PRICE_ANOMALY_THRESHOLD_PCT = 15.0


class NoTrackedMatchesError(Exception):
    """Raised only when there is truly nothing to report on — no confirmed
    trackable match AND no discovered competitor product anywhere in the
    workspace. Deliberately broad (not "zero matches" alone): a workspace
    with real saved competitors and rich discovered catalogs but few/no
    confirmed matches yet still has a genuine market-coverage story to
    tell, and blocking that entirely was the exact "isn't this limited"
    problem this data source was added to fix."""


async def _get_active_config(db: AsyncSession, workspace_id: int) -> AiProviderConfig:
    """Same inline lookup discovery/router.py's create_discovery_run already
    does before building its own row (rather than reaching into
    ai_client._get_active_config) — the report needs the provider/model for
    its own columns regardless of whether the narrative call later succeeds,
    and ai_client's own dispatch will look this up again for the actual
    call. Duplicated on purpose, matching that existing precedent."""
    result = await db.execute(
        select(AiProviderConfig).where(
            AiProviderConfig.workspace_id == workspace_id, AiProviderConfig.is_active.is_(True)
        )
    )
    config = result.scalars().first()
    if config is None:
        raise ai_client.NoActiveProviderError(
            "No active AI provider configured for this workspace. Set one up in Settings first."
        )
    return config


async def get_previous_report(db: AsyncSession, workspace_id: int) -> Optional[CompetitorReport]:
    """Most recent report, any status, any trigger_source — manual and
    scheduled reports form one unified chronological chain, so a manual
    regenerate between two scheduled ones is correctly picked up as the
    next scheduled report's predecessor."""
    result = await db.execute(
        select(CompetitorReport)
        .where(CompetitorReport.workspace_id == workspace_id)
        .order_by(CompetitorReport.generated_at.desc())
        .limit(1)
    )
    return result.scalars().first()


async def _compute_trend(
    db: AsyncSession,
    competitor_product_id: int,
    previous_report: Optional[CompetitorReport],
    current_price: Optional[float],
) -> Optional[dict]:
    """Looks up the CompetitorProductSnapshot closest at-or-before the
    previous report's generated_at (already indexed on checked_at), so a
    report can say "up/down since last time" — null if this is the first
    report or nothing that old exists. Also flags is_anomaly per the
    threshold above."""
    if previous_report is None or current_price is None:
        return None
    result = await db.execute(
        select(CompetitorProductSnapshot)
        .where(
            CompetitorProductSnapshot.competitor_product_id == competitor_product_id,
            CompetitorProductSnapshot.checked_at <= previous_report.generated_at,
        )
        .order_by(CompetitorProductSnapshot.checked_at.desc())
        .limit(1)
    )
    snapshot = result.scalars().first()
    if snapshot is None or snapshot.price is None:
        return None
    previous_price = float(snapshot.price)
    if previous_price == 0:
        return None
    delta_pct = round(((current_price - previous_price) / previous_price) * 100, 1)
    return {
        "previous_price": previous_price,
        # .isoformat() — a raw datetime isn't JSON-serializable by the JSONB column.
        "previous_checked_at": snapshot.checked_at.isoformat(),
        "direction": "up" if delta_pct > 0 else "down" if delta_pct < 0 else "same",
        "delta_pct": delta_pct,
        "is_anomaly": abs(delta_pct) >= PRICE_ANOMALY_THRESHOLD_PCT,
    }


def _compute_comparison_row(match, product, cproduct, site, trend: Optional[dict]) -> dict:
    """Ports the exact same-currency-gated price-delta and MAP-violation
    determination frontend/app/(app)/tracked/page.tsx's priceDelta()/
    belowMap compute client-side — this is now the single Python source of
    truth reports read from (that page still computes its own display
    copy from its own live fetch; the underlying determination logic is
    the same rule, just no longer duplicated a third time by this module)."""
    same_currency = cproduct.currency == product.currency
    competitor_price = float(cproduct.price) if cproduct.price is not None else None
    own_price = float(product.price)
    min_price = float(product.min_price) if product.min_price is not None else None

    price_delta_pct = None
    if same_currency and cproduct.is_trackable and competitor_price is not None and own_price:
        price_delta_pct = round(((competitor_price - own_price) / own_price) * 100, 1)

    below_map = (
        same_currency
        and site.relationship_type == "reseller"
        and min_price is not None
        and competitor_price is not None
        and competitor_price < min_price
    )

    return {
        "match_id": match.id,
        "match_method": match.match_method,
        "confidence": match.confidence,
        "rationale": match.rationale,
        "product_id": product.id,
        "product_name": product.name,
        "product_price": own_price,
        "product_currency": product.currency,
        "product_min_price": min_price,
        "competitor_product_id": cproduct.id,
        "competitor_product_title": cproduct.title,
        "competitor_product_price": competitor_price,
        "competitor_product_currency": cproduct.currency,
        "competitor_product_is_trackable": cproduct.is_trackable,
        "competitor_site_id": site.id,
        "competitor_site_domain": site.domain,
        "competitor_site_name": site.name,
        "competitor_site_relationship_type": site.relationship_type,
        "same_currency": same_currency,
        "price_delta_pct": price_delta_pct,
        "below_map": below_map,
        "trend": trend,
    }


def _build_alerts(rows: list[dict]) -> list[dict]:
    """Pure, deterministic — no AI call. A row can produce zero, one, or
    both alert types; messages are plain templated sentences built from
    numbers already computed above, not AI text."""
    alerts = []
    for row in rows:
        if row["below_map"]:
            alerts.append(
                {
                    "type": "map_violation",
                    "severity": "high",
                    "message": (
                        f"{row['competitor_site_name'] or row['competitor_site_domain']} is advertising "
                        f"\"{row['competitor_product_title']}\" at {row['competitor_product_currency']} "
                        f"{row['competitor_product_price']:.2f}, below your {row['product_currency']} "
                        f"{row['product_min_price']:.2f} MAP floor for \"{row['product_name']}\"."
                    ),
                    **row,
                }
            )
        trend = row.get("trend")
        if trend and trend.get("is_anomaly"):
            direction_word = "jumped" if trend["direction"] == "up" else "dropped"
            alerts.append(
                {
                    "type": "price_anomaly",
                    "severity": "medium",
                    "message": (
                        f"{row['competitor_site_name'] or row['competitor_site_domain']}'s price for "
                        f"\"{row['competitor_product_title']}\" {direction_word} "
                        f"{abs(trend['delta_pct']):.0f}% since the last report."
                    ),
                    **row,
                }
            )
    return alerts


def _build_new_product_alerts(new_products: list[dict]) -> list[dict]:
    """Pure, deterministic — no AI call, same reasoning as _build_alerts.
    One alert per competitor site with genuinely new products since the
    previous report (discovery/service.py.fetch_new_competitor_products
    already excludes a site's very first discovery from counting as
    "new")."""
    alerts = []
    for site in new_products:
        count = site["new_product_count"]
        sample = ", ".join(f'"{t}"' for t in site["new_product_titles"][:5])
        alerts.append(
            {
                "type": "new_competitor_product",
                "severity": "medium",
                "message": (
                    f"{site['competitor_site_name'] or site['competitor_site_domain']} added {count} new "
                    f"product{'s' if count != 1 else ''} since your last report, including {sample}."
                ),
                "competitor_site_id": site["competitor_site_id"],
                "competitor_site_domain": site["competitor_site_domain"],
                "competitor_site_name": site["competitor_site_name"],
                "new_product_count": count,
                "new_product_titles": site["new_product_titles"],
            }
        )
    return alerts


def _build_summary_stats(rows: list[dict], alerts: list[dict]) -> dict:
    """price_increases/price_decreases must come from `trend` (a
    competitor's own price now vs. its CompetitorProductSnapshot at the
    previous report) — NOT from `price_delta_pct` (your price vs. that
    competitor's price right now, a snapshot comparison with no time
    dimension at all). Mixing the two up was a real bug: a competitor
    simply priced higher than you today isn't a "price increase" unless
    it actually rose since last time, and on a workspace's very first
    report (no previous report to compare against) trend is always None,
    so these correctly read 0/0 rather than double as an ersatz
    higher/lower-than-you count."""
    return {
        "matches_tracked": len(rows),
        "alerts_count": len(alerts),
        "map_violations_count": sum(1 for a in alerts if a["type"] == "map_violation"),
        "price_anomalies_count": sum(1 for a in alerts if a["type"] == "price_anomaly"),
        "price_increases": sum(1 for r in rows if r.get("trend") and r["trend"]["direction"] == "up"),
        "price_decreases": sum(1 for r in rows if r.get("trend") and r["trend"]["direction"] == "down"),
        "no_price_count": sum(1 for r in rows if not r["competitor_product_is_trackable"]),
    }


async def generate_report(db: AsyncSession, workspace: Workspace, trigger_source: str = "manual") -> CompetitorReport:
    """The one function both the manual endpoint and the scheduler call."""
    match_rows = await fetch_tracked_matches(db, workspace.id, status_filter="confirmed")
    market_coverage = await fetch_market_coverage(db, workspace.id)

    has_trackable_match = any(cproduct.is_trackable for _match, _product, cproduct, _site in match_rows)
    has_discovered_competitor_data = market_coverage["total_competitor_products_discovered"] > 0
    if not has_trackable_match and not has_discovered_competitor_data:
        raise NoTrackedMatchesError(
            "Nothing to report on yet — save a competitor and discover their products, or confirm a priced match, first."
        )

    config = await _get_active_config(db, workspace.id)
    previous_report = await get_previous_report(db, workspace.id)

    flat_rows = []
    for match, product, cproduct, site in match_rows:
        competitor_price = float(cproduct.price) if cproduct.price is not None else None
        trend = await _compute_trend(db, cproduct.id, previous_report, competitor_price)
        flat_rows.append(_compute_comparison_row(match, product, cproduct, site, trend))

    alerts = _build_alerts(flat_rows)
    # No previous report means no "since when" baseline — a first report
    # correctly has nothing to flag as new yet (same reasoning as trend
    # being null throughout on a first report).
    if previous_report is not None:
        new_products = await fetch_new_competitor_products(db, workspace.id, previous_report.generated_at)
        alerts += _build_new_product_alerts(new_products)
    summary_stats = _build_summary_stats(flat_rows, alerts)
    price_comparison = group_comparison_rows(flat_rows)

    narrative_error = None
    try:
        narrative = await ai_client.generate_report_narrative(
            db,
            workspace.id,
            workspace,
            price_comparison,
            alerts,
            market_coverage,
            previous_executive_summary=(previous_report.content.get("executive_summary") if previous_report else None),
        )
        status_ = "completed"
        executive_summary = narrative["executive_summary"]
        market_position = narrative["market_position"]
        competitive_gaps = narrative["competitive_gaps"]
        recommendations = narrative["recommendations"]
    except Exception as exc:
        status_ = "failed"
        executive_summary = None
        market_position = None
        competitive_gaps = None
        recommendations = []
        narrative_error = str(exc)[:2000]

    content = {
        "schema_version": 2,
        "summary_stats": summary_stats,
        "price_comparison": price_comparison,
        "market_coverage": market_coverage,
        "alerts": alerts,
        "executive_summary": executive_summary,
        "market_position": market_position,
        "competitive_gaps": competitive_gaps,
        "recommendations": recommendations,
    }

    report = CompetitorReport(
        workspace_id=workspace.id,
        fed_forward_from_report_id=previous_report.id if previous_report else None,
        trigger_source=trigger_source,
        ai_provider=config.provider,
        model=config.model_override or default_model_for(config.provider),
        status=status_,
        error_message=narrative_error,
        content=content,
    )
    db.add(report)
    await db.commit()
    await db.refresh(report)
    return report
