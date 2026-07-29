"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowLeft,
  ArrowUpRight,
  Compass,
  Download,
  FileText,
  Layers,
  Lightbulb,
  Link2,
  Minus,
  Printer,
  Trash2,
  TrendingDown,
  TrendingUp,
  X,
} from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { PageHeader } from "@/components/ui/page-header";
import {
  api,
  ApiError,
  KNOWN_OBJECTIVES,
  type CompetitorReport,
  type PriceComparisonRow,
  type ProductMetrics,
  type SiteCoverage,
  type TrendInfo,
} from "@/lib/api";
import { priceDeltaFromPct } from "@/lib/pricing";
import { usePersistedTab } from "@/lib/usePersistedTab";
import { cn } from "@/lib/utils";

const ALERT_TONE: Record<string, BadgeTone> = {
  map_violation: "danger",
  price_anomaly: "accent",
  new_competitor_product: "accent",
  own_price_change: "accent",
};

const STATUS_TONE: Record<string, BadgeTone> = {
  completed: "good",
  failed: "danger",
};

const OBJECTIVE_LABEL: Record<string, string> = Object.fromEntries(KNOWN_OBJECTIVES.map((o) => [o.value, o.label]));

function StatTile({
  icon: Icon,
  label,
  value,
  tone,
  tooltip,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  tone?: "danger" | "good";
  tooltip?: string;
}) {
  return (
    <Card className="flex items-center gap-3">
      <div
        className={cn(
          "flex size-9 shrink-0 items-center justify-center rounded-lg",
          tone === "danger" ? "bg-danger/10 text-danger" : tone === "good" ? "bg-good/10 text-good" : "bg-slate/10 text-slate"
        )}
      >
        <Icon className="size-4.5" />
      </div>
      <div>
        <p className="text-xl font-semibold tabular-nums leading-tight text-ink">{value}</p>
        <p className="flex items-center gap-1 text-xs text-slate-soft">
          {label}
          {tooltip && <InfoTooltip text={tooltip} />}
        </p>
      </div>
    </Card>
  );
}

function MetricsBadges({
  metrics,
  productPrice,
  productCurrency,
}: {
  metrics: ProductMetrics;
  productPrice: number;
  productCurrency: string;
}) {
  if (metrics.price_rank == null) {
    return <Badge tone="neutral">No same-currency data</Badge>;
  }
  // Derived, not a new backend field: price_index = product_price / marketAvg * 100.
  const marketAvg = metrics.price_index ? (productPrice / metrics.price_index) * 100 : null;
  return (
    <div className="flex flex-col items-start gap-1">
      <Badge tone="accent">
        Rank #{metrics.price_rank} of {metrics.same_currency_competitors_count + 1}
      </Badge>
      <Badge tone="neutral">Index {metrics.price_index}</Badge>
      {marketAvg != null && (
        <span className="text-xs text-slate-soft">
          Avg {productCurrency} {marketAvg.toFixed(2)} · {metrics.sellers_cheaper}/{metrics.same_currency_competitors_count} cheaper
        </span>
      )}
    </div>
  );
}

// A competitor's own price trend since the previous report — independent
// of same_currency, since it only ever compares that competitor's price
// to itself over time, never to your own price. Shown even on
// cross-currency rows, where price_delta_pct/priceDeltaFromPct can't say
// anything at all.
function TrendIndicator({ trend }: { trend: TrendInfo | null | undefined }) {
  if (!trend || trend.direction === "same") return null;
  const Icon = trend.direction === "up" ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      title={`${trend.direction === "up" ? "Up" : "Down"} ${Math.abs(trend.delta_pct)}% since the previous report (was ${trend.previous_price.toFixed(2)} on ${new Date(trend.previous_checked_at).toLocaleDateString()})`}
      className={cn("inline-flex items-center", trend.is_anomaly ? "text-accent" : "text-slate-soft")}
    >
      <Icon className="size-3" />
    </span>
  );
}

function MatchPill({ row }: { row: PriceComparisonRow }) {
  const delta = row.same_currency && row.price_delta_pct != null ? priceDeltaFromPct(row.price_delta_pct) : null;
  const priceColor = delta ? (delta.tone === "good" ? "text-good" : delta.tone === "danger" ? "text-danger" : "text-slate-soft") : "text-slate-soft";

  return (
    <Link
      href={`/discovery/${row.competitor_site_id}`}
      title={delta ? delta.label : row.same_currency ? undefined : "Different currency — not directly comparable"}
      className="inline-flex items-center gap-1.5 rounded-lg border border-border px-2 py-1 text-xs hover:border-accent"
    >
      <span className="font-medium text-ink">{row.competitor_site_name || row.competitor_site_domain}</span>
      {row.competitor_product_price != null ? (
        <span className={cn("tabular-nums", priceColor)}>
          {row.competitor_product_currency} {row.competitor_product_price.toFixed(2)}
        </span>
      ) : (
        <span className="text-slate-soft">no price</span>
      )}
      <TrendIndicator trend={row.trend} />
      {row.below_map && (
        <Badge tone="danger" className="px-1.5 py-0">
          MAP
        </Badge>
      )}
    </Link>
  );
}

function SiteCoverageCard({ site }: { site: SiteCoverage }) {
  const unmatchedCount = site.total_products_discovered - site.matched_products_count;
  return (
    <Card>
      <div className="flex items-center justify-between gap-2">
        <Link href={`/discovery/${site.competitor_site_id}`} className="font-medium text-ink hover:text-accent">
          {site.competitor_site_name || site.competitor_site_domain}
        </Link>
        <Badge tone={site.relationship_type === "reseller" ? "accent" : "neutral"}>{site.relationship_type}</Badge>
      </div>
      <p className="mt-1 text-xs text-slate-soft">
        {site.total_products_discovered} discovered · {site.matched_products_count} matched
        {unmatchedCount > 0 && ` · ${unmatchedCount} unmatched`}
      </p>
      {site.unmatched_sample.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1">
          {site.unmatched_sample.slice(0, 5).map((p) => (
            <span key={p.competitor_product_id} className="rounded-full bg-black/[0.03] px-2 py-0.5 text-xs text-slate">
              {p.title}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}

function SectionCard({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Card>
      <div className="flex items-center gap-2 text-ink">
        <Icon className="size-4 text-accent" />
        <h2 className="text-sm font-medium">{title}</h2>
      </div>
      <div className="mt-2 text-sm leading-relaxed text-slate">{children}</div>
    </Card>
  );
}

type TabKey = "overview" | "alerts" | "comparison" | "coverage";
const TAB_OPTIONS = ["overview", "alerts", "comparison", "coverage"] as const;

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const reportId = Number(params.id);

  const [report, setReport] = useState<CompetitorReport | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [tab, setTab] = usePersistedTab<TabKey>("tab", `report-tab-${reportId}`, TAB_OPTIONS, "overview");
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  useEffect(() => {
    api.reporting.get(reportId).then(setReport).catch(() => setNotFound(true));
  }, [reportId]);

  async function handleDelete() {
    setDeleting(true);
    try {
      await api.reporting.delete(reportId);
      router.push("/reports");
    } catch (err) {
      setDeleteError(err instanceof ApiError ? err.message : "Couldn't delete this report. Try again.");
      setDeleting(false);
    }
  }

  if (notFound) {
    return (
      <div className="mx-auto max-w-6xl px-8 py-10">
        <p className="text-sm text-danger">Couldn't find this report.</p>
        <Link href="/reports" className="mt-2 inline-block text-sm text-accent hover:underline">
          Back to Reports
        </Link>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="mx-auto max-w-6xl px-8 py-10">
        <p className="text-sm text-slate-soft">Loading…</p>
      </div>
    );
  }

  const stats = report.content.summary_stats;
  const hasCoverage = Boolean(report.content.competitive_gaps) || report.content.market_coverage.sites.length > 0;

  // A breakdown by alert type — map_violations_count is already computed
  // server-side; the anomaly split by direction is derived here from data
  // already on each alert (no backend change needed) since "price
  // anomaly" alone doesn't say whether it jumped or dropped.
  const priceJumped = report.content.alerts.filter((a) => a.type === "price_anomaly" && a.trend?.direction === "up").length;
  const priceDropped = report.content.alerts.filter((a) => a.type === "price_anomaly" && a.trend?.direction === "down").length;
  const newCompetitorProducts = report.content.alerts
    .filter((a) => a.type === "new_competitor_product")
    .reduce((sum, a) => sum + (a.new_product_count ?? 0), 0);
  const ownPriceChanges = report.content.alerts.filter((a) => a.type === "own_price_change").length;

  const tabs: Array<[TabKey, string, number | undefined]> = [
    ["overview", "Overview", undefined],
    ["alerts", "Alerts", report.content.alerts.length],
    ["comparison", "Price comparison", report.content.price_comparison.length],
  ];
  if (hasCoverage) {
    tabs.push(["coverage", "Market coverage", report.content.market_coverage.sites.length]);
  }
  // A persisted/URL "coverage" tab can point at a report that turns out to
  // have none — fall back for rendering rather than getting stuck with
  // every panel hidden (no useEffect needed, self-corrects every render).
  const effectiveTab: TabKey = tab === "coverage" && !hasCoverage ? "overview" : tab;

  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      <style>
        {"@media print { aside, .no-print { display: none !important; } .tab-panel { display: block !important; margin-top: 1.5rem; } }"}
      </style>

      <Link href="/reports" className="no-print inline-flex items-center gap-1.5 text-sm text-slate-soft hover:text-ink">
        <ArrowLeft className="size-4" />
        Back to Reports
      </Link>

      <div className="mt-4">
        <PageHeader
          title={new Date(report.generated_at).toLocaleString()}
          description={
            <span className="inline-flex items-center gap-2">
              <Badge tone={STATUS_TONE[report.status] ?? "neutral"} className="capitalize">
                {report.status}
              </Badge>
              <span className="capitalize">{report.trigger_source}</span>
            </span>
          }
          actions={
            <div className="no-print flex gap-2">
              <a href={api.reporting.exportUrl(report.id)} download>
                <Button variant="outline" size="sm">
                  <Download className="size-3.5" />
                  Export CSV
                </Button>
              </a>
              <Button variant="outline" size="sm" onClick={() => window.print()}>
                <Printer className="size-3.5" />
                Print
              </Button>
              {confirmingDelete ? (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={handleDelete}
                    disabled={deleting}
                    className="border-danger/30 text-danger hover:bg-danger/10"
                  >
                    {deleting ? "Deleting…" : "Confirm delete"}
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => setConfirmingDelete(false)} disabled={deleting}>
                    <X className="size-3.5" />
                  </Button>
                </>
              ) : (
                <Button variant="outline" size="sm" onClick={() => setConfirmingDelete(true)}>
                  <Trash2 className="size-3.5" />
                  Delete
                </Button>
              )}
            </div>
          }
        />
      </div>

      {report.status === "failed" && (
        <p className="mt-4 text-sm text-danger">
          The AI summary couldn't be generated ({report.error_message}) — the price comparison below is still accurate.
        </p>
      )}

      {deleteError && <p className="mt-4 text-sm text-danger">{deleteError}</p>}

      {/* At-a-glance KPIs so a manager can read the headline numbers without
          scrolling into any section's detail. */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile icon={Link2} label="Matches tracked" value={stats.matches_tracked} />
        <StatTile icon={AlertTriangle} label="Alerts" value={stats.alerts_count} tone={stats.alerts_count > 0 ? "danger" : undefined} />
        <StatTile
          icon={TrendingUp}
          label="Price increases"
          value={stats.price_increases}
          tooltip="Competitors whose own price rose since the previous report — not how many are pricier than you right now."
        />
        <StatTile
          icon={TrendingDown}
          label="Price decreases"
          value={stats.price_decreases}
          tone={stats.price_decreases > 0 ? "good" : undefined}
          tooltip="Competitors whose own price dropped since the previous report. Both tiles read 0 on a workspace's first report — there's no prior price yet to compare against."
        />
      </div>

      {/* Tabs instead of one long vertical stack — the narrative, the
          product-by-product comparison, and the full-catalog coverage detail
          are three different reading tasks, not something scanned together. */}
      <div className="no-print mt-8 flex items-center gap-1 border-b border-border">
        {tabs.map(([key, label, count]) => (
          <button
            key={key}
            onClick={() => setTab(key)}
            className={cn(
              "border-b-2 px-3 py-2 text-sm font-medium transition-colors",
              effectiveTab === key ? "border-accent text-ink" : "border-transparent text-slate-soft hover:text-ink"
            )}
          >
            {label}
            {count != null && <span className="ml-1 tabular-nums opacity-70">({count})</span>}
          </button>
        ))}
      </div>

      <div className={cn("tab-panel mt-6 space-y-4", effectiveTab !== "overview" && "hidden")}>
        {report.content.executive_summary && (
          <SectionCard icon={FileText} title="Executive summary">
            {report.content.executive_summary}
          </SectionCard>
        )}

        {report.content.market_position && (
          <SectionCard icon={Compass} title="Market position">
            {report.content.market_position}
          </SectionCard>
        )}

        {report.content.recommendations.length > 0 && (
          <div>
            <h2 className="mb-2 flex items-center gap-2 text-sm font-medium text-ink">
              <Lightbulb className="size-4 text-accent" />
              Recommendations
            </h2>
            <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
              {report.content.recommendations.map((rec, i) => (
                <Card key={i}>
                  <Badge tone="accent">{OBJECTIVE_LABEL[rec.objective] ?? rec.objective}</Badge>
                  <p className="mt-2 text-sm text-ink">{rec.text}</p>
                </Card>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className={cn("tab-panel mt-6 space-y-4", effectiveTab !== "alerts" && "hidden")}>
        <div className="flex flex-wrap gap-2">
          <Badge tone={stats.map_violations_count > 0 ? "danger" : "neutral"}>
            {stats.map_violations_count} MAP violation{stats.map_violations_count === 1 ? "" : "s"}
          </Badge>
          <Badge tone={priceJumped > 0 ? "accent" : "neutral"}>
            {priceJumped} price jump{priceJumped === 1 ? "" : "s"}
          </Badge>
          <Badge tone={priceDropped > 0 ? "accent" : "neutral"}>
            {priceDropped} price drop{priceDropped === 1 ? "" : "s"}
          </Badge>
          <Badge tone={newCompetitorProducts > 0 ? "accent" : "neutral"}>
            {newCompetitorProducts} new competitor product{newCompetitorProducts === 1 ? "" : "s"}
          </Badge>
          <Badge tone={ownPriceChanges > 0 ? "accent" : "neutral"}>
            {ownPriceChanges} own price change{ownPriceChanges === 1 ? "" : "s"}
          </Badge>
        </div>

        {report.content.alerts.length > 0 ? (
          <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
            {report.content.alerts.map((alert) => (
              <Card
                key={`${alert.type}-${alert.match_id ?? alert.competitor_site_id ?? alert.product_id}`}
                className="flex items-start gap-2"
              >
                <Badge tone={ALERT_TONE[alert.type] ?? "neutral"} className="mt-0.5 shrink-0 capitalize">
                  {alert.type.replaceAll("_", " ")}
                </Badge>
                <div className="min-w-0">
                  <p className="text-sm text-ink">{alert.message}</p>
                  {alert.competitor_site_id != null ? (
                    <Link
                      href={`/discovery/${alert.competitor_site_id}`}
                      className="mt-1 inline-block text-xs font-medium text-accent hover:underline"
                    >
                      View {alert.competitor_site_name || alert.competitor_site_domain} →
                    </Link>
                  ) : (
                    alert.product_id != null && (
                      <Link
                        href={`/catalog?highlight=${alert.product_id}`}
                        className="mt-1 inline-block text-xs font-medium text-accent hover:underline"
                      >
                        View {alert.product_name} →
                      </Link>
                    )
                  )}
                </div>
              </Card>
            ))}
          </div>
        ) : (
          <Card className="text-sm text-slate">
            <p className="font-medium text-ink">No alerts this period.</p>
            <p className="mt-2">An alert appears here when:</p>
            <ul className="mt-1 list-disc space-y-1 pl-5">
              <li>
                <span className="font-medium text-ink">MAP violation</span> — a reseller advertises one of your
                products below the minimum price you've set for it.
              </li>
              <li>
                <span className="font-medium text-ink">Price anomaly</span> — a tracked competitor's price for a
                matched product moves by 15% or more since your previous report.
              </li>
              <li>
                <span className="font-medium text-ink">New competitor product</span> — a saved competitor's
                catalog gains products it didn't have at your previous report.
              </li>
              <li>
                <span className="font-medium text-ink">Own price change</span> — one of your own product's
                prices moves by 15% or more since your previous report.
              </li>
            </ul>
          </Card>
        )}
      </div>

      <div className={cn("tab-panel mt-6", effectiveTab !== "comparison" && "hidden")}>
        <div className="overflow-x-auto rounded-xl border border-border">
          <table className="w-full min-w-[720px] text-sm">
            <thead className="border-b border-border bg-black/[0.02] text-left text-xs font-medium uppercase tracking-wide text-slate-soft">
              <tr>
                <th className="px-3 py-2 font-medium">Product</th>
                <th className="px-3 py-2 font-medium">Ranking</th>
                <th className="px-3 py-2 font-medium">Cheapest competitor</th>
                <th className="px-3 py-2 font-medium">Tracked competitors</th>
              </tr>
            </thead>
            <tbody>
              {report.content.price_comparison.map((group) => (
                <tr key={group.product_id} className="border-b border-border align-top last:border-0">
                  <td className="px-3 py-3">
                    <Link href={`/catalog?highlight=${group.product_id}`} className="font-medium text-ink hover:text-accent">
                      {group.product_name}
                    </Link>
                    <div className="flex items-center gap-1 text-xs tabular-nums text-slate-soft">
                      {group.product_currency} {group.product_price.toFixed(2)}
                      <TrendIndicator trend={group.own_trend} />
                    </div>
                    {group.product_min_price != null && (
                      <div className="text-xs tabular-nums text-slate-soft" title="Minimum advertised price (MAP)">
                        MAP {group.product_currency} {group.product_min_price.toFixed(2)}
                      </div>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <MetricsBadges metrics={group.metrics} productPrice={group.product_price} productCurrency={group.product_currency} />
                  </td>
                  <td className="px-3 py-3">
                    {group.metrics.cheapest_competitor_name ? (
                      <>
                        {group.metrics.cheapest_competitor_site_id ? (
                          <Link
                            href={`/discovery/${group.metrics.cheapest_competitor_site_id}`}
                            className="text-ink hover:text-accent"
                          >
                            {group.metrics.cheapest_competitor_name}
                          </Link>
                        ) : (
                          <div className="text-ink">{group.metrics.cheapest_competitor_name}</div>
                        )}
                        <div className="text-xs tabular-nums text-slate-soft">
                          {group.metrics.cheapest_competitor_price?.toFixed(2)}
                        </div>
                      </>
                    ) : (
                      <span className="text-slate-soft">—</span>
                    )}
                  </td>
                  <td className="px-3 py-3">
                    <div className="flex flex-wrap gap-1.5">
                      {group.matches.map((row) => (
                        <MatchPill key={row.match_id} row={row} />
                      ))}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {hasCoverage && (
        <div className={cn("tab-panel mt-6 space-y-4", effectiveTab !== "coverage" && "hidden")}>
          {report.content.competitive_gaps && (
            <SectionCard icon={Layers} title="Competitive gaps">
              {report.content.competitive_gaps}
            </SectionCard>
          )}
          {report.content.market_coverage.sites.length > 0 && (
            <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
              {report.content.market_coverage.sites.map((site) => (
                <SiteCoverageCard key={site.competitor_site_id} site={site} />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
