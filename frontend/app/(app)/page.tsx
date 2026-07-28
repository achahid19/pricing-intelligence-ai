"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowRight, Package, Search, Settings, ShieldCheck, TrendingUp } from "lucide-react";

import { Badge, type BadgeTone } from "@/components/ui/badge";
import { Card, cardClassName } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { cn } from "@/lib/utils";
import { api, type CompetitorSite, type DiscoveryRun, type Product, type TrackedMatch } from "@/lib/api";

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
    <Card>
      <div className="flex items-center gap-2 text-slate">
        <Icon className="size-4" />
        <span className="text-xs font-medium">{label}</span>
      </div>
      <p className="mt-2 text-2xl font-semibold tabular-nums text-ink">{value}</p>
      <p className="mt-1 text-xs text-slate-soft">{hint}</p>
    </Card>
  );
}

const RUN_STATUS_TONE: Record<string, BadgeTone> = {
  completed: "good",
  running: "accent",
  failed: "danger",
};

function QuickActionLink({
  href,
  title,
  description,
}: {
  href: string;
  title: string;
  description: string;
}) {
  return (
    <Link href={href} className={cn(cardClassName, "flex items-center justify-between transition-colors hover:bg-black/[0.02]")}>
      <div>
        <p className="text-sm font-medium text-ink">{title}</p>
        <p className="mt-0.5 text-xs text-slate-soft">{description}</p>
      </div>
      <ArrowRight className="size-4 shrink-0 text-slate-soft" />
    </Link>
  );
}

export default function Home() {
  const [products, setProducts] = useState<Product[] | null>(null);
  const [savedSites, setSavedSites] = useState<CompetitorSite[] | null>(null);
  const [runs, setRuns] = useState<DiscoveryRun[] | null>(null);
  const [trackedMatches, setTrackedMatches] = useState<TrackedMatch[] | null>(null);

  useEffect(() => {
    api.products.list().then(setProducts).catch(() => setProducts([]));
    api.discovery.listSites("saved").then(setSavedSites).catch(() => setSavedSites([]));
    api.discovery.listRuns().then(setRuns).catch(() => setRuns([]));
    api.discovery.listTrackedMatches().then(setTrackedMatches).catch(() => setTrackedMatches([]));
  }, []);

  const lastRun = runs?.[0];
  const lastRunDate = lastRun ? new Date(lastRun.triggered_at).toLocaleString() : null;

  return (
    <div className="mx-auto max-w-4xl px-8 py-10">
      <PageHeader title="Welcome back" description="Here's where things stand across your catalog and competitor research." />

      <div className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-4">
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
        <StatCard
          icon={TrendingUp}
          label="Tracked"
          value={trackedMatches ? String(trackedMatches.length) : "…"}
          hint={trackedMatches && trackedMatches.length === 0 ? "No matches confirmed yet" : "confirmed matches"}
        />
        <Card>
          <div className="flex items-center gap-2 text-slate">
            <Search className="size-4" />
            <span className="text-xs font-medium">Last discovery run</span>
          </div>
          {lastRun ? (
            <>
              <Badge tone={RUN_STATUS_TONE[lastRun.status] ?? "neutral"} className="mt-2 capitalize">
                {lastRun.status}
              </Badge>
              <p className="mt-1.5 text-xs text-slate-soft">{lastRunDate}</p>
            </>
          ) : (
            <>
              <p className="mt-2 text-2xl font-semibold text-ink">—</p>
              <p className="mt-1 text-xs text-slate-soft">Never run yet</p>
            </>
          )}
        </Card>
      </div>

      <div className="mt-8 space-y-2">
        <h2 className="text-sm font-medium text-ink">Quick actions</h2>
        {products && products.length === 0 && (
          <QuickActionLink
            href="/catalog"
            title="Add your first products"
            description="Discovery uses your catalog to find relevant competitors."
          />
        )}
        {!lastRun && products && products.length > 0 && (
          <QuickActionLink
            href="/discovery"
            title="Run competitor discovery"
            description="Find real competitors based on your business context and catalog."
          />
        )}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Link
            href="/catalog"
            className={cn(cardClassName, "flex items-center gap-2 p-3 text-sm font-medium text-ink transition-colors hover:bg-black/[0.02]")}
          >
            <Package className="size-4 text-slate-soft" />
            Catalog
          </Link>
          <Link
            href="/discovery"
            className={cn(cardClassName, "flex items-center gap-2 p-3 text-sm font-medium text-ink transition-colors hover:bg-black/[0.02]")}
          >
            <Search className="size-4 text-slate-soft" />
            Discovery
          </Link>
          <Link
            href="/tracked"
            className={cn(cardClassName, "flex items-center gap-2 p-3 text-sm font-medium text-ink transition-colors hover:bg-black/[0.02]")}
          >
            <TrendingUp className="size-4 text-slate-soft" />
            Tracked
          </Link>
          <Link
            href="/settings"
            className={cn(cardClassName, "flex items-center gap-2 p-3 text-sm font-medium text-ink transition-colors hover:bg-black/[0.02]")}
          >
            <Settings className="size-4 text-slate-soft" />
            Settings
          </Link>
        </div>
      </div>
    </div>
  );
}
