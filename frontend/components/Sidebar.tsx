"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LayoutGrid, LogOut, Package, Settings } from "lucide-react";

import { ThemeToggle } from "@/components/ThemeToggle";
import { clearToken } from "@/lib/api";

const NAV = [
  { href: "/", label: "Home", icon: LayoutGrid },
  { href: "/catalog", label: "Catalog", icon: Package },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar({ workspaceName }: { workspaceName: string }) {
  const pathname = usePathname();
  const router = useRouter();

  function handleLogout() {
    clearToken();
    router.replace("/login");
  }

  return (
    <aside className="flex h-full w-56 shrink-0 flex-col border-r border-border bg-paper-raised">
      <div className="border-b border-border px-4 py-4">
        <p className="truncate font-[family-name:var(--font-display)] text-sm font-semibold text-ink">
          {workspaceName}
        </p>
      </div>

      <nav className="flex-1 space-y-0.5 p-2">
        {NAV.map((item) => {
          const active = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
          const Icon = item.icon;
          return (
            <Link
              key={item.href}
              href={item.href}
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
  );
}
