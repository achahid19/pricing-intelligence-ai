"use client";

import { useCallback, useEffect, useState } from "react";
import { Check, ExternalLink, Search, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api, ApiError, type CompetitorSite, type DiscoveryRun } from "@/lib/api";

function ConfidenceBadge({ score }: { score: number }) {
  const tone = score >= 75 ? "bg-good/10 text-good" : score >= 50 ? "bg-slate/10 text-slate" : "bg-accent/10 text-accent";
  return <span className={`rounded-full px-2 py-0.5 text-xs font-medium tabular-nums ${tone}`}>{score}% match</span>;
}

function SiteCard({
  site,
  onUpdate,
  updating,
}: {
  site: CompetitorSite;
  onUpdate: (id: number, status: "saved" | "dismissed") => void;
  updating: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-paper-raised p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <a
              href={`https://${site.domain}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-ink hover:text-accent"
            >
              {site.name || site.domain}
              <ExternalLink className="size-3" />
            </a>
            <ConfidenceBadge score={site.confidence_score} />
          </div>
          <p className="mt-0.5 text-xs text-slate-soft">
            {site.domain}
            {site.estimated_product_count != null && ` · ~${site.estimated_product_count} products`}
          </p>
          <p className="mt-2 text-sm text-slate">{site.rationale}</p>
        </div>
        <div className="flex shrink-0 gap-1.5">
          {site.status === "candidate" && (
            <>
              <button
                onClick={() => onUpdate(site.id, "saved")}
                disabled={updating}
                aria-label="Save competitor"
                className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-good/10 hover:text-good"
              >
                <Check className="size-4" />
              </button>
              <button
                onClick={() => onUpdate(site.id, "dismissed")}
                disabled={updating}
                aria-label="Dismiss competitor"
                className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-danger/10 hover:text-danger"
              >
                <X className="size-4" />
              </button>
            </>
          )}
          {site.status === "saved" && (
            <button
              onClick={() => onUpdate(site.id, "dismissed")}
              disabled={updating}
              className="rounded-md px-2 py-1 text-xs font-medium text-slate transition-colors hover:bg-black/[0.03]"
            >
              Remove
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export default function DiscoveryPage() {
  const [runs, setRuns] = useState<DiscoveryRun[] | null>(null);
  const [savedSites, setSavedSites] = useState<CompetitorSite[] | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<number | null>(null);

  const load = useCallback(() => {
    api.discovery.listRuns().then(setRuns).catch(() => setRuns([]));
    api.discovery.listSites("saved").then(setSavedSites).catch(() => setSavedSites([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRun() {
    setError(null);
    setRunning(true);
    try {
      await api.discovery.createRun();
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setRunning(false);
    }
  }

  async function handleUpdate(id: number, status: "saved" | "dismissed") {
    setUpdatingId(id);
    try {
      await api.discovery.updateSite(id, status);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update that competitor. Try again.");
    } finally {
      setUpdatingId(null);
    }
  }

  const latestRun = runs?.[0];
  const candidates = latestRun?.sites.filter((s) => s.status === "candidate") ?? [];

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-ink">Discovery</h1>
          <p className="mt-1 text-sm text-slate">
            Find real competitors using web search, tailored to your business context and catalog.
          </p>
        </div>
        <Button onClick={handleRun} disabled={running}>
          <Sparkles className="size-4" />
          {running ? "Researching…" : "Run discovery"}
        </Button>
      </div>

      {running && <p className="mt-4 text-sm text-slate-soft">This can take up to 30 seconds — your AI provider is actively searching the web.</p>}
      {error && <p className="mt-4 text-sm text-danger">{error}</p>}

      {latestRun?.status === "failed" && (
        <p className="mt-4 text-sm text-danger">The last run failed: {latestRun.error_message}</p>
      )}

      {candidates.length > 0 && (
        <div className="mt-6">
          <h2 className="text-sm font-medium text-ink">
            {candidates.length} candidate{candidates.length === 1 ? "" : "s"} to review
          </h2>
          <div className="mt-2 space-y-2">
            {candidates.map((site) => (
              <SiteCard key={site.id} site={site} onUpdate={handleUpdate} updating={updatingId === site.id} />
            ))}
          </div>
        </div>
      )}

      {runs && runs.length === 0 && (
        <div className="mt-16 flex flex-col items-center text-center">
          <div className="flex size-12 items-center justify-center rounded-full bg-black/[0.03]">
            <Search className="size-5 text-slate-soft" />
          </div>
          <p className="mt-4 text-sm font-medium text-ink">No discovery runs yet</p>
          <p className="mt-1 max-w-xs text-sm text-slate">
            Run discovery to find competitors based on your business context and catalog.
          </p>
        </div>
      )}

      {savedSites && savedSites.length > 0 && (
        <div className="mt-8">
          <h2 className="text-sm font-medium text-ink">Saved competitors</h2>
          <div className="mt-2 space-y-2">
            {savedSites.map((site) => (
              <SiteCard key={site.id} site={site} onUpdate={handleUpdate} updating={updatingId === site.id} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
