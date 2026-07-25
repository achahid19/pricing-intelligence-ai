"use client";

import { useCallback, useEffect, useState } from "react";
import { Package } from "lucide-react";

import { AddProductDialog } from "@/components/catalog/AddProductDialog";
import { ImportProductsDialog } from "@/components/catalog/ImportProductsDialog";
import { Button } from "@/components/ui/button";
import { api, type Product } from "@/lib/api";

export default function CatalogPage() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    api.products
      .list()
      .then(setProducts)
      .catch(() => setError("Couldn't load your catalog. Try refreshing."));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-ink">
            Catalog
          </h1>
          <p className="mt-1 text-sm text-slate">
            {products ? `${products.length} product${products.length === 1 ? "" : "s"}` : "Loading…"}
          </p>
        </div>
        <div className="flex gap-2">
          <ImportProductsDialog onImported={load} />
          <AddProductDialog onAdded={load} />
        </div>
      </div>

      {error && <p className="mt-6 text-sm text-danger">{error}</p>}

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

      {products && products.length > 0 && (
        <div className="mt-6 divide-y divide-border rounded-lg border border-border bg-paper-raised">
          {products.map((p) => (
            <div key={p.id} className="flex items-center justify-between gap-4 px-4 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-ink">{p.name}</p>
                <p className="mt-0.5 truncate text-xs text-slate">
                  {[p.brand, p.category, p.sku].filter(Boolean).join(" · ") || "—"}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-3">
                <span className="font-[family-name:var(--font-data)] text-sm text-ink">
                  {p.currency} {p.price}
                </span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
