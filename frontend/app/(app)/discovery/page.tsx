"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { Check, ExternalLink, Package, Plus, Search, Sparkles, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, cardClassName } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfidenceBadge } from "@/components/discovery/ConfidenceBadge";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { api, ApiError, type CompetitorSite, type DiscoveryRun } from "@/lib/api";
import { cn } from "@/lib/utils";

const SITE_CONFIDENCE_TOOLTIP =
  "The AI's own self-assessed confidence based on what it found during research — not a verified or independently calibrated metric.";

function SiteCard({
  site,
  onUpdate,
  updating,
  selected,
  onToggleSelect,
}: {
  site: CompetitorSite;
  onUpdate: (id: number, status: "candidate" | "saved" | "dismissed") => void;
  updating: boolean;
  selected?: boolean;
  onToggleSelect?: (id: number) => void;
}) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          {onToggleSelect && (
            <Checkbox
              checked={!!selected}
              onCheckedChange={() => onToggleSelect(site.id)}
              aria-label={`Select ${site.name || site.domain}`}
              className="mt-0.5"
            />
          )}
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
              <ConfidenceBadge score={site.confidence_score} tooltip={SITE_CONFIDENCE_TOOLTIP} />
            </div>
            <p className="mt-0.5 text-xs text-slate-soft">
              {site.domain}
              {site.estimated_product_count != null && ` · ~${site.estimated_product_count} products`}
            </p>
            {site.rationale && <p className="mt-2 text-sm text-slate">{site.rationale}</p>}
          </div>
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
            <>
              <Link
                href={`/discovery/${site.id}`}
                className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-slate transition-colors hover:bg-black/[0.03] hover:text-ink"
              >
                <Package className="size-3.5" />
                View products
              </Link>
              <button
                onClick={() => onUpdate(site.id, "dismissed")}
                disabled={updating}
                className="rounded-md px-2 py-1 text-xs font-medium text-slate transition-colors hover:bg-black/[0.03]"
              >
                Remove
              </button>
            </>
          )}
          {site.status === "dismissed" && (
            <button
              onClick={() => onUpdate(site.id, "candidate")}
              disabled={updating}
              className="rounded-md px-2 py-1 text-xs font-medium text-slate transition-colors hover:bg-black/[0.03] hover:text-ink"
            >
              Restore
            </button>
          )}
        </div>
      </div>
    </Card>
  );
}

function AddCompetitorForm({ onAdded }: { onAdded: () => void }) {
  const [domain, setDomain] = useState("");
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!domain.trim()) {
      setError("Enter a domain.");
      return;
    }
    setError(null);
    setAdding(true);
    try {
      await api.discovery.createSite(domain.trim(), name.trim() || undefined);
      setDomain("");
      setName("");
      onAdded();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't add that competitor. Try again.");
    } finally {
      setAdding(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-wrap items-end gap-2">
      <div className="space-y-1">
        <Label htmlFor="add-domain">Domain</Label>
        <Input
          id="add-domain"
          value={domain}
          onChange={(e) => setDomain(e.target.value)}
          placeholder="competitor.com"
          className="h-9 w-40"
        />
      </div>
      <div className="space-y-1">
        <Label htmlFor="add-name">Name (optional)</Label>
        <Input
          id="add-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Company name"
          className="h-9 w-40"
        />
      </div>
      <Button type="submit" variant="outline" size="sm" disabled={adding}>
        <Plus className="size-3.5" />
        {adding ? "Adding…" : "Add competitor"}
      </Button>
      {error && <p className="w-full text-xs text-danger">{error}</p>}
    </form>
  );
}

export default function DiscoveryPage() {
  const [runs, setRuns] = useState<DiscoveryRun[] | null>(null);
  const [candidates, setCandidates] = useState<CompetitorSite[] | null>(null);
  const [savedSites, setSavedSites] = useState<CompetitorSite[] | null>(null);
  const [dismissedSites, setDismissedSites] = useState<CompetitorSite[] | null>(null);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRunNote, setLastRunNote] = useState<string | null>(null);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [maxCandidates, setMaxCandidates] = useState(10);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkUpdating, setBulkUpdating] = useState(false);

  const load = useCallback(() => {
    api.discovery.listRuns().then(setRuns).catch(() => setRuns([]));
    // Pending candidates from every past run, not just the latest — an
    // older run's un-actioned suggestions shouldn't just disappear.
    api.discovery.listSites("candidate").then(setCandidates).catch(() => setCandidates([]));
    api.discovery.listSites("saved").then(setSavedSites).catch(() => setSavedSites([]));
    api.discovery.listSites("dismissed").then(setDismissedSites).catch(() => setDismissedSites([]));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function handleRun() {
    setError(null);
    setLastRunNote(null);
    setRunning(true);
    try {
      const run = await api.discovery.createRun(maxCandidates);
      if (run.skipped_known_count) {
        setLastRunNote(
          `Skipped ${run.skipped_known_count} competitor${run.skipped_known_count === 1 ? "" : "s"} you'd already seen before.`
        );
      }
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setRunning(false);
    }
  }

  async function handleUpdate(id: number, status: "candidate" | "saved" | "dismissed") {
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

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  async function handleBulkUpdate(status: "saved" | "dismissed") {
    setBulkUpdating(true);
    try {
      await Promise.all(Array.from(selectedIds).map((id) => api.discovery.updateSite(id, status)));
      setSelectedIds(new Set());
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update those competitors. Try again.");
    } finally {
      setBulkUpdating(false);
    }
  }

  const latestRun = runs?.[0];
  const allCandidatesSelected = !!candidates && candidates.length > 0 && candidates.every((c) => selectedIds.has(c.id));

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <PageHeader
        title="Discovery"
        description="Find real competitors using web search, tailored to your business context and catalog."
        actions={
          <>
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <label htmlFor="max-candidates" className="text-xs font-medium text-slate">
                  Max competitors
                </label>
                <InfoTooltip text="More competitors found means more AI reasoning and web-search cost on this run — your provider bills for both, so higher isn't free." />
              </div>
              <Input
                id="max-candidates"
                type="number"
                min={1}
                max={25}
                value={maxCandidates}
                onChange={(e) => {
                  const next = Number(e.target.value);
                  setMaxCandidates(Number.isNaN(next) ? 10 : Math.min(25, Math.max(1, next)));
                }}
                className="w-20"
              />
            </div>
            <Button onClick={handleRun} disabled={running}>
              <Sparkles className="size-4" />
              {running ? "Researching…" : "Run discovery"}
            </Button>
          </>
        }
      />

      {running && <p className="mt-4 text-sm text-slate-soft">This can take up to 30 seconds — your AI provider is actively searching the web.</p>}
      {error && <p className="mt-4 text-sm text-danger">{error}</p>}
      {lastRunNote && <p className="mt-4 text-sm text-slate-soft">{lastRunNote}</p>}

      {latestRun?.status === "failed" && (
        <p className="mt-4 text-sm text-danger">The last run failed: {latestRun.error_message}</p>
      )}

      {latestRun && (
        <details className={cn(cardClassName, "mt-4 p-0")}>
          <summary className="cursor-pointer select-none px-4 py-2.5 text-xs font-medium text-slate">
            Business context used for the last run
          </summary>
          <div className="border-t border-border px-4 py-3">
            <pre className="whitespace-pre-wrap font-sans text-xs text-slate">{latestRun.context_snapshot.context}</pre>
            <p className="mt-2 text-xs text-slate-soft">Max competitors requested: {latestRun.context_snapshot.max_candidates}</p>
          </div>
        </details>
      )}

      {candidates && candidates.length > 0 && (
        <div className="mt-6">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <Checkbox
                checked={allCandidatesSelected}
                onCheckedChange={() =>
                  setSelectedIds(allCandidatesSelected ? new Set() : new Set(candidates.map((c) => c.id)))
                }
                aria-label="Select all candidates"
              />
              <h2 className="text-sm font-medium text-ink">
                {candidates.length} candidate{candidates.length === 1 ? "" : "s"} to review
              </h2>
            </div>
            {selectedIds.size > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-slate-soft">{selectedIds.size} selected</span>
                <Button variant="outline" size="sm" disabled={bulkUpdating} onClick={() => handleBulkUpdate("saved")}>
                  <Check className="size-3.5" />
                  Save all
                </Button>
                <Button variant="outline" size="sm" disabled={bulkUpdating} onClick={() => handleBulkUpdate("dismissed")}>
                  <X className="size-3.5" />
                  Dismiss all
                </Button>
              </div>
            )}
          </div>
          <div className="mt-2 space-y-2">
            {candidates.map((site) => (
              <SiteCard
                key={site.id}
                site={site}
                onUpdate={handleUpdate}
                updating={updatingId === site.id || bulkUpdating}
                selected={selectedIds.has(site.id)}
                onToggleSelect={toggleSelect}
              />
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

      <div className="mt-8">
        <h2 className="text-sm font-medium text-ink">Saved competitors</h2>
        <p className="mt-1 text-xs text-slate-soft">Already know a competitor discovery hasn't found? Add them directly.</p>
        <div className="mt-2">
          <AddCompetitorForm onAdded={load} />
        </div>
        {savedSites && savedSites.length > 0 && (
          <div className="mt-4 space-y-2">
            {savedSites.map((site) => (
              <SiteCard key={site.id} site={site} onUpdate={handleUpdate} updating={updatingId === site.id} />
            ))}
          </div>
        )}
      </div>

      {dismissedSites && dismissedSites.length > 0 && (
        <details className={cn(cardClassName, "mt-8 p-0")}>
          <summary className="cursor-pointer select-none px-4 py-2.5 text-xs font-medium text-slate">
            Dismissed ({dismissedSites.length}) — a dismissed competitor is never re-suggested by discovery; restore
            one here if you want it back
          </summary>
          <div className="space-y-2 border-t border-border p-4">
            {dismissedSites.map((site) => (
              <SiteCard key={site.id} site={site} onUpdate={handleUpdate} updating={updatingId === site.id} />
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
