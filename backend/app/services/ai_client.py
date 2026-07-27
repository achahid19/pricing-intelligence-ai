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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.model_catalog import default_model_for
from app.workspace.encryption import decrypt_key
from app.workspace.models import AiProviderConfig

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"

_DESCRIBE_PROMPT = (
    "You're looking at a photo of a single product for an e-commerce catalog. "
    "Respond with ONLY a JSON object, no markdown fences, no commentary: "
    '{"title": "<a concise, specific product title, under 80 characters>", '
    '"description": "<a 1-3 sentence product description a shopper would find useful>"}'
)

_EXTRACT_PROMPT_TEMPLATE = (
    "You're looking at the text content of a web page ({url}), possibly a single "
    "product page from an e-commerce site. If it describes exactly one purchasable "
    "product with a price, respond with ONLY this JSON object, no markdown fences: "
    '{{"title": "<product name>", "price": "<numeric price only, e.g. 29.99, no currency symbol>", '
    '"currency": "<3-letter currency code if determinable, else null>", '
    '"description": "<a 1-3 sentence description>", "brand": "<brand/manufacturer if mentioned, else null>"}} '
    'If the page is NOT a single product page (e.g. a homepage, category/listing page, '
    'article, or cart/account page), respond with exactly: {{"title": null}}\n\n'
    "Page content:\n{page_text}"
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


async def describe_product_image(
    db: AsyncSession, workspace_id: int, image_bytes: bytes, content_type: str
) -> dict:
    """Ask the workspace's active AI provider for a title + description of a
    single product photo. Raises NoActiveProviderError if none configured."""
    config = await _get_active_config(db, workspace_id)
    api_key = decrypt_key(config.encrypted_api_key)
    model = config.model_override or default_model_for(config.provider)
    b64 = base64.b64encode(image_bytes).decode()

    if config.provider in ("openai", "openrouter"):
        from openai import AsyncOpenAI

        # OpenRouter is a drop-in OpenAI-API-compatible endpoint — same SDK,
        # same request/response shape (including vision), just a different
        # base_url and provider-prefixed model IDs (e.g. "google/gemini-3.6-flash").
        base_url = OPENROUTER_BASE_URL if config.provider == "openrouter" else None
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
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

        client = genai.Client(api_key=api_key)
        resp = await client.aio.models.generate_content(
            model=model,
            contents=[
                _DESCRIBE_PROMPT,
                types.Part.from_bytes(data=image_bytes, mime_type=content_type),
            ],
        )
        return _extract_json(resp.text)

    raise ValueError(f"Unknown provider: {config.provider}")


async def extract_product_from_text(
    db: AsyncSession, workspace_id: int, page_text: str, url: str
) -> dict:
    """Ask the workspace's active AI provider whether a page's text content
    describes a single product, and if so extract title/price/etc as JSON.
    Returns {"title": None} for pages that aren't a single product page.
    Text-only (no image) — a separate call from describe_product_image since
    the content shape genuinely differs per provider, not just duplicated
    for no reason."""
    config = await _get_active_config(db, workspace_id)
    api_key = decrypt_key(config.encrypted_api_key)
    model = config.model_override or default_model_for(config.provider)
    prompt = _EXTRACT_PROMPT_TEMPLATE.format(url=url, page_text=page_text)

    if config.provider in ("openai", "openrouter"):
        from openai import AsyncOpenAI

        base_url = OPENROUTER_BASE_URL if config.provider == "openrouter" else None
        client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        resp = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_json(resp.choices[0].message.content)

    if config.provider == "anthropic":
        from anthropic import AsyncAnthropic

        client = AsyncAnthropic(api_key=api_key)
        resp = await client.messages.create(
            model=model,
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        return _extract_json(resp.content[0].text)

    if config.provider == "google":
        from google import genai

        client = genai.Client(api_key=api_key)
        resp = await client.aio.models.generate_content(model=model, contents=[prompt])
        return _extract_json(resp.text)

    raise ValueError(f"Unknown provider: {config.provider}")
