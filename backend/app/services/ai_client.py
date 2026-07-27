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
    "You are researching real, currently-operating competitor businesses using web search — "
    "not guessing from memory or training data. Use your web search tool to find actual companies.\n\n"
    "Business context:\n{context}\n\n"
    "Search the web and identify up to {max_candidates} real competitor businesses: companies "
    "selling similar products or services, at a similar price tier, to a similar customer base — "
    "weigh the specific products and their descriptions above more heavily than the category "
    "labels or industry name alone, since two businesses in the same industry can target very "
    "different customers. Do not include this business's own website as a candidate. For each "
    "one, base your confidence on what you actually found, not assumptions.\n\n"
    "Respond with ONLY a JSON object, no markdown fences, no commentary before or after: "
    '{{"candidates": [{{"domain": "<bare domain, e.g. example.com, no scheme or path>", '
    '"name": "<company name>", '
    '"confidence": <integer 0-100, how well this is actually a competitor based on what you found>, '
    '"rationale": "<1-2 sentences explaining the match, citing specific products/categories or '
    'price positioning you compared, not just \\"same industry\\">", '
    '"estimated_product_count": <integer estimate if you can tell from what you found, else null>}}]}}'
)


_MAX_SAMPLE_PRODUCTS = 15
_MAX_DESCRIPTION_CHARS = 300


def build_discovery_context(workspace, products: list) -> str:
    """Renders a workspace's business context + catalog summary into the
    text block sent to discover_competitor_sites(). Deliberately a bounded
    sample with descriptions, not the full catalog — enough for the AI to
    understand what's actually sold, not just names or category labels,
    without letting prompt size grow with catalog size."""
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


async def discover_competitor_sites(
    db: AsyncSession, workspace_id: int, business_context: str, max_candidates: int = 10
) -> tuple[dict, Optional[int]]:
    """Ask the workspace's active AI provider to research and propose
    competitor businesses via its native web search tool. Returns
    (parsed_json, search_count) — search_count is a best-effort usage
    figure for the lightweight cost-transparency note, None where the
    provider's response doesn't expose one. Raises NoActiveProviderError
    if none configured."""
    config = await _get_active_config(db, workspace_id)
    api_key = decrypt_key(config.encrypted_api_key)
    model = config.model_override or default_model_for(config.provider)
    prompt = _DISCOVER_PROMPT_TEMPLATE.format(context=business_context, max_candidates=max_candidates)

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
            tools=[{"type": "web_search_20250305", "name": "web_search", "max_uses": max_candidates}],
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
