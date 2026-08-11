"""
Small text-cleanup helpers shared by any module consuming raw AI web-search
output — extracted here once catalog/router.py's website-import needed the
exact same cleanup discovery/router.py already had for competitor-site/
product discovery.
"""
import re
from typing import Optional

_MARKDOWN_CITATION_RE = re.compile(r"\s*\(\[[^\]]+\]\(https?://[^)]+\)\)")


def strip_citations(text: Optional[str]) -> Optional[str]:
    """Web-search-enabled responses sometimes embed an inline markdown
    citation like "([genious.ma](https://...))" right in a text field —
    it renders as literal text, not a link, wherever we just display the
    field as plain text, so strip it before storing rather than leaving
    visual noise in the data for every future consumer (matching, reports)."""
    if not text:
        return text
    return _MARKDOWN_CITATION_RE.sub("", text).strip() or None


def normalize_domain(raw: str) -> str:
    """Strip scheme, a leading www., and any trailing path/slash — so
    "https://www.example.com/" and "example.com" are recognized as the same
    site rather than creating a duplicate row. Also cuts at the first
    whitespace/parenthesis: the AI sometimes appends a trailing annotation
    after the bare domain (e.g. "genious.ma (genious communications)") — a
    valid domain never contains either, so this is safe to cut on."""
    domain = raw.strip().lower().removeprefix("https://").removeprefix("http://").removeprefix("www.")
    domain = domain.split("/")[0]
    return re.split(r"[\s(]", domain, maxsplit=1)[0]


_TRAILING_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*$")


def normalize_product_name(name: str) -> str:
    """Lowercase and strip a single trailing parenthetical — so "Rise" and
    "Rise (Hébergement Web Mutualisé – shared hosting)" are recognized as
    the same product for duplicate-detection purposes. AI discovery output
    isn't deterministic across runs (same real product, differently
    phrased title each time), and appending a descriptive parenthetical
    like this is the specific, observed, narrow pattern — only strips one
    trailing "(...)", not anything in the middle of the name, to avoid
    conflating two genuinely different products that happen to share a
    common prefix."""
    return _TRAILING_PAREN_RE.sub("", name).strip().lower()
