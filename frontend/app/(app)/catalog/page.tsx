"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ExternalLink, Package, Search, Trash2, TrendingUp, X } from "lucide-react";

import { DeleteAllProductsDialog } from "@/components/catalog/DeleteAllProductsDialog";
import { ImportProductsDialog } from "@/components/catalog/ImportProductsDialog";
import { ProductDialog } from "@/components/catalog/ProductDialog";
import { WebsiteImportDialog } from "@/components/catalog/WebsiteImportDialog";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { PageHeader } from "@/components/ui/page-header";
import { Select } from "@/components/ui/select";
import { api, ApiError, type Product } from "@/lib/api";
import { cn } from "@/lib/utils";

const SOURCE_LABEL: Record<string, string> = {
  manual: "Manual",
  csv: "CSV import",
  image_ai: "AI from photo",
  website_ai: "Website import",
  url: "URL import",
};

type SortKey = "category" | "name" | "price_asc" | "price_desc";

export default function CatalogPage() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("category");
  const [confirmingDelete, setConfirmingDelete] = useState<number | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);
  const [highlightId, setHighlightId] = useState<number | null>(null);
  // Confirmed-match count per product_id — a product row otherwise shows
  // price/category/source but nothing about competitive tracking at all,
  // the clearest "can't find everything" gap found in the nav audit.
  // Computed client-side from the same workspace-wide list Tracked itself
  // renders; no new backend endpoint needed.
  const [trackedCounts, setTrackedCounts] = useState<Record<number, number>>({});

  const load = useCallback(() => {
    api.products
      .list()
      .then(setProducts)
      .catch(() => setError("Couldn't load your catalog. Try refreshing."));
    api.discovery
      .listTrackedMatches()
      .then((matches) => {
        const counts: Record<number, number> = {};
        for (const m of matches) counts[m.product_id] = (counts[m.product_id] ?? 0) + 1;
        setTrackedCounts(counts);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    load();
    // Plain window.location read (not useSearchParams) so this page never
    // needs a Suspense boundary — a one-time read at mount is all a deep
    // link needs, no reactivity to later client-side query changes.
    const id = Number(new URLSearchParams(window.location.search).get("highlight"));
    if (id) setHighlightId(id);
  }, [load]);

  // Scroll the linked-to row into view once it's actually rendered, then
  // fade the highlight after a few seconds instead of leaving it stuck on.
  useEffect(() => {
    if (!highlightId || !products) return;
    const row = document.getElementById(`product-${highlightId}`);
    row?.scrollIntoView({ behavior: "smooth", block: "center" });
    const timer = setTimeout(() => setHighlightId(null), 2500);
    return () => clearTimeout(timer);
  }, [highlightId, products]);

  const categories = useMemo(() => {
    if (!products) return [];
    const set = new Set(products.map((p) => p.category).filter((c): c is string => !!c));
    return Array.from(set).sort();
  }, [products]);

  const visibleProducts = useMemo(() => {
    if (!products) return [];
    const query = search.trim().toLowerCase();
    let list = products.filter((p) => {
      if (activeCategory && p.category !== activeCategory) return false;
      if (!query) return true;
      return [p.name, p.sku, p.brand, p.category].some((field) => field?.toLowerCase().includes(query));
    });
    // Priceless products (no price set yet) always sort last regardless of
    // direction — there's nothing to rank them by, not a reason to flip
    // them to the top on descending sort.
    const priceOrNull = (p: Product) => (p.price != null ? parseFloat(p.price) : null);
    list = [...list].sort((a, b) => {
      switch (sortKey) {
        case "name":
          return a.name.localeCompare(b.name);
        case "price_asc":
        case "price_desc": {
          const av = priceOrNull(a);
          const bv = priceOrNull(b);
          if (av == null && bv == null) return 0;
          if (av == null) return 1;
          if (bv == null) return -1;
          return sortKey === "price_asc" ? av - bv : bv - av;
        }
        case "category":
        default:
          return (a.category ?? "￿").localeCompare(b.category ?? "￿") || a.name.localeCompare(b.name);
      }
    });
    return list;
  }, [products, search, activeCategory, sortKey]);

  async function handleDelete(id: number) {
    setDeleting(id);
    try {
      await api.products.delete(id);
      setConfirmingDelete(null);
      load();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't delete this product. Try again.");
    } finally {
      setDeleting(null);
    }
  }

  return (
    <div className="mx-auto max-w-5xl px-8 py-10">
      <PageHeader
        title="Catalog"
        description={products ? `${products.length} product${products.length === 1 ? "" : "s"}` : "Loading…"}
        actions={
          <>
            <WebsiteImportDialog onImported={load} />
            <ImportProductsDialog onImported={load} />
            <ProductDialog onSaved={load} />
          </>
        }
      />

      {error && <p className="mt-6 text-sm text-danger">{error}</p>}

      {products && products.length > 0 && (
        <div className="mt-6 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-[200px] flex-1">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-soft" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name, SKU, or brand…"
                className="h-9 pr-3 pl-9"
              />
            </div>
            <Select value={sortKey} onChange={(e) => setSortKey(e.target.value as SortKey)} className="h-9">
              <option value="category">Sort: Category</option>
              <option value="name">Sort: Name A–Z</option>
              <option value="price_asc">Sort: Price low–high</option>
              <option value="price_desc">Sort: Price high–low</option>
            </Select>
            <DeleteAllProductsDialog count={products.length} onDeleted={load} />
          </div>

          {categories.length > 1 && (
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => setActiveCategory(null)}
                className={cn(
                  "rounded-full px-2 py-0.5 text-xs font-medium transition-colors",
                  activeCategory === null ? "bg-accent text-white" : "bg-black/[0.03] text-slate hover:bg-black/[0.06]"
                )}
              >
                All
              </button>
              {categories.map((c) => (
                <button
                  key={c}
                  onClick={() => setActiveCategory(c === activeCategory ? null : c)}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-medium transition-colors",
                    activeCategory === c ? "bg-accent text-white" : "bg-black/[0.03] text-slate hover:bg-black/[0.06]"
                  )}
                >
                  {c}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {products && products.length === 0 && (
        <div className="mt-16 flex flex-col items-center text-center">
          <div className="flex size-12 items-center justify-center rounded-full bg-black/[0.03]">
            <Package className="size-5 text-slate-soft" />
          </div>
          <p className="mt-4 text-sm font-medium text-ink">No products yet</p>
          <p className="mt-1 max-w-xs text-sm text-slate">
            Add one manually or import a spreadsheet to get started.
          </p>
        </div>
      )}

      {products && products.length > 0 && visibleProducts.length === 0 && (
        <p className="mt-10 text-center text-sm text-slate">No products match your search or filter.</p>
      )}

      {visibleProducts.length > 0 && (
        <Card className="mt-4 overflow-x-auto p-0">
          <table className="w-full min-w-[720px] border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-slate-soft">
                <th className="px-4 py-2.5 font-medium">Product</th>
                <th className="px-4 py-2.5 font-medium">Category</th>
                <th className="px-4 py-2.5 font-medium">Description</th>
                <th className="px-4 py-2.5 font-medium">Source</th>
                <th className="px-4 py-2.5 text-right font-medium">Price</th>
                <th className="w-20 px-4 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {visibleProducts.map((p) => (
                <tr
                  key={p.id}
                  id={`product-${p.id}`}
                  className={cn(
                    "border-b border-border transition-colors last:border-0 hover:bg-black/[0.015]",
                    highlightId === p.id && "bg-accent/10 hover:bg-accent/10"
                  )}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-3">
                      {p.image_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={p.image_url} alt="" className="size-9 shrink-0 rounded object-cover" />
                      ) : (
                        <div className="flex size-9 shrink-0 items-center justify-center rounded bg-black/[0.03]">
                          <Package className="size-4 text-slate-soft" />
                        </div>
                      )}
                      <div className="min-w-0">
                        {p.source_url ? (
                          <a
                            href={p.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            title={
                              p.source_url_verified === false
                                ? `Unconfirmed — may not be this product's exact page: ${p.source_url}`
                                : `Open source page: ${p.source_url}`
                            }
                            className="group inline-flex max-w-full items-center gap-1 truncate font-medium text-ink hover:text-accent"
                          >
                            <span className="truncate">{p.name}</span>
                            {p.source_url_verified === false ? (
                              <AlertTriangle className="size-3 shrink-0 text-amber-500" />
                            ) : (
                              <ExternalLink className="size-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
                            )}
                          </a>
                        ) : (
                          <p className="truncate font-medium text-ink">{p.name}</p>
                        )}
                        <p className="mt-0.5 truncate text-xs text-slate">
                          {[p.brand, p.sku].filter(Boolean).join(" · ") || "—"}
                        </p>
                        {trackedCounts[p.id] > 0 && (
                          <Link
                            href="/tracked"
                            className="mt-0.5 inline-flex items-center gap-1 text-xs text-slate-soft hover:text-accent"
                          >
                            <TrendingUp className="size-3" />
                            {trackedCounts[p.id]} competitor{trackedCounts[p.id] === 1 ? "" : "s"} tracked
                          </Link>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {p.category ? (
                      <Badge tone="neutral">{p.category}</Badge>
                    ) : (
                      <span className="text-xs text-slate-soft">—</span>
                    )}
                  </td>
                  <td className="max-w-64 px-4 py-3">
                    <p className="truncate text-xs text-slate" title={p.description ?? undefined}>
                      {p.description || "—"}
                    </p>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-slate-soft">{SOURCE_LABEL[p.import_source] ?? p.import_source}</span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    {p.price != null ? (
                      <span className="font-[family-name:var(--font-data)] text-sm tabular-nums text-ink">
                        {p.currency} {p.price}
                      </span>
                    ) : (
                      <span className="text-xs text-slate-soft">No price set</span>
                    )}
                    {p.min_price && (
                      <p className="font-[family-name:var(--font-data)] text-xs tabular-nums text-slate-soft" title="Minimum advertised price (MAP)">
                        MAP {p.currency} {p.min_price}
                      </p>
                    )}
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-1">
                      {confirmingDelete === p.id ? (
                        <>
                          <button
                            onClick={() => handleDelete(p.id)}
                            disabled={deleting === p.id}
                            className="rounded-md px-2 py-1 text-xs font-medium text-danger transition-colors hover:bg-danger/10"
                          >
                            {deleting === p.id ? "…" : "Confirm"}
                          </button>
                          <button
                            onClick={() => setConfirmingDelete(null)}
                            className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-black/[0.03] hover:text-ink"
                            aria-label="Cancel delete"
                          >
                            <X className="size-4" />
                          </button>
                        </>
                      ) : (
                        <>
                          <ProductDialog product={p} onSaved={load} />
                          <button
                            onClick={() => setConfirmingDelete(p.id)}
                            aria-label="Delete product"
                            className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-danger/10 hover:text-danger"
                          >
                            <Trash2 className="size-4" />
                          </button>
                        </>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  );
}
