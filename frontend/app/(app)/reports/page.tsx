"use client";

import { useMemo, useState, useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Check, Download, Pencil, Search, Sparkles, Trash2, X } from "lucide-react";

import { AiProviderRequiredNotice } from "@/components/ui/ai-provider-notice";
import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { api, ApiError, type CompetitorReport } from "@/lib/api";
import { useAiProviderStatus } from "@/lib/aiProvider";

const STATUS_TONE: Record<string, BadgeTone> = {
  completed: "good",
  failed: "danger",
};

function ReportCard({
  report,
  onOpen,
  onDelete,
  onRename,
  onDownload,
  deleting,
  downloading,
}: {
  report: CompetitorReport;
  onOpen: () => void;
  onDelete: () => Promise<void>;
  onRename: (name: string) => Promise<void>;
  onDownload: () => void;
  deleting: boolean;
  downloading: boolean;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [renaming, setRenaming] = useState(false);
  const [nameDraft, setNameDraft] = useState(report.name ?? "");
  const [saving, setSaving] = useState(false);

  async function handleSaveName() {
    setSaving(true);
    try {
      await onRename(nameDraft);
      setRenaming(false);
    } finally {
      setSaving(false);
    }
  }

  const dateLabel = new Date(report.generated_at).toLocaleString();

  return (
    <a
      href="#"
      onClick={(e) => {
        e.preventDefault();
        if (!renaming) onOpen();
      }}
      className="block"
    >
      <Card interactive={!renaming}>
        <div className="flex items-start justify-between gap-2">
          {renaming ? (
            <div className="flex min-w-0 flex-1 items-center gap-1.5" onClick={(e) => e.stopPropagation()}>
              <Input
                autoFocus
                value={nameDraft}
                onChange={(e) => setNameDraft(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") handleSaveName();
                  if (e.key === "Escape") setRenaming(false);
                }}
                placeholder={dateLabel}
                className="h-8 text-sm"
              />
              <button
                onClick={handleSaveName}
                disabled={saving}
                aria-label="Save name"
                className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-good/10 hover:text-good"
              >
                <Check className="size-4" />
              </button>
              <button
                onClick={() => setRenaming(false)}
                disabled={saving}
                aria-label="Cancel rename"
                className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-black/[0.03] hover:text-ink"
              >
                <X className="size-4" />
              </button>
            </div>
          ) : (
            <div className="flex min-w-0 items-center gap-1.5">
              <span className="truncate text-sm font-medium text-ink">{report.name || dateLabel}</span>
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setNameDraft(report.name ?? "");
                  setRenaming(true);
                }}
                aria-label="Rename report"
                className="shrink-0 rounded-md p-1 text-slate-soft opacity-0 transition-opacity hover:text-ink group-hover:opacity-100"
              >
                <Pencil className="size-3.5" />
              </button>
            </div>
          )}
          <div
            className="flex shrink-0 items-center gap-1.5"
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
            }}
          >
            <Badge tone={STATUS_TONE[report.status] ?? "neutral"} className="capitalize">
              {report.status}
            </Badge>
            <button
              onClick={onDownload}
              disabled={downloading}
              aria-label="Download PDF"
              className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-accent/10 hover:text-accent"
            >
              <Download className="size-4" />
            </button>
            {confirmingDelete ? (
              <div className="flex items-center gap-1">
                <button
                  onClick={onDelete}
                  disabled={deleting}
                  className="rounded-md px-2 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/10"
                >
                  {deleting ? "…" : "Confirm"}
                </button>
                <button
                  onClick={() => setConfirmingDelete(false)}
                  aria-label="Cancel delete"
                  className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-black/[0.03] hover:text-ink"
                >
                  <X className="size-4" />
                </button>
              </div>
            ) : (
              <button
                onClick={() => setConfirmingDelete(true)}
                aria-label="Delete report"
                className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-danger/10 hover:text-danger"
              >
                <Trash2 className="size-4" />
              </button>
            )}
          </div>
        </div>
        {report.name && <p className="mt-0.5 text-xs text-slate-soft">{dateLabel}</p>}
        <p className="mt-1 text-xs text-slate-soft capitalize">{report.trigger_source}</p>
        <p className="mt-2 text-sm text-slate">
          {report.content.summary_stats.matches_tracked} matches
          {report.content.summary_stats.alerts_count > 0 && (
            <span className="text-danger"> · {report.content.summary_stats.alerts_count} alerts</span>
          )}
        </p>
      </Card>
    </a>
  );
}

export default function ReportsPage() {
  const router = useRouter();
  const [reports, setReports] = useState<CompetitorReport[] | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [downloading, setDownloading] = useState<number | null>(null);
  const [search, setSearch] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [reportIntervalHours, setReportIntervalHours] = useState<number | null>(null);
  const [startedMessage, setStartedMessage] = useState<string | null>(null);
  const { hasActiveProvider } = useAiProviderStatus();

  function load() {
    api.reporting.list().then(setReports).catch(() => setReports([]));
  }

  useEffect(() => {
    load();
    // Settings defines the schedule but never showed it anywhere near
    // where a due report would actually appear — this is the connection.
    api.workspace.me().then((ws) => setReportIntervalHours(ws.report_interval_hours)).catch(() => {});
  }, []);

  async function handleGenerate() {
    setError(null);
    setStartedMessage(null);
    setGenerating(true);
    try {
      // Fire-and-forget on purpose: this now kicks off the full pipeline
      // in the background (can take minutes — see reporting/service.py's
      // run_full_pipeline), so there's no report id yet to navigate to.
      // The Sidebar's activity bell (via lib/pipelineStatus.tsx's poller)
      // picks this run up within ~15s and links straight to the report
      // once it's actually ready.
      await api.reporting.create();
      setStartedMessage("Report generation started. Check Activity (bell icon) for progress.");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setGenerating(false);
    }
  }

  async function handleDelete(id: number) {
    setDeleting(id);
    try {
      await api.reporting.delete(id);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete this report. Try again.");
    } finally {
      setDeleting(null);
    }
  }

  async function handleRename(id: number, name: string) {
    try {
      await api.reporting.rename(id, name);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't rename this report. Try again.");
      throw err;
    }
  }

  async function handleDownload(id: number) {
    setDownloading(id);
    try {
      await api.reporting.downloadPdf(id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't download this report. Try again.");
    } finally {
      setDownloading(null);
    }
  }

  const hasFilters = Boolean(search.trim() || dateFrom || dateTo);
  const filtered = useMemo(() => {
    if (!reports) return [];
    const query = search.trim().toLowerCase();
    return reports.filter((r) => {
      if (query && !(r.name ?? "").toLowerCase().includes(query)) return false;
      const generated = new Date(r.generated_at);
      if (dateFrom && generated < new Date(`${dateFrom}T00:00:00`)) return false;
      if (dateTo && generated > new Date(`${dateTo}T23:59:59.999`)) return false;
      return true;
    });
  }, [reports, search, dateFrom, dateTo]);

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <PageHeader
        title="Reports"
        description="An AI-written summary of your tracked matches: price comparisons, alerts, and recommendations."
        actions={
          <Button onClick={handleGenerate} disabled={generating || hasActiveProvider === false}>
            <Sparkles className="size-4" />
            {generating ? "Generating…" : "Generate report"}
          </Button>
        }
      />

      {hasActiveProvider === false && (
        <div className="mt-2">
          <AiProviderRequiredNotice action="Report generation" />
        </div>
      )}

      {reportIntervalHours != null && (
        <p className="mt-2 text-sm text-slate-soft">
          Next report generates automatically ({reportIntervalHours === 24 ? "Daily" : "Weekly"}).{" "}
          <Link href="/settings" className="text-accent hover:underline">
            change in Settings →
          </Link>
        </p>
      )}

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}
      {startedMessage && !error && <p className="mt-4 text-sm text-good">{startedMessage}</p>}

      {reports && reports.length > 0 && (
        <div className="mt-6 flex flex-wrap items-end gap-3">
          <div className="relative min-w-[220px] flex-1">
            <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-soft" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search by report name…"
              className="pl-9"
            />
          </div>
          <div className="space-y-1">
            <label htmlFor="date-from" className="text-xs font-medium text-slate">
              From
            </label>
            <Input id="date-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="w-40" />
          </div>
          <div className="space-y-1">
            <label htmlFor="date-to" className="text-xs font-medium text-slate">
              To
            </label>
            <Input id="date-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="w-40" />
          </div>
          {hasFilters && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setSearch("");
                setDateFrom("");
                setDateTo("");
              }}
            >
              Clear filters
            </Button>
          )}
        </div>
      )}

      {!reports && !error && <p className="mt-6 text-sm text-slate-soft">Loading…</p>}

      {reports && reports.length === 0 && (
        <p className="mt-6 text-sm text-slate">
          No reports yet. Confirm at least one{" "}
          <Link href="/discovery" className="text-accent hover:underline">
            priced product match
          </Link>
          , then click "Generate report" above.
        </p>
      )}

      {reports && reports.length > 0 && filtered.length === 0 && (
        <p className="mt-6 text-sm text-slate">No reports match your filters.</p>
      )}

      {filtered.length > 0 && (
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {filtered.map((report) => (
            <div key={report.id} className="group">
              <ReportCard
                report={report}
                onOpen={() => router.push(`/reports/${report.id}`)}
                onDelete={() => handleDelete(report.id)}
                onRename={(name) => handleRename(report.id, name)}
                onDownload={() => handleDownload(report.id)}
                deleting={deleting === report.id}
                downloading={downloading === report.id}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
