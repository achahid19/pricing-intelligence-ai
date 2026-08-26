"""
Tool definitions + executors for the agentic chat assistant. Read tools
(get_workspace_summary, list_catalog_products, list_saved_competitor_sites)
execute inline, inside ai_client.run_assistant_turn's own loop — see this
module's send_message(). Write tools are never executed there: a write-tool
call comes back as a proposal, gets validated + given a human-readable
`display` here, persisted as AssistantToolCall(status="proposed"), and only
actually runs once a human approves it via approve_tool_call() below — the
"AI proposes, human approves" boundary this whole module exists to enforce
(see AssistantToolCall's docstring).

Every write tool's validator AND executor re-applies the exact cooldown/
guard its human-triggered HTTP twin already enforces (DISCOVERY_COOLDOWN_
SECONDS, a site's last_auto_match_at, REPORT_COOLDOWN_SECONDS + pipeline_
status=="running") — imported directly from discovery/router.py and
reporting/router.py rather than redefined here, so the two can never
silently drift apart. Skipping this would make the assistant a silent
bypass of guards that exist specifically to protect real AI-provider cost.
"""
import logging
from datetime import datetime, timezone

from fastapi import BackgroundTasks, HTTPException, status
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.assistant.models import AssistantToolCall
from app.catalog import service as catalog_service
from app.catalog.models import Product
from app.catalog.schemas import ProductCreate
from app.discovery import service as discovery_service
from app.discovery.models import CompetitorSite, DiscoveryRun, ProductMatch
from app.discovery.router import DISCOVERY_COOLDOWN_SECONDS
from app.reporting import service as reporting_service
from app.reporting.router import REPORT_COOLDOWN_SECONDS
from app.services import ai_client
from app.services.cooldown import check_cooldown
from app.workspace.models import Workspace
from app.workspace.schemas import WorkspaceContextUpdate

logger = logging.getLogger(__name__)

READ_TOOL_NAMES = {"get_workspace_summary", "list_catalog_products", "list_saved_competitor_sites"}


class ToolValidationError(Exception):
    """Raised when a proposed write tool's arguments fail validation —
    malformed (wrong type/shape) or referentially invalid (a site_id that
    doesn't belong to this workspace, a cooldown still active, a pipeline
    already running). Caught by send_message() to drive one bounded
    self-correction retry before giving up and replying in plain text
    instead of ever showing a proposal card for something that can't
    actually run. Also caught by approve_tool_call() for the same
    condition re-checked at approve time (state may have changed since
    propose) — there it marks the row "failed" with this message rather
    than raising, since approval always resolves the row one way or
    another, never a silent no-op or a raw HTTP error."""


def _pydantic_error_summary(exc: PydanticValidationError) -> str:
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"]) or "value"
    return f"{field}: {first['msg']}"


# ── Tool schemas (canonical, provider-agnostic — see ai_client.run_assistant_turn) ──
#
# Every optional field is still listed in "required" with a nullable type
# ("type": [..., "null"]) — OpenAI's strict function-calling mode demands
# every property be required (nullable is how you spell "optional" under
# strict mode); Anthropic/Google tolerate the same schema fine, and this
# app's argument readers all use dict.get() with a None fallback regardless
# of what a given provider actually sends.

_TOOL_DEFS: list[dict] = [
    {
        "name": "get_workspace_summary",
        "description": (
            "Get a snapshot of this workspace: business context, catalog size, saved competitor/"
            "reseller counts, confirmed match count, latest report, and current pipeline status. "
            "Call this first for any question about the workspace's current state."
        ),
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "list_catalog_products",
        "description": "List the workspace's own catalog products, optionally filtered by name.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": ["string", "null"],
                    "description": "Case-insensitive substring to filter product names by. Null to list all (capped at 50).",
                }
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_saved_competitor_sites",
        "description": (
            "List the workspace's saved competitor/reseller sites, with their id, domain, name, and "
            "relationship type. Use this to resolve a business name the user mentions to a site_id "
            "before calling auto_match_site."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "relationship_type": {
                    "type": ["string", "null"],
                    "enum": ["competitor", "reseller", None],
                    "description": "Filter to only this relationship type, or null for all saved sites.",
                }
            },
            "required": ["relationship_type"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_product",
        "description": "Propose adding a new product to the workspace's own catalog. Requires human approval before it's created.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Product name."},
                "price": {"type": "number", "description": "Selling price, a positive number."},
                "currency": {"type": ["string", "null"], "description": "3-letter currency code, e.g. USD. Null defaults to USD."},
                "description": {"type": ["string", "null"], "description": "A short factual description, or null."},
                "category": {"type": ["string", "null"], "description": "Product category, or null."},
                "brand": {"type": ["string", "null"], "description": "Brand name, or null."},
                "min_price": {
                    "type": ["number", "null"],
                    "description": "Minimum advertised price / MAP floor, only if the user specified one, else null.",
                },
            },
            "required": ["name", "price", "currency", "description", "category", "brand", "min_price"],
            "additionalProperties": False,
        },
    },
    {
        "name": "run_competitor_discovery",
        "description": (
            "Propose a web search for new competitor businesses, using the workspace's own business "
            "context. Costs a real AI provider call. Requires human approval before it runs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "max_candidates": {
                    "type": ["integer", "null"],
                    "description": "Max number of competitor candidates to search for, 1-20. Null defaults to 10.",
                }
            },
            "required": ["max_candidates"],
            "additionalProperties": False,
        },
    },
    {
        "name": "auto_match_site",
        "description": (
            "Propose matching a saved competitor site's discovered products against the workspace's own "
            "catalog. Look up the site_id with list_saved_competitor_sites first — never guess it. "
            "Costs a real AI provider call. Requires human approval before it runs."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "site_id": {"type": "integer", "description": "The id of a saved competitor site, from list_saved_competitor_sites."}
            },
            "required": ["site_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "generate_report",
        "description": (
            "Propose running the full discover -> match -> report pipeline to generate a new competitor "
            "pricing report now. Costs real AI provider calls and can take minutes. Requires human "
            "approval before it runs."
        ),
        "parameters": {"type": "object", "properties": {}, "required": [], "additionalProperties": False},
    },
    {
        "name": "update_business_context",
        "description": (
            "Propose a change to the workspace's own business context (objectives, country, market/"
            "industry, website, or report frequency). Only include fields actually being changed — "
            "pass null for every field you are not changing, never a guess. Requires human approval."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "objectives_selected": {
                    "type": ["array", "null"],
                    "items": {"type": "string"},
                    "description": "New full list of objectives (market_research, price_alignment, map_compliance), or null.",
                },
                "objectives_note": {"type": ["string", "null"], "description": "New free-text objectives note, or null."},
                "country": {"type": ["string", "null"], "description": "New country, or null."},
                "market": {"type": ["string", "null"], "description": "New market/industry, or null."},
                "website": {"type": ["string", "null"], "description": "New business website, or null."},
                "report_interval_hours": {
                    "type": ["integer", "null"],
                    "description": "New scheduled report interval in hours (1-168), or null to leave unchanged.",
                },
            },
            "required": ["objectives_selected", "objectives_note", "country", "market", "website", "report_interval_hours"],
            "additionalProperties": False,
        },
    },
]

_CONTEXT_UPDATE_FIELDS = ("objectives_selected", "objectives_note", "country", "market", "website", "report_interval_hours")


# ── Read tool executors ──────────────────────────────────────────────────────


async def _tool_get_workspace_summary(db: AsyncSession, workspace: Workspace) -> dict:
    from sqlalchemy import func

    product_count = await db.scalar(select(func.count(Product.id)).where(Product.workspace_id == workspace.id))
    competitor_count = await db.scalar(
        select(func.count(CompetitorSite.id)).where(
            CompetitorSite.workspace_id == workspace.id,
            CompetitorSite.relationship_type == "competitor",
            CompetitorSite.status == "saved",
        )
    )
    reseller_count = await db.scalar(
        select(func.count(CompetitorSite.id)).where(
            CompetitorSite.workspace_id == workspace.id,
            CompetitorSite.relationship_type == "reseller",
            CompetitorSite.status == "saved",
        )
    )
    candidate_count = await db.scalar(
        select(func.count(CompetitorSite.id)).where(
            CompetitorSite.workspace_id == workspace.id, CompetitorSite.status == "candidate"
        )
    )
    confirmed_match_count = await db.scalar(
        select(func.count(ProductMatch.id)).where(
            ProductMatch.workspace_id == workspace.id, ProductMatch.status == "confirmed"
        )
    )
    latest_report = await reporting_service.get_previous_report(db, workspace.id)
    return {
        "workspace_name": workspace.name,
        "objectives": workspace.objectives_selected or [],
        "country": workspace.country,
        "market": workspace.market,
        "website": workspace.website,
        "catalog_product_count": product_count or 0,
        "saved_competitor_count": competitor_count or 0,
        "saved_reseller_count": reseller_count or 0,
        "pending_candidate_sites_count": candidate_count or 0,
        "confirmed_match_count": confirmed_match_count or 0,
        "latest_report": (
            {"id": latest_report.id, "generated_at": latest_report.generated_at.isoformat(), "status": latest_report.status}
            if latest_report
            else None
        ),
        "pipeline_status": workspace.pipeline_status,
    }


_LIST_PRODUCTS_LIMIT = 50


async def _tool_list_catalog_products(db: AsyncSession, workspace: Workspace, args: dict) -> dict:
    query = select(Product).where(Product.workspace_id == workspace.id)
    q = (args.get("query") or "").strip()
    if q:
        query = query.where(Product.name.ilike(f"%{q}%"))
    result = await db.execute(query.order_by(Product.name).limit(_LIST_PRODUCTS_LIMIT))
    products = result.scalars().all()
    return {
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "price": float(p.price) if p.price is not None else None,
                "currency": p.currency,
                "category": p.category,
                "brand": p.brand,
            }
            for p in products
        ],
        "shown": len(products),
        "capped": len(products) == _LIST_PRODUCTS_LIMIT,
    }


async def _tool_list_saved_competitor_sites(db: AsyncSession, workspace: Workspace, args: dict) -> dict:
    query = select(CompetitorSite).where(CompetitorSite.workspace_id == workspace.id, CompetitorSite.status == "saved")
    relationship_type = args.get("relationship_type")
    if relationship_type:
        query = query.where(CompetitorSite.relationship_type == relationship_type)
    result = await db.execute(query.order_by(CompetitorSite.domain))
    sites = result.scalars().all()
    return {
        "sites": [
            {
                "id": s.id,
                "domain": s.domain,
                "name": s.name,
                "relationship_type": s.relationship_type,
                "last_auto_match_at": s.last_auto_match_at.isoformat() if s.last_auto_match_at else None,
            }
            for s in sites
        ]
    }


def _make_read_tool_executor(db: AsyncSession, workspace: Workspace):
    async def _execute(name: str, args: dict) -> dict:
        if name == "get_workspace_summary":
            return await _tool_get_workspace_summary(db, workspace)
        if name == "list_catalog_products":
            return await _tool_list_catalog_products(db, workspace, args)
        if name == "list_saved_competitor_sites":
            return await _tool_list_saved_competitor_sites(db, workspace, args)
        return {"error": f"Unknown read tool: {name}"}

    return _execute


# ── Write tool validators (propose time) — build the human-readable `display` ──


async def _validate_create_product(db: AsyncSession, workspace: Workspace, args: dict) -> dict:
    try:
        payload = ProductCreate(
            name=args.get("name"),
            price=args.get("price"),
            currency=args.get("currency") or "USD",
            min_price=args.get("min_price"),
            description=args.get("description"),
            category=args.get("category"),
            brand=args.get("brand"),
        )
    except PydanticValidationError as exc:
        raise ToolValidationError(_pydantic_error_summary(exc)) from exc
    display = {"Product": payload.name, "Price": f"{payload.currency} {payload.price}"}
    if payload.category:
        display["Category"] = payload.category
    return display


async def _check_discovery_cooldown(db: AsyncSession, workspace: Workspace) -> None:
    last_run_result = await db.execute(
        select(DiscoveryRun.triggered_at)
        .where(DiscoveryRun.workspace_id == workspace.id, DiscoveryRun.mode == "competitor")
        .order_by(DiscoveryRun.triggered_at.desc())
        .limit(1)
    )
    try:
        check_cooldown(last_run_result.scalars().first(), DISCOVERY_COOLDOWN_SECONDS)
    except HTTPException as exc:
        raise ToolValidationError(str(exc.detail)) from exc


async def _validate_run_competitor_discovery(db: AsyncSession, workspace: Workspace, args: dict) -> dict:
    try:
        max_candidates = int(args.get("max_candidates") or 10)
    except (TypeError, ValueError):
        raise ToolValidationError("max_candidates must be a whole number.")
    max_candidates = max(1, min(20, max_candidates))
    await _check_discovery_cooldown(db, workspace)
    return {"Action": "Search the web for new competitor businesses", "Max candidates": max_candidates}


async def _get_owned_saved_site(db: AsyncSession, workspace: Workspace, args: dict) -> CompetitorSite:
    try:
        site_id = int(args.get("site_id"))
    except (TypeError, ValueError):
        raise ToolValidationError("site_id must be the numeric id of a saved competitor site.")
    result = await db.execute(select(CompetitorSite).where(CompetitorSite.id == site_id, CompetitorSite.workspace_id == workspace.id))
    site = result.scalars().first()
    if site is None:
        raise ToolValidationError(f"No saved competitor site with id {site_id} was found. Look it up with list_saved_competitor_sites first.")
    if site.status != "saved":
        raise ToolValidationError("That site hasn't been saved yet, it can't be auto-matched until it is.")
    return site


async def _validate_auto_match_site(db: AsyncSession, workspace: Workspace, args: dict) -> dict:
    site = await _get_owned_saved_site(db, workspace, args)
    try:
        check_cooldown(site.last_auto_match_at, DISCOVERY_COOLDOWN_SECONDS)
    except HTTPException as exc:
        raise ToolValidationError(str(exc.detail)) from exc
    return {"Competitor": site.name or site.domain, "Domain": site.domain}


async def _check_report_guards(db: AsyncSession, workspace: Workspace) -> None:
    last_report = await reporting_service.get_previous_report(db, workspace.id)
    try:
        check_cooldown(last_report.generated_at if last_report else None, REPORT_COOLDOWN_SECONDS)
    except HTTPException as exc:
        raise ToolValidationError(str(exc.detail)) from exc
    if workspace.pipeline_status == "running":
        raise ToolValidationError("A report is already being generated for this workspace. Check Activity for progress.")


async def _validate_generate_report(db: AsyncSession, workspace: Workspace, args: dict) -> dict:
    await _check_report_guards(db, workspace)
    return {"Action": "Run the full discover → match → report pipeline and generate a new report"}


def _context_changes(args: dict) -> dict:
    return {k: v for k, v in args.items() if k in _CONTEXT_UPDATE_FIELDS and v is not None}


async def _validate_update_business_context(db: AsyncSession, workspace: Workspace, args: dict) -> dict:
    changes = _context_changes(args)
    if not changes:
        raise ToolValidationError("No fields to change were given. Pass at least one non-null field.")
    try:
        WorkspaceContextUpdate(**changes)
    except PydanticValidationError as exc:
        raise ToolValidationError(_pydantic_error_summary(exc)) from exc
    return {k.replace("_", " ").title(): v for k, v in changes.items()}


_VALIDATORS = {
    "create_product": _validate_create_product,
    "run_competitor_discovery": _validate_run_competitor_discovery,
    "auto_match_site": _validate_auto_match_site,
    "generate_report": _validate_generate_report,
    "update_business_context": _validate_update_business_context,
}


# ── Write tool executors (approve time) — re-validate referentially, then act ──


async def _execute_create_product(db: AsyncSession, background_tasks: BackgroundTasks, workspace: Workspace, args: dict) -> dict:
    try:
        payload = ProductCreate(
            name=args.get("name"),
            price=args.get("price"),
            currency=args.get("currency") or "USD",
            min_price=args.get("min_price"),
            description=args.get("description"),
            category=args.get("category"),
            brand=args.get("brand"),
        )
    except PydanticValidationError as exc:
        raise ToolValidationError(_pydantic_error_summary(exc)) from exc
    product = await catalog_service.create_product(db, background_tasks, workspace, payload)
    return {"product_id": product.id, "name": product.name}


async def _execute_run_competitor_discovery(db: AsyncSession, background_tasks: BackgroundTasks, workspace: Workspace, args: dict) -> dict:
    await _check_discovery_cooldown(db, workspace)
    max_candidates = max(1, min(20, int(args.get("max_candidates") or 10)))
    run, search_count, _skipped = await discovery_service.run_site_discovery(db, workspace, "competitor", max_candidates=max_candidates)
    return {"discovery_run_id": run.id, "sites_found": len(run.sites), "search_count": search_count}


async def _execute_auto_match_site(db: AsyncSession, background_tasks: BackgroundTasks, workspace: Workspace, args: dict) -> dict:
    site = await _get_owned_saved_site(db, workspace, args)
    try:
        check_cooldown(site.last_auto_match_at, DISCOVERY_COOLDOWN_SECONDS)
    except HTTPException as exc:
        raise ToolValidationError(str(exc.detail)) from exc
    matches = await discovery_service.run_site_auto_match(db, workspace.id, site)
    return {"site_id": site.id, "matches_proposed": len(matches)}


async def _execute_generate_report(db: AsyncSession, background_tasks: BackgroundTasks, workspace: Workspace, args: dict) -> dict:
    await _check_report_guards(db, workspace)
    background_tasks.add_task(reporting_service.run_full_pipeline_background, workspace.id, "manual")
    return {"status": "started", "note": "Check Activity for progress."}


async def _execute_update_business_context(db: AsyncSession, background_tasks: BackgroundTasks, workspace: Workspace, args: dict) -> dict:
    changes = _context_changes(args)
    try:
        payload = WorkspaceContextUpdate(**changes)
    except PydanticValidationError as exc:
        raise ToolValidationError(_pydantic_error_summary(exc)) from exc
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(workspace, field, value)
    await db.commit()
    await db.refresh(workspace)
    return {"changed_fields": list(changes.keys())}


_EXECUTORS = {
    "create_product": _execute_create_product,
    "run_competitor_discovery": _execute_run_competitor_discovery,
    "auto_match_site": _execute_auto_match_site,
    "generate_report": _execute_generate_report,
    "update_business_context": _execute_update_business_context,
}


# ── Entry points used by assistant/router.py ────────────────────────────────


async def _propose_with_retry(
    db: AsyncSession, workspace: Workspace, messages: list[dict], execute_read, result: dict, retried: bool = False
) -> dict:
    """A proposed write tool whose arguments fail validation is never shown
    as a card — instead, ONE extra provider round-trip is attempted with a
    synthetic correction turn appended (not a hidden native tool-result
    turn — a plain client-visible message, kept simple deliberately),
    giving the model exactly one bounded chance to self-correct before
    falling back to a plain-text explanation."""
    validator = _VALIDATORS[result["tool_name"]]
    try:
        display = await validator(db, workspace, result["tool_arguments"])
    except ToolValidationError as exc:
        if retried:
            return {"type": "message", "text": f"I couldn't do that: {exc}"}
        repair_messages = messages + [
            {"role": "assistant", "content": f"(attempted to use {result['tool_name']})"},
            {
                "role": "user",
                "content": f"That didn't work: {exc}. Please try again with corrected details, or explain in plain text if you can't.",
            },
        ]
        retry = await ai_client.run_assistant_turn(
            db, workspace.id, repair_messages, _TOOL_DEFS, READ_TOOL_NAMES, execute_read
        )
        if retry["type"] != "tool_call":
            return retry
        return await _propose_with_retry(db, workspace, repair_messages, execute_read, retry, retried=True)
    result["display"] = display
    return result


async def send_message(db: AsyncSession, workspace: Workspace, messages: list[dict]) -> dict:
    execute_read = _make_read_tool_executor(db, workspace)
    result = await ai_client.run_assistant_turn(db, workspace.id, messages, _TOOL_DEFS, READ_TOOL_NAMES, execute_read)
    if result["type"] == "tool_call":
        result = await _propose_with_retry(db, workspace, messages, execute_read, result)
    if result["type"] == "message":
        return {"type": "message", "text": result["text"]}

    call = AssistantToolCall(
        workspace_id=workspace.id,
        tool_name=result["tool_name"],
        arguments=result["tool_arguments"],
        display=result["display"],
        status="proposed",
        ai_provider=result["ai_provider"],
        model=result["model"],
        tier=result["tier"],
    )
    db.add(call)
    await db.commit()
    await db.refresh(call)
    return {"type": "tool_proposal", "call_id": call.id, "tool_name": call.tool_name, "display": call.display, "tier": call.tier}


async def _get_owned_call(db: AsyncSession, call_id: int, workspace_id: int) -> AssistantToolCall:
    result = await db.execute(
        select(AssistantToolCall).where(AssistantToolCall.id == call_id, AssistantToolCall.workspace_id == workspace_id)
    )
    call = result.scalars().first()
    if call is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tool call not found")
    return call


async def dismiss_tool_call(db: AsyncSession, workspace: Workspace, call_id: int) -> AssistantToolCall:
    call = await _get_owned_call(db, call_id, workspace.id)
    if call.status != "proposed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This proposal has already been resolved.")
    call.status = "dismissed"
    await db.commit()
    await db.refresh(call)
    return call


async def approve_tool_call(
    db: AsyncSession, background_tasks: BackgroundTasks, workspace: Workspace, call_id: int
) -> AssistantToolCall:
    """Executes ONLY using `call.arguments` already stored at propose
    time — this function's signature takes no arguments payload at all,
    which is the actual security guarantee (see AssistantToolCall's
    docstring): there is no channel for a tampered request to substitute
    different arguments than what was actually proposed and shown to the
    user."""
    call = await _get_owned_call(db, call_id, workspace.id)
    if call.status != "proposed":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="This proposal has already been resolved.")

    executor = _EXECUTORS.get(call.tool_name)
    try:
        if executor is None:
            raise ToolValidationError(f"Unknown tool: {call.tool_name}")
        result_summary = await executor(db, background_tasks, workspace, call.arguments)
    except ToolValidationError as exc:
        call.status = "failed"
        call.error_message = str(exc)
    except Exception as exc:
        logger.exception("assistant tool call %s (%s) failed for workspace %s", call.id, call.tool_name, workspace.id)
        call.status = "failed"
        call.error_message = str(exc)[:2000]
    else:
        call.status = "executed"
        call.result_summary = result_summary
        call.executed_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(call)
    return call
