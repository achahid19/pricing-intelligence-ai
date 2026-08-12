"""
Plain (non-HTTP) functions shared between the discovery router and other
callers that need the same logic but aren't a live HTTP request — reporting
(reads tracked matches to build a report) and the automated
discover→match→report pipeline (backend/app/reporting/scheduler.py, and the
post-catalog-import background refresh) both depend on this module; it must
never depend back on discovery/router.py (that would couple it to the HTTP
layer and invert the intended one-way dependency).
"""
import asyncio
import logging
from datetime import datetime, timezone
from typing import Awaitable, Callable

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.catalog.models import Product
from app.db.database import AsyncSessionLocal
from app.discovery.models import (
    CompetitorProduct,
    CompetitorProductSnapshot,
    CompetitorSite,
    DiscoveryRun,
    ProductMatch,
)
from app.services import ai_client, url_check
from app.services.model_catalog import default_model_for
from app.services.text import normalize_domain, strip_citations
from app.workspace.models import AiProviderConfig, Workspace

logger = logging.getLogger(__name__)

# Same "hard safety cap" convention as ai_client._MAX_SAMPLE_PRODUCTS /
# _MAX_MATCH_OWN_PRODUCTS — bounds prompt size regardless of how large a
# competitor's real discovered catalog gets.
_MAX_UNMATCHED_SAMPLE_PER_SITE = 10
_MAX_NEW_PRODUCTS_SAMPLE_PER_SITE = 10

# The automated pipeline's bar for skipping human review — reporting/
# service.py's run_full_pipeline passes these to run_site_discovery/
# run_site_auto_match; every manual/interactive call site leaves them
# unset, so nothing about today's human-reviewed flow changes.
PIPELINE_AUTO_SAVE_THRESHOLD = 80  # CompetitorSite.confidence_score
PIPELINE_AUTO_CONFIRM_THRESHOLD = 80  # ProductMatch.confidence


class NoCompetitorProductsError(Exception):
    """Raised by run_site_auto_match when the site has no discovered
    CompetitorProducts yet — nothing to match against."""


class EmptyCatalogError(Exception):
    """Raised by run_site_auto_match when the workspace has no own
    Products yet — nothing to match to."""


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
        .where(
            ProductMatch.workspace_id == workspace_id,
            ProductMatch.status == status_filter,
            CompetitorProduct.is_dismissed.is_(False),
        )
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
        .where(CompetitorProduct.workspace_id == workspace_id, CompetitorProduct.is_dismissed.is_(False))
        .group_by(CompetitorProduct.competitor_site_id)
    )
    totals_by_site = dict(totals_result.all())

    matched_result = await db.execute(
        select(CompetitorProduct.competitor_site_id, func.count(func.distinct(CompetitorProduct.id)))
        .join(ProductMatch, ProductMatch.competitor_product_id == CompetitorProduct.id)
        .where(
            CompetitorProduct.workspace_id == workspace_id,
            CompetitorProduct.is_dismissed.is_(False),
            ProductMatch.status == "confirmed",
        )
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
                CompetitorProduct.is_dismissed.is_(False),
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


async def fetch_new_competitor_products(db: AsyncSession, workspace_id: int, since: datetime) -> list[dict]:
    """Competitor products first discovered after `since` (the previous
    report's generated_at) — the deterministic basis for reporting's
    "new_competitor_product" alert. Only `status="saved"`,
    `relationship_type="competitor"` sites: a reseller's new listings are
    new sightings of THIS workspace's own products, not a rival launching
    something (same reseller-exclusion reasoning as fetch_market_coverage).

    Gated on the site having had at least one product discovered
    at-or-before `since` too — otherwise a competitor only saved (or
    first ever discovered) after the previous report would have its
    entire starting catalog misread as "just launched N new products",
    when really it's only new to US, not new to the market. Only sites
    already being tracked with some real catalog depth qualify."""
    had_products_before_ids = (
        select(CompetitorProduct.competitor_site_id)
        .where(CompetitorProduct.workspace_id == workspace_id, CompetitorProduct.discovered_at <= since)
        .distinct()
    )

    result = await db.execute(
        select(CompetitorProduct, CompetitorSite)
        .join(CompetitorSite, CompetitorProduct.competitor_site_id == CompetitorSite.id)
        .where(
            CompetitorSite.workspace_id == workspace_id,
            CompetitorSite.status == "saved",
            CompetitorSite.relationship_type == "competitor",
            CompetitorProduct.discovered_at > since,
            CompetitorProduct.competitor_site_id.in_(had_products_before_ids),
            CompetitorProduct.is_dismissed.is_(False),
        )
        .order_by(CompetitorProduct.discovered_at.desc())
    )

    by_site: dict[int, dict] = {}
    order: list[int] = []
    for product, site in result.all():
        if site.id not in by_site:
            by_site[site.id] = {
                "competitor_site_id": site.id,
                "competitor_site_domain": site.domain,
                "competitor_site_name": site.name,
                "new_product_count": 0,
                "new_product_titles": [],
            }
            order.append(site.id)
        entry = by_site[site.id]
        entry["new_product_count"] += 1
        if len(entry["new_product_titles"]) < _MAX_NEW_PRODUCTS_SAMPLE_PER_SITE:
            entry["new_product_titles"].append(product.title)

    return [by_site[site_id] for site_id in order]


async def run_site_discovery(
    db: AsyncSession,
    workspace: Workspace,
    mode: str,
    max_candidates: int = 10,
    auto_save_threshold: int | None = None,
) -> tuple[DiscoveryRun, int | None, int]:
    """Core of create_discovery_run (discovery/router.py), minus the
    cooldown check — that's an HTTP-layer guard against an impatient
    double-click, irrelevant to a caller invoked at most once per pipeline
    cycle. Ask the workspace's active AI provider to research the web and
    propose up to max_candidates competitor/reseller sites, creating a
    CompetitorSite per genuinely new domain. Returns (run, search_count,
    skipped_known_count) — the same three pieces of transient response
    metadata the router's own _to_run_out already assembles, not persisted
    on DiscoveryRun itself.

    When auto_save_threshold is set, a candidate whose confidence_score
    meets it is created directly as "saved" instead of "candidate" —
    used by the automated pipeline (reporting/service.py's
    run_full_pipeline) to skip human review for high-confidence finds; the
    manual /runs endpoint never passes this, so its own behavior is
    unchanged. Raises ai_client.NoActiveProviderError (no DiscoveryRun row
    created at all) or propagates the discover-call's own exception (after
    marking the row "failed") — both uncaught, same convention as
    run_site_product_discovery/run_site_auto_match; callers decide how to
    handle each."""
    active_result = await db.execute(
        select(AiProviderConfig).where(
            AiProviderConfig.workspace_id == workspace.id,
            AiProviderConfig.is_active.is_(True),
        )
    )
    active_config = active_result.scalars().first()
    if active_config is None:
        raise ai_client.NoActiveProviderError("No active AI provider configured for this workspace.")
    model = active_config.model_override or default_model_for(active_config.provider)

    products_result = await db.execute(select(Product).where(Product.workspace_id == workspace.id))
    products = products_result.scalars().all()
    context = ai_client.build_discovery_context(workspace, products)

    # Domains already known for this workspace (any status, any prior run)
    # — re-running discovery shouldn't re-suggest a competitor the user has
    # already saved, dismissed, or is still sitting on from an earlier run.
    known_result = await db.execute(
        select(CompetitorSite.domain).where(CompetitorSite.workspace_id == workspace.id)
    )
    known_domains = {normalize_domain(d) for d in known_result.scalars().all()}

    run = DiscoveryRun(
        workspace_id=workspace.id,
        ai_provider=active_config.provider,
        model=model,
        mode=mode,
        context_snapshot={"context": context, "max_candidates": max_candidates},
        status="running",
    )
    db.add(run)
    await db.flush()

    discover_fn = ai_client.discover_reseller_sites if mode == "reseller" else ai_client.discover_competitor_sites
    try:
        result, search_count = await discover_fn(db, workspace.id, context, max_candidates=max_candidates)
    except Exception as exc:
        logger.exception("discovery run %s failed for workspace %s (mode=%s)", run.id, workspace.id, mode)
        run.status = "failed"
        run.error_message = str(exc)[:2000]
        await db.commit()
        raise

    skipped_known = 0
    for candidate in result.get("candidates", [])[:max_candidates]:
        domain = normalize_domain(candidate.get("domain") or "")
        if not domain:
            continue
        if domain in known_domains:
            skipped_known += 1
            continue
        known_domains.add(domain)  # a run can propose the same domain twice; don't double-add within one run either
        try:
            confidence = max(0, min(100, int(candidate.get("confidence", 0))))
        except (TypeError, ValueError):
            confidence = 0
        db.add(
            CompetitorSite(
                workspace_id=workspace.id,
                discovery_run_id=run.id,
                domain=domain,
                name=candidate.get("name"),
                relationship_type=mode,
                confidence_score=confidence,
                rationale=strip_citations(candidate.get("rationale")) or "",
                estimated_product_count=candidate.get("estimated_product_count"),
                status="saved" if auto_save_threshold is not None and confidence >= auto_save_threshold else "candidate",
            )
        )

    run.status = "completed"
    await db.commit()

    refreshed = await db.execute(
        select(DiscoveryRun).where(DiscoveryRun.id == run.id).options(selectinload(DiscoveryRun.sites))
    )
    return refreshed.scalars().one(), search_count, skipped_known


async def run_site_product_discovery(
    db: AsyncSession, workspace_id: int, site: CompetitorSite, max_products: int = 15
) -> list[CompetitorProduct]:
    """Core of discover_products_for_site (discovery/router.py), minus the
    cooldown check — that's an HTTP-layer guard against an impatient
    double-click, irrelevant to a caller invoked at most once per report
    cycle. Ask the workspace's active AI provider to browse this saved
    competitor's site and list real products it found, upserting by
    (url, title) — re-running updates existing rows rather than
    duplicating, and never deletes rows no longer found. Commits and
    returns the site's full current product list. Propagates any
    ai_client exception uncaught — callers decide how to handle it."""
    result, _search_count = await ai_client.discover_competitor_products(
        db,
        workspace_id,
        site.domain,
        site.name,
        max_products=max_products,
        relationship_type=site.relationship_type,
    )

    # selectinload(.snapshots) is required, not optional: the loop below
    # calls existing.snapshots.append(...) on rows returned here, and
    # under async SQLAlchemy appending to an unloaded lazy collection tries
    # to fire an implicit synchronous fetch — which fails outright
    # ("greenlet_spawn has not been called") rather than degrading
    # gracefully. Confirmed live: this was a real, pre-existing bug (not
    # introduced by extracting this function) that only ever manifested
    # when a discovery run's upsert hit an *existing* product, which
    # earlier ad-hoc testing this session happened not to exercise.
    existing_result = await db.execute(
        select(CompetitorProduct)
        .where(CompetitorProduct.competitor_site_id == site.id)
        .options(selectinload(CompetitorProduct.snapshots))
    )
    # Keyed on (url, title), not url alone — a single pricing/listing page
    # legitimately lists several distinct products under the same URL when
    # they don't each have their own page, so url alone would silently
    # collapse multiple real products onto one row within the same run.
    existing_by_key = {(p.url, p.title): p for p in existing_result.scalars().all()}

    raw_candidates = result.get("products", [])[:max_products]
    # Citation-based verification (set by ai_client.discover_competitor_
    # products, from the AI provider's own search tool) is the strongest
    # signal but sparse in practice for a JSON-only prompt — top it up with
    # a real HTTP reachability check for whatever it didn't already
    # confirm, same as catalog/router.py's website-import does. Deduped by
    # URL first since several products commonly share one listing page.
    urls_to_check = {
        (c.get("url") or "").strip() for c in raw_candidates if not c.get("url_verified") and (c.get("url") or "").strip()
    }
    reachable_by_url: dict[str, bool] = {}
    if urls_to_check:
        async with httpx.AsyncClient() as client:
            reachable = await asyncio.gather(*(url_check.url_is_reachable(client, u) for u in urls_to_check))
        reachable_by_url = dict(zip(urls_to_check, reachable))

    # Final override: a URL claimed by several genuinely distinct products
    # (past what a real single product-family page groups together — see
    # find_generic_urls) is a sign the AI fell back to one generic listing
    # page rather than each product's own page, even though that page is
    # itself real and reachable.
    generic_urls = url_check.find_generic_urls(
        [((c.get("url") or "").strip(), (c.get("title") or "").strip()) for c in raw_candidates]
    )

    for candidate in raw_candidates:
        title = (candidate.get("title") or "").strip()
        url = (candidate.get("url") or "").strip()
        if not title or not url:
            continue
        try:
            price = candidate.get("price")
            price = round(float(price), 2) if price is not None else None
        except (TypeError, ValueError):
            price = None

        description = strip_citations(candidate.get("description"))
        additional_info = strip_citations(candidate.get("additional_info"))

        stock_status = candidate.get("stock_status")
        is_trackable = price is not None
        is_url_verified = (bool(candidate.get("url_verified")) or reachable_by_url.get(url, False)) and (
            url not in generic_urls
        )

        key = (url, title)
        existing = existing_by_key.get(key)
        if existing is not None:
            existing.price = price
            existing.currency = candidate.get("currency")
            existing.description = description
            existing.stock_status = stock_status
            existing.additional_info = additional_info
            existing.is_trackable = is_trackable
            existing.is_url_verified = is_url_verified
            product = existing
        else:
            product = CompetitorProduct(
                workspace_id=workspace_id,
                competitor_site_id=site.id,
                title=title,
                price=price,
                currency=candidate.get("currency"),
                url=url,
                description=description,
                stock_status=stock_status,
                additional_info=additional_info,
                is_trackable=is_trackable,
                is_url_verified=is_url_verified,
            )
            db.add(product)
            existing_by_key[key] = product

        # A price/stock reading for every product touched this run — the
        # CompetitorProduct row above only ever holds the latest state, so
        # without this the previous value would be silently overwritten and
        # lost the moment this run commits. Appending via the relationship
        # (rather than setting competitor_product_id directly) lets
        # SQLAlchemy resolve the FK at flush time even for a brand-new,
        # not-yet-committed product.
        product.snapshots.append(
            CompetitorProductSnapshot(workspace_id=workspace_id, price=price, stock_status=stock_status)
        )

    site.products_discovered_at = datetime.now(timezone.utc)
    await db.commit()

    refreshed = await db.execute(
        select(CompetitorProduct).where(CompetitorProduct.competitor_site_id == site.id).order_by(CompetitorProduct.discovered_at.desc())
    )
    return refreshed.scalars().all()


async def run_site_auto_match(
    db: AsyncSession, workspace_id: int, site: CompetitorSite, auto_confirm_threshold: int | None = None
) -> list[ProductMatch]:
    """Core of auto_match_site_products (discovery/router.py), minus the
    cooldown check (same reasoning as run_site_product_discovery). Ask the
    workspace's active AI provider to propose matches between this site's
    discovered products and the workspace's own catalog, writing
    ProductMatch rows as "candidate" for the user to confirm/dismiss — a
    confirmed or dismissed pair already on file is left alone, never
    silently overwritten by a fresh proposal. Raises NoCompetitorProducts
    Error / EmptyCatalogError instead of an HTTP error when there's
    nothing to match yet; propagates any ai_client exception uncaught.

    When auto_confirm_threshold is set, a newly-created match whose
    confidence meets it is written directly as "confirmed" instead of
    "candidate" — used by the automated pipeline (reporting/service.py's
    run_full_pipeline) to skip human review for high-confidence matches;
    the manual /auto-match endpoint never passes this, so its own behavior
    is unchanged. Only ever applies to a brand-new pair, same as the
    existing candidate-refresh branch above it — a pair already on file
    keeps whatever decision (human or automated) was already made for it."""
    competitor_products_result = await db.execute(
        select(CompetitorProduct).where(
            CompetitorProduct.competitor_site_id == site.id, CompetitorProduct.is_dismissed.is_(False)
        )
    )
    competitor_products = competitor_products_result.scalars().all()
    if not competitor_products:
        raise NoCompetitorProductsError("Discover this competitor's products before running auto-match.")

    own_products_result = await db.execute(select(Product).where(Product.workspace_id == workspace_id))
    own_products = own_products_result.scalars().all()
    if not own_products:
        raise EmptyCatalogError("Your catalog is empty.")

    result, _search_count = await ai_client.match_products(db, workspace_id, own_products, competitor_products)

    existing_result = await db.execute(
        select(ProductMatch).where(ProductMatch.competitor_product_id.in_([p.id for p in competitor_products]))
    )
    existing_by_pair = {(m.product_id, m.competitor_product_id): m for m in existing_result.scalars().all()}

    for match in result.get("matches", []):
        try:
            comp_idx = int(match["competitor_product_index"])
            prod_idx = int(match["product_index"])
            confidence = max(0, min(100, int(match.get("confidence", 0))))
        except (KeyError, TypeError, ValueError):
            continue
        if not (0 <= comp_idx < len(competitor_products)) or not (0 <= prod_idx < len(own_products)):
            continue
        competitor_product = competitor_products[comp_idx]
        product = own_products[prod_idx]
        rationale = match.get("rationale") or ""

        pair_key = (product.id, competitor_product.id)
        existing = existing_by_pair.get(pair_key)
        if existing is not None:
            if existing.status == "candidate":
                existing.confidence = confidence
                existing.rationale = rationale
            # A confirmed or dismissed pair is left alone — a fresh AI
            # proposal shouldn't silently overwrite a decision already made.
            continue
        new_match = ProductMatch(
            workspace_id=workspace_id,
            product_id=product.id,
            competitor_product_id=competitor_product.id,
            match_method="ai_auto",
            confidence=confidence,
            rationale=rationale,
            status="confirmed" if auto_confirm_threshold is not None and confidence >= auto_confirm_threshold else "candidate",
        )
        db.add(new_match)
        existing_by_pair[pair_key] = new_match

    site.last_auto_match_at = datetime.now(timezone.utc)
    await db.commit()

    refreshed = await db.execute(
        select(ProductMatch)
        .join(CompetitorProduct, ProductMatch.competitor_product_id == CompetitorProduct.id)
        .where(CompetitorProduct.competitor_site_id == site.id)
    )
    return refreshed.scalars().all()


async def refresh_matches_for_workspace(workspace_id: int) -> None:
    """FastAPI BackgroundTasks entry point: re-run auto-match for every one
    of the workspace's saved CompetitorSites after new products land in the
    catalog (catalog/router.py's confirm_website_import / import_products),
    so newly-imported products get matched against already-discovered
    competitor products without the user having to click "Auto-match" on
    each site by hand. Deliberately matching only, never fresh product
    discovery — nothing about competitors changed just because this
    workspace's own catalog did, so a new AI web-search call here would be
    pure wasted cost.

    Opens its own AsyncSessionLocal(): the triggering request's own `db`
    session is already closed by the time a BackgroundTasks callback
    actually runs (same reasoning reporting/scheduler.py's background loop
    already documents for itself). Per-site isolated and never raises —
    safe to fire-and-forget."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(CompetitorSite).where(CompetitorSite.workspace_id == workspace_id, CompetitorSite.status == "saved")
        )
        for site in result.scalars().all():
            try:
                await run_site_auto_match(db, workspace_id, site)
            except ai_client.NoActiveProviderError:
                # Workspace-wide condition, not per-site — retrying it for
                # every remaining site would just log the same failure N
                # times for no benefit.
                logger.info(
                    "No active AI provider for workspace %s; skipping remaining post-import match refresh",
                    workspace_id,
                )
                break
            except (NoCompetitorProductsError, EmptyCatalogError):
                # Nothing to match yet for this site — not a real error,
                # just means it hasn't had product discovery run on it.
                continue
            except Exception:
                logger.exception("post-import match refresh failed for site %s, workspace %s", site.id, workspace_id)


MAX_CONCURRENT_SITE_REFRESHES = 4
# Bounds how many saved sites run product-discovery + auto-match at once in
# refresh_saved_sites below. The default async engine pool (db/database.py,
# no explicit pool_size/max_overflow override) allows 15 concurrent
# connections; one pipeline run at this cap holds up to
# MAX_CONCURRENT_SITE_REFRESHES site sessions (each held for that site's
# whole two-step lifecycle — AsyncSession doesn't release its connection
# between the two awaited AI calls) + 1 dedicated substep-write session
# (see run_full_pipeline's _mark_substep in reporting/service.py) + 1 idle
# outer session ~= 6 at peak, leaving headroom for ordinary HTTP traffic on
# the same pool and for a second workspace's pipeline running concurrently
# (~12 of 15 in that case). This is a per-pipeline-run semaphore, not a
# global one — it does NOT protect against multiple simultaneous pipelines
# each independently saturating the pool. Don't raise this constant without
# re-deriving that math, same spirit as reporting/scheduler.py's own
# documented single-replica deployment assumption.


async def _cancel_requested(db: AsyncSession, workspace_id: int) -> bool:
    """A targeted column read (not a full Workspace fetch) — called from
    inside a concurrent site task's own session, so this must stay cheap
    and side-effect-free rather than touching that session's identity map
    with a full ORM object."""
    return bool(await db.scalar(select(Workspace.pipeline_cancel_requested).where(Workspace.id == workspace_id)))


async def refresh_saved_sites(
    db: AsyncSession,
    workspace_id: int,
    auto_confirm_threshold: int | None = None,
    on_step: Callable[[str, str], Awaitable[None]] | None = None,
) -> None:
    """The heavier, opt-in (Workspace.refresh_before_report) pipeline step:
    for every saved CompetitorSite, fresh product discovery THEN
    auto-match, run CONCURRENTLY across sites (bounded by
    MAX_CONCURRENT_SITE_REFRESHES above). Sole caller: reporting/service.py's
    run_full_pipeline (auto_confirm_threshold=PIPELINE_AUTO_CONFIRM_
    THRESHOLD, run after run_site_discovery has had a chance to auto-save
    new sites too).

    The db session passed in here is only used for the initial site query
    and the up-front provider check below — each site's actual work runs in
    its OWN AsyncSessionLocal(), opened fresh inside that site's own task.
    A SQLAlchemy AsyncSession wraps a single connection and isn't safe for
    concurrent use by multiple coroutines, which is exactly why this used
    to run strictly sequentially on the caller's session; this function is
    the first place in the backend using asyncio.Semaphore.

    Per-site AND per-step isolated, and never raises: a discovery failure
    for one site still falls through to that site's auto-match (against
    whatever CompetitorProduct rows already exist from an earlier run,
    if any), and one site's total failure never stops another site's task.
    generate_report() must always still run afterward regardless of how
    this went — a report reflecting stale-but-present data beats no
    report at all, same "don't let one thing's failure block everything
    downstream" principle the scheduler already applies per-workspace,
    just one level deeper here (per-step within one workspace's run).

    on_step, when given, is awaited as (step_id, "done"|"error"|"cancelled") right
    after each site's product-discovery and auto-match calls resolve —
    run_full_pipeline uses this to flip Workspace.pipeline_substeps
    entries live as the run progresses. Since sites now run concurrently,
    steps resolve in whatever order their AI calls actually finish, not
    strictly in the order sites were enumerated — on_step itself must
    therefore be safe to call from multiple concurrent tasks (run_full_
    pipeline's on_step is lock-protected; see _mark_substep there)."""
    result = await db.execute(
        select(CompetitorSite).where(CompetitorSite.workspace_id == workspace_id, CompetitorSite.status == "saved")
    )
    sites = result.scalars().all()
    if not sites:
        return

    # Cheap up-front check: if there's no active provider at all, every
    # site would independently rediscover the exact same workspace-wide
    # fact a moment later. Check once, mark every step "error" directly,
    # and skip the fan-out entirely instead of doing N redundant lookups
    # (this also fixes a latent bug in the old sequential loop: it used to
    # `return` on the first NoActiveProviderError, leaving later sites'
    # steps stuck "pending" forever instead of explicitly "error").
    provider_check = await db.execute(
        select(AiProviderConfig).where(
            AiProviderConfig.workspace_id == workspace_id, AiProviderConfig.is_active.is_(True)
        )
    )
    if provider_check.scalars().first() is None:
        logger.info(
            "No active AI provider for workspace %s; marking all pre-report refresh steps as error", workspace_id
        )
        for site in sites:
            if on_step:
                await on_step(f"site-{site.id}-products", "error")
                await on_step(f"site-{site.id}-match", "error")
        return

    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SITE_REFRESHES)

    async def _process_site(site_id: int) -> None:
        async with semaphore:
            try:
                async with AsyncSessionLocal() as site_db:
                    site = await site_db.get(CompetitorSite, site_id)
                    if site is None:
                        return  # deleted between enumeration and this task's turn

                    # Checked here (before this task's first AI call) rather
                    # than only once up front in refresh_saved_sites: a site
                    # still waiting on the semaphore when cancellation is
                    # requested should never start its work at all, not just
                    # sites enumerated after the check. Marks BOTH of this
                    # site's steps "cancelled" — neither has run yet.
                    if await _cancel_requested(site_db, workspace_id):
                        if on_step:
                            await on_step(f"site-{site.id}-products", "cancelled")
                            await on_step(f"site-{site.id}-match", "cancelled")
                        return

                    try:
                        await run_site_product_discovery(site_db, workspace_id, site)
                        if on_step:
                            await on_step(f"site-{site.id}-products", "done")
                    except ai_client.NoActiveProviderError:
                        if on_step:
                            await on_step(f"site-{site.id}-products", "error")
                        return  # provider was deactivated mid-run — matching would fail identically
                    except Exception:
                        logger.exception(
                            "pre-report discovery refresh failed for site %s, workspace %s", site.id, workspace_id
                        )
                        if on_step:
                            await on_step(f"site-{site.id}-products", "error")
                        # Deliberately still fall through to auto-match below: a
                        # fresh discovery call failing doesn't invalidate whatever
                        # CompetitorProducts this site already has from earlier
                        # runs — matching against the existing catalog is still
                        # worthwhile.

                    # A second checkpoint between the two AI calls: the
                    # products call above can take a while, long enough for
                    # cancellation to arrive mid-site — the match call is
                    # still skippable even though products already ran.
                    if await _cancel_requested(site_db, workspace_id):
                        if on_step:
                            await on_step(f"site-{site.id}-match", "cancelled")
                        return

                    try:
                        await run_site_auto_match(
                            site_db, workspace_id, site, auto_confirm_threshold=auto_confirm_threshold
                        )
                        if on_step:
                            await on_step(f"site-{site.id}-match", "done")
                    except ai_client.NoActiveProviderError:
                        if on_step:
                            await on_step(f"site-{site.id}-match", "error")
                    except (NoCompetitorProductsError, EmptyCatalogError):
                        if on_step:
                            await on_step(f"site-{site.id}-match", "error")
                    except Exception:
                        logger.exception(
                            "pre-report match refresh failed for site %s, workspace %s", site.id, workspace_id
                        )
                        if on_step:
                            await on_step(f"site-{site.id}-match", "error")
            except Exception:
                # Belt-and-suspenders: an unexpected failure outside the two
                # blocks above (session checkout, the site_db.get() lookup
                # itself) must still not raise — asyncio.gather below doesn't
                # cancel sibling tasks on one task's exception, so a raise
                # here could leave this task's steps stuck "pending" while
                # other sites keep running and the pipeline is later marked
                # failed/completed out from under it.
                logger.exception(
                    "site refresh task failed unexpectedly for site %s, workspace %s", site_id, workspace_id
                )
                if on_step:
                    try:
                        await on_step(f"site-{site_id}-products", "error")
                        await on_step(f"site-{site_id}-match", "error")
                    except Exception:
                        logger.exception("failed to mark error substep for site %s after task failure", site_id)

    await asyncio.gather(*(_process_site(site.id) for site in sites))
