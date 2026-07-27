"""
Website catalog import: given a business's website URL, discover product
pages and extract product data automatically (Product.import_source =
"website_ai" — this is Step 8's website-import path from PROGRESS.md,
pulled forward the same way ai_client.py was pulled forward for the
photo-assist feature).

Deterministic extraction first — Shopify's public /products.json, then
schema.org Product JSON-LD on individual pages found via sitemap.xml — with
AI text-extraction as a fallback only for pages that have neither. Plain
httpx + BeautifulSoup fetching, no headless browser: Playwright is in
requirements.txt for a later discovery-crawling phase, but its browsers
aren't installed in this image yet (see backend/Dockerfile — no
`playwright install` step). This means JS-rendered storefronts (product
data injected client-side with no server-rendered HTML or JSON-LD) won't
be discoverable via this path — a real, known limitation, not silently
papered over. Revisit if/when Playwright is wired up for Step 3 discovery.
"""
import json
import re
from decimal import Decimal, InvalidOperation
from typing import Optional

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import ai_client

MAX_PAGES_PER_IMPORT = 20
_TIMEOUT = httpx.Timeout(10.0)
_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; PricingIntelligenceBot/1.0)"}


class FetchError(Exception):
    """Raised when the given URL can't be reached at all."""


def _normalize_url(raw: str) -> str:
    raw = raw.strip()
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw.rstrip("/")


def _clean_price(raw) -> Optional[Decimal]:
    if raw is None:
        return None
    try:
        # Keep digits/./, only, then resolve comma meaning the same way the
        # CSV importer does: a lone comma (no dot) is a decimal separator
        # ("29,99" -> "29.99"), otherwise it's a thousands separator to drop
        # ("1,299.00" -> "1299.00"). Without this, "29,99" silently parsed as
        # 2999 — a real 100x pricing bug caught via a direct unit test.
        cleaned = re.sub(r"[^\d.,]", "", str(raw))
        if "," in cleaned and "." not in cleaned:
            cleaned = cleaned.replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
        value = Decimal(cleaned) if cleaned else None
        return value if value and value > 0 else None
    except InvalidOperation:
        return None


def _strip_html(html: str, limit: int = 2000) -> str:
    return BeautifulSoup(html or "", "html.parser").get_text(" ", strip=True)[:limit]


async def _fetch(client: httpx.AsyncClient, url: str) -> Optional[httpx.Response]:
    try:
        resp = await client.get(url, headers=_HEADERS, follow_redirects=True, timeout=_TIMEOUT)
        return resp if resp.status_code == 200 else None
    except httpx.HTTPError:
        return None


async def _try_shopify_products_json(client: httpx.AsyncClient, base_url: str) -> Optional[list[dict]]:
    resp = await _fetch(client, f"{base_url}/products.json?limit={MAX_PAGES_PER_IMPORT}")
    if resp is None:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    products = data.get("products") if isinstance(data, dict) else None
    if not isinstance(products, list) or not products:
        return None

    candidates = []
    for p in products[:MAX_PAGES_PER_IMPORT]:
        variants = p.get("variants") or []
        price = _clean_price(variants[0].get("price")) if variants else None
        if price is None:
            continue
        images = p.get("images") or []
        candidates.append(
            {
                "title": (p.get("title") or "").strip(),
                "price": price,
                "currency": None,  # Shopify's public products.json doesn't expose currency
                "image_url": images[0].get("src") if images else None,
                "description": _strip_html(p.get("body_html")),
                "brand": p.get("vendor") or None,
                "category": p.get("product_type") or None,
                "source_url": f"{base_url}/products/{p['handle']}" if p.get("handle") else base_url,
                "method": "structured",
            }
        )
    return candidates or None


def _extract_json_ld_product(soup: BeautifulSoup, url: str) -> Optional[dict]:
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (ValueError, TypeError):
            continue
        items = data if isinstance(data, list) else [data]
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = item.get("@type")
            if item_type != "Product" and "Product" not in (item_type or []):
                continue
            offers = item.get("offers") or {}
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price = _clean_price(offers.get("price"))
            if price is None:
                continue
            image = item.get("image")
            if isinstance(image, list):
                image = image[0] if image else None
            brand = item.get("brand")
            if isinstance(brand, dict):
                brand = brand.get("name")
            return {
                "title": (item.get("name") or "").strip(),
                "price": price,
                "currency": offers.get("priceCurrency"),
                "image_url": image,
                "description": (item.get("description") or "")[:2000],
                "brand": brand,
                "category": None,
                "source_url": url,
                "method": "structured",
            }
    return None


def _parse_sitemap_locs(xml_text: str) -> list[str]:
    # Regex rather than an XML parser: sitemaps are a simple, well-defined
    # <loc> list and this avoids pulling in lxml (bs4's "xml" parser needs
    # it) just for this one thing.
    return re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml_text)


async def _discover_candidate_urls(client: httpx.AsyncClient, base_url: str) -> list[str]:
    for sitemap_path in ("/sitemap.xml", "/sitemap_products_1.xml"):
        resp = await _fetch(client, base_url + sitemap_path)
        if resp is None:
            continue
        locs = _parse_sitemap_locs(resp.text)
        if not locs:
            continue
        product_like = [u for u in locs if re.search(r"/(products?|shop|item)s?/", u, re.I)]
        return (product_like or locs)[:MAX_PAGES_PER_IMPORT]
    return []


async def discover_products(db: AsyncSession, workspace_id: int, raw_url: str) -> dict:
    base_url = _normalize_url(raw_url)

    async with httpx.AsyncClient() as client:
        if await _fetch(client, base_url) is None:
            raise FetchError(f"Couldn't reach {base_url} — check the URL and try again.")

        shopify_candidates = await _try_shopify_products_json(client, base_url)
        if shopify_candidates:
            return {
                "candidates": shopify_candidates,
                "pages_scanned": len(shopify_candidates),
                "ai_calls_used": 0,
                "truncated": False,
            }

        candidate_urls = await _discover_candidate_urls(client, base_url)
        if not candidate_urls:
            candidate_urls = [base_url]  # last resort: try the given page itself directly

        candidates: list[dict] = []
        ai_calls_used = 0
        ai_available = True

        for url in candidate_urls:
            resp = await _fetch(client, url)
            if resp is None:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")

            structured = _extract_json_ld_product(soup, url)
            if structured:
                candidates.append(structured)
                continue

            if not ai_available:
                continue

            page_text = soup.get_text(" ", strip=True)[:6000]
            try:
                result = await ai_client.extract_product_from_text(db, workspace_id, page_text, url)
                ai_calls_used += 1
            except ai_client.NoActiveProviderError:
                ai_available = False
                continue
            except Exception:
                ai_calls_used += 1
                continue

            price = _clean_price(result.get("price"))
            if not result.get("title") or price is None:
                continue
            candidates.append(
                {
                    "title": result["title"].strip(),
                    "price": price,
                    "currency": result.get("currency"),
                    "image_url": None,
                    "description": result.get("description"),
                    "brand": result.get("brand"),
                    "category": None,
                    "source_url": url,
                    "method": "ai",
                }
            )

        return {
            "candidates": candidates,
            "pages_scanned": len(candidate_urls),
            "ai_calls_used": ai_calls_used,
            "truncated": len(candidate_urls) >= MAX_PAGES_PER_IMPORT,
        }
