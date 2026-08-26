"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Check, ExternalLink, Package, Plus, Search, Sparkles, Trash2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, cardClassName } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { ConfidenceBadge } from "@/components/discovery/ConfidenceBadge";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageHeader } from "@/components/ui/page-header";
import { AiProviderRequiredNotice } from "@/components/ui/ai-provider-notice";
import { api, ApiError, type CompetitorSite, type DiscoveryMode, type DiscoveryRun } from "@/lib/api";
import { useActivity } from "@/lib/activity";
import { useAiProviderStatus } from "@/lib/aiProvider";
import { usePersistedTab } from "@/lib/usePersistedTab";
import { cn } from "@/lib/utils";

const DISCOVERY_MODES = ["competitor", "reseller"] as const;
const SITE_VIEWS = ["candidates", "saved", "dismissed"] as const;

const SITE_CONFIDENCE_TOOLTIP =
  "The AI's own self-assessed confidence based on what it found during research, not a verified or independently calibrated metric.";

function SiteCard({
  site,
  onUpdate,
  updating,
  selected,
  onToggleSelect,
  onDelete,
  confirmingDelete,
  deleting,
  onStartDelete,
  onCancelDelete,
}: {
  site: CompetitorSite;
  onUpdate: (id: number, status: "candidate" | "saved" | "dismissed") => void;
  updating: boolean;
  selected?: boolean;
  onToggleSelect?: (id: number) => void;
  onDelete?: (id: number) => void;
  confirmingDelete?: boolean;
  deleting?: boolean;
  onStartDelete?: (id: number) => void;
  onCancelDelete?: () => void;
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
          {site.status === "dismissed" && !confirmingDelete && (
            <>
              <button
                onClick={() => onUpdate(site.id, "candidate")}
                disabled={updating}
                className="rounded-md px-2 py-1 text-xs font-medium text-slate transition-colors hover:bg-black/[0.03] hover:text-ink"
              >
                Restore
              </button>
              {onStartDelete && (
                <button
                  onClick={() => onStartDelete(site.id)}
                  disabled={updating || deleting}
                  aria-label="Delete competitor"
                  className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-danger/10 hover:text-danger"
                >
                  <Trash2 className="size-4" />
                </button>
              )}
            </>
          )}
          {site.status === "dismissed" && confirmingDelete && (
            <>
              <button
                onClick={() => onDelete?.(site.id)}
                disabled={deleting}
                className="rounded-md px-2 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/10"
              >
                {deleting ? "Deleting…" : "Confirm"}
              </button>
              <button
                onClick={onCancelDelete}
                disabled={deleting}
                aria-label="Cancel delete"
                className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-black/[0.03] hover:text-ink"
              >
                <X className="size-4" />
              </button>
            </>
          )}
        </div>
      </div>
    </Card>
  );
}

function AddCompetitorForm({ onAdded, relationshipType }: { onAdded: () => void; relationshipType: DiscoveryMode }) {
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
      await api.discovery.createSite(domain.trim(), name.trim() || undefined, relationshipType);
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
          placeholder={relationshipType === "reseller" ? "reseller.com" : "competitor.com"}
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
        {adding ? "Adding…" : relationshipType === "reseller" ? "Add reseller" : "Add competitor"}
      </Button>
      {error && <p className="w-full text-xs text-danger">{error}</p>}
    </form>
  );
}

type SiteView = "candidates" | "saved" | "dismissed";

export default function DiscoveryPage() {
  const [mode, setMode] = usePersistedTab<DiscoveryMode>("mode", "discovery-mode", DISCOVERY_MODES, "competitor");
  const [view, setView] = usePersistedTab<SiteView>("view", "discovery-view", SITE_VIEWS, "candidates");
  const [showResellerMode, setShowResellerMode] = useState(false);
  // Tracks the mode last seen by the reset-on-mode-change effect below —
  // a value comparison, not a boolean "have I run yet" latch, since React
  // Strict Mode double-invokes effects on mount in development and would
  // flip a plain latch on the harmless synthetic second call, incorrectly
  // treating it as a genuine mode change and stomping a restored view.
  const prevModeRef = useRef(mode);
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
  const [confirmingDeleteId, setConfirmingDeleteId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [confirmingDeleteAllDismissed, setConfirmingDeleteAllDismissed] = useState(false);
  const [deletingAllDismissed, setDeletingAllDismissed] = useState(false);
  const [discoveringAllProducts, setDiscoveringAllProducts] = useState(false);
  const { track } = useActivity();
  const { hasActiveProvider } = useAiProviderStatus();

  // The reseller-tracking mode only makes sense for workspaces that
  // actually monitor MAP compliance — hidden entirely otherwise, so this
  // stays a single simple "Discovery" page for everyone else, per the
  // objectives already captured at onboarding/Settings.
  useEffect(() => {
    api.workspace
      .me()
      .then((ws) => {
        const canUseResellerMode = (ws.objectives_selected ?? []).includes("map_compliance");
        setShowResellerMode(canUseResellerMode);
        // A persisted reseller mode from a previous session shouldn't get
        // stuck active if the workspace's objectives no longer allow it.
        if (!canUseResellerMode && mode === "reseller") setMode("competitor");
      })
      .catch(() => setShowResellerMode(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback(() => {
    api.discovery.listRuns(mode).then(setRuns).catch(() => setRuns([]));
    // Pending candidates from every past run, not just the latest — an
    // older run's un-actioned suggestions shouldn't just disappear.
    api.discovery.listSites("candidate", mode).then(setCandidates).catch(() => setCandidates([]));
    api.discovery.listSites("saved", mode).then(setSavedSites).catch(() => setSavedSites([]));
    api.discovery.listSites("dismissed", mode).then(setDismissedSites).catch(() => setDismissedSites([]));
  }, [mode]);

  useEffect(() => {
    // Only reset to Candidates when mode has actually changed since the
    // last time this ran — leaves a persisted/URL-restored view alone on
    // mount, while still resetting on a genuine user-driven mode switch.
    if (prevModeRef.current !== mode) {
      prevModeRef.current = mode;
      setSelectedIds(new Set());
      setView("candidates");
    }
    load();
  }, [load, mode]);

  async function handleRun() {
    setError(null);
    setLastRunNote(null);
    setRunning(true);
    try {
      const run = await track(
        `discovery-run-${mode}`,
        mode === "reseller" ? "Reseller discovery" : "Competitor discovery",
        api.discovery.createRun(maxCandidates, mode),
        { href: "/discovery" }
      );
      if (run.skipped_known_count) {
        const noun = mode === "reseller" ? "reseller" : "competitor";
        setLastRunNote(
          `Skipped ${run.skipped_known_count} ${noun}${run.skipped_known_count === 1 ? "" : "s"} you'd already seen before.`
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

  async function handleDiscoverAllProducts() {
    if (!savedSites || savedSites.length === 0) return;
    setError(null);
    setDiscoveringAllProducts(true);
    const sites = savedSites;
    try {
      const results = await track(
        "discover-all-products",
        `Discover products (${sites.length} competitor${sites.length === 1 ? "" : "s"})`,
        Promise.allSettled(sites.map((site) => api.discovery.discoverProducts(site.id, 15))),
        { href: "/discovery" }
      );
      const failed = results.filter((r) => r.status === "rejected").length;
      if (failed > 0) {
        setError(`${sites.length - failed} of ${sites.length} succeeded; ${failed} couldn't run right now (likely still in cooldown). Try those again in a bit.`);
      }
    } finally {
      setDiscoveringAllProducts(false);
    }
  }

  async function handleDeleteSite(id: number) {
    setDeletingId(id);
    try {
      await api.discovery.deleteSite(id);
      setConfirmingDeleteId(null);
      setDismissedSites((prev) => (prev ? prev.filter((s) => s.id !== id) : prev));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete that competitor. Try again.");
    } finally {
      setDeletingId(null);
    }
  }

  async function handleDeleteAllDismissed() {
    if (!dismissedSites || dismissedSites.length === 0) return;
    setDeletingAllDismissed(true);
    try {
      await Promise.all(dismissedSites.map((s) => api.discovery.deleteSite(s.id)));
      setConfirmingDeleteAllDismissed(false);
      setDismissedSites([]);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete those competitors. Try again.");
      load();
    } finally {
      setDeletingAllDismissed(false);
    }
  }

  const latestRun = runs?.[0];
  const allCandidatesSelected = !!candidates && candidates.length > 0 && candidates.every((c) => selectedIds.has(c.id));

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <PageHeader
        title={mode === "reseller" ? "Reseller discovery" : "Discovery"}
        description={
          mode === "reseller"
            ? "Find businesses that advertise or sell your own products, so you can check their prices against your MAP policy."
            : "Find real competitors using web search, tailored to your business context and catalog."
        }
        actions={
          <>
            <div className="space-y-1">
              <div className="flex items-center gap-1.5">
                <label htmlFor="max-candidates" className="text-xs font-medium text-slate">
                  {mode === "reseller" ? "Max resellers" : "Max competitors"}
                </label>
                <InfoTooltip text="More results found means more AI reasoning and web-search cost on this run; your provider bills for both, so higher isn't free." />
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
            <Button onClick={handleRun} disabled={running || hasActiveProvider === false}>
              <Sparkles className="size-4" />
              {running ? "Researching…" : mode === "reseller" ? "Run reseller discovery" : "Run discovery"}
            </Button>
          </>
        }
      />

      {hasActiveProvider === false && (
        <div className="mt-4">
          <AiProviderRequiredNotice action="Discovery" />
        </div>
      )}

      {showResellerMode && (
        <div className="mt-4 inline-flex rounded-md border border-border bg-paper-raised p-1">
          <button
            onClick={() => setMode("competitor")}
            className={cn(
              "rounded px-3 py-1.5 text-sm font-medium transition-colors",
              mode === "competitor" ? "bg-accent text-white" : "text-slate hover:text-ink"
            )}
          >
            Competitors
          </button>
          <button
            onClick={() => setMode("reseller")}
            className={cn(
              "rounded px-3 py-1.5 text-sm font-medium transition-colors",
              mode === "reseller" ? "bg-accent text-white" : "text-slate hover:text-ink"
            )}
          >
            Resellers (MAP)
          </button>
        </div>
      )}

      {running && <p className="mt-4 text-sm text-slate-soft">This can take up to 30 seconds; your AI provider is actively searching the web.</p>}
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

      {/* Tabs, not always-expanded sections — candidates/saved/dismissed are
          review states a user works through one at a time, not something
          meant to be scanned together, and rendering all three (dismissed
          especially, which only grows) at once turned this page into an
          endless scroll. */}
      <div className="mt-6 flex items-center gap-1 border-b border-border">
        {(
          [
            ["candidates", "Candidates", candidates?.length],
            ["saved", mode === "reseller" ? "Saved resellers" : "Saved", savedSites?.length],
            ["dismissed", "Dismissed", dismissedSites?.length],
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
            {count != null && count > 0 && <span className="ml-1 tabular-nums opacity-70">({count})</span>}
          </button>
        ))}
      </div>

      {view === "candidates" && (
        <div className="mt-4">
          {candidates && candidates.length > 0 ? (
            <>
              <div className="flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Checkbox
                    checked={allCandidatesSelected}
                    onCheckedChange={() =>
                      setSelectedIds(allCandidatesSelected ? new Set() : new Set(candidates.map((c) => c.id)))
                    }
                    aria-label="Select all candidates"
                  />
                  <span className="text-xs text-slate-soft">Select all</span>
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
              <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
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
            </>
          ) : runs && runs.length === 0 ? (
            <div className="flex flex-col items-center py-16 text-center">
              <div className="flex size-12 items-center justify-center rounded-full bg-black/[0.03]">
                <Search className="size-5 text-slate-soft" />
              </div>
              <p className="mt-4 text-sm font-medium text-ink">
                No {mode === "reseller" ? "reseller " : ""}discovery runs yet
              </p>
              <p className="mt-1 max-w-xs text-sm text-slate">
                {mode === "reseller"
                  ? "Run reseller discovery to find businesses advertising your own products, for MAP compliance."
                  : "Run discovery to find competitors based on your business context and catalog."}
              </p>
            </div>
          ) : (
            <p className="py-8 text-center text-sm text-slate">No candidates to review right now.</p>
          )}
        </div>
      )}

      {view === "saved" && (
        <div className="mt-4">
          <p className="text-xs text-slate-soft">
            {mode === "reseller"
              ? "Already know a reseller discovery hasn't found? Add them directly."
              : "Already know a competitor discovery hasn't found? Add them directly."}
          </p>
          <div className="mt-2">
            <AddCompetitorForm onAdded={load} relationshipType={mode} />
          </div>
          {savedSites && savedSites.length > 0 && (
            <div className="mt-3 flex items-center justify-end">
              <Button
                variant="outline"
                size="sm"
                disabled={discoveringAllProducts || hasActiveProvider === false}
                onClick={handleDiscoverAllProducts}
              >
                <Sparkles className="size-3.5" />
                {discoveringAllProducts ? "Discovering…" : `Discover products for all (${savedSites.length})`}
              </Button>
            </div>
          )}
          {savedSites && savedSites.length > 0 ? (
            <div className="mt-4 grid grid-cols-1 gap-3 lg:grid-cols-2">
              {savedSites.map((site) => (
                <SiteCard key={site.id} site={site} onUpdate={handleUpdate} updating={updatingId === site.id} />
              ))}
            </div>
          ) : (
            <p className="mt-6 text-center text-sm text-slate">Nothing saved yet.</p>
          )}
        </div>
      )}

      {view === "dismissed" && (
        <div className="mt-4">
          {dismissedSites && dismissedSites.length > 0 ? (
            <>
              <div className="flex items-center justify-between gap-3">
                <p className="text-xs text-slate-soft">
                  A dismissed {mode === "reseller" ? "reseller" : "competitor"} is never re-suggested by discovery.
                  Restore one here if you want it back, or delete it for good.
                </p>
                {confirmingDeleteAllDismissed ? (
                  <div className="flex shrink-0 items-center gap-2">
                    <span className="text-xs text-slate-soft">
                      Delete all {dismissedSites.length}?
                    </span>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={deletingAllDismissed}
                      onClick={handleDeleteAllDismissed}
                      className="text-danger"
                    >
                      {deletingAllDismissed ? "Deleting…" : "Confirm"}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={deletingAllDismissed}
                      onClick={() => setConfirmingDeleteAllDismissed(false)}
                    >
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <Button
                    variant="outline"
                    size="sm"
                    className="shrink-0"
                    onClick={() => setConfirmingDeleteAllDismissed(true)}
                  >
                    <Trash2 className="size-3.5" />
                    Delete all
                  </Button>
                )}
              </div>
              <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-2">
                {dismissedSites.map((site) => (
                  <SiteCard
                    key={site.id}
                    site={site}
                    onUpdate={handleUpdate}
                    updating={updatingId === site.id}
                    onDelete={handleDeleteSite}
                    confirmingDelete={confirmingDeleteId === site.id}
                    deleting={deletingId === site.id}
                    onStartDelete={setConfirmingDeleteId}
                    onCancelDelete={() => setConfirmingDeleteId(null)}
                  />
                ))}
              </div>
            </>
          ) : (
            <p className="py-8 text-center text-sm text-slate">Nothing dismissed.</p>
          )}
        </div>
      )}
    </div>
  );
}
