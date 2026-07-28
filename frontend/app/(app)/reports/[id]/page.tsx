"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Compass,
  Download,
  FileText,
  Layers,
  Lightbulb,
  Link2,
  Printer,
  TrendingDown,
  TrendingUp,
} from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import {
  api,
  KNOWN_OBJECTIVES,
  type CompetitorReport,
  type PriceComparisonRow,
  type ProductMetrics,
  type SiteCoverage,
} from "@/lib/api";
import { priceDeltaFromPct } from "@/lib/pricing";
import { cn } from "@/lib/utils";

const ALERT_TONE: Record<string, BadgeTone> = {
  map_violation: "danger",
  price_anomaly: "accent",
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
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: number;
  tone?: "danger" | "good";
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
        <p className="text-xs text-slate-soft">{label}</p>
      </div>
    </Card>
  );
}

function MetricsBadges({ metrics }: { metrics: ProductMetrics }) {
  if (metrics.price_rank == null) {
    return <Badge tone="neutral">No same-currency data</Badge>;
  }
  return (
    <div className="flex flex-col items-start gap-1">
      <Badge tone="accent">
        Rank #{metrics.price_rank} of {metrics.same_currency_competitors_count + 1}
      </Badge>
      <Badge tone="neutral">Index {metrics.price_index}</Badge>
    </div>
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
        <span className="font-medium text-ink">{site.competitor_site_name || site.competitor_site_domain}</span>
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

type TabKey = "overview" | "comparison" | "coverage";

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const reportId = Number(params.id);

  const [report, setReport] = useState<CompetitorReport | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [tab, setTab] = useState<TabKey>("overview");

  useEffect(() => {
    api.reporting.get(reportId).then(setReport).catch(() => setNotFound(true));
  }, [reportId]);

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

  const tabs: Array<[TabKey, string, number | undefined]> = [
    ["overview", "Overview", undefined],
    ["comparison", "Price comparison", report.content.price_comparison.length],
  ];
  if (hasCoverage) {
    tabs.push(["coverage", "Market coverage", report.content.market_coverage.sites.length]);
  }

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
            </div>
          }
        />
      </div>

      {report.status === "failed" && (
        <p className="mt-4 text-sm text-danger">
          The AI summary couldn't be generated ({report.error_message}) — the price comparison below is still accurate.
        </p>
      )}

      {/* At-a-glance KPIs so a manager can read the headline numbers without
          scrolling into any section's detail. */}
      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatTile icon={Link2} label="Matches tracked" value={stats.matches_tracked} />
        <StatTile icon={AlertTriangle} label="Alerts" value={stats.alerts_count} tone={stats.alerts_count > 0 ? "danger" : undefined} />
        <StatTile icon={TrendingUp} label="Price increases" value={stats.price_increases} />
        <StatTile icon={TrendingDown} label="Price decreases" value={stats.price_decreases} tone={stats.price_decreases > 0 ? "good" : undefined} />
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
              tab === key ? "border-accent text-ink" : "border-transparent text-slate-soft hover:text-ink"
            )}
          >
            {label}
            {count != null && <span className="ml-1 tabular-nums opacity-70">({count})</span>}
          </button>
        ))}
      </div>

      <div className={cn("tab-panel mt-6 space-y-4", tab !== "overview" && "hidden")}>
        {report.content.alerts.length > 0 && (
          <div>
            <h2 className="mb-2 flex items-center gap-2 text-sm font-medium text-ink">
              <AlertTriangle className="size-4 text-danger" />
              Alerts ({report.content.alerts.length})
            </h2>
            <div className="grid grid-cols-1 gap-2 lg:grid-cols-2">
              {report.content.alerts.map((alert) => (
                <Card key={`${alert.type}-${alert.match_id}`} className="flex items-start gap-2">
                  <Badge tone={ALERT_TONE[alert.type] ?? "neutral"} className="mt-0.5 shrink-0 capitalize">
                    {alert.type.replace("_", " ")}
                  </Badge>
                  <p className="text-sm text-ink">{alert.message}</p>
                </Card>
              ))}
            </div>
          </div>
        )}

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

        {report.content.competitive_gaps && (
          <SectionCard icon={Layers} title="Competitive gaps">
            {report.content.competitive_gaps}
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

      <div className={cn("tab-panel mt-6", tab !== "comparison" && "hidden")}>
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
                    <div className="font-medium text-ink">{group.product_name}</div>
                    <div className="text-xs tabular-nums text-slate-soft">
                      {group.product_currency} {group.product_price.toFixed(2)}
                    </div>
                  </td>
                  <td className="px-3 py-3">
                    <MetricsBadges metrics={group.metrics} />
                  </td>
                  <td className="px-3 py-3">
                    {group.metrics.cheapest_competitor_name ? (
                      <>
                        <div className="text-ink">{group.metrics.cheapest_competitor_name}</div>
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
        <div className={cn("tab-panel mt-6", tab !== "coverage" && "hidden")}>
          {report.content.competitive_gaps && (
            <p className="mb-4 text-sm leading-relaxed text-slate">{report.content.competitive_gaps}</p>
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
