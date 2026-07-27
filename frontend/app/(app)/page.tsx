"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Package, Search, Settings, ShieldCheck } from "lucide-react";

import { api, type CompetitorSite, type DiscoveryRun, type Product } from "@/lib/api";

function StatCard({
  icon: Icon,
  label,
  value,
  hint,
}: {
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
  hint: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-paper-raised p-4">
      <div className="flex items-center gap-2 text-slate">
        <Icon className="size-4" />
        <span className="text-xs font-medium">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-ink">{value}</p>
      <p className="mt-1 text-xs text-slate-soft">{hint}</p>
    </div>
  );
}

const RUN_STATUS_TONE: Record<string, string> = {
  completed: "bg-good/10 text-good",
  running: "bg-accent/10 text-accent",
  failed: "bg-danger/10 text-danger",
};

export default function Home() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [savedSites, setSavedSites] = useState<CompetitorSite[] | null>(null);
  const [runs, setRuns] = useState<DiscoveryRun[] | null>(null);

  useEffect(() => {
    api.products.list().then(setProducts).catch(() => setProducts([]));
    api.discovery.listSites("saved").then(setSavedSites).catch(() => setSavedSites([]));
    api.discovery.listRuns().then(setRuns).catch(() => setRuns([]));
  }, []);

  const lastRun = runs?.[0];
  const lastRunDate = lastRun ? new Date(lastRun.triggered_at).toLocaleString() : null;

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <h1 className="font-[family-name:var(--font-display)] text-2xl font-semibold text-ink">Welcome back</h1>
      <p className="mt-1 text-sm text-slate">Here's where things stand across your catalog and competitor research.</p>

      <div className="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-3">
        <StatCard
          icon={Package}
          label="Catalog"
          value={products ? String(products.length) : "…"}
          hint={products && products.length === 0 ? "No products yet" : "products tracked"}
        />
        <StatCard
          icon={ShieldCheck}
          label="Competitors"
          value={savedSites ? String(savedSites.length) : "…"}
          hint={savedSites && savedSites.length === 0 ? "None saved yet" : "saved for tracking"}
        />
        <div className="rounded-lg border border-border bg-paper-raised p-4">
          <div className="flex items-center gap-2 text-slate">
            <Search className="size-4" />
            <span className="text-xs font-medium">Last discovery run</span>
          </div>
          {lastRun ? (
            <>
              <span
                className={`mt-2 inline-flex rounded-full px-2 py-0.5 text-xs font-medium capitalize ${RUN_STATUS_TONE[lastRun.status] ?? "bg-slate/10 text-slate"}`}
              >
                {lastRun.status}
              </span>
              <p className="mt-1.5 text-xs text-slate-soft">{lastRunDate}</p>
            </>
          ) : (
            <>
              <p className="mt-2 text-2xl font-semibold text-ink">—</p>
              <p className="mt-1 text-xs text-slate-soft">Never run yet</p>
            </>
          )}
        </div>
      </div>

      <div className="mt-8 space-y-2">
        <h2 className="text-sm font-medium text-ink">Quick actions</h2>
        {products && products.length === 0 && (
          <Link
            href="/catalog"
            className="flex items-center justify-between rounded-lg border border-border bg-paper-raised p-4 transition-colors hover:bg-black/[0.02]"
          >
            <div>
              <p className="text-sm font-medium text-ink">Add your first products</p>
              <p className="mt-0.5 text-xs text-slate-soft">Discovery uses your catalog to find relevant competitors.</p>
            </div>
            <ArrowRight className="size-4 shrink-0 text-slate-soft" />
          </Link>
        )}
        {!lastRun && products && products.length > 0 && (
          <Link
            href="/discovery"
            className="flex items-center justify-between rounded-lg border border-border bg-paper-raised p-4 transition-colors hover:bg-black/[0.02]"
          >
            <div>
              <p className="text-sm font-medium text-ink">Run competitor discovery</p>
              <p className="mt-0.5 text-xs text-slate-soft">Find real competitors based on your business context and catalog.</p>
            </div>
            <ArrowRight className="size-4 shrink-0 text-slate-soft" />
          </Link>
        )}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          <Link
            href="/catalog"
            className="flex items-center gap-2 rounded-lg border border-border bg-paper-raised p-3 text-sm font-medium text-ink transition-colors hover:bg-black/[0.02]"
          >
            <Package className="size-4 text-slate-soft" />
            Catalog
          </Link>
          <Link
            href="/discovery"
            className="flex items-center gap-2 rounded-lg border border-border bg-paper-raised p-3 text-sm font-medium text-ink transition-colors hover:bg-black/[0.02]"
          >
            <Search className="size-4 text-slate-soft" />
            Discovery
          </Link>
          <Link
            href="/settings"
            className="flex items-center gap-2 rounded-lg border border-border bg-paper-raised p-3 text-sm font-medium text-ink transition-colors hover:bg-black/[0.02]"
          >
            <Settings className="size-4 text-slate-soft" />
            Settings
          </Link>
        </div>
      </div>
    </div>
  );
}
