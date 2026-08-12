"""
Deterministic report aggregation — this is where CLAUDE.md's "AI narrates
on top of deterministic data" boundary actually lives. Every number and
flag in a report's price_comparison/alerts is computed here from real DB
rows; only executive_summary/recommendations (produced by
ai_client.generate_report_narrative) are AI-authored text. The AI is never
asked to compute or judge a comparison, only to write about one already
computed.
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.catalog.models import Product, ProductSnapshot
from app.db.database import AsyncSessionLocal
from app.discovery.models import CompetitorProductSnapshot, CompetitorSite
from app.discovery.service import (
    PIPELINE_AUTO_CONFIRM_THRESHOLD,
    PIPELINE_AUTO_SAVE_THRESHOLD,
    fetch_market_coverage,
    fetch_new_competitor_products,
    fetch_tracked_matches,
    refresh_saved_sites,
    run_site_discovery,
)
from app.reporting.metrics import group_comparison_rows
from app.reporting.models import CompetitorReport
from app.services import ai_client
from app.services.model_catalog import default_model_for
from app.workspace.models import AiProviderConfig, Workspace

logger = logging.getLogger(__name__)

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


async def _compute_own_trend(
    db: AsyncSession,
    product_id: int,
    previous_report: Optional[CompetitorReport],
    current_price: float,
) -> Optional[dict]:
    """Same shape and reasoning as _compute_trend, mirrored for the
    workspace's OWN product price instead of a competitor's — see
    catalog/models.py's ProductSnapshot. Kept as its own function rather
    than parameterizing _compute_trend: the two snapshot tables differ in
    FK column name and timestamp field name, and duplicating a dozen
    lines here reads more clearly than genericizing over that mismatch."""
    if previous_report is None:
        return None
    result = await db.execute(
        select(ProductSnapshot)
        .where(
            ProductSnapshot.product_id == product_id,
            ProductSnapshot.recorded_at <= previous_report.generated_at,
        )
        .order_by(ProductSnapshot.recorded_at.desc())
        .limit(1)
    )
    snapshot = result.scalars().first()
    if snapshot is None:
        return None
    previous_price = float(snapshot.price)
    if previous_price == 0:
        return None
    delta_pct = round(((current_price - previous_price) / previous_price) * 100, 1)
    return {
        "previous_price": previous_price,
        "previous_checked_at": snapshot.recorded_at.isoformat(),
        "direction": "up" if delta_pct > 0 else "down" if delta_pct < 0 else "same",
        "delta_pct": delta_pct,
        "is_anomaly": abs(delta_pct) >= PRICE_ANOMALY_THRESHOLD_PCT,
    }


# stock_status is free-text (AI-observed from whatever the page showed —
# see discovery/models.py's CompetitorProduct.stock_status docstring), not
# a fixed vocabulary, so a genuine in-stock <-> out-of-stock flip can't be
# detected by exact-string comparison. This is a small, fixed keyword
# classifier (plain Python, not an AI call) — still deterministic per
# CLAUDE.md's rule, it just tolerates the AI's own wording variance from
# the discovery call that originally wrote the text.
_OUT_OF_STOCK_KEYWORDS = ("out of stock", "out-of-stock", "sold out", "unavailable", "not available", "backorder", "discontinued")
_IN_STOCK_KEYWORDS = ("in stock", "in-stock", "available", "ready to ship")


def _classify_stock_status(text: Optional[str]) -> str:
    if not text:
        return "unknown"
    lowered = text.lower()
    if any(k in lowered for k in _OUT_OF_STOCK_KEYWORDS):
        return "out_of_stock"
    if any(k in lowered for k in _IN_STOCK_KEYWORDS):
        return "in_stock"
    return "unknown"


async def _compute_stock_change(
    db: AsyncSession,
    competitor_product_id: int,
    previous_report: Optional[CompetitorReport],
    current_stock_status: Optional[str],
) -> Optional[dict]:
    """Same snapshot-lookup shape as _compute_trend, but for stock_status
    text. Only returns non-None on a genuine in_stock <-> out_of_stock
    flip — "unknown" on either side (no stock note observed, or wording
    the classifier can't place) never fires an alert, since there's
    nothing reliable to compare."""
    if previous_report is None:
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
    if snapshot is None:
        return None
    previous_state = _classify_stock_status(snapshot.stock_status)
    current_state = _classify_stock_status(current_stock_status)
    if previous_state == current_state or "unknown" in (previous_state, current_state):
        return None
    return {
        "previous_stock_status": snapshot.stock_status,
        "current_stock_status": current_stock_status,
        "went_out_of_stock": current_state == "out_of_stock",
    }


async def _build_own_price_alerts(db: AsyncSession, workspace_id: int, previous_report: Optional[CompetitorReport]) -> list[dict]:
    """Deterministic — one alert per own Product whose price has moved by
    at least PRICE_ANOMALY_THRESHOLD_PCT since the previous report (same
    threshold and reasoning as the competitor-side price_anomaly alert).
    Covers the FULL catalog, not just matched products — a price change on
    a product with zero competitor matches is exactly as real as one that
    has some, and until now nothing in reporting ever looked at unmatched
    products' prices at all. No previous report means no baseline —
    correctly produces nothing on a first report."""
    if previous_report is None:
        return []
    result = await db.execute(select(Product).where(Product.workspace_id == workspace_id))
    alerts = []
    for product in result.scalars().all():
        if product.price is None:
            # No price to have moved — a priceless product (e.g. a
            # website-imported one from a site with no published price)
            # simply has nothing to alert on until a real price is set.
            continue
        trend = await _compute_own_trend(db, product.id, previous_report, float(product.price))
        if trend and trend["is_anomaly"]:
            direction_word = "raised" if trend["direction"] == "up" else "lowered"
            alerts.append(
                {
                    "type": "own_price_change",
                    "severity": "medium",
                    "message": (
                        f"You {direction_word} \"{product.name}\"'s price by {abs(trend['delta_pct']):.0f}% "
                        f"since your last report ({product.currency} {trend['previous_price']:.2f} → "
                        f"{product.currency} {float(product.price):.2f})."
                    ),
                    "product_id": product.id,
                    "product_name": product.name,
                    "product_price": float(product.price),
                    "product_currency": product.currency,
                    "trend": trend,
                }
            )
    return alerts


def _compute_comparison_row(
    match, product, cproduct, site, trend: Optional[dict], own_trend: Optional[dict], stock_change: Optional[dict]
) -> dict:
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
        "competitor_product_stock_status": cproduct.stock_status,
        "competitor_site_id": site.id,
        "competitor_site_domain": site.domain,
        "competitor_site_name": site.name,
        "competitor_site_relationship_type": site.relationship_type,
        "same_currency": same_currency,
        "price_delta_pct": price_delta_pct,
        "below_map": below_map,
        "trend": trend,
        "own_trend": own_trend,
        "stock_change": stock_change,
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
        stock_change = row.get("stock_change")
        if stock_change:
            direction_word = "went out of stock" if stock_change["went_out_of_stock"] else "is back in stock"
            alerts.append(
                {
                    "type": "stock_status_change",
                    "severity": "medium",
                    "message": (
                        f"{row['competitor_site_name'] or row['competitor_site_domain']}'s "
                        f"\"{row['competitor_product_title']}\" {direction_word} since the last report "
                        f"(was \"{stock_change['previous_stock_status']}\", now "
                        f"\"{stock_change['current_stock_status']}\")."
                    ),
                    **row,
                    "previous_stock_status": stock_change["previous_stock_status"],
                    "current_stock_status": stock_change["current_stock_status"],
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
        if product.price is None:
            # Can't build a price-comparison row with no price on our own
            # side to compare from (e.g. a website-imported product from a
            # site with no published price) — excluded until a real price
            # is set, same as this match simply not existing for reporting
            # purposes yet. Still fully trackable/visible on the Tracked
            # page in the meantime.
            continue
        competitor_price = float(cproduct.price) if cproduct.price is not None else None
        trend = await _compute_trend(db, cproduct.id, previous_report, competitor_price)
        own_trend = await _compute_own_trend(db, product.id, previous_report, float(product.price))
        stock_change = await _compute_stock_change(db, cproduct.id, previous_report, cproduct.stock_status)
        flat_rows.append(_compute_comparison_row(match, product, cproduct, site, trend, own_trend, stock_change))

    alerts = _build_alerts(flat_rows)
    # No previous report means no "since when" baseline — a first report
    # correctly has nothing to flag as new yet (same reasoning as trend
    # being null throughout on a first report).
    if previous_report is not None:
        new_products = await fetch_new_competitor_products(db, workspace.id, previous_report.generated_at)
        alerts += _build_new_product_alerts(new_products)
        alerts += await _build_own_price_alerts(db, workspace.id, previous_report)
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
        logger.exception("report narrative generation failed for workspace %s", workspace.id)
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


async def run_full_pipeline(db: AsyncSession, workspace: Workspace, trigger_source: str) -> CompetitorReport:
    """The automated discover→match→report pipeline: fresh competitor
    discovery (auto-saving ≥PIPELINE_AUTO_SAVE_THRESHOLD confidence,
    skipping human review), then product discovery + auto-match for every
    saved site (auto-confirming ≥PIPELINE_AUTO_CONFIRM_THRESHOLD
    confidence matches), then generate_report. Two callers: catalog/
    router.py's onboarding trigger (trigger_source="onboarding", the first
    time a workspace's catalog goes from empty to non-empty) and
    reporting/scheduler.py (trigger_source="scheduled", only when
    Workspace.refresh_before_report is on).

    Reseller/MAP discovery is deliberately never run here — it's its own
    opt-in flow (only surfaced when a workspace selects the map_compliance
    objective), and auto-running it for workspaces that never asked for
    MAP tracking would be a real surprise, unlike competitor discovery
    which every workspace already uses by default.

    Site discovery failing (rather than just finding nothing) doesn't
    abort the pipeline — refresh_saved_sites still runs against whatever
    sites are already saved from an earlier run, same "one thing failing
    doesn't block the rest" principle refresh_saved_sites already applies
    one level deeper (per saved site). Only a missing AI provider skips
    straight to generate_report, which will raise the same
    NoActiveProviderError itself moments later anyway — no point
    duplicating that check here.

    A first real run of this (2026-08-10) failed outright on a transient
    Cloudflare 520 from api.openai.com ("wait and retry") — with no human
    watching an unattended background pipeline to click "try again," that
    single AI-provider hiccup was enough to turn a real, otherwise-working
    setup into an empty one. One retry after a short pause covers exactly
    that class of failure without meaningfully slowing down a job nothing
    is waiting on synchronously; NoActiveProviderError is excluded since a
    missing key will never fix itself between the two attempts.

    The whole run is bracketed by Workspace.pipeline_status (committed to
    "running" immediately, before any AI call, so a concurrent poll can
    observe it mid-run — this can take minutes) and finalized to
    "completed"/"failed" in every exit path, success or exception. This
    is the only visibility a frontend has into this pipeline at all: it
    runs entirely server-side (BackgroundTasks or the scheduler), so
    there's no in-flight promise for the existing client-side
    ActivityProvider to wrap the way every other tracked action is —
    without this, the whole run (started, and how it ended) was silently
    invisible, confirmed as a real gap live on 2026-08-10.

    Workspace.pipeline_substeps adds per-step granularity on top of that
    single status: site discovery, one products+match pair per saved
    site, then the report itself — built up front as "pending" once the
    saved-site list is known, flipped to "done"/"error" as each actually
    resolves (via _mark_substep and refresh_saved_sites' on_step
    callback), not written once at the end. The frontend renders these as
    child rows under the one parent activity entry. refresh_saved_sites
    now runs its per-site work CONCURRENTLY (bounded by discovery/
    service.py's MAX_CONCURRENT_SITE_REFRESHES), so these child rows can
    resolve out of the order they were seeded in — expected, not a bug."""
    workspace.pipeline_status = "running"
    workspace.pipeline_trigger_source = trigger_source
    workspace.pipeline_started_at = datetime.now(timezone.utc)
    workspace.pipeline_finished_at = None
    workspace.pipeline_error_message = None
    workspace.pipeline_report_id = None
    # The full plan isn't known yet (which sites will be saved depends on
    # the discovery step about to run) — seeded with just the first step so
    # a poller sees *something* immediately; the per-site steps get
    # appended once that's resolved, below.
    workspace.pipeline_substeps = [{"id": "discovery", "label": "Searching for new competitors", "status": "pending"}]
    await db.commit()

    # From here on, workspace.pipeline_substeps is owned EXCLUSIVELY by
    # _mark_substep below, via its own dedicated session (substep_db) and
    # lock (substep_lock) — never reassigned directly on the outer
    # `workspace` object again. That's what makes it safe for refresh_
    # saved_sites' concurrent per-site tasks (each on their own session)
    # to call it too: asyncio is single-threaded/cooperative, so the lock
    # fully serializes each read-modify-reassign-commit cycle, and reusing
    # one session's identity map (rather than the outer `db`, or a fresh
    # session per call) means every call sees the cumulative effect of
    # every prior write through it — no update from a fast-finishing site
    # can ever be silently lost under a slower one's stale in-memory copy.
    substep_lock = asyncio.Lock()
    substep_db = AsyncSessionLocal()

    async def _mark_substep(step_id: str, status: str, label: Optional[str] = None) -> None:
        """Flips one Workspace.pipeline_substeps entry (adding it if it
        wasn't pre-registered yet) and commits. Reassigns the whole list
        rather than mutating in place: this column isn't wrapped in
        SQLAlchemy's MutableList, so an in-place .append()/item mutation
        wouldn't be seen as a change to flush, same reasoning already
        documented on the model field itself."""
        async with substep_lock:
            ws = await substep_db.get(Workspace, workspace.id)
            if ws is None:
                return
            steps = list(ws.pipeline_substeps or [])
            for i, step in enumerate(steps):
                if step["id"] == step_id:
                    steps[i] = {**step, "status": status}
                    break
            else:
                steps.append({"id": step_id, "label": label or step_id, "status": status})
            ws.pipeline_substeps = steps
            await substep_db.commit()

    try:
        try:
            try:
                await run_site_discovery(
                    db, workspace, mode="competitor", auto_save_threshold=PIPELINE_AUTO_SAVE_THRESHOLD
                )
                await _mark_substep("discovery", "done")
            except ai_client.NoActiveProviderError:
                await _mark_substep("discovery", "error")
            except Exception:
                logger.warning("pipeline site discovery failed for workspace %s, retrying once in 20s", workspace.id)
                await asyncio.sleep(20)
                try:
                    await run_site_discovery(
                        db, workspace, mode="competitor", auto_save_threshold=PIPELINE_AUTO_SAVE_THRESHOLD
                    )
                    await _mark_substep("discovery", "done")
                except ai_client.NoActiveProviderError:
                    await _mark_substep("discovery", "error")
                except Exception:
                    logger.exception("pipeline site discovery failed for workspace %s after retry", workspace.id)
                    await _mark_substep("discovery", "error")

            # Built from the CURRENT saved-site list, not whatever existed
            # before this function started — includes anything the
            # discovery step above just auto-saved, so the plan a poller
            # sees reflects what refresh_saved_sites is actually about to
            # do. Seeded one _mark_substep call at a time (cheap, still
            # strictly sequential here — the concurrent phase hasn't
            # started yet) rather than one bulk write on the outer `db`,
            # so every pipeline_substeps write funnels through the same
            # lock-protected path from this point on.
            saved_sites_result = await db.execute(
                select(CompetitorSite).where(
                    CompetitorSite.workspace_id == workspace.id, CompetitorSite.status == "saved"
                )
            )
            for site in saved_sites_result.scalars().all():
                name = site.name or site.domain
                await _mark_substep(f"site-{site.id}-products", "pending", label=f"Discovering products — {name}")
                await _mark_substep(f"site-{site.id}-match", "pending", label=f"Matching — {name}")

            await refresh_saved_sites(
                db, workspace.id, auto_confirm_threshold=PIPELINE_AUTO_CONFIRM_THRESHOLD, on_step=_mark_substep
            )

            await _mark_substep("report", "pending", label="Writing the report")
            report = await generate_report(db, workspace, trigger_source=trigger_source)
            await _mark_substep("report", "done")
        except Exception as exc:
            # Discard this object's now-stale in-memory pipeline_substeps
            # (last touched before the concurrent phase began) so this
            # commit's dirty-attribute set can't include it — see the
            # ownership note above the substep_lock/substep_db setup.
            await db.refresh(workspace)
            workspace.pipeline_status = "failed"
            workspace.pipeline_finished_at = datetime.now(timezone.utc)
            workspace.pipeline_error_message = str(exc)[:2000]
            await db.commit()
            raise
    finally:
        await substep_db.close()

    # Same reasoning as the failure path above.
    await db.refresh(workspace)
    workspace.pipeline_status = "completed"
    workspace.pipeline_finished_at = datetime.now(timezone.utc)
    workspace.pipeline_report_id = report.id
    await db.commit()
    return report


async def run_full_pipeline_background(workspace_id: int, trigger_source: str) -> None:
    """BackgroundTasks entry point for the onboarding trigger (catalog/
    router.py) — opens its own AsyncSessionLocal() since the triggering
    request's own db session is already closed by the time a
    BackgroundTasks callback actually runs (same reasoning refresh_
    matches_for_workspace already documents for itself). Never raises —
    safe to fire-and-forget."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Workspace).where(Workspace.id == workspace_id))
        workspace = result.scalars().first()
        if workspace is None:
            return
        try:
            await run_full_pipeline(db, workspace, trigger_source=trigger_source)
        except NoTrackedMatchesError:
            logger.info("Skipping %s report for workspace %s: no trackable confirmed matches yet", trigger_source, workspace_id)
        except ai_client.NoActiveProviderError:
            logger.info("Skipping %s report for workspace %s: no active AI provider configured", trigger_source, workspace_id)
        except Exception:
            logger.exception("automated pipeline failed for workspace %s", workspace_id)
