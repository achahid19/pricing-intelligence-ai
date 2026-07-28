"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Download, ExternalLink, Printer } from "lucide-react";

import { ConfidenceBadge } from "@/components/discovery/ConfidenceBadge";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import {
  api,
  KNOWN_OBJECTIVES,
  type AlertItem,
  type CompetitorReport,
  type PriceComparisonRow,
  type ProductMetrics,
  type SiteCoverage,
} from "@/lib/api";
import { priceDeltaFromPct } from "@/lib/pricing";

const MATCH_CONFIDENCE_TOOLTIP =
  "The AI's own self-assessed confidence that these are genuinely the same or a directly comparable item — not a verified metric.";

const ALERT_TONE: Record<string, BadgeTone> = {
  map_violation: "danger",
  price_anomaly: "accent",
};

const STATUS_TONE: Record<string, BadgeTone> = {
  completed: "good",
  failed: "danger",
};

function MetricsBadges({ metrics }: { metrics: ProductMetrics }) {
  if (metrics.price_rank == null) {
    return <Badge tone="neutral">No same-currency competitor data</Badge>;
  }
  return (
    <>
      <Badge tone="accent">
        Ranked #{metrics.price_rank} of {metrics.same_currency_competitors_count + 1}
      </Badge>
      <Badge tone="neutral">Price index {metrics.price_index}</Badge>
    </>
  );
}

function ComparisonRow({ row }: { row: PriceComparisonRow }) {
  const delta = row.same_currency && row.price_delta_pct != null ? priceDeltaFromPct(row.price_delta_pct) : null;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 border-t border-border py-2.5 first:border-t-0 first:pt-0">
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href={`/discovery/${row.competitor_site_id}`}
            className="inline-flex items-center gap-1 text-sm font-medium text-ink hover:text-accent"
          >
            {row.competitor_site_name || row.competitor_site_domain}
            <ExternalLink className="size-3" />
          </Link>
          <Badge tone={row.competitor_site_relationship_type === "reseller" ? "accent" : "neutral"}>
            {row.competitor_site_relationship_type}
          </Badge>
          {row.match_method === "ai_auto" && <ConfidenceBadge score={row.confidence} tooltip={MATCH_CONFIDENCE_TOOLTIP} />}
        </div>
        <p className="mt-1 text-xs text-slate-soft">{row.competitor_product_title}</p>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {row.competitor_product_price != null ? (
          <span className="text-sm tabular-nums text-ink">
            {row.competitor_product_currency} {row.competitor_product_price.toFixed(2)}
          </span>
        ) : (
          <Badge tone="neutral">No price found</Badge>
        )}
        {delta && <Badge tone={delta.tone}>{delta.label}</Badge>}
        {!row.same_currency && row.competitor_product_price != null && <Badge tone="neutral">Different currency</Badge>}
        {row.below_map && <Badge tone="danger">Below MAP floor</Badge>}
      </div>
    </div>
  );
}

function AlertCard({ alert }: { alert: AlertItem }) {
  return (
    <Card className="flex items-start gap-2">
      <Badge tone={ALERT_TONE[alert.type] ?? "neutral"} className="mt-0.5 shrink-0 capitalize">
        {alert.type.replace("_", " ")}
      </Badge>
      <p className="text-sm text-ink">{alert.message}</p>
    </Card>
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
            <span
              key={p.competitor_product_id}
              className="rounded-full bg-black/[0.03] px-2 py-0.5 text-xs text-slate"
            >
              {p.title}
            </span>
          ))}
        </div>
      )}
    </Card>
  );
}

const OBJECTIVE_LABEL: Record<string, string> = Object.fromEntries(KNOWN_OBJECTIVES.map((o) => [o.value, o.label]));

export default function ReportDetailPage() {
  const params = useParams<{ id: string }>();
  const reportId = Number(params.id);

  const [report, setReport] = useState<CompetitorReport | null>(null);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    api.reporting.get(reportId).then(setReport).catch(() => setNotFound(true));
  }, [reportId]);

  if (notFound) {
    return (
      <div className="mx-auto max-w-5xl px-8 py-10">
        <p className="text-sm text-danger">Couldn't find this report.</p>
        <Link href="/reports" className="mt-2 inline-block text-sm text-accent hover:underline">
          Back to Reports
        </Link>
      </div>
    );
  }

  if (!report) {
    return (
      <div className="mx-auto max-w-5xl px-8 py-10">
        <p className="text-sm text-slate-soft">Loading…</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <style>{"@media print { aside, .no-print { display: none !important; } }"}</style>

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

      {report.content.alerts.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-medium text-ink">Alerts ({report.content.alerts.length})</h2>
          <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-2">
            {report.content.alerts.map((alert) => (
              <AlertCard key={`${alert.type}-${alert.match_id}`} alert={alert} />
            ))}
          </div>
        </div>
      )}

      {report.content.executive_summary && (
        <div className="mt-8">
          <h2 className="text-sm font-medium text-ink">Executive summary</h2>
          <p className="mt-2 text-sm text-slate">{report.content.executive_summary}</p>
        </div>
      )}

      {report.content.market_position && (
        <div className="mt-8">
          <h2 className="text-sm font-medium text-ink">Market position</h2>
          <p className="mt-2 text-sm text-slate">{report.content.market_position}</p>
        </div>
      )}

      {(report.content.competitive_gaps || report.content.market_coverage.sites.length > 0) && (
        <div className="mt-8">
          <h2 className="text-sm font-medium text-ink">Market coverage</h2>
          {report.content.competitive_gaps && <p className="mt-2 text-sm text-slate">{report.content.competitive_gaps}</p>}
          {report.content.market_coverage.sites.length > 0 && (
            <div className="mt-3 grid grid-cols-1 gap-2 lg:grid-cols-2">
              {report.content.market_coverage.sites.map((site) => (
                <SiteCoverageCard key={site.competitor_site_id} site={site} />
              ))}
            </div>
          )}
        </div>
      )}

      {report.content.recommendations.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-medium text-ink">Recommendations</h2>
          <div className="mt-2 space-y-2">
            {report.content.recommendations.map((rec, i) => (
              <Card key={i}>
                <Badge tone="accent">{OBJECTIVE_LABEL[rec.objective] ?? rec.objective}</Badge>
                <p className="mt-2 text-sm text-ink">{rec.text}</p>
              </Card>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8">
        <h2 className="text-sm font-medium text-ink">Price comparison ({report.content.price_comparison.length})</h2>
        <div className="mt-2 grid grid-cols-1 gap-3 lg:grid-cols-2">
          {report.content.price_comparison.map((group) => (
            <Card key={group.product_id}>
              <div className="flex items-center justify-between gap-2">
                <h3 className="font-medium text-ink">{group.product_name}</h3>
                <span className="shrink-0 text-sm tabular-nums text-slate-soft">
                  {group.product_currency} {group.product_price.toFixed(2)}
                </span>
              </div>
              <div className="mt-1.5 flex flex-wrap gap-1.5">
                <MetricsBadges metrics={group.metrics} />
              </div>
              <div className="mt-1">
                {group.matches.map((row) => (
                  <ComparisonRow key={row.match_id} row={row} />
                ))}
              </div>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
