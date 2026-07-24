"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";

import { applyTheme, getStoredTheme, type Theme } from "@/lib/theme";

export function ThemeToggle({ className }: { className?: string }) {
  const [theme, setTheme] = useState<Theme | null>(null);

  useEffect(() => {
    // The inline pre-hydration script already applied a theme to <html>;
    // read it back from there rather than re-deriving it, so this stays
    // in sync with whatever it actually chose (stored pref or OS default).
    const current = (document.documentElement.getAttribute("data-theme") as Theme | null)
      ?? getStoredTheme()
      ?? "light";
    setTheme(current);
  }, []);

  function toggle() {
    const next: Theme = theme === "dark" ? "light" : "dark";
    applyTheme(next);
    setTheme(next);
  }

  if (!theme) return null;

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={theme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
      className={
        className ??
        "inline-flex size-9 items-center justify-center rounded-md text-slate transition-colors hover:bg-black/[0.04] hover:text-ink"
      }
    >
      {theme === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </button>
  );
}
