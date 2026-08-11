"""
Same-currency-gated port of ai_crafters_pfa's services/metrics.py
build_comparison_table() (see docs/ARCHITECTURE.md's "ports directly" note
and docs/DECISIONS.md for the full port decision) — that repo had a
currency-conversion system this app deliberately doesn't have, so unlike
its converted `seller_price`, cross-currency matches must be excluded from
ranking/index/cheapest-seller math entirely, not silently mixed in (the
same class of mistake already caught once this session in the AI
narrative). Pure functions, no DB access — operate on the flat per-match
dicts reporting/service.py._compute_comparison_row() already produces.
"""


def _ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def describe_price_position(
    price_rank: int | None, price_index: float | None, same_currency_competitors_count: int
) -> str | None:
    """One plain-English sentence describing a product's price standing —
    the business-readable replacement for ever showing a raw "rank"/
    "index" number as a label (reports are for management reading, not
    analytics — see docs/PROGRESS.md). price_rank is rank-from-cheapest
    (1 = cheapest, see build_comparison_metrics's tie-handling comment),
    so the "most expensive" branch needs total - price_rank + 1, not
    price_rank directly — get this backwards and a rank-6-of-8 product
    (the 3rd most expensive) reads as "6th most expensive" instead. None
    under the exact same condition price_rank/price_index are None (no
    same-currency competitor prices).

    The +/-5% band is deliberate: near-tied prices flipping rank by one
    position between reports is noise, not a real repositioning, and this
    app already treats 15% as its significant-change threshold elsewhere
    (reporting/service.py's PRICE_ANOMALY_THRESHOLD_PCT) — 5% is a
    defensible third of that. Rank is deliberately omitted inside the
    band: it's the noisiest part of the number when the gap is tiny."""
    if price_rank is None or price_index is None:
        return None
    n = same_currency_competitors_count
    total = n + 1
    pct = round(price_index - 100)
    plural = "s" if n != 1 else ""
    if abs(pct) <= 5:
        return f"In line with the {n} tracked competitor{plural}"
    if pct > 0:
        expensive_rank = total - price_rank + 1
        label = "The most expensive" if expensive_rank == 1 else f"{_ordinal(expensive_rank)} most expensive"
        return f"{label} of {total} tracked sellers — {pct}% above the average"
    label = "The cheapest" if price_rank == 1 else f"{_ordinal(price_rank)} cheapest"
    return f"{label} of {total} tracked sellers — {abs(pct)}% below the average"


def build_comparison_metrics(product_price: float, matches: list[dict]) -> dict:
    """One product's metrics block, computed only from matches where
    same_currency is True and competitor_product_price is not None.
    total_competitors_compared still reflects the real, any-currency match
    count — only the ranking fields below it are gated."""
    same_currency_priced = [
        m for m in matches if m["same_currency"] and m["competitor_product_price"] is not None
    ]
    if not same_currency_priced:
        return {
            "price_rank": None,
            "total_competitors_compared": len(matches),
            "same_currency_competitors_count": 0,
            "sellers_cheaper": 0,
            "price_index": None,
            "price_position_summary": None,
            "cheapest_competitor_name": None,
            "cheapest_competitor_price": None,
            "cheapest_competitor_site_id": None,
        }

    prices = [m["competitor_product_price"] for m in same_currency_priced]
    avg_price = sum(prices) / len(prices)
    sellers_cheaper = sum(1 for p in prices if p < product_price)
    # Tie-handling: a competitor priced exactly the same as product_price
    # shares its rank number (sorted() is stable, ties resolve to the same
    # index) — a deliberate "ties share the best rank" convention carried
    # over from the validated old logic, not a bug to fix.
    price_rank = sorted(prices + [product_price]).index(product_price) + 1
    price_index = round((product_price / avg_price) * 100, 2) if avg_price else None
    cheapest = min(same_currency_priced, key=lambda m: m["competitor_product_price"])

    return {
        "price_rank": price_rank,
        "total_competitors_compared": len(matches),
        "same_currency_competitors_count": len(same_currency_priced),
        "sellers_cheaper": sellers_cheaper,
        "price_index": price_index,
        "price_position_summary": describe_price_position(price_rank, price_index, len(same_currency_priced)),
        "cheapest_competitor_name": cheapest["competitor_site_name"] or cheapest["competitor_site_domain"],
        "cheapest_competitor_price": cheapest["competitor_product_price"],
        "cheapest_competitor_site_id": cheapest["competitor_site_id"],
    }


def group_comparison_rows(rows: list[dict]) -> list[dict]:
    """Groups the flat per-match rows into one entry per own Product —
    order follows first-seen order in `rows` (fetch_tracked_matches's own
    Product.name ordering), not a re-sort. A product with zero confirmed
    matches can never appear here: fetch_tracked_matches joins FROM
    ProductMatch, so `rows` only ever contains products with >=1 match."""
    groups: dict[int, dict] = {}
    order: list[int] = []
    for row in rows:
        pid = row["product_id"]
        if pid not in groups:
            groups[pid] = {
                "product_id": pid,
                "product_name": row["product_name"],
                "product_price": row["product_price"],
                "product_currency": row["product_currency"],
                "product_min_price": row["product_min_price"],
                "own_trend": row["own_trend"],
                "matches": [],
            }
            order.append(pid)
        groups[pid]["matches"].append(row)

    result = []
    for pid in order:
        group = groups[pid]
        group["metrics"] = build_comparison_metrics(group["product_price"], group["matches"])
        result.append(group)
    return result
