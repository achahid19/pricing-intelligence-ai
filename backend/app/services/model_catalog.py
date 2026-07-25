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
            "id": "gpt-4.1-nano",
            "label": "GPT-4.1 Nano",
            "tier": "low",
            "blurb": "The cheapest OpenAI model available — simple classification, tagging.",
        },
        {
            "id": "gpt-4o-mini",
            "label": "GPT-4o Mini",
            "tier": "low",
            "blurb": "Small, fast, well-known — good default for lightweight tasks.",
        },
        {
            "id": "gpt-5.6-luna",
            "label": "GPT-5.6 Luna",
            "tier": "low",
            "blurb": "Fastest of the current GPT-5.6 family — high-volume extraction.",
        },
        {
            "id": "gpt-4o",
            "label": "GPT-4o",
            "tier": "medium",
            "blurb": "OpenAI's widely-used multimodal workhorse.",
        },
        {
            "id": "o3",
            "label": "o3",
            "tier": "medium",
            "blurb": "Reasoning-focused model — multi-step analysis at moderate cost.",
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
            "blurb": "Flagship GPT-5.6 tier — best reasoning, highest cost.",
        },
        {
            "id": "o1",
            "label": "o1",
            "tier": "high",
            "blurb": "Premium reasoning tier — the most expensive OpenAI option here.",
        },
    ],
    "google": [
        {
            "id": "gemini-3.1-flash-lite",
            "label": "Gemini 3.1 Flash-Lite",
            "tier": "low",
            "blurb": "Cheapest current Gemini tier.",
        },
        {
            "id": "gemini-3-flash",
            "label": "Gemini 3 Flash",
            "tier": "low",
            "blurb": "Fast and cheap, a step up from Flash-Lite.",
        },
        {
            "id": "gemini-3.6-flash",
            "label": "Gemini 3.6 Flash",
            "tier": "medium",
            "blurb": "Fast, current-generation default.",
            "default": True,
        },
        {
            "id": "gemini-3.5-flash",
            "label": "Gemini 3.5 Flash",
            "tier": "medium",
            "blurb": "Previous-generation Flash — similar cost to 3.6.",
        },
        {
            "id": "gemini-2.5-pro",
            "label": "Gemini 2.5 Pro",
            "tier": "medium",
            "blurb": "Older Pro-tier model, still widely used.",
        },
        {
            "id": "gemini-3.1-pro",
            "label": "Gemini 3.1 Pro",
            "tier": "high",
            "blurb": "Higher-reasoning Gemini tier, highest cost here.",
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
            "id": "claude-sonnet-4-5",
            "label": "Claude Sonnet 4.5",
            "tier": "medium",
            "blurb": "Previous-generation Sonnet — still active and well known.",
        },
        {
            "id": "claude-sonnet-5",
            "label": "Claude Sonnet 5",
            "tier": "medium",
            "blurb": "Balanced default — near-Opus quality at Sonnet cost.",
            "default": True,
        },
        {
            "id": "claude-opus-4-7",
            "label": "Claude Opus 4.7",
            "tier": "high",
            "blurb": "Previous-generation Opus — highly capable, still active.",
        },
        {
            "id": "claude-opus-4-8",
            "label": "Claude Opus 4.8",
            "tier": "high",
            "blurb": "Most capable current Opus tier.",
        },
        {
            "id": "claude-fable-5",
            "label": "Claude Fable 5",
            "tier": "high",
            "blurb": "Anthropic's most capable model overall — premium pricing to match.",
        },
    ],
    # OpenRouter proxies hundreds of models behind one key. This curated list
    # deliberately spans real providers (not just re-listing the three
    # above) since that's OpenRouter's actual value: one key, many vendors —
    # including open-weight models with no native provider option in this
    # app at all.
    "openrouter": [
        {
            "id": "qwen/qwen3-vl-8b-instruct",
            "label": "Qwen3 VL 8B",
            "tier": "low",
            "blurb": "Open-weight vision model, lowest cost of any option here.",
        },
        {
            "id": "qwen/qwen2.5-vl-72b-instruct",
            "label": "Qwen2.5 VL 72B",
            "tier": "low",
            "blurb": "Larger open-weight vision model, still very cheap.",
        },
        {
            "id": "google/gemini-3.6-flash",
            "label": "Gemini 3.6 Flash",
            "tier": "medium",
            "blurb": "Same model as the native Google option, via OpenRouter's key.",
            "default": True,
        },
        {
            "id": "openai/gpt-5.6-terra",
            "label": "GPT-5.6 Terra",
            "tier": "medium",
            "blurb": "Same model as the native OpenAI option, via OpenRouter's key.",
        },
        {
            "id": "anthropic/claude-sonnet-5",
            "label": "Claude Sonnet 5",
            "tier": "high",
            "blurb": "Higher-reasoning option, billed through the same OpenRouter key.",
        },
        {
            "id": "anthropic/claude-opus-4-8",
            "label": "Claude Opus 4.8",
            "tier": "high",
            "blurb": "Most capable option available through OpenRouter here.",
        },
    ],
}


def default_model_for(provider: str) -> str:
    for model in MODEL_CATALOG.get(provider, []):
        if model.get("default"):
            return model["id"]
    raise ValueError(f"No default model configured for provider: {provider}")
