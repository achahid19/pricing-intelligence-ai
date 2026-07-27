"use client";

import { useState } from "react";
import { Globe, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { api, ApiError, type ImportResult, type WebsiteImportCandidate, type WebsiteImportDiscoverResult } from "@/lib/api";

export function WebsiteImportDialog({ onImported }: { onImported: () => void }) {
  const [open, setOpen] = useState(false);
  const [url, setUrl] = useState("");
  const [discovering, setDiscovering] = useState(false);
  const [discoverError, setDiscoverError] = useState<string | null>(null);
  const [result, setResult] = useState<WebsiteImportDiscoverResult | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [importing, setImporting] = useState(false);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);

  function reset() {
    setUrl("");
    setDiscoverError(null);
    setResult(null);
    setSelected(new Set());
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
    if (!url.trim()) {
      setDiscoverError("Enter a website URL.");
      return;
    }
    setDiscoverError(null);
    setDiscovering(true);
    try {
      const res = await api.products.discoverFromWebsite(url.trim());
      setResult(res);
      setSelected(new Set(res.candidates.map((_, i) => i)));
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

  async function handleImport() {
    if (!result || selected.size === 0) return;
    const chosen: WebsiteImportCandidate[] = Array.from(selected)
      .sort((a, b) => a - b)
      .map((i) => result.candidates[i]);
    setImporting(true);
    try {
      const res = await api.products.confirmWebsiteImport(chosen);
      setImportResult(res);
      onImported();
    } catch (err) {
      setDiscoverError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setImporting(false);
    }
  }

  const structuredCount = result?.candidates.filter((c) => c.method === "structured").length ?? 0;
  const aiCount = result?.candidates.filter((c) => c.method === "ai").length ?? 0;

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
      <DialogContent className="max-w-lg">
        <DialogTitle>Import from website</DialogTitle>

        {!result && (
          <>
            <DialogDescription>
              We'll look for a product feed or sitemap first (fast, free, exact), and use AI to read pages that
              don't have one. Works best on server-rendered storefronts — sites that load products entirely via
              JavaScript may not be found yet.
            </DialogDescription>

            <form onSubmit={handleDiscover} className="mt-5 space-y-4">
              <Input
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                placeholder="yourstore.com"
                autoFocus
              />
              {discoverError && <p className="text-sm text-danger">{discoverError}</p>}
              <Button type="submit" disabled={discovering} className="w-full">
                {discovering ? "Scanning…" : "Discover products"}
              </Button>
            </form>
          </>
        )}

        {result && !importResult && (
          <>
            <DialogDescription>
              Found {result.candidates.length} product{result.candidates.length === 1 ? "" : "s"}
              {result.candidates.length > 0 && (
                <span className="text-slate-soft">
                  {" "}
                  ({structuredCount} from structured data, {aiCount} via AI)
                </span>
              )}
              . Review and pick which ones to add.
              {result.truncated && " Only the first batch is shown — run again to pick up more."}
            </DialogDescription>

            {result.candidates.length === 0 ? (
              <p className="mt-4 text-sm text-slate">
                Nothing found. The site may load products via JavaScript, which this import can't read yet — try
                a CSV export instead.
              </p>
            ) : (
              <div className="mt-4 max-h-80 space-y-1.5 overflow-y-auto">
                {result.candidates.map((c, i) => (
                  <label
                    key={i}
                    className={`flex cursor-pointer items-center gap-3 rounded-md border px-3 py-2 transition-colors ${
                      selected.has(i) ? "border-accent bg-accent/5" : "border-border hover:border-slate-soft"
                    }`}
                  >
                    <input
                      type="checkbox"
                      className="size-4 accent-[var(--accent)]"
                      checked={selected.has(i)}
                      onChange={() => toggle(i)}
                    />
                    {c.image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={c.image_url} alt="" className="size-10 shrink-0 rounded object-cover" />
                    ) : (
                      <div className="size-10 shrink-0 rounded bg-black/[0.03]" />
                    )}
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium text-ink">{c.title}</p>
                      <p className="text-xs text-slate">
                        {c.currency ?? "USD"} {c.price}
                      </p>
                    </div>
                    {c.method === "ai" && (
                      <span className="flex shrink-0 items-center gap-1 rounded-full bg-accent/10 px-2 py-0.5 text-xs font-medium text-accent">
                        <Sparkles className="size-3" />
                        AI
                      </span>
                    )}
                  </label>
                ))}
              </div>
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
            <p className="font-medium text-good">
              {importResult.created} product{importResult.created === 1 ? "" : "s"} added
            </p>
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
