"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ExternalLink, Link2, Package, Search, Store } from "lucide-react";

import { ConfidenceBadge } from "@/components/discovery/ConfidenceBadge";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { api, ApiError, type DiscoveryMode, type TrackedMatch } from "@/lib/api";
import { priceDelta } from "@/lib/pricing";
import { usePersistedTab } from "@/lib/usePersistedTab";
import { cn } from "@/lib/utils";

const MATCH_CONFIDENCE_TOOLTIP =
  "The AI's own self-assessed confidence that these are genuinely the same or a directly comparable item, not a verified metric.";

const VIEW_OPTIONS = ["by-product", "by-competitor"] as const;
type View = (typeof VIEW_OPTIONS)[number];
type RelationshipFilter = "all" | DiscoveryMode;

// No currency-conversion system in this app yet — comparing raw numbers
// across currencies would produce a meaningless percentage (e.g. USD 48 vs
// MAD 2499 isn't "5000% pricier"), so only compare when both sides share a
// currency; otherwise the match is still shown, just with no verdict.
function deriveMatchInfo(match: TrackedMatch) {
  // product_price is null when the product hasn't had a price set yet
  // (e.g. website-imported from a site with no published price) — no
  // delta/MAP verdict is possible until one is added, same treatment as a
  // competitor price that isn't trackable.
  const ownPrice = match.product_price != null ? Number(match.product_price) : null;
  const competitorPrice = match.competitor_product_price != null ? Number(match.competitor_product_price) : null;
  const minPrice = match.product_min_price != null ? Number(match.product_min_price) : null;
  const sameCurrency = match.competitor_product_currency === match.product_currency;
  const belowMap =
    sameCurrency &&
    match.competitor_site_relationship_type === "reseller" &&
    minPrice != null &&
    competitorPrice != null &&
    competitorPrice < minPrice;
  const delta =
    sameCurrency && match.competitor_product_is_trackable && competitorPrice != null && ownPrice != null
      ? priceDelta(ownPrice, competitorPrice)
      : null;
  return { ownPrice, competitorPrice, sameCurrency, belowMap, delta };
}

function StatTile({
  icon: Icon,
  label,
  value,
  tone,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  tone?: "danger";
}) {
  return (
    <Card className="flex items-center gap-3">
      <div
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-lg",
          tone === "danger" ? "bg-danger/10 text-danger" : "bg-slate/10 text-slate"
        )}
      >
        <Icon className="size-4.5" />
      </div>
      <div>
        <p className="text-xl font-semibold tabular-nums leading-tight text-ink">{value}</p>
        <p className="text-xs text-slate-soft">{label}</p>
      </div>
    </Card>
  );
}

function MatchPill({
  href,
  label,
  relationshipType,
  match,
}: {
  href: string;
  label: string;
  relationshipType?: DiscoveryMode;
  match: TrackedMatch;
}) {
  const { competitorPrice, sameCurrency, belowMap, delta } = deriveMatchInfo(match);
  const priceColor = delta ? (delta.tone === "good" ? "text-good" : delta.tone === "danger" ? "text-danger" : "text-slate-soft") : "text-slate-soft";
  const tooltipParts = [match.competitor_product_title, `last checked ${new Date(match.competitor_product_updated_at).toLocaleDateString()}`];
  if (match.match_method === "ai_auto" && match.confidence != null) tooltipParts.push(`AI matched · ${match.confidence}% confidence`);
  if (delta) tooltipParts.push(delta.label);

  return (
    <Link
      href={href}
      title={tooltipParts.join(" · ")}
      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2 py-1 text-xs hover:border-accent"
    >
      <span className="font-medium text-ink">{label}</span>
      {relationshipType && (
        <Badge tone={relationshipType === "reseller" ? "accent" : "neutral"} className="px-1.5 py-0">
          {relationshipType}
        </Badge>
      )}
      {competitorPrice != null ? (
        <span className={cn("tabular-nums", priceColor)}>
          {match.competitor_product_currency} {competitorPrice.toFixed(2)}
        </span>
      ) : (
        <span className="text-slate-soft">no price</span>
      )}
      {!sameCurrency && competitorPrice != null && <span className="text-slate-soft">diff. currency</span>}
      {belowMap && (
        <Badge tone="danger" className="px-1.5 py-0">
          MAP
        </Badge>
      )}
    </Link>
  );
}

function groupMatchesByCounterpart(matches: TrackedMatch[], keyFn: (m: TrackedMatch) => number) {
  const map = new Map<number, TrackedMatch[]>();
  for (const m of matches) {
    const k = keyFn(m);
    if (!map.has(k)) map.set(k, []);
    map.get(k)!.push(m);
  }
  return Array.from(map.entries());
}

// A product can be confirmed-matched to several products from the SAME
// competitor (e.g. one of ours against four trims of one competitor car) —
// flat pills all sharing one label (the competitor/product name), only
// distinguished by price, are genuinely unreadable in that case. When a
// counterpart repeats, this renders one header (the shared identity + a
// count) with the specific distinguishing title on each pill underneath;
// a counterpart with exactly one match still renders as a single plain
// pill, unchanged from before.
function MatchCell({
  matches,
  groupKeyFn,
  groupHeader,
  pillHref,
  pillLabel,
  singleHref,
  singleLabel,
  singleBadge,
}: {
  matches: TrackedMatch[];
  groupKeyFn: (m: TrackedMatch) => number;
  groupHeader: (m: TrackedMatch) => { label: string; href: string; badge?: DiscoveryMode };
  pillHref: (m: TrackedMatch) => string;
  pillLabel: (m: TrackedMatch) => string;
  singleHref: (m: TrackedMatch) => string;
  singleLabel: (m: TrackedMatch) => string;
  singleBadge?: (m: TrackedMatch) => DiscoveryMode | undefined;
}) {
  const groups = groupMatchesByCounterpart(matches, groupKeyFn);
  return (
    <div className="flex flex-wrap items-start gap-1.5">
      {groups.map(([key, groupMatches]) => {
        const first = groupMatches[0];
        if (groupMatches.length === 1) {
          return (
            <MatchPill
              key={first.id}
              href={singleHref(first)}
              label={singleLabel(first)}
              relationshipType={singleBadge?.(first)}
              match={first}
            />
          );
        }
        const header = groupHeader(first);
        return (
          <div key={key} className="w-full rounded-lg border border-border/70 bg-black/[0.015] p-1.5">
            <Link
              href={header.href}
              className="inline-flex items-center gap-1.5 text-xs font-medium text-slate hover:text-accent"
            >
              {header.label}
              <span className="tabular-nums text-slate-soft">({groupMatches.length})</span>
              {header.badge && (
                <Badge tone={header.badge === "reseller" ? "accent" : "neutral"} className="px-1.5 py-0">
                  {header.badge}
                </Badge>
              )}
            </Link>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {groupMatches.map((m) => (
                <MatchPill key={m.id} href={pillHref(m)} label={pillLabel(m)} match={m} />
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default function TrackedPage() {
  const [matches, setMatches] = useState<TrackedMatch[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [relationshipFilter, setRelationshipFilter] = useState<RelationshipFilter>("all");
  const [view, setView] = usePersistedTab<View>("view", "tracked-view", VIEW_OPTIONS, "by-product");

  useEffect(() => {
    api.discovery
      .listTrackedMatches()
      .then(setMatches)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Something went wrong. Try again."));
  }, []);

  const hasCompetitors = useMemo(() => (matches ?? []).some((m) => m.competitor_site_relationship_type === "competitor"), [matches]);
  const hasResellers = useMemo(() => (matches ?? []).some((m) => m.competitor_site_relationship_type === "reseller"), [matches]);

  const stats = useMemo(() => {
    const list = matches ?? [];
    return {
      products: new Set(list.map((m) => m.product_id)).size,
      competitors: new Set(list.map((m) => m.competitor_site_id)).size,
      matches: list.length,
      belowMap: list.filter((m) => deriveMatchInfo(m).belowMap).length,
    };
  }, [matches]);

  const filtered = useMemo(() => {
    const query = search.trim().toLowerCase();
    return (matches ?? []).filter((m) => {
      if (relationshipFilter !== "all" && m.competitor_site_relationship_type !== relationshipFilter) return false;
      if (!query) return true;
      return [m.product_name, m.competitor_site_name, m.competitor_site_domain, m.competitor_product_title].some(
        (field) => field?.toLowerCase().includes(query)
      );
    });
  }, [matches, search, relationshipFilter]);

  const byProduct = useMemo(() => {
    const map = new Map<number, { name: string; price: string | null; currency: string; minPrice: string | null; matches: TrackedMatch[] }>();
    for (const m of filtered) {
      if (!map.has(m.product_id)) {
        map.set(m.product_id, { name: m.product_name, price: m.product_price, currency: m.product_currency, minPrice: m.product_min_price, matches: [] });
      }
      map.get(m.product_id)!.matches.push(m);
    }
    return Array.from(map.entries())
      .map(([productId, data]) => ({ productId, ...data }))
      .sort((a, b) => a.name.localeCompare(b.name));
  }, [filtered]);

  const byCompetitor = useMemo(() => {
    const map = new Map<number, { domain: string; name: string | null; relationshipType: DiscoveryMode; matches: TrackedMatch[] }>();
    for (const m of filtered) {
      if (!map.has(m.competitor_site_id)) {
        map.set(m.competitor_site_id, {
          domain: m.competitor_site_domain,
          name: m.competitor_site_name,
          relationshipType: m.competitor_site_relationship_type,
          matches: [],
        });
      }
      map.get(m.competitor_site_id)!.matches.push(m);
    }
    return Array.from(map.entries())
      .map(([siteId, data]) => ({ siteId, ...data }))
      .sort((a, b) => b.matches.length - a.matches.length);
  }, [filtered]);

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
          No confirmed matches yet. Confirm a match on a{" "}
          <Link href="/discovery" className="text-accent hover:underline">
            competitor's product page
          </Link>{" "}
          to start tracking it here.
        </p>
      )}

      {matches && matches.length > 0 && (
        <>
          {/* At-a-glance counts — the exact "which competitors, how many
              products" overview this page previously buried inside the
              card list below. */}
          <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatTile icon={Package} label="Products tracked" value={stats.products} />
            <StatTile icon={Store} label="Competitors tracked" value={stats.competitors} />
            <StatTile icon={Link2} label="Confirmed matches" value={stats.matches} />
            <StatTile icon={AlertTriangle} label="Below MAP floor" value={stats.belowMap} tone={stats.belowMap > 0 ? "danger" : undefined} />
          </div>

          <div className="mt-6 flex flex-wrap items-center gap-2">
            <div className="relative min-w-[220px] flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-soft" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by product or competitor…"
                className="h-9 pl-9"
              />
            </div>
            {hasCompetitors && hasResellers && (
              <div className="flex flex-wrap gap-1.5">
                {(["all", "competitor", "reseller"] as const).map((key) => (
                  <button
                    key={key}
                    onClick={() => setRelationshipFilter(key)}
                    className={cn(
                      "rounded-full px-2 py-0.5 text-xs font-medium capitalize transition-colors",
                      relationshipFilter === key ? "bg-accent text-white" : "bg-black/[0.03] text-slate hover:bg-black/[0.06]"
                    )}
                  >
                    {key === "all" ? "All" : key === "reseller" ? "Resellers" : "Competitors"}
                  </button>
                ))}
              </div>
            )}
          </div>

          <div className="mt-6 flex items-center gap-1 border-b border-border">
            {(
              [
                ["by-product", "By product", byProduct.length],
                ["by-competitor", "By competitor", byCompetitor.length],
              ] as const
            ).map(([key, label, count]) => (
              <button
                key={key}
                onClick={() => setView(key)}
                className={cn(
                  "border-b-2 px-3 py-2 text-sm font-medium transition-colors",
                  view === key ? "border-accent text-ink" : "border-transparent text-slate-soft hover:text-ink"
                )}
              >
                {label}
                <span className="ml-1 tabular-nums opacity-70">({count})</span>
              </button>
            ))}
          </div>

          {filtered.length === 0 ? (
            <p className="mt-6 text-sm text-slate">No tracked matches found for your search or filter.</p>
          ) : view === "by-product" ? (
            <div className="mt-4 overflow-x-auto rounded-xl border border-border">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="border-b border-border bg-black/[0.02] text-left text-xs font-medium uppercase tracking-wide text-slate-soft">
                  <tr>
                    <th className="px-3 py-2 font-medium">Product</th>
                    <th className="px-3 py-2 font-medium">Tracked competitors</th>
                  </tr>
                </thead>
                <tbody>
                  {byProduct.map((group) => (
                    <tr key={group.productId} className="border-b border-border align-top last:border-0">
                      <td className="px-3 py-3">
                        <Link href={`/catalog?highlight=${group.productId}`} className="font-medium text-ink hover:text-accent">
                          {group.name}
                        </Link>
                        <div className="text-xs tabular-nums text-slate-soft">
                          {group.price != null ? `${group.currency} ${Number(group.price).toFixed(2)}` : "No price set"}
                        </div>
                        {group.minPrice != null && (
                          <div className="text-xs tabular-nums text-slate-soft" title="Minimum advertised price (MAP)">
                            MAP {group.currency} {Number(group.minPrice).toFixed(2)}
                          </div>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        <MatchCell
                          matches={group.matches}
                          groupKeyFn={(m) => m.competitor_site_id}
                          groupHeader={(m) => ({
                            label: m.competitor_site_name || m.competitor_site_domain,
                            href: `/discovery/${m.competitor_site_id}`,
                            badge: m.competitor_site_relationship_type,
                          })}
                          pillHref={(m) => `/discovery/${m.competitor_site_id}?q=${encodeURIComponent(m.competitor_product_title)}`}
                          pillLabel={(m) => m.competitor_product_title}
                          singleHref={(m) => `/discovery/${m.competitor_site_id}?q=${encodeURIComponent(m.competitor_product_title)}`}
                          singleLabel={(m) => m.competitor_site_name || m.competitor_site_domain}
                          singleBadge={(m) => m.competitor_site_relationship_type}
                        />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-xl border border-border">
              <table className="w-full min-w-[640px] text-sm">
                <thead className="border-b border-border bg-black/[0.02] text-left text-xs font-medium uppercase tracking-wide text-slate-soft">
                  <tr>
                    <th className="px-3 py-2 font-medium">Competitor</th>
                    <th className="px-3 py-2 font-medium">Your products tracked</th>
                  </tr>
                </thead>
                <tbody>
                  {byCompetitor.map((group) => (
                    <tr key={group.siteId} className="border-b border-border align-top last:border-0">
                      <td className="px-3 py-3">
                        <Link
                          href={`/discovery/${group.siteId}`}
                          className="inline-flex items-center gap-1 font-medium text-ink hover:text-accent"
                        >
                          {group.name || group.domain}
                          <ExternalLink className="size-3" />
                        </Link>
                        <div className="mt-1">
                          <Badge tone={group.relationshipType === "reseller" ? "accent" : "neutral"}>{group.relationshipType}</Badge>
                        </div>
                      </td>
                      <td className="px-3 py-3">
                        <MatchCell
                          matches={group.matches}
                          groupKeyFn={(m) => m.product_id}
                          groupHeader={(m) => ({
                            label: m.product_name,
                            href: `/catalog?highlight=${m.product_id}`,
                          })}
                          pillHref={(m) => `/discovery/${m.competitor_site_id}?q=${encodeURIComponent(m.competitor_product_title)}`}
                          pillLabel={(m) => m.competitor_product_title}
                          singleHref={(m) => `/catalog?highlight=${m.product_id}`}
                          singleLabel={(m) => m.product_name}
                        />
                        {group.matches.some((m) => m.match_method === "ai_auto") && (
                          <div className="mt-1.5">
                            <ConfidenceBadge
                              score={Math.round(
                                group.matches.filter((m) => m.confidence != null).reduce((sum, m) => sum + (m.confidence ?? 0), 0) /
                                  Math.max(1, group.matches.filter((m) => m.confidence != null).length)
                              )}
                              tooltip={`${MATCH_CONFIDENCE_TOOLTIP} (average across ${group.matches.length} AI-suggested and manual matches with this competitor)`}
                            />
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
