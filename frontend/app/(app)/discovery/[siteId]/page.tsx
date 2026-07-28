"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Check, ExternalLink, Sparkles, X } from "lucide-react";

import { ConfidenceBadge } from "@/components/discovery/ConfidenceBadge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { InfoTooltip } from "@/components/ui/info-tooltip";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import {
  api,
  ApiError,
  type CompetitorProduct,
  type CompetitorSite,
  type Product,
  type ProductMatch,
} from "@/lib/api";
import { cn } from "@/lib/utils";

const MATCH_CONFIDENCE_TOOLTIP =
  "The AI's own self-assessed confidence that these are genuinely the same or a directly comparable item — not a verified metric.";

function MatchCandidateCard({
  match,
  product,
  competitorProduct,
  onUpdate,
  updating,
  selected,
  onToggleSelect,
}: {
  match: ProductMatch;
  product: Product | undefined;
  competitorProduct: CompetitorProduct | undefined;
  onUpdate: (id: number, status: "confirmed" | "dismissed") => void;
  updating: boolean;
  selected: boolean;
  onToggleSelect: (id: number) => void;
}) {
  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-start gap-3">
          <Checkbox
            checked={selected}
            onCheckedChange={() => onToggleSelect(match.id)}
            aria-label="Select match"
            className="mt-0.5"
          />
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-medium text-ink">{product?.name ?? "Unknown product"}</span>
              <span className="text-slate-soft">↔</span>
              <span className="font-medium text-ink">{competitorProduct?.title ?? "Unknown product"}</span>
              <ConfidenceBadge score={match.confidence} tooltip={MATCH_CONFIDENCE_TOOLTIP} />
            </div>
            {match.rationale && <p className="mt-2 text-sm text-slate">{match.rationale}</p>}
          </div>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <button
            onClick={() => onUpdate(match.id, "confirmed")}
            disabled={updating}
            aria-label="Confirm match"
            className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-good/10 hover:text-good"
          >
            <Check className="size-4" />
          </button>
          <button
            onClick={() => onUpdate(match.id, "dismissed")}
            disabled={updating}
            aria-label="Dismiss match"
            className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-danger/10 hover:text-danger"
          >
            <X className="size-4" />
          </button>
        </div>
      </div>
    </Card>
  );
}

function OwnProductDropTarget({
  product,
  confirmedMatches,
  competitorProductById,
  onUnmatch,
  onDropCompetitorProduct,
}: {
  product: Product;
  confirmedMatches: ProductMatch[];
  competitorProductById: Record<number, CompetitorProduct>;
  onUnmatch: (matchId: number) => void;
  onDropCompetitorProduct: (productId: number, competitorProductId: number) => void;
}) {
  const [dragOver, setDragOver] = useState(false);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragOver(false);
        const competitorProductId = Number(e.dataTransfer.getData("text/plain"));
        if (competitorProductId) onDropCompetitorProduct(product.id, competitorProductId);
      }}
      className={cn(
        "rounded-md border p-3 transition-colors",
        dragOver ? "border-accent bg-accent/5" : "border-border bg-paper-raised"
      )}
    >
      <p className="truncate text-sm font-medium text-ink">{product.name}</p>
      <p className="text-xs tabular-nums text-slate-soft">
        {product.currency} {product.price}
      </p>
      {confirmedMatches.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {confirmedMatches.map((m) => (
            <span
              key={m.id}
              className="inline-flex items-center gap-1 rounded-full bg-good/10 px-2 py-0.5 text-xs font-medium text-good"
            >
              {competitorProductById[m.competitor_product_id]?.title ?? "Matched product"}
              <button onClick={() => onUnmatch(m.id)} aria-label="Unmatch" className="hover:text-danger">
                <X className="size-3" />
              </button>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

function CompetitorProductChip({ product }: { product: CompetitorProduct }) {
  return (
    <div
      draggable
      onDragStart={(e) => e.dataTransfer.setData("text/plain", String(product.id))}
      className="cursor-grab rounded-md border border-border bg-paper-raised p-3 active:cursor-grabbing"
    >
      <p className="truncate text-sm font-medium text-ink">{product.title}</p>
      {product.price != null && (
        <p className="text-xs tabular-nums text-slate-soft">
          {product.currency} {product.price}
        </p>
      )}
    </div>
  );
}

type ProductView = "products" | "auto-match" | "manual";

export default function CompetitorProductsPage() {
  const params = useParams<{ siteId: string }>();
  const siteId = Number(params.siteId);

  const [view, setView] = useState<ProductView>("products");
  const [site, setSite] = useState<CompetitorSite | null>(null);
  const [products, setProducts] = useState<CompetitorProduct[] | null>(null);
  const [ownProducts, setOwnProducts] = useState<Product[] | null>(null);
  const [matches, setMatches] = useState<ProductMatch[] | null>(null);
  const [maxProducts, setMaxProducts] = useState(15);
  const [discovering, setDiscovering] = useState(false);
  const [matching, setMatching] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [updatingId, setUpdatingId] = useState<number | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkUpdating, setBulkUpdating] = useState(false);

  const load = useCallback(() => {
    api.discovery.getSite(siteId).then(setSite).catch(() => setNotFound(true));
    api.discovery.listProducts(siteId).then(setProducts).catch(() => setProducts([]));
    api.products.list().then(setOwnProducts).catch(() => setOwnProducts([]));
    api.discovery.listMatches(siteId).then(setMatches).catch(() => setMatches([]));
  }, [siteId]);

  useEffect(() => {
    load();
  }, [load]);

  const competitorProductById = useMemo(
    () => Object.fromEntries((products ?? []).map((p) => [p.id, p])),
    [products]
  );
  const ownProductById = useMemo(() => Object.fromEntries((ownProducts ?? []).map((p) => [p.id, p])), [ownProducts]);
  const candidateMatches = useMemo(() => (matches ?? []).filter((m) => m.status === "candidate"), [matches]);
  const confirmedByProduct = useMemo(() => {
    const map: Record<number, ProductMatch[]> = {};
    for (const m of matches ?? []) {
      if (m.status !== "confirmed") continue;
      (map[m.product_id] ??= []).push(m);
    }
    return map;
  }, [matches]);
  const allCandidatesSelected =
    candidateMatches.length > 0 && candidateMatches.every((m) => selectedIds.has(m.id));
  const confirmedMatchCount = useMemo(() => (matches ?? []).filter((m) => m.status === "confirmed").length, [matches]);

  async function handleDiscover() {
    setError(null);
    setDiscovering(true);
    try {
      await api.discovery.discoverProducts(siteId, maxProducts);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setDiscovering(false);
    }
  }

  async function handleAutoMatch() {
    setError(null);
    setMatching(true);
    try {
      await api.discovery.autoMatch(siteId);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setMatching(false);
    }
  }

  async function handleUpdateMatch(id: number, status: "confirmed" | "dismissed") {
    setUpdatingId(id);
    try {
      await api.discovery.updateMatch(id, status);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update that match. Try again.");
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

  async function handleBulkUpdate(status: "confirmed" | "dismissed") {
    setBulkUpdating(true);
    try {
      await Promise.all(Array.from(selectedIds).map((id) => api.discovery.updateMatch(id, status)));
      setSelectedIds(new Set());
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't update those matches. Try again.");
    } finally {
      setBulkUpdating(false);
    }
  }

  async function handleManualMatch(productId: number, competitorProductId: number) {
    try {
      await api.discovery.createMatch(productId, competitorProductId);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't create that match. Try again.");
    }
  }

  async function handleUnmatch(matchId: number) {
    try {
      await api.discovery.updateMatch(matchId, "dismissed");
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't remove that match. Try again.");
    }
  }

  if (notFound) {
    return (
      <div className="mx-auto max-w-6xl px-8 py-10">
        <p className="text-sm text-danger">Couldn't find this competitor.</p>
        <Link href="/discovery" className="mt-2 inline-block text-sm text-accent hover:underline">
          Back to Discovery
        </Link>
      </div>
    );
  }

  if (!site) {
    return (
      <div className="mx-auto max-w-6xl px-8 py-10">
        <p className="text-sm text-slate-soft">Loading…</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl px-8 py-10">
      <Link href="/discovery" className="inline-flex items-center gap-1.5 text-sm text-slate-soft hover:text-ink">
        <ArrowLeft className="size-4" />
        Back to Discovery
      </Link>

      <div className="mt-4">
        <PageHeader
          title={site.name || site.domain}
          description={
            <a
              href={`https://${site.domain}`}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 hover:text-accent"
            >
              {site.domain}
              <ExternalLink className="size-3" />
            </a>
          }
          actions={
            <>
              <div className="space-y-1">
                <div className="flex items-center gap-1.5">
                  <label htmlFor="max-products" className="text-xs font-medium text-slate">
                    Max products
                  </label>
                  <InfoTooltip text="More products found means more AI reasoning and web-search cost on this run — your provider bills for both, so higher isn't free." />
                </div>
                <Input
                  id="max-products"
                  type="number"
                  min={1}
                  max={25}
                  value={maxProducts}
                  onChange={(e) => {
                    const next = Number(e.target.value);
                    setMaxProducts(Number.isNaN(next) ? 15 : Math.min(25, Math.max(1, next)));
                  }}
                  className="w-20"
                />
              </div>
              <Button onClick={handleDiscover} disabled={discovering}>
                <Sparkles className="size-4" />
                {discovering ? "Researching…" : "Discover products"}
              </Button>
            </>
          }
        />
      </div>

      {error && <p className="mt-4 text-sm text-danger">{error}</p>}
      {discovering && (
        <p className="mt-4 text-sm text-slate-soft">This can take up to 30 seconds — your AI provider is actively searching the web.</p>
      )}

      {/* Tabs, not always-expanded sections — browsing discovered products,
          reviewing AI match candidates, and manually pairing products are
          three separate tasks a user does one at a time, not something
          meant to be scanned together. */}
      <div className="mt-8 flex items-center gap-1 border-b border-border">
        {(
          [
            ["products", "Products", products?.length],
            ["auto-match", "Auto-match", candidateMatches.length],
            ["manual", "Manual matching", confirmedMatchCount],
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

      {view === "products" && (
        <div className="mt-6">
          {!products && <p className="text-sm text-slate-soft">Loading…</p>}
          {products && products.length === 0 && (
            <p className="text-sm text-slate">No products discovered yet — click "Discover products" above.</p>
          )}
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
            {products?.map((p) => (
              <Card key={p.id}>
                <div className="flex flex-wrap items-center gap-2">
                  <a
                    href={p.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 font-medium text-ink hover:text-accent"
                  >
                    {p.title}
                    <ExternalLink className="size-3" />
                  </a>
                  {p.stock_status && <Badge tone="neutral">{p.stock_status}</Badge>}
                </div>
                {p.price != null && (
                  <p className="mt-0.5 text-xs tabular-nums text-slate-soft">
                    {p.currency} {p.price}
                  </p>
                )}
                {p.description && <p className="mt-2 text-sm text-slate">{p.description}</p>}
                {p.additional_info && <p className="mt-1 text-xs text-slate-soft">{p.additional_info}</p>}
              </Card>
            ))}
          </div>
        </div>
      )}

      {view === "auto-match" && (
        <div className="mt-6">
          <div className="flex items-center justify-between gap-3">
            <h2 className="text-sm font-medium text-ink">Auto-match with your catalog</h2>
            <Button variant="outline" size="sm" onClick={handleAutoMatch} disabled={matching || !products?.length}>
              <Sparkles className="size-3.5" />
              {matching ? "Matching…" : "Auto-match"}
            </Button>
          </div>

          {!products?.length ? (
            <p className="mt-3 text-sm text-slate">Discover products first, then auto-match against your catalog.</p>
          ) : candidateMatches.length > 0 ? (
            <>
              <div className="mt-3 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <Checkbox
                    checked={allCandidatesSelected}
                    onCheckedChange={() =>
                      setSelectedIds(allCandidatesSelected ? new Set() : new Set(candidateMatches.map((m) => m.id)))
                    }
                    aria-label="Select all candidate matches"
                  />
                  <span className="text-xs text-slate-soft">
                    {candidateMatches.length} candidate{candidateMatches.length === 1 ? "" : "s"} to review
                  </span>
                </div>
                {selectedIds.size > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-soft">{selectedIds.size} selected</span>
                    <Button variant="outline" size="sm" disabled={bulkUpdating} onClick={() => handleBulkUpdate("confirmed")}>
                      <Check className="size-3.5" />
                      Confirm all
                    </Button>
                    <Button variant="outline" size="sm" disabled={bulkUpdating} onClick={() => handleBulkUpdate("dismissed")}>
                      <X className="size-3.5" />
                      Dismiss all
                    </Button>
                  </div>
                )}
              </div>
              <div className="mt-2 grid grid-cols-1 gap-2 lg:grid-cols-2">
                {candidateMatches.map((m) => (
                  <MatchCandidateCard
                    key={m.id}
                    match={m}
                    product={ownProductById[m.product_id]}
                    competitorProduct={competitorProductById[m.competitor_product_id]}
                    onUpdate={handleUpdateMatch}
                    updating={updatingId === m.id || bulkUpdating}
                    selected={selectedIds.has(m.id)}
                    onToggleSelect={toggleSelect}
                  />
                ))}
              </div>
            </>
          ) : (
            <p className="mt-3 text-sm text-slate">No candidates to review — click "Auto-match" above.</p>
          )}
        </div>
      )}

      {view === "manual" && (
        <div className="mt-6">
          <h2 className="text-sm font-medium text-ink">Manual matching</h2>
          {!products?.length ? (
            <p className="mt-3 text-sm text-slate">Discover products first, then drag one onto one of your own to pair them.</p>
          ) : (
            <>
              <p className="mt-1 text-xs text-slate-soft">Drag a competitor product onto one of your own to pair them.</p>
              <div className="mt-2 grid grid-cols-1 gap-4 lg:grid-cols-2">
                <div>
                  <p className="text-xs font-medium text-slate-soft">Your products</p>
                  <div className="mt-2 grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {ownProducts?.map((p) => (
                      <OwnProductDropTarget
                        key={p.id}
                        product={p}
                        confirmedMatches={confirmedByProduct[p.id] ?? []}
                        competitorProductById={competitorProductById}
                        onUnmatch={handleUnmatch}
                        onDropCompetitorProduct={handleManualMatch}
                      />
                    ))}
                  </div>
                </div>
                <div>
                  <p className="text-xs font-medium text-slate-soft">{site.name || site.domain}&rsquo;s products</p>
                  <div className="mt-2 grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {products.map((p) => (
                      <CompetitorProductChip key={p.id} product={p} />
                    ))}
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
