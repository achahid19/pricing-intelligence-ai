"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ExternalLink } from "lucide-react";

import { ConfidenceBadge } from "@/components/discovery/ConfidenceBadge";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { api, ApiError, type TrackedMatch } from "@/lib/api";
import { priceDelta } from "@/lib/pricing";

const MATCH_CONFIDENCE_TOOLTIP =
  "The AI's own self-assessed confidence that these are genuinely the same or a directly comparable item — not a verified metric.";

function CompetitorRow({ match }: { match: TrackedMatch }) {
  const ownPrice = Number(match.product_price);
  const competitorPrice = match.competitor_product_price != null ? Number(match.competitor_product_price) : null;
  const minPrice = match.product_min_price != null ? Number(match.product_min_price) : null;
  // No currency-conversion system in this app yet — comparing raw numbers
  // across currencies would produce a meaningless percentage (e.g. USD 48
  // vs MAD 2499 isn't "5000% pricier"), so only compare when both sides
  // share a currency; otherwise show prices side by side with no verdict.
  const sameCurrency = match.competitor_product_currency === match.product_currency;
  const belowMap =
    sameCurrency &&
    match.competitor_site_relationship_type === "reseller" &&
    minPrice != null &&
    competitorPrice != null &&
    competitorPrice < minPrice;
  const delta =
    sameCurrency && match.competitor_product_is_trackable && competitorPrice != null
      ? priceDelta(ownPrice, competitorPrice)
      : null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-2.5 first:border-t-0 first:pt-0">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`/discovery/${match.competitor_site_id}`}
            className="inline-flex items-center gap-1 text-sm font-medium text-ink hover:text-accent"
          >
            {match.competitor_site_name || match.competitor_site_domain}
            <ExternalLink className="size-3" />
          </Link>
          <Badge tone={match.competitor_site_relationship_type === "reseller" ? "accent" : "neutral"}>
            {match.competitor_site_relationship_type}
          </Badge>
          {match.match_method === "ai_auto" && (
            <ConfidenceBadge score={match.confidence} tooltip={MATCH_CONFIDENCE_TOOLTIP} />
          )}
        </div>
        <p className="mt-1 text-xs text-slate-soft">
          {match.competitor_product_title} · last checked {new Date(match.competitor_product_updated_at).toLocaleDateString()}
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {competitorPrice != null ? (
          <span className="text-sm tabular-nums text-ink">
            {match.competitor_product_currency} {competitorPrice.toFixed(2)}
          </span>
        ) : (
          <Badge tone="neutral">No price found</Badge>
        )}
        {delta && <Badge tone={delta.tone}>{delta.label}</Badge>}
        {!sameCurrency && competitorPrice != null && <Badge tone="neutral">Different currency</Badge>}
        {belowMap && <Badge tone="danger">Below MAP floor</Badge>}
      </div>
    </div>
  );
}

export default function TrackedPage() {
  const [matches, setMatches] = useState<TrackedMatch[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.discovery
      .listTrackedMatches()
      .then(setMatches)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Try again."));
  }, []);

  const grouped = useMemo(() => {
    const byProduct = new Map<number, { name: string; price: string; currency: string; matches: TrackedMatch[] }>();
    for (const m of matches ?? []) {
      if (!byProduct.has(m.product_id)) {
        byProduct.set(m.product_id, { name: m.product_name, price: m.product_price, currency: m.product_currency, matches: [] });
      }
      byProduct.get(m.product_id)!.matches.push(m);
    }
    return Array.from(byProduct.entries()).map(([productId, data]) => ({ productId, ...data }));
  }, [matches]);

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <PageHeader
        title="Tracked products"
        description="Your catalog against every competitor you've confirmed a match with, in one place."
      />

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}

      {!matches && !error && <p className="mt-6 text-sm text-slate-soft">Loading…</p>}

      {matches && matches.length === 0 && (
        <p className="mt-6 text-sm text-slate">
          No confirmed matches yet — confirm a match on a competitor's product page to start tracking it here.
        </p>
      )}

      {grouped.length > 0 && (
        <div className="mt-6 grid grid-cols-1 gap-3 lg:grid-cols-2">
          {grouped.map((group) => (
            <Card key={group.productId}>
              <div className="flex items-center justify-between gap-2">
                <h2 className="font-medium text-ink">{group.name}</h2>
                <span className="shrink-0 text-sm tabular-nums text-slate-soft">
                  {group.currency} {Number(group.price).toFixed(2)}
                </span>
              </div>
              <div className="mt-1">
                {group.matches.map((m) => (
                  <CompetitorRow key={m.id} match={m} />
                ))}
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
