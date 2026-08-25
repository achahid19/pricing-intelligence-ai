"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { Activity as ActivityIcon, Bot, FileText, LayoutGrid, LogOut, Menu, Package, Search, Settings, TrendingUp, X } from "lucide-react";

import { ActivityIndicator } from "@/components/ActivityIndicator";
import { ThemeToggle } from "@/components/ThemeToggle";
import { api, clearToken } from "@/lib/api";
import { useActivity } from "@/lib/activity";
import { useProductTour } from "@/lib/productTour";

// "Apex" is the product name for the AI assistant (the route itself stays
// /assistant — functional/internal, not part of the branding). The nav
// link opens the full-page, wider-focus view of the same conversation the
// floating widget (components/assistant/AssistantWidget.tsx) shows
// everywhere else — both read/write the shared AssistantChatProvider
// context, so it's one conversation either way, not two that could drift
// apart.
const NAV = [
  { href: "/", label: "Home", icon: LayoutGrid },
  { href: "/catalog", label: "Catalog", icon: Package },
  { href: "/discovery", label: "Discovery", icon: Search },
  { href: "/tracked", label: "Tracked", icon: TrendingUp },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/activity", label: "Activity", icon: ActivityIcon },
  { href: "/assistant", label: "Apex", icon: Bot },
  { href: "/settings", label: "Settings", icon: Settings },
];

function NavLinks({
  pathname,
  onNavigate,
  candidateCount,
  runningCount,
}: {
  pathname: string;
  onNavigate?: () => void;
  candidateCount: number;
  runningCount: number;
}) {
  return (
    <nav className="flex-1 space-y-0.5 p-2">
      {NAV.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        const Icon = item.icon;
        const badge =
          item.href === "/discovery" && candidateCount > 0
            ? candidateCount
            : item.href === "/activity" && runningCount > 0
              ? runningCount
              : null;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            data-tour={`nav-${item.href === "/" ? "home" : item.href.slice(1)}`}
            className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              active ? "bg-accent/10 text-accent" : "text-slate hover:bg-black/[0.03] hover:text-ink"
            }`}
          >
            <Icon className="size-4" />
            <span className="flex-1">{item.label}</span>
            {badge != null && (
              <span className="inline-flex min-w-[1.25rem] items-center justify-center rounded-full bg-accent px-1.5 py-0.5 text-[11px] font-semibold leading-none text-white">
                {badge}
              </span>
            )}
          </Link>
        );
      })}
    </nav>
  );
}

export function Sidebar({ workspaceName }: { workspaceName: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const { entries } = useActivity();
  const { active: tourActive } = useProductTour();
  const [mobileOpen, setMobileOpen] = useState(false);
  const [candidateCount, setCandidateCount] = useState(0);
  const runningCount = entries.filter((e) => e.status === "running").length;

  // Closing on every route change covers both nav-link clicks and any other
  // way the path changes (back/forward) — simpler than wiring onNavigate
  // through every possible exit.
  useEffect(() => {
    setMobileOpen(false);
  }, [pathname]);

  // The product tour spotlights nav items that live inside this drawer on
  // narrow viewports — without forcing it open, ProductTourOverlay would
  // find only the desktop <aside>'s copy (present in the DOM but
  // display:none below md) and measure a degenerate zero-sized rect.
  // Only forces it open once when the tour starts, not on every render —
  // a manual close mid-tour is left alone rather than fought.
  useEffect(() => {
    if (tourActive && window.innerWidth < 768) {
      setMobileOpen(true);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tourActive]);

  // Refetch on pathname change so leaving Discovery after reviewing
  // candidates updates the badge without a full reload.
  useEffect(() => {
    api.discovery
      .listSites("candidate")
      .then((sites) => setCandidateCount(sites.length))
      .catch(() => {});
  }, [pathname]);

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <>
      <div className="flex items-center justify-between border-b border-border bg-paper-raised px-4 py-3 md:hidden">
        <p className="truncate font-[family-name:var(--font-display)] text-sm font-semibold text-ink">
          {workspaceName}
        </p>
        <button
          type="button"
          onClick={() => setMobileOpen(true)}
          aria-label="Open menu"
          className="rounded-md p-1.5 text-slate transition-colors hover:bg-black/[0.03] hover:text-ink"
        >
          <Menu className="size-5" />
        </button>
      </div>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 md:hidden">
          <div className="absolute inset-0 bg-black/30" onClick={() => setMobileOpen(false)} />
          <aside className="absolute inset-y-0 left-0 flex w-72 max-w-[80vw] flex-col bg-paper-raised shadow-xl">
            <div className="flex items-center justify-between border-b border-border px-4 py-4">
              <p className="truncate font-[family-name:var(--font-display)] text-sm font-semibold text-ink">
                {workspaceName}
              </p>
              <button
                type="button"
                onClick={() => setMobileOpen(false)}
                aria-label="Close menu"
                className="rounded-md p-1.5 text-slate transition-colors hover:bg-black/[0.03] hover:text-ink"
              >
                <X className="size-4" />
              </button>
            </div>
            <NavLinks pathname={pathname} candidateCount={candidateCount} runningCount={runningCount} />
            <div className="flex items-center justify-between border-t border-border p-2">
              <div className="flex items-center gap-1">
                <ThemeToggle />
                <ActivityIndicator />
              </div>
              <button
                type="button"
                onClick={handleLogout}
                className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm text-slate transition-colors hover:bg-black/[0.03] hover:text-ink"
              >
                <LogOut className="size-4" />
                Log out
              </button>
            </div>
          </aside>
        </div>
      )}

      <aside className="hidden h-full w-56 shrink-0 flex-col border-r border-border bg-paper-raised md:flex">
        <div className="border-b border-border px-4 py-4">
          <p className="truncate font-[family-name:var(--font-display)] text-sm font-semibold text-ink">
            {workspaceName}
          </p>
        </div>

        <NavLinks pathname={pathname} candidateCount={candidateCount} runningCount={runningCount} />

        <div className="flex items-center justify-between border-t border-border p-2">
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <ActivityIndicator />
          </div>
          <button
            type="button"
            onClick={handleLogout}
            className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 text-sm text-slate transition-colors hover:bg-black/[0.03] hover:text-ink"
          >
            <LogOut className="size-4" />
            Log out
          </button>
        </div>
      </aside>
    </>
  );
}
