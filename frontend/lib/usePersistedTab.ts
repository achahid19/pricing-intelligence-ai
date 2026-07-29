"use client";

import { useEffect, useState } from "react";

// Keeps a page's active tab/view in sync with both the URL (so browser
// back/forward lands on the same tab) and sessionStorage (so navigating
// away via a plain link — not back/forward — and returning still restores
// it, since a fresh navigation to the same path carries no query string).
// history.replaceState, not pushState/router.push: switching tabs is not a
// new navigable page, it shouldn't grow the back-button stack.
export function usePersistedTab<T extends string>(
  queryParam: string,
  storageKey: string,
  options: readonly T[],
  fallback: T
): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(() => {
    if (typeof window === "undefined") return fallback;
    const fromUrl = new URLSearchParams(window.location.search).get(queryParam);
    if (fromUrl && (options as readonly string[]).includes(fromUrl)) return fromUrl as T;
    const fromStorage = window.sessionStorage.getItem(storageKey);
    if (fromStorage && (options as readonly string[]).includes(fromStorage)) return fromStorage as T;
    return fallback;
  });

  useEffect(() => {
    const url = new URL(window.location.href);
    url.searchParams.set(queryParam, value);
    window.history.replaceState({}, "", url);
    window.sessionStorage.setItem(storageKey, value);
  }, [queryParam, storageKey, value]);

  return [value, setValue];
}
