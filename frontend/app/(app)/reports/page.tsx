"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Sparkles, Trash2, X } from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { PageHeader } from "@/components/ui/page-header";
import { api, ApiError, type CompetitorReport } from "@/lib/api";

const STATUS_TONE: Record<string, BadgeTone> = {
  completed: "good",
  failed: "danger",
};

export default function ReportsPage() {
  const router = useRouter();
  const [reports, setReports] = useState<CompetitorReport[] | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  function load() {
    api.reporting.list().then(setReports).catch(() => setReports([]));
  }

  useEffect(() => {
    load();
  }, []);

  async function handleGenerate() {
    setError(null);
    setGenerating(true);
    try {
      const report = await api.reporting.create();
      router.push(`/reports/${report.id}`);
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
      setConfirmingDelete(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete this report. Try again.");
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <PageHeader
        title="Reports"
        description="An AI-written summary of your tracked matches — price comparisons, alerts, and recommendations."
        actions={
          <Button onClick={handleGenerate} disabled={generating}>
            <Sparkles className="size-4" />
            {generating ? "Generating…" : "Generate report"}
          </Button>
        }
      />

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}
      {generating && (
        <p className="mt-4 text-sm text-slate-soft">This can take a few seconds — the AI is writing your summary.</p>
      )}

      {!reports && !error && <p className="mt-6 text-sm text-slate-soft">Loading…</p>}

      {reports && reports.length === 0 && (
        <p className="mt-6 text-sm text-slate">
          No reports yet — confirm at least one priced product match, then click "Generate report" above.
        </p>
      )}

      {reports && reports.length > 0 && (
        <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
          {reports.map((report) => (
            <a
              key={report.id}
              href={`/reports/${report.id}`}
              onClick={(e) => {
                e.preventDefault();
                router.push(`/reports/${report.id}`);
              }}
              className="block"
            >
              <Card interactive>
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium text-ink">
                    {new Date(report.generated_at).toLocaleString()}
                  </span>
                  <div
                    className="flex shrink-0 items-center gap-2"
                    onClick={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                    }}
                  >
                    <Badge tone={STATUS_TONE[report.status] ?? "neutral"} className="capitalize">
                      {report.status}
                    </Badge>
                    {confirmingDelete === report.id ? (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleDelete(report.id)}
                          disabled={deleting === report.id}
                          className="rounded-md px-2 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/10"
                        >
                          {deleting === report.id ? "…" : "Confirm"}
                        </button>
                        <button
                          onClick={() => setConfirmingDelete(null)}
                          aria-label="Cancel delete"
                          className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-black/[0.03] hover:text-ink"
                        >
                          <X className="size-4" />
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setConfirmingDelete(report.id)}
                        aria-label="Delete report"
                        className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-danger/10 hover:text-danger"
                      >
                        <Trash2 className="size-4" />
                      </button>
                    )}
                  </div>
                </div>
                <p className="mt-1 text-xs text-slate-soft capitalize">{report.trigger_source}</p>
                <p className="mt-2 text-sm text-slate">
                  {report.content.summary_stats.matches_tracked} matches
                  {report.content.summary_stats.alerts_count > 0 && (
                    <span className="text-danger"> · {report.content.summary_stats.alerts_count} alerts</span>
                  )}
                </p>
              </Card>
            </a>
          ))}
        </div>
      )}
    </div>
  );
}
