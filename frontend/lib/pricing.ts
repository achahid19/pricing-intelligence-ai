import type { BadgeTone } from "@/components/ui/badge";

// Shared by /tracked and /reports/[id] so both render identical wording
// from a price-delta percentage instead of two independently-written
// display schemes. No currency-conversion system exists in this app —
// callers must only pass a percentage already computed from a same-currency
// pair (see reporting/service.py's same_currency gate on the backend, and
// /tracked's own sameCurrency check), never a raw cross-currency ratio.
export function priceDeltaFromPct(deltaPct: number): { label: string; tone: BadgeTone } {
  if (Math.abs(deltaPct) < 1) return { label: "Same price", tone: "neutral" };
  if (deltaPct > 0) return { label: `${deltaPct.toFixed(0)}% pricier than you`, tone: "good" };
  return { label: `${Math.abs(deltaPct).toFixed(0)}% cheaper than you`, tone: "danger" };
}

export function priceDelta(ownPrice: number, competitorPrice: number): { label: string; tone: BadgeTone } {
  return priceDeltaFromPct(((competitorPrice - ownPrice) / ownPrice) * 100);
}
