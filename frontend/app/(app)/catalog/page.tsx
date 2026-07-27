"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Package, Search, Trash2, X } from "lucide-react";

import { ImportProductsDialog } from "@/components/catalog/ImportProductsDialog";
import { ProductDialog } from "@/components/catalog/ProductDialog";
import { api, ApiError, type Product } from "@/lib/api";

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

  const load = useCallback(() => {
    api.products
      .list()
      .then(setProducts)
      .catch(() => setError("Couldn't load your catalog. Try refreshing."));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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
    list = [...list].sort((a, b) => {
      switch (sortKey) {
        case "name":
          return a.name.localeCompare(b.name);
        case "price_asc":
          return parseFloat(a.price) - parseFloat(b.price);
        case "price_desc":
          return parseFloat(b.price) - parseFloat(a.price);
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
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-ink">
            Catalog
          </h1>
          <p className="mt-1 text-sm text-slate">
            {products ? `${products.length} product${products.length === 1 ? "" : "s"}` : "Loading…"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <ImportProductsDialog onImported={load} />
          <ProductDialog onSaved={load} />
        </div>
      </div>

      {error && <p className="mt-6 text-sm text-danger">{error}</p>}

      {products && products.length > 0 && (
        <div className="mt-6 space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-slate-soft" />
              <input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search by name, SKU, or brand…"
                className="h-9 w-full rounded-md border border-border bg-paper-raised pr-3 pl-9 text-sm text-ink placeholder:text-slate-soft outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/20"
              />
            </div>
            <select
              value={sortKey}
              onChange={(e) => setSortKey(e.target.value as SortKey)}
              className="h-9 rounded-md border border-border bg-paper-raised px-2 text-sm text-ink outline-none focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/20"
            >
              <option value="category">Sort: Category</option>
              <option value="name">Sort: Name A–Z</option>
              <option value="price_asc">Sort: Price low–high</option>
              <option value="price_desc">Sort: Price high–low</option>
            </select>
          </div>

          {categories.length > 1 && (
            <div className="flex flex-wrap gap-1.5">
              <button
                onClick={() => setActiveCategory(null)}
                className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                  activeCategory === null ? "bg-accent text-white" : "bg-black/[0.03] text-slate hover:bg-black/[0.06]"
                }`}
              >
                All
              </button>
              {categories.map((c) => (
                <button
                  key={c}
                  onClick={() => setActiveCategory(c === activeCategory ? null : c)}
                  className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                    activeCategory === c ? "bg-accent text-white" : "bg-black/[0.03] text-slate hover:bg-black/[0.06]"
                  }`}
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
        <div className="mt-4 overflow-x-auto rounded-lg border border-border bg-paper-raised">
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
                <tr key={p.id} className="border-b border-border last:border-0 hover:bg-black/[0.015]">
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
                        <p className="truncate font-medium text-ink">{p.name}</p>
                        <p className="mt-0.5 truncate text-xs text-slate">
                          {[p.brand, p.sku].filter(Boolean).join(" · ") || "—"}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    {p.category ? (
                      <span className="rounded-full bg-slate/10 px-2 py-0.5 text-xs font-medium text-slate">
                        {p.category}
                      </span>
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
                    <span className="font-[family-name:var(--font-data)] text-sm tabular-nums text-ink">
                      {p.currency} {p.price}
                    </span>
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
        </div>
      )}
    </div>
  );
}
