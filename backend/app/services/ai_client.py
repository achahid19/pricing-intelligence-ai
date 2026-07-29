"""
Provider-flexible AI dispatcher — one call contract regardless of which
provider (OpenAI, Google, or Anthropic) a workspace has configured. Callers
never branch on provider; see docs/DECISIONS.md for why (billing follows
the tenant, and a workspace can switch providers without touching call
sites). Same idea as ai_crafters_pfa's ai_client.py, reimplemented per
workspace instead of a single global setting.
"""
import base64
import json
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.model_catalog import default_model_for
from app.workspace.encryption import decrypt_key
from app.workspace.models import AiProviderConfig

_DESCRIBE_PROMPT = (
    "You're looking at a photo of a single product being entered into a market-research "
    "product catalog — not a sales listing. Respond with ONLY a JSON object, no markdown "
    "fences, no commentary: "
    '{"title": "<a concise, specific product title, under 80 characters>", '
    '"description": "<a factual, neutral 1-3 sentence description of what the product actually '
    'is — its type, materials or components, and function — written so someone can identify '
    'and research it later, not to sell it. No marketing language (\\"stylish\\", \\"premium\\", '
    '\\"perfect for\\", etc.)>", '
    '"category": "<a concise product category, e.g. \'Home & Garden\', \'Electronics\', '
    '\'Apparel\' — or null if you genuinely can\'t tell>"}'
)


class NoActiveProviderError(Exception):
    """Raised when a workspace has no active AiProviderConfig configured."""


async def _get_active_config(db: AsyncSession, workspace_id: int) -> AiProviderConfig:
    result = await db.execute(
        select(AiProviderConfig).where(
            AiProviderConfig.workspace_id == workspace_id,
            AiProviderConfig.is_active.is_(True),
        )
    )
    config = result.scalars().first()
    if config is None:
        raise NoActiveProviderError(
            "No active AI provider configured for this workspace. Set one up in Settings first."
        )
    return config


def _extract_json(text: str) -> dict:
    """Models sometimes wrap JSON replies in markdown code fences — strip those before parsing."""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def _extract_json_object(text: str) -> dict:
    """More lenient than _extract_json: web-search-enabled responses are more
    likely to include a sentence of preamble ("Based on my research...")
    before the JSON, even when explicitly told not to. Finds the outermost
    {...} block rather than assuming the whole string is valid JSON on its
    own."""
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in response")
    return json.loads(text[start : end + 1])


async def describe_product_image(
    db: AsyncSession, workspace_id: int, image_bytes: bytes, content_type: str
) -> dict:
    """Ask the workspace's active AI provider for a title + description of a
    single product photo. Raises NoActiveProviderError if none configured."""
    config = await _get_active_config(db, workspace_id)
    api_key = decrypt_key(config.encrypted_api_key)
    model = config.model_override or default_model_for(config.provider)
    b64 = base64.b64encode(image_bytes).decode()

    if config.provider == "openai":
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _DESCRIBE_PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{b64}"}},
                    ],
                }
            ],
        )
        return _extract_json(resp.choices[0].message.content)

    if config.provider == "anthropic":
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=model,
            max_tokens=500,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": b64}},
                        {"type": "text", "text": _DESCRIBE_PROMPT},
                    ],
                }
            ],
        )
        return _extract_json(resp.content[0].text)

    if config.provider == "google":
        from google import genai
        from google.genai import types

        # Unlike the OpenAI/Anthropic SDKs (which retry transient failures
        # twice by default), google-genai does NOT retry at all unless
        # retry_options is explicitly set — without this, one 429/5xx/
        # timeout fails the whole call.
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=3)),
        )
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[
                _DESCRIBE_PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type=content_type),
            ],
        )
        return _extract_json(resp.text)

    raise ValueError(f"Unknown provider: {config.provider}")


_DISCOVER_PROMPT_TEMPLATE = (
    "You are researching real, currently-operating competitor BUSINESSES using web search — "
    "not guessing from memory or training data. Use your web search tool to find actual companies.\n\n"
    "Business context:\n{context}\n\n"
    "Search the web and identify up to {max_candidates} real competitor businesses: companies "
    "that own and sell their own competing product or service to the same customer base — "
    "weigh the specific products and their descriptions above more heavily than the category "
    "labels or industry name alone, since two businesses in the same industry can target very "
    "different customers.\n\n"
    "CRITICAL — exclude anyone who is not a true business-model rival: do NOT include "
    "resellers, retailers, marketplaces, distributors, affiliates, or price-comparison sites "
    "that merely sell or list many different companies' products (even in the same category, "
    "even if that includes this business's own products) rather than operating their own "
    "distinct, competing product or brand. A real competitor is another company with its own "
    "rival offering — for example, if this business made and sold a soft drink, a real "
    "competitor is another soft-drink maker with its own rival brand (e.g. a competing cola or "
    "soda), NOT a supermarket, convenience store, or online retailer that simply stocks many "
    "brands including this one. If you're unsure whether a candidate operates its own "
    "competing offering or is just reselling/distributing others', leave it out rather than "
    "guessing. Do not include this business's own website as a candidate. For each candidate "
    "you do include, base your confidence on what you actually found, not assumptions, and "
    "explicitly confirm in the rationale that they sell their own product/brand, not someone "
    "else's.\n\n"
    "Respond with ONLY a JSON object, no markdown fences, no commentary before or after: "
    '{{"candidates": [{{"domain": "<bare domain, e.g. example.com, no scheme or path>", '
    '"name": "<company name>", '
    '"confidence": <integer 0-100, how well this is actually a competitor based on what you found>, '
    '"rationale": "<1-2 sentences explaining the match AND confirming this is their own '
    'product/brand, not a reseller/retailer/marketplace, citing specific products/categories or '
    'price positioning you compared, not just \\"same industry\\">", '
    '"estimated_product_count": <integer estimate if you can tell from what you found, else null>}}]}}'
)


_MAX_SAMPLE_PRODUCTS = 15
_MAX_DESCRIPTION_CHARS = 300


def _render_business_context(workspace) -> list[str]:
    """The objectives/country/market/website block only — shared by
    build_discovery_context (which appends a catalog sample on top) and
    generate_report_narrative (which doesn't need one: the report's own
    price-comparison table already tells the AI what's sold and at what
    price, in more relevant detail than a generic catalog sample)."""
    lines = []
    if workspace.objectives_selected:
        lines.append(f"Objectives: {', '.join(workspace.objectives_selected)}")
    if workspace.objectives_note:
        lines.append(f"Additional context from the business owner: {workspace.objectives_note}")
    if workspace.country:
        lines.append(f"Country: {workspace.country}")
    if workspace.market:
        lines.append(f"Industry/market: {workspace.market}")
    if workspace.website:
        lines.append(f"Business website: {workspace.website}")
    return lines


def build_discovery_context(workspace, products: list) -> str:
    """Renders a workspace's business context + catalog summary into the
    text block sent to discover_competitor_sites(). Deliberately a bounded
    sample with descriptions, not the full catalog — enough for the AI to
    understand what's actually sold, not just names or category labels,
    without letting prompt size grow with catalog size."""
    lines = _render_business_context(workspace)

    categories = sorted({p.category for p in products if p.category})
    if categories:
        lines.append(f"Product categories sold: {', '.join(categories)}")

    prices = [float(p.price) for p in products]
    if prices:
        lines.append(f"Price range: {min(prices):.2f}-{max(prices):.2f} {products[0].currency}")

    # One product per category first, so every category the business
    # sells is actually represented (not just whichever rows happened to
    # come back first from the DB), then fill remaining slots with other
    # products up to the cap.
    sample: list = []
    seen_categories: set = set()
    for p in products:
        if p.category and p.category not in seen_categories:
            sample.append(p)
            seen_categories.add(p.category)
    for p in products:
        if len(sample) >= _MAX_SAMPLE_PRODUCTS:
            break
        if p not in sample:
            sample.append(p)

    if sample:
        lines.append("Representative products:")
        for p in sample:
            desc = (p.description or "").strip()
            if len(desc) > _MAX_DESCRIPTION_CHARS:
                desc = desc[:_MAX_DESCRIPTION_CHARS].rstrip() + "…"
            entry = f"- {p.name}"
            if p.category:
                entry += f" ({p.category})"
            if desc:
                entry += f": {desc}"
            lines.append(entry)

    return "\n".join(lines) if lines else "No business context provided yet."


async def _run_web_search_prompt(
    db: AsyncSession, workspace_id: int, prompt: str, max_results: int
) -> tuple[dict, Optional[int]]:
    """Shared per-provider native-web-search dispatch — the same call
    shape used by discover_competitor_sites(), discover_reseller_sites(),
    and discover_competitor_products(); only the prompt text differs
    between them, so the provider plumbing lives here once instead of
    being duplicated a third time. Returns (parsed_json, search_count) —
    search_count is a best-effort usage figure for the lightweight
    cost-transparency note, None where the provider's response doesn't
    expose one. Raises NoActiveProviderError if none configured."""
    config = await _get_active_config(db, workspace_id)
    api_key = decrypt_key(config.encrypted_api_key)
    model = config.model_override or default_model_for(config.provider)

    if config.provider == "openai":
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        resp = await client.responses.create(
            model=model,
            tools=[{"type": "web_search"}],
            input=prompt,
        )
        search_count = sum(1 for item in resp.output if getattr(item, "type", None) == "web_search_call")
        return _extract_json_object(resp.output_text), search_count or None

    if config.provider == "anthropic":
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_results}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        search_count = None
        server_tool_use = getattr(resp.usage, "server_tool_use", None)
        if server_tool_use is not None:
            search_count = getattr(server_tool_use, "web_search_requests", None)
        return _extract_json_object(text), search_count

    if config.provider == "google":
        from google import genai
        from google.genai import types

        # Unlike the OpenAI/Anthropic SDKs (which retry transient failures
        # twice by default), google-genai does NOT retry at all unless
        # retry_options is explicitly set — without this, one 429/5xx/
        # timeout fails the whole call.
        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=3)),
        )
        grounding_tool = types.Tool(google_search=types.GoogleSearch())
        gen_config = types.GenerateContentConfig(tools=[grounding_tool])
        resp = await client.aio.models.generate_content(model=model, contents=[prompt], config=gen_config)
        search_count = None
        grounding_metadata = getattr(resp.candidates[0], "grounding_metadata", None) if resp.candidates else None
        if grounding_metadata is not None:
            queries = getattr(grounding_metadata, "web_search_queries", None)
            if queries is not None:
                search_count = len(queries)
        return _extract_json_object(resp.text), search_count

    raise ValueError(f"Unknown provider: {config.provider}")


async def discover_competitor_sites(
    db: AsyncSession, workspace_id: int, business_context: str, max_candidates: int = 10
) -> tuple[dict, Optional[int]]:
    """Ask the workspace's active AI provider to research and propose
    competitor businesses via its native web search tool. See
    _run_web_search_prompt for the (parsed_json, search_count) return
    shape and NoActiveProviderError behavior."""
    prompt = _DISCOVER_PROMPT_TEMPLATE.format(context=business_context, max_candidates=max_candidates)
    return await _run_web_search_prompt(db, workspace_id, prompt, max_candidates)


_DISCOVER_RESELLERS_PROMPT_TEMPLATE = (
    "You are researching real businesses that resell, distribute, or advertise this "
    "business's own products — not rival companies with their own competing brand — using "
    "web search, not guessing from memory or training data. This is for MAP (minimum "
    "advertised price) compliance monitoring: finding resellers, retailers, distributors, "
    "marketplaces, or affiliate sites that list or sell this business's actual products, so "
    "their advertised prices can later be checked against this business's own MAP policy.\n\n"
    "Business context:\n{context}\n\n"
    "Search the web and identify up to {max_candidates} real businesses that currently "
    "advertise or sell THIS business's own products — e.g. an authorized reseller, "
    "distributor, marketplace listing, or third-party retailer actually carrying this "
    "business's product line. Marketplaces and large retailers are exactly what you're "
    "looking for here, unlike a search for rival competitors. Do NOT include other companies "
    "selling their OWN competing brand or products instead of this business's — that is a "
    "different kind of research, not what is needed here. Do not include this business's own "
    "website. For each one, base your confidence on concrete evidence you actually found (for "
    "example, this business's specific product listed on their site), not assumptions — if "
    "you cannot find real evidence they carry this business's own products, leave them out "
    "rather than guessing.\n\n"
    "Respond with ONLY a JSON object, no markdown fences, no commentary before or after: "
    '{{"candidates": [{{"domain": "<bare domain, e.g. example.com, no scheme or path>", '
    '"name": "<company name>", '
    '"confidence": <integer 0-100, how confident you are this reseller genuinely carries the '
    'business\'s own products, based on what you found>, '
    '"rationale": "<1-2 sentences citing the specific evidence you found that they resell or '
    'advertise the business\'s own products>", '
    '"estimated_product_count": <integer estimate if you can tell from what you found, else null>}}]}}'
)


async def discover_reseller_sites(
    db: AsyncSession, workspace_id: int, business_context: str, max_candidates: int = 10
) -> tuple[dict, Optional[int]]:
    """The inverse of discover_competitor_sites(): finds businesses that
    advertise/sell THIS workspace's own products (resellers, retailers,
    distributors, marketplaces) rather than rival businesses with their
    own competing brand. Needed for MAP-compliance monitoring — you can't
    check whether a reseller is advertising below your MAP floor until
    you've found the resellers, which is a fundamentally different search
    than finding your competitors. See _run_web_search_prompt for the
    return shape and NoActiveProviderError behavior."""
    prompt = _DISCOVER_RESELLERS_PROMPT_TEMPLATE.format(context=business_context, max_candidates=max_candidates)
    return await _run_web_search_prompt(db, workspace_id, prompt, max_candidates)


# Two different intros, same as the site-discovery templates above — a
# reseller site isn't a rival with its own catalog to browse generically,
# it's a channel carrying THIS business's own products, so the AI needs to
# be told that or it has no reason to focus on the relevant listings rather
# than the reseller's entire (often huge, unrelated) inventory.
_DISCOVER_PRODUCTS_INTRO = {
    "competitor": (
        "You are researching real products currently offered by {label}, a known competitor "
        "business, using web search — not guessing from memory or training data. Use your web "
        "search tool to actually browse this site's pricing, plans, and product/category pages "
        "in detail — not just the homepage or a single search snippet."
    ),
    "reseller": (
        "You are researching real listings for THIS business's own products on {label}'s site, "
        "using web search — not guessing from memory or training data. {label} is a reseller, "
        "retailer, distributor, or marketplace known to carry this business's own products (for "
        "MAP — minimum advertised price — compliance monitoring), not a rival with its own "
        "competing brand. Focus specifically on listings for this business's own products, not "
        "the reseller's entire unrelated catalog. Use your web search tool to actually browse "
        "this site's relevant product and pricing pages in detail — not just the homepage or a "
        "single search snippet."
    ),
}


_DISCOVER_PRODUCTS_PROMPT_TEMPLATE = (
    "{intro}\n\n"
    "Search {domain} and identify up to {max_products} real, distinct products or plans "
    "currently offered. IMPORTANT: many business sites show several products, plans, or "
    "tiers on a single page (a pricing table with multiple plans, a category page listing "
    "several items) — when you find a page like that, extract EACH distinct product or plan "
    "as its own separate entry. Never collapse multiple offerings into one combined entry "
    "just because they appeared on the same page. Use the most specific URL available for "
    "each one (its own page if it has one, otherwise the listing/pricing page it came from).\n\n"
    "For each product, capture whatever you actually found on the page:\n"
    "- name and a factual 1-2 sentence description\n"
    "- price and currency, if shown\n"
    "- stock or availability, if the page indicates it (e.g. \"in stock\", \"sold out\", "
    "\"limited availability\", \"pre-order\") — null if the page doesn't show this\n"
    "- any other specifics worth noting (specs, capacity, contract length, included "
    "features, setup fees, etc.) as a short free-text note — null if there's nothing beyond "
    "the description\n\n"
    "Respond with ONLY a JSON object, no markdown fences, no commentary before or after: "
    '{{"products": [{{"title": "<product name>", '
    '"price": <numeric price only, no currency symbol, or null if you could not find one>, '
    '"currency": "<3-letter currency code if determinable, else null>", '
    '"url": "<the specific product page URL you found this on>", '
    '"description": "<a factual 1-2 sentence description>", '
    '"stock_status": "<a short availability note if the page shows one, else null>", '
    '"additional_info": "<other useful specifics actually found on the page, else null>"}}]}}'
)


async def discover_competitor_products(
    db: AsyncSession,
    workspace_id: int,
    domain: str,
    name: Optional[str],
    max_products: int = 15,
    relationship_type: str = "competitor",
) -> tuple[dict, Optional[int]]:
    """Ask the workspace's active AI provider to browse a specific saved
    competitor or reseller site (via its native web search tool) and list
    real products found there. relationship_type selects which intro frames
    the request — a reseller site needs to be told it's specifically
    carrying the workspace's own products (see _DISCOVER_PRODUCTS_INTRO),
    not treated like a rival's generic catalog. Same dispatch shape as
    discover_competitor_sites — reused deliberately rather than adding a
    per-provider fetch/url-context tool: none of the three providers render
    JavaScript anyway, so a dedicated fetch tool wouldn't close that gap.
    See _run_web_search_prompt for the return shape and
    NoActiveProviderError behavior."""
    label = f"{name} ({domain})" if name else domain
    intro_template = _DISCOVER_PRODUCTS_INTRO.get(relationship_type, _DISCOVER_PRODUCTS_INTRO["competitor"])
    prompt = _DISCOVER_PRODUCTS_PROMPT_TEMPLATE.format(
        intro=intro_template.format(label=label), domain=domain, max_products=max_products
    )
    return await _run_web_search_prompt(db, workspace_id, prompt, max_products)


_MATCH_PROMPT_TEMPLATE = (
    "You are matching a competitor's products against a business's own product catalog to "
    "find equivalent or directly comparable items for price comparison — not just same "
    "category, the same or a very similar item.\n\n"
    "The business's own products (indexed from 0):\n{own_products}\n\n"
    "The competitor's products (indexed from 0):\n{competitor_products}\n\n"
    "For each competitor product that has a clear equivalent among the business's own "
    "products, respond with a pairing. Skip competitor products with no reasonable match "
    "rather than forcing a weak one — it is fine to return fewer matches than competitor "
    "products, or none at all.\n\n"
    "Respond with ONLY a JSON object, no markdown fences, no commentary before or after: "
    '{{"matches": [{{"competitor_product_index": <int>, "product_index": <int>, '
    '"confidence": <integer 0-100, how confident this is genuinely the same/comparable item>, '
    '"rationale": "<1-2 sentences explaining why these are comparable>"}}]}}'
)

_MAX_MATCH_OWN_PRODUCTS = 300


def _format_products_for_matching(products: list, id_attr: str = "id") -> str:
    lines = []
    for i, p in enumerate(products):
        parts = [p.name if hasattr(p, "name") else p.title]
        if getattr(p, "category", None):
            parts.append(f"({p.category})")
        price = getattr(p, "price", None)
        if price is not None:
            currency = getattr(p, "currency", None) or ""
            parts.append(f"- {currency} {price}".strip())
        desc = (getattr(p, "description", None) or "").strip()
        if desc:
            if len(desc) > _MAX_DESCRIPTION_CHARS:
                desc = desc[:_MAX_DESCRIPTION_CHARS].rstrip() + "…"
            parts.append(f": {desc}")
        lines.append(f"{i}. " + " ".join(parts))
    return "\n".join(lines) if lines else "(none)"


async def match_products(
    db: AsyncSession, workspace_id: int, own_products: list, competitor_products: list
) -> tuple[dict, Optional[int]]:
    """Ask the workspace's active AI provider to propose matches between
    the workspace's own catalog and a competitor's discovered products.
    Unlike build_discovery_context's bounded representative sample, this
    sends the (near-)full own catalog — matching precision depends on
    seeing every candidate on your side, not just a representative slice —
    capped defensively at _MAX_MATCH_OWN_PRODUCTS as a safety bound, not a
    design target. No web search tool: this is pure reasoning over data
    already in hand, so it's a plain text call, not counted as a search.
    Returns (parsed_json, None) — no search_count for a non-search call.
    Raises NoActiveProviderError if none configured."""
    config = await _get_active_config(db, workspace_id)
    api_key = decrypt_key(config.encrypted_api_key)
    model = config.model_override or default_model_for(config.provider)
    prompt = _MATCH_PROMPT_TEMPLATE.format(
        own_products=_format_products_for_matching(own_products[:_MAX_MATCH_OWN_PRODUCTS]),
        competitor_products=_format_products_for_matching(competitor_products),
    )

    if config.provider == "openai":
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_json_object(resp.choices[0].message.content), None

    if config.provider == "anthropic":
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=model,
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return _extract_json_object(text), None

    if config.provider == "google":
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=3)),
        )
        resp = await client.aio.models.generate_content(model=model, contents=[prompt])
        return _extract_json_object(resp.text), None

    raise ValueError(f"Unknown provider: {config.provider}")


# Same "hard safety cap" reasoning as _MAX_MATCH_OWN_PRODUCTS — this many
# rows is already far more than any real report needs to make its point.
_MAX_NARRATIVE_ROWS = 200
_MAX_NARRATIVE_PRODUCT_GROUPS = 200
_MAX_NARRATIVE_COVERAGE_SITES = 30

_OBJECTIVE_GUIDANCE = {
    "market_research": (
        "landscape/positioning observations — how this business's pricing compares to the competitive set "
        "overall, notable gaps or clusters worth knowing about. If there are several genuinely distinct "
        "observations (e.g. a specific catalog gap AND a specific pricing-tier pattern), write one "
        "recommendation for each rather than merging them into one vague paragraph."
    ),
    "price_alignment": (
        "specific price-adjustment suggestions for individual products meaningfully out of line with tracked "
        "competitors, citing the product by name and the direction/magnitude. Every product that genuinely "
        "warrants attention gets its own recommendation — don't merge two different products into one."
    ),
    "map_compliance": (
        "concrete next steps for any reseller MAP violations found — which reseller to contact and about which "
        "product — or explicit confirmation there are none this period. Every distinct violation (different "
        "reseller or different product) gets its own recommendation, not one merged summary."
    ),
}

_REPORT_NARRATIVE_PROMPT_TEMPLATE = (
    "You are writing a periodic competitor-pricing report for a business, based ENTIRELY on already-computed, "
    "already-correct data below — you are not researching anything new and must not invent, alter, or "
    "second-guess any number in it. Your only job is to write prose sections about data that has already been "
    "decided for you.\n\n"
    "Business context:\n{business_context}\n\n"
    "{since_last_time}"
    "Price comparison + ranking metrics across every tracked (confirmed) competitor match, grouped by your own "
    "product ({group_count} of your products have at least one tracked match):\n"
    "{price_comparison_text}\n\n"
    "IMPORTANT — some rows are marked \"different currency, not directly comparable\" because this data has no "
    "currency conversion. For those rows, never describe one price as higher/lower/cheaper/pricier than the "
    "other, and never characterize the size of a gap between them. Only make a higher/lower/percentage claim "
    "about a pair when a percentage difference is explicitly given.\n\n"
    "IMPORTANT — reading price_index: a price_index of exactly 100 means priced at the tracked same-currency "
    "average; price_index MINUS 100 is the exact percentage above/below that average (e.g. 112.34 means about "
    "12% above average, 87 means about 13% below average). Never restate the index number itself as a "
    "percentage, and never compute or restate a ranking/index number for a product where none is given below.\n\n"
    "Market coverage — full discovered catalogs of every saved competitor, not just matched products "
    "(this is what lets you talk about assortment/whitespace, not only price):\n"
    "{market_coverage_text}\n\n"
    "IMPORTANT — a site marked \"reseller\" sells THIS BUSINESS'S OWN products, it is not a rival with its own "
    "product lineup. Its unmatched listings are a missed-match signal, not evidence of a competitor's "
    "assortment — never use reseller-type sites when writing about market coverage or competitive gaps. Only "
    "sites marked \"competitor\" represent a rival's own catalog.\n\n"
    "Alerts already flagged by the system (these are already decided facts — write about them, don't re-derive "
    "or second-guess them):\n{alerts_text}\n\n"
    "Write four things:\n"
    "1. executive_summary (2-4 sentences, plain and factual; if a previous report's summary is given, note the "
    "most important change(s) since then).\n"
    "2. market_position (3-5 sentences synthesizing the ranking metrics above — cite specific products by name "
    "with their real rank/index/sellers_cheaper numbers already given; if most or all products have no "
    "same-currency ranking data, say so plainly rather than inventing a comparison).\n"
    "3. competitive_gaps (3-5 sentences synthesizing the market-coverage data — catalog-size differences, and "
    "notable unmatched products by name from competitor-type sites only; if there are no saved competitor-type "
    "sites, say so plainly).\n"
    "4. recommendations, ONLY for these selected business objectives: {objectives_list}. Do NOT cap yourself at "
    "one recommendation per objective — a single objective can genuinely produce zero, one, or several "
    "recommendations depending on how much real, distinct signal is in the data above; write as many specific, "
    "well-crafted recommendations as the data actually supports, each citing real products/competitors/numbers "
    "from above, never a vague generality. For each objective:\n"
    "{guidance_lines}\n"
    "The hard rule cuts both ways: if there is nothing meaningful to say for a given objective, omit it rather "
    "than padding — never invent a second recommendation just to make the list look fuller, and never repeat "
    "the same point twice with different wording to inflate the count. A correct list of one is better than a "
    "padded list of three.\n\n"
    "Respond with ONLY a JSON object, no markdown fences, no commentary before or after: "
    '{{"executive_summary": "<2-4 sentences>", "market_position": "<3-5 sentences>", '
    '"competitive_gaps": "<3-5 sentences>", '
    '"recommendations": [{{"objective": "<one of: {objectives_list}>", '
    '"text": "<1-2 sentence, specific, actionable recommendation>"}}]}}'
)


def _format_comparison_groups_for_narrative(groups: list[dict]) -> str:
    lines = []
    for g in groups[:_MAX_NARRATIVE_PRODUCT_GROUPS]:
        own = f"{g['product_name']} (yours: {g['product_currency']} {g['product_price']:.2f}"
        if g["product_min_price"] is not None:
            own += f", MAP {g['product_min_price']:.2f}"
        own += ")"
        lines.append(f"- {own}")

        m = g["metrics"]
        if m["price_rank"] is not None:
            lines.append(
                f"  metrics: ranked #{m['price_rank']} of {m['same_currency_competitors_count'] + 1} tracked "
                f"sellers (same currency), price_index {m['price_index']}, {m['sellers_cheaper']} cheaper, "
                f"cheapest tracked competitor \"{m['cheapest_competitor_name']}\" at {m['cheapest_competitor_price']:.2f}"
            )
        else:
            lines.append("  metrics: no same-currency competitor price data available for ranking")

        for r in g["matches"]:
            competitor_label = r["competitor_site_name"] or r["competitor_site_domain"]
            if r["competitor_product_price"] is not None:
                comp = f'  vs {competitor_label}\'s "{r["competitor_product_title"]}" at {r["competitor_product_currency"]} {r["competitor_product_price"]:.2f}'
                if r["same_currency"] and r["price_delta_pct"] is not None:
                    comp += f" ({r['price_delta_pct']:+.1f}% vs yours)"
                elif not r["same_currency"]:
                    comp += " — different currency, not directly comparable"
            else:
                comp = f'  vs {competitor_label}\'s "{r["competitor_product_title"]}" (no price found)'
            lines.append(comp)
    return "\n".join(lines) if lines else "(no tracked matches yet)"


def _format_alerts_for_narrative(alerts: list[dict]) -> str:
    if not alerts:
        return "No alerts this period."
    return "\n".join(f"- [{a['type']}] {a['message']}" for a in alerts[:_MAX_NARRATIVE_ROWS])


def _format_market_coverage_for_narrative(coverage: dict) -> str:
    lines = [
        f"Your catalog: {coverage['own_catalog_size']} products "
        f"({coverage['own_products_with_confirmed_match']} with a tracked competitor match).",
        f"Total competitor products discovered across all saved sites: {coverage['total_competitor_products_discovered']}.",
        "",
    ]
    sites = coverage.get("sites", [])
    if not sites:
        lines.append("(no saved competitor or reseller sites yet)")
        return "\n".join(lines)

    for site in sites[:_MAX_NARRATIVE_COVERAGE_SITES]:
        label = site["competitor_site_name"] or site["competitor_site_domain"]
        line = (
            f"- {label} ({site['relationship_type']}): {site['total_products_discovered']} discovered, "
            f"{site['matched_products_count']} matched."
        )
        unmatched = site.get("unmatched_sample") or []
        if unmatched:
            sample_titles = ", ".join(f'"{p["title"]}"' for p in unmatched[:5])
            line += f" Not yet matched to anything in your catalog (sample): {sample_titles}."
        if site["relationship_type"] == "reseller":
            line += " (reseller — sells YOUR OWN products, not a rival's assortment.)"
        lines.append(line)
    return "\n".join(lines)


async def generate_report_narrative(
    db: AsyncSession,
    workspace_id: int,
    workspace,
    price_comparison: list[dict],
    alerts: list[dict],
    market_coverage: dict,
    previous_executive_summary: Optional[str] = None,
) -> dict:
    """Ask the workspace's active AI provider to write four prose sections
    OVER already-computed, already-correct data — reporting/service.py has
    already decided every number, metric, and alert; this call only ever
    produces prose about them (see CLAUDE.md's "AI narrates on top of
    deterministic data" rule). No web search — pure reasoning over data
    already in hand, same non-search dispatch shape as match_products().
    Raises NoActiveProviderError if none configured."""
    config = await _get_active_config(db, workspace_id)
    api_key = decrypt_key(config.encrypted_api_key)
    model = config.model_override or default_model_for(config.provider)

    objectives = workspace.objectives_selected or ["market_research"]
    objectives_list = ", ".join(objectives)
    guidance_lines = "\n".join(
        f"- {o}: {_OBJECTIVE_GUIDANCE.get(o, 'relevant observations from the data above.')}" for o in objectives
    )
    since_last_time = (
        f"Previous report's executive summary (for context on what's changed since then):\n{previous_executive_summary}\n\n"
        if previous_executive_summary
        else "This is the first report for this workspace — there is no prior report to compare against.\n\n"
    )

    prompt = _REPORT_NARRATIVE_PROMPT_TEMPLATE.format(
        business_context="\n".join(_render_business_context(workspace)) or "No business context provided yet.",
        since_last_time=since_last_time,
        group_count=len(price_comparison),
        price_comparison_text=_format_comparison_groups_for_narrative(price_comparison),
        market_coverage_text=_format_market_coverage_for_narrative(market_coverage),
        alerts_text=_format_alerts_for_narrative(alerts),
        objectives_list=objectives_list,
        guidance_lines=guidance_lines,
    )

    if config.provider == "openai":
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=api_key)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_json_object(resp.choices[0].message.content)

    if config.provider == "anthropic":
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=model,
            max_tokens=4000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(block.text for block in resp.content if block.type == "text")
        return _extract_json_object(text)

    if config.provider == "google":
        from google import genai
        from google.genai import types

        client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(retry_options=types.HttpRetryOptions(attempts=3)),
        )
        resp = await client.aio.models.generate_content(model=model, contents=[prompt])
        return _extract_json_object(resp.text)

    raise ValueError(f"Unknown provider: {config.provider}")
