"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { FileText, LayoutGrid, LogOut, Menu, Package, Search, Settings, TrendingUp, X } from "lucide-react";

import { ThemeToggle } from "@/components/ThemeToggle";
import { clearToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Home", icon: LayoutGrid },
  { href: "/catalog", label: "Catalog", icon: Package },
  { href: "/discovery", label: "Discovery", icon: Search },
  { href: "/tracked", label: "Tracked", icon: TrendingUp },
  { href: "/reports", label: "Reports", icon: FileText },
  { href: "/settings", label: "Settings", icon: Settings },
];

function NavLinks({ pathname, onNavigate }: { pathname: string; onNavigate?: () => void }) {
  return (
    <nav className="flex-1 space-y-0.5 p-2">
      {NAV.map((item) => {
        const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
        const Icon = item.icon;
        return (
          <Link
            key={item.href}
            href={item.href}
            onClick={onNavigate}
            className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium transition-colors ${
              active ? "bg-accent/10 text-accent" : "text-slate hover:bg-black/[0.03] hover:text-ink"
            }`}
          >
            <Icon className="size-4" />
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}

export function Sidebar({ workspaceName }: { workspaceName: string }) {
  const pathname = usePathname();
  const router = useRouter();
  const [mobileOpen, setMobileOpen] = useState(false);

  // Closing on every route change covers both nav-link clicks and any other
  // way the path changes (back/forward) — simpler than wiring onNavigate
  // through every possible exit.
  useEffect(() => {
    setMobileOpen(false);
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
            <NavLinks pathname={pathname} />
            <div className="flex items-center justify-between border-t border-border p-2">
              <ThemeToggle />
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

        <NavLinks pathname={pathname} />

        <div className="flex items-center justify-between border-t border-border p-2">
          <ThemeToggle />
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
