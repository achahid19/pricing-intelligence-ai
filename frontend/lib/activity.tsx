"use client";

// Global, cross-page activity registry — fixes a real bug: every
// long-running AI action (discovery run, per-site product discovery,
// auto-match, website-import, report generation, ai-describe, CSV import)
// used to track its "in progress" state in a plain page/dialog-local
// useState. Navigating away unmounts that component; the in-flight fetch
// isn't cancelled (no AbortController anywhere in this app) and completes
// server-side regardless, but the setState calls in its finally/.then
// continuation now target an unmounted component and silently no-op — the
// work finishes for real, the user just has no way to know. Polling the
// backend isn't a fix either: e.g. DiscoveryRun's "running" status is
// never committed (only flushed within its own transaction, committed
// only once terminal), so no concurrent request could ever observe it.
//
// The fix has to be a registry whose own state setters live above the
// page — provided once in app/(app)/layout.tsx, which is the one thing
// that genuinely persists across every route change in this route group.
// track() wraps an already-in-flight promise; it doesn't create the
// request or change any page's own try/catch/finally, so every existing
// call site keeps its own error handling exactly as before.
import { createContext, useCallback, useContext, useMemo, useRef, useState } from "react";

export type ActivityStatus = "running" | "done" | "error";

export interface ActivityChild {
  id: string;
  label: string;
  status: "pending" | "done" | "error";
}

export interface ActivityEntry {
  id: string;
  label: string;
  href?: string;
  status: ActivityStatus;
  startedAt: number;
  finishedAt?: number;
  errorMessage?: string;
  // Whether the user has opened the popover since this entry last settled
  // to "done"/"error" — the basis for the Sidebar bell's passive dot (see
  // ActivityIndicator.tsx). Irrelevant while "running": the spinner+count
  // is already a visible signal for that state, so this only tracks
  // "finished and not yet looked at."
  seen: boolean;
  // Sub-steps of a server-tracked pipeline run (see lib/pipelineStatus.tsx)
  // rendered nested under this one entry — e.g. "Discovering products —
  // Cap Connect" under a parent "Report generation." Only ever set via
  // syncEntry(); track()-driven entries (a single frontend promise) never
  // have a meaningful sub-step breakdown, so this stays undefined for them.
  children?: ActivityChild[];
}

export interface SyncedActivityEntry {
  id: string;
  label: string;
  href?: string;
  status: ActivityStatus;
  startedAt: number;
  finishedAt?: number;
  errorMessage?: string;
  children?: ActivityChild[];
}

interface ActivityContextValue {
  entries: ActivityEntry[];
  track<T>(id: string, label: string, promise: Promise<T>, opts?: { href?: string }): Promise<T>;
  // For state that isn't a promise this app made — a server-side process
  // (the automated pipeline, see lib/pipelineStatus.tsx) polled rather than
  // awaited directly. Idempotent: calling it repeatedly with the same
  // snapshot (e.g. every poll while nothing's changed) is a no-op, and
  // won't resurrect an entry the user already dismissed for that same
  // finish — only a genuinely new run (a different finishedAt) does.
  syncEntry(entry: SyncedActivityEntry): void;
  dismiss(id: string): void;
  markAllSeen(): void;
}

const ActivityContext = createContext<ActivityContextValue | null>(null);

// How long a finished entry stays visible before auto-clearing. Long
// enough that the new /activity page (a real "recent activity" view, not
// just a glance-and-forget popover) has something worth showing hours
// later — this registry is still purely in-memory/session-scoped (a page
// refresh or new tab loses it entirely, see the module docstring above),
// so there's no real cost to keeping entries around for a full session;
// the cap is about not accumulating forever, not about hiding history fast.
const FINISHED_TTL_MS = 24 * 60 * 60 * 1000;

export function ActivityProvider({ children }: { children: React.ReactNode }) {
  const [entries, setEntries] = useState<Record<string, ActivityEntry>>({});
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  // One token per id, bumped on every track() call for that id — a
  // promise's resolution only applies if it's still the most recent call
  // for that id, so a stale/superseded run can't clobber a newer one's
  // state (e.g. a rejected double-click retry resolving after the real run).
  const tokens = useRef<Record<string, symbol>>({});
  // id -> the finishedAt of the last dismissal for that id — lets syncEntry
  // (unlike track(), which only ever fires once per real action) tell "the
  // user already dismissed this exact finish" apart from "a new run
  // finished since," since a poller will otherwise keep re-observing the
  // same server-side finished state on every poll.
  const dismissedFinishes = useRef<Record<string, number | undefined>>({});

  const clearTimer = useCallback((id: string) => {
    if (timers.current[id]) {
      clearTimeout(timers.current[id]);
      delete timers.current[id];
    }
  }, []);

  const dismiss = useCallback(
    (id: string) => {
      clearTimer(id);
      setEntries((prev) => {
        if (!(id in prev)) return prev;
        dismissedFinishes.current[id] = prev[id].finishedAt;
        const next = { ...prev };
        delete next[id];
        return next;
      });
    },
    [clearTimer]
  );

  const track = useCallback(
    <T,>(id: string, label: string, promise: Promise<T>, opts?: { href?: string }): Promise<T> => {
      const token = Symbol(id);
      tokens.current[id] = token;
      clearTimer(id);
      setEntries((prev) => ({
        ...prev,
        [id]: { id, label, href: opts?.href, status: "running", startedAt: Date.now(), seen: true },
      }));

      const scheduleAutoClear = () => {
        timers.current[id] = setTimeout(() => dismiss(id), FINISHED_TTL_MS);
      };

      return promise.then(
        (result) => {
          if (tokens.current[id] !== token) return result;
          setEntries((prev) => ({
            ...prev,
            [id]: { ...prev[id], status: "done", finishedAt: Date.now(), seen: false },
          }));
          scheduleAutoClear();
          return result;
        },
        (err) => {
          if (tokens.current[id] !== token) throw err;
          setEntries((prev) => ({
            ...prev,
            [id]: {
              ...prev[id],
              status: "error",
              finishedAt: Date.now(),
              errorMessage: err instanceof Error ? err.message : "Failed",
              seen: false,
            },
          }));
          scheduleAutoClear();
          throw err;
        }
      );
    },
    [clearTimer, dismiss]
  );

  const syncEntry = useCallback(
    (entry: SyncedActivityEntry) => {
      // A dismissed finish shouldn't reappear just because the poller
      // observes the exact same server-side state again — but a genuinely
      // new run (different finishedAt, or still running) always shows.
      if (
        entry.status !== "running" &&
        dismissedFinishes.current[entry.id] !== undefined &&
        dismissedFinishes.current[entry.id] === entry.finishedAt
      ) {
        return;
      }
      setEntries((prev) => {
        const existing = prev[entry.id];
        const isNewFinish = entry.status !== "running" && (!existing || existing.finishedAt !== entry.finishedAt);
        const seen = entry.status === "running" ? true : isNewFinish ? false : (existing?.seen ?? false);
        // JSON comparison, not reference equality — pipelineStatus.tsx
        // builds a fresh array on every poll even when nothing in it
        // actually changed. The list is tiny (at most a couple dozen
        // sub-steps), so this is cheap.
        const childrenChanged = JSON.stringify(existing?.children) !== JSON.stringify(entry.children);
        if (
          existing &&
          existing.status === entry.status &&
          existing.finishedAt === entry.finishedAt &&
          existing.errorMessage === entry.errorMessage &&
          existing.seen === seen &&
          !childrenChanged
        ) {
          return prev; // nothing actually changed — skip the re-render
        }
        if (isNewFinish) {
          clearTimer(entry.id);
          timers.current[entry.id] = setTimeout(() => dismiss(entry.id), FINISHED_TTL_MS);
        }
        return { ...prev, [entry.id]: { ...entry, seen } };
      });
    },
    [clearTimer, dismiss]
  );

  const markAllSeen = useCallback(() => {
    setEntries((prev) => {
      let changed = false;
      const next: Record<string, ActivityEntry> = {};
      for (const [key, entry] of Object.entries(prev)) {
        if (!entry.seen) changed = true;
        next[key] = entry.seen ? entry : { ...entry, seen: true };
      }
      return changed ? next : prev;
    });
  }, []);

  const value = useMemo<ActivityContextValue>(
    () => ({
      entries: Object.values(entries).sort((a, b) => b.startedAt - a.startedAt),
      track,
      syncEntry,
      dismiss,
      markAllSeen,
    }),
    [entries, track, syncEntry, dismiss, markAllSeen]
  );

  return <ActivityContext.Provider value={value}>{children}</ActivityContext.Provider>;
}

export function useActivity(): ActivityContextValue {
  const ctx = useContext(ActivityContext);
  if (!ctx) throw new Error("useActivity must be used within an ActivityProvider");
  return ctx;
}
