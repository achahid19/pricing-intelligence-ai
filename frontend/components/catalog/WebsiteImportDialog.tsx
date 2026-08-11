"use client";

import { useState } from "react";
import { ExternalLink, Globe, Package } from "lucide-react";

import { AiProviderRequiredNotice } from "@/components/ui/ai-provider-notice";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, ApiError, type ImportResult, type WebsiteImportCandidate, type WebsiteImportDiscoverResult } from "@/lib/api";
import { useActivity } from "@/lib/activity";
import { useAiProviderStatus } from "@/lib/aiProvider";

export function WebsiteImportDialog({ onImported }: { onImported: () => void }) {
  const { track } = useActivity();
  const { hasActiveProvider } = useAiProviderStatus();
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [result, setResult] = useState<WebsiteImportDiscoverResult | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  // Optional manually-typed price for candidates the AI found no price for
  // (keyed by candidate index) — not every site publishes one (B2B,
  // quote-based, brand sites), and those products are still worth
  // importing without one; a price can always be added later via the
  // normal edit flow. This is just a convenience to skip that extra step
  // when the user already knows the real/internal price.
  const [manualPrices, setManualPrices] = useState<Record<number, string>>({});
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  function reset() {
    setUrl("");
    setDiscoverError(null);
    setResult(null);
    setSelected(new Set());
    setManualPrices({});
    setImportResult(null);
  }

  async function handleOpenChange(next: boolean) {
    setOpen(next);
    if (!next) {
      reset();
      return;
    }
    try {
      const workspace = await api.workspace.me();
      if (workspace.website) setUrl(workspace.website);
    } catch {
      // no prefill available — user can still type a URL manually
    }
  }

  async function handleDiscover(e: React.FormEvent) {
    e.preventDefault();
    setDiscoverError(null);
    setDiscovering(true);
    try {
      const res = await track(
        "website-import-discover",
        `Scan website for products — ${url.trim() || "your site"}`,
        api.products.discoverFromWebsite(url.trim() || undefined),
        { href: "/catalog" }
      );
      setResult(res);
      // Pre-select only candidates with a confirmed link — an unverified
      // one (dimmed icon below) needs a deliberate opt-in, not a click to
      // deselect. Missing that distinction is exactly how a real workspace
      // ended up importing a dozen products that all pointed at the same
      // generic homepage: everything was pre-checked, the dimmed icon was
      // easy to miss, and nothing stopped the import.
      setSelected(new Set(res.candidates.reduce<number[]>((acc, c, i) => (c.url_verified ? [...acc, i] : acc), [])));
    } catch (err) {
      setDiscoverError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setDiscovering(false);
    }
  }

  function toggle(index: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  }

  function selectAll() {
    if (!result) return;
    setSelected(new Set(result.candidates.map((_, i) => i)));
  }

  function deselectAll() {
    setSelected(new Set());
  }

  async function handleImport() {
    if (!result || selected.size === 0) return;
    const chosen: WebsiteImportCandidate[] = Array.from(selected)
      .sort((a, b) => a - b)
      .map((i) => {
        const c = result.candidates[i];
        if (c.price != null) return c;
        const manual = manualPrices[i]?.trim();
        return manual ? { ...c, price: manual } : c;
      });
    setImporting(true);
    try {
      const res = await track(
        "website-import-confirm",
        `Import ${chosen.length} product${chosen.length === 1 ? "" : "s"} from website`,
        api.products.confirmWebsiteImport(chosen),
        { href: "/catalog" }
      );
      setImportResult(res);
      onImported();
    } catch (err) {
      setDiscoverError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setImporting(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger
        render={
          <Button variant="outline">
            <Globe className="size-4" />
            Import from website
          </Button>
        }
      />
      <DialogContent className="max-w-2xl">
        <DialogTitle>Import from website</DialogTitle>

        {!result && (
          <>
            <DialogDescription>
              Your workspace&apos;s active AI provider will browse this site (native web search — the same
              machinery used for competitor discovery) and list the distinct products it finds, with a price. Works
              best on sites where products are server-rendered or search-indexable.
            </DialogDescription>

            {hasActiveProvider === false && <AiProviderRequiredNotice action="Website import" />}

            <form onSubmit={handleDiscover} className="mt-5 space-y-4">
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="yourstore.com"
                autoFocus
              />
              {discoverError && <p className="text-sm text-danger">{discoverError}</p>}
              <Button type="submit" disabled={discovering || hasActiveProvider === false} className="w-full">
                {discovering ? "Scanning…" : "Discover products"}
              </Button>
            </form>
          </>
        )}

        {result && !importResult && (
          <>
            <DialogDescription>
              {(() => {
                const notes: string[] = [];
                if (result.no_price_count > 0) notes.push(`${result.no_price_count} with no price found`);
                if (result.already_imported_count > 0)
                  notes.push(`${result.already_imported_count} already in your catalog, not shown again`);
                const suffix = notes.length ? ` (${notes.join("; ")})` : "";
                return `Found ${result.candidates.length} product${result.candidates.length === 1 ? "" : "s"} on ${result.domain}${suffix}.`;
              })()}{" "}
              Review and pick which ones to add — the link icon opens the exact page it was found on, so you can
              verify it before importing.
            </DialogDescription>

            {result.candidates.length === 0 ? (
              <p className="mt-4 text-sm text-slate">
                {result.already_imported_count > 0
                  ? "Everything found is already in your catalog."
                  : "Nothing found. Try a more specific URL, or use CSV import instead."}
              </p>
            ) : (
              <>
                <div className="mt-4 flex items-center justify-between">
                  <p className="text-xs text-slate-soft">
                    {selected.size} of {result.candidates.length} selected
                  </p>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={selectAll}
                      className="rounded px-2 py-1 text-xs font-medium text-accent transition-colors hover:bg-accent/10"
                    >
                      Select all
                    </button>
                    <button
                      type="button"
                      onClick={deselectAll}
                      className="rounded px-2 py-1 text-xs font-medium text-slate transition-colors hover:bg-black/[0.03]"
                    >
                      Deselect all
                    </button>
                  </div>
                </div>
                <div className="mt-2 grid max-h-[30rem] grid-cols-1 gap-1.5 overflow-y-auto sm:grid-cols-2">
                {result.candidates.map((c, i) => {
                  const manualPrice = manualPrices[i] ?? "";
                  const hasPrice = c.price != null;
                  const isSelected = selected.has(i);
                  return (
                    <div
                      key={i}
                      className={`flex items-start gap-3 rounded-md border px-3 py-2 transition-colors ${
                        isSelected ? "border-accent bg-accent/5" : "border-border hover:border-slate-soft"
                      }`}
                    >
                      <input
                        type="checkbox"
                        className="mt-1 size-4 accent-[var(--accent)]"
                        checked={isSelected}
                        onChange={() => toggle(i)}
                      />
                      <div className="flex size-10 shrink-0 items-center justify-center rounded bg-black/[0.03]">
                        <Package className="size-4 text-slate-soft" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-start justify-between gap-2">
                          <p className="truncate text-sm font-medium text-ink">{c.title}</p>
                          <a
                            href={c.url}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={
                              c.url_verified
                                ? "Confirmed real page — open to verify"
                                : "Couldn't confirm this exact page — click to try anyway"
                            }
                            onClick={(e) => e.stopPropagation()}
                            className={`shrink-0 transition-colors hover:text-accent ${
                              c.url_verified ? "text-slate-soft" : "text-slate-soft/50"
                            }`}
                          >
                            <ExternalLink className="size-3.5" />
                          </a>
                        </div>
                        {hasPrice ? (
                          <p className="text-xs text-slate">
                            {c.currency ?? "USD"} {c.price}
                            {c.stock_status && <span className="text-slate-soft"> · {c.stock_status}</span>}
                          </p>
                        ) : (
                          <div className="mt-1 flex items-center gap-1.5">
                            <span className="text-xs text-slate-soft">No price found —</span>
                            <Input
                              type="number"
                              min="0"
                              step="0.01"
                              placeholder="Add a price (optional)"
                              value={manualPrice}
                              onChange={(e) =>
                                setManualPrices((prev) => ({ ...prev, [i]: e.target.value }))
                              }
                              className="h-7 w-32 px-2 text-xs"
                            />
                          </div>
                        )}
                        {c.description && (
                          <p className="mt-0.5 line-clamp-2 text-xs text-slate-soft">{c.description}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
                </div>
              </>
            )}

            {discoverError && <p className="mt-3 text-sm text-danger">{discoverError}</p>}

            <div className="mt-4 flex gap-2">
              <Button type="button" variant="outline" onClick={reset} className="flex-1">
                Start over
              </Button>
              <Button
                type="button"
                onClick={handleImport}
                disabled={importing || selected.size === 0}
                className="flex-1"
              >
                {importing ? "Importing…" : `Import ${selected.size} selected`}
              </Button>
            </div>
          </>
        )}

        {importResult && (
          <div className="mt-2 space-y-2 text-sm">
            <Badge tone="good" className="text-sm">
              {importResult.created} product{importResult.created === 1 ? "" : "s"} added
            </Badge>
            {importResult.skipped.length > 0 && (
              <div>
                <p className="text-slate">Skipped ({importResult.skipped.length}):</p>
                <ul className="mt-1 list-inside list-disc text-xs text-slate-soft">
                  {importResult.skipped.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
