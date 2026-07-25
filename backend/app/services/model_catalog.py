"""
Curated model list per AI provider, tagged by relative cost tier so the
Settings UI can show users what they're picking without them having to go
look up pricing pages themselves.

Tiers are relative *within* a provider, not across providers — "low" on
Anthropic and "low" on Google aren't necessarily the same absolute price.
Pricing shifts fast (see docs/DECISIONS.md) — re-verify against each
provider's current pricing page before trusting this if months have passed,
same caveat as ai_client.py's model choices.
"""
from typing import Literal, TypedDict

Tier = Literal["low", "medium", "high"]


class ModelInfo(TypedDict, total=False):
    id: str
    label: str
    tier: Tier
    blurb: str
    default: bool


MODEL_CATALOG: dict[str, list[ModelInfo]] = {
    "openai": [
        {
            "id": "gpt-5.6-luna",
            "label": "GPT-5.6 Luna",
            "tier": "low",
            "blurb": "Fastest, cheapest tier — good for high-volume extraction tasks.",
        },
        {
            "id": "gpt-5.6-terra",
            "label": "GPT-5.6 Terra",
            "tier": "medium",
            "blurb": "Balanced everyday-work tier.",
            "default": True,
        },
        {
            "id": "gpt-5.6-sol",
            "label": "GPT-5.6 Sol",
            "tier": "high",
            "blurb": "Flagship tier — best reasoning, highest cost.",
        },
    ],
    "google": [
        {
            "id": "gemini-3.1-flash-lite",
            "label": "Gemini 3.1 Flash-Lite",
            "tier": "low",
            "blurb": "Cheapest Gemini tier.",
        },
        {
            "id": "gemini-3.6-flash",
            "label": "Gemini 3.6 Flash",
            "tier": "medium",
            "blurb": "Fast, current-generation default.",
            "default": True,
        },
        {
            "id": "gemini-3.1-pro",
            "label": "Gemini 3.1 Pro",
            "tier": "high",
            "blurb": "Higher-reasoning Gemini tier.",
        },
    ],
    "anthropic": [
        {
            "id": "claude-haiku-4-5",
            "label": "Claude Haiku 4.5",
            "tier": "low",
            "blurb": "Fastest, cheapest Claude tier.",
        },
        {
            "id": "claude-sonnet-5",
            "label": "Claude Sonnet 5",
            "tier": "medium",
            "blurb": "Balanced default — near-Opus quality at Sonnet cost.",
            "default": True,
        },
        {
            "id": "claude-opus-4-8",
            "label": "Claude Opus 4.8",
            "tier": "high",
            "blurb": "Most capable Claude tier.",
        },
    ],
    # OpenRouter proxies hundreds of models behind one key. This curated list
    # deliberately spans real providers (not just re-listing the three
    # above) since that's OpenRouter's actual value: one key, many vendors —
    # including open-weight models with no native provider option in this
    # app at all.
    "openrouter": [
        {
            "id": "deepseek/deepseek-v4-flash",
            "label": "DeepSeek V4 Flash",
            "tier": "low",
            "blurb": "Open-weight model, lowest cost of any option here.",
        },
        {
            "id": "google/gemini-3.6-flash",
            "label": "Gemini 3.6 Flash",
            "tier": "medium",
            "blurb": "Same model as the native Google option, via OpenRouter's key.",
            "default": True,
        },
        {
            "id": "anthropic/claude-sonnet-5",
            "label": "Claude Sonnet 5",
            "tier": "high",
            "blurb": "Higher-reasoning option, billed through the same OpenRouter key.",
        },
    ],
}


def default_model_for(provider: str) -> str:
    for model in MODEL_CATALOG.get(provider, []):
        if model.get("default"):
            return model["id"]
    raise ValueError(f"No default model configured for provider: {provider}")
