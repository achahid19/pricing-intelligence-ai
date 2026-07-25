"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { api, ApiError, type ImportResult } from "@/lib/api";

export function ImportProductsDialog({ onImported }: { onImported: () => void }) {
  const [open, setOpen] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<ImportResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      const res = await api.products.importFile(file);
      setResult(res);
      onImported();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setLoading(false);
    }
  }

  function reset() {
    setError(null);
    setResult(null);
    setDragActive(false);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (!next) reset();
      }}
    >
      <DialogTrigger
        render={
          <Button variant="outline">
            <Upload className="size-4" />
            Import
          </Button>
        }
      />
      <DialogContent>
        <DialogTitle>Import products</DialogTitle>
        <DialogDescription>CSV or XLSX. Columns: name, price required; sku, currency, category, brand, barcode, description optional.</DialogDescription>

        <div className="mt-5">
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDragActive(true);
            }}
            onDragLeave={() => setDragActive(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragActive(false);
              const file = e.dataTransfer.files?.[0];
              if (file) handleFile(file);
            }}
            className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-lg border-2 border-dashed px-6 py-10 text-center transition-colors ${
              dragActive ? "border-accent bg-accent/5" : "border-border hover:border-slate-soft"
            }`}
          >
            <Upload className="size-5 text-slate-soft" />
            <p className="text-sm text-ink">
              <span className="font-medium text-accent">Click to upload</span> or drag a file here
            </p>
            <p className="text-xs text-slate-soft">.csv, .xlsx up to 5MB</p>
            <input
              ref={inputRef}
              type="file"
              accept=".csv,.xlsx,.xlsm"
              className="hidden"
              onChange={(e) => {
                const file = e.target.files?.[0];
                if (file) handleFile(file);
              }}
            />
          </label>

          {loading && <p className="mt-3 text-sm text-slate">Importing…</p>}
          {error && <p className="mt-3 text-sm text-danger">{error}</p>}

          {result && (
            <div className="mt-4 space-y-2 text-sm">
              <p className="font-medium text-good">{result.created} product{result.created === 1 ? "" : "s"} added</p>
              {result.skipped.length > 0 && (
                <div>
                  <p className="text-slate">Skipped ({result.skipped.length}):</p>
                  <ul className="mt-1 list-inside list-disc text-xs text-slate-soft">
                    {result.skipped.map((s, i) => (
                      <li key={i}>{s}</li>
                    ))}
                  </ul>
                </div>
              )}
              {result.errors.length > 0 && (
                <div>
                  <p className="text-danger">Errors ({result.errors.length}):</p>
                  <ul className="mt-1 list-inside list-disc text-xs text-danger/80">
                    {result.errors.map((e, i) => (
                      <li key={i}>{e}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
