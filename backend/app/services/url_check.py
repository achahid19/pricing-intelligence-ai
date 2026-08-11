"""
Shared best-effort HTTP checks for AI-reported URLs — extracted here once
discovery/router.py needed the exact same reachability check catalog/
router.py already had for website-import (see docs/PROGRESS.md: AI web
search tools only annotate real, tool-verified citation URLs sparsely for
a JSON-only prompt, so a genuine HTTP check is the second, complementary
signal that catches URLs the model guessed wrong).
"""
import httpx

TIMEOUT = httpx.Timeout(5.0)
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PricingIntelligenceBot/1.0)"}


# A response in this set means "we got blocked," not "this page doesn't
# exist" — 401/403/429 are access-control signals from anti-bot WAFs
# (common on brand/manufacturer sites: Akamai, Cloudflare, etc.), not
# evidence about whether the content is real. Confirmed directly against a
# real case (peugeot.ma): a plain automated request gets 403 even with a
# full realistic browser User-Agent — this is TLS/fingerprint-based
# blocking a header change can't get around, not a simple UA check. A real
# person clicking the same link in their own browser overwhelmingly
# succeeds fine. Treating a block as "probably broken" would be actively
# wrong far more often than it's right, so it's treated as inconclusive
# (counts as reachable) rather than a negative signal — unlike a genuine
# 404/410 or a 5xx, which really do indicate a problem.
_BLOCKED_STATUS_CODES = {401, 403, 429}


def _looks_reachable(status_code: int) -> bool:
    return status_code < 400 or status_code in _BLOCKED_STATUS_CODES


async def url_is_reachable(client: httpx.AsyncClient, url: str) -> bool:
    """Does this URL actually resolve, or at least not show a genuine
    not-found/server-error signal? A HEAD request first (cheaper — no
    body), falling back to GET since some servers reject/mishandle HEAD
    (405, or silently 404 a page that's really there). Any network failure
    counts as unreachable rather than raising — this must never block
    discovery."""
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    try:
        resp = await client.head(url, headers=HEADERS, follow_redirects=True, timeout=TIMEOUT)
        if _looks_reachable(resp.status_code):
            return True
        resp = await client.get(url, headers=HEADERS, follow_redirects=True, timeout=TIMEOUT)
        return _looks_reachable(resp.status_code)
    except httpx.HTTPError:
        return False


def find_generic_urls(url_title_pairs: list[tuple[str, str]], min_distinct_titles: int = 4) -> set[str]:
    """Given (url, title) pairs from one discovery batch, return the URLs
    claimed by `min_distinct_titles`-or-more genuinely distinct products —
    a real, observed sign the AI fell back to one generic listing/category
    page for products it couldn't find an individual page for. This
    happens even when the AI's own citation marked the URL, and even
    though the page itself genuinely resolves (a reachability check alone
    can't catch it, since the shared page IS real, just not specific) —
    e.g. 6 different Renault models all reported as
    renault.ma/vehicules-particuliers.html, a top-level "all our cars"
    listing page, not any one model's own page.

    The default threshold is 4, not 2 — a real, legitimate page routinely
    hosts a genuine small group of distinct-but-related items (e.g. Cap
    Connect's actual /en/pro-email page correctly lists exactly 3 real
    Email PRO tiers with their real individual prices; deployment history
    also showed 3-way groupings for a reseller VPS product line). Flagging
    at 2 would wrongly demote those. 4+ is past what a normal single
    product-family page groups together in every real case observed in
    this app so far, without being so high it lets an actual generic
    catch-all page slip through.

    Apply this as a final override AFTER citation/reachability checks:
    reachable-and-cited doesn't rescue a URL that's provably shared across
    unrelated products."""
    titles_by_url: dict[str, set[str]] = {}
    for url, title in url_title_pairs:
        titles_by_url.setdefault(url, set()).add(title)
    return {url for url, titles in titles_by_url.items() if len(titles) >= min_distinct_titles}
