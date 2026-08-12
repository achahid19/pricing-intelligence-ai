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

export type ActivityStatus = "running" | "done" | "error" | "cancelled";

export interface ActivityChild {
  id: string;
  label: string;
  status: "pending" | "done" | "error" | "cancelled";
}

export interface ActivityEntry {
  // A unique key PER RUN, not per action-type — two separate report
  // generations, or two separate "discover products for site 5" calls,
  // each get their own ActivityEntry rather than the second silently
  // overwriting the first. See track()/syncEntry() below for how this is
  // derived from the caller's (stable, per-type) id.
  id: string;
  label: string;
  href?: string;
  status: ActivityStatus;
  startedAt: number;
  finishedAt?: number;
  errorMessage?: string;
  // Whether the user has opened the popover since this entry last settled
  // to "done"/"error"/"cancelled" — the basis for the Sidebar bell's
  // passive dot (see ActivityIndicator.tsx). Irrelevant while "running":
  // the spinner+count is already a visible signal for that state, so this
  // only tracks "finished and not yet looked at."
  seen: boolean;
  // Sub-steps of a server-tracked pipeline run (see lib/pipelineStatus.tsx)
  // rendered nested under this one entry — e.g. "Discovering products —
  // Cap Connect" under a parent "Report generation." Only ever set via
  // syncEntry(); track()-driven entries (a single frontend promise) never
  // have a meaningful sub-step breakdown, so this stays undefined for them.
  children?: ActivityChild[];
  // Present only for entries backed by real server-side cancellation
  // support (currently just the automated pipeline, wired in
  // lib/pipelineStatus.tsx) — track()-driven entries never set this,
  // since there's no way to interrupt an already-in-flight single HTTP
  // request short of AbortController + backend disconnect-handling that
  // doesn't exist here yet. ActivityIndicator.tsx only renders a Stop
  // button when this is present AND status is "running".
  onCancel?: () => void;
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
  onCancel?: () => void;
}

interface ActivityContextValue {
  entries: ActivityEntry[];
  // `id` here is a stable per ACTION-TYPE key (e.g. "ai-describe",
  // `discover-products-${siteId}`) — every existing call site keeps
  // passing exactly that, unchanged. track() itself turns it into a
  // unique per-run storage key internally, so calling the same action
  // twice produces two separate history entries instead of the second
  // silently overwriting the first.
  track<T>(id: string, label: string, promise: Promise<T>, opts?: { href?: string }): Promise<T>;
  // For state that isn't a promise this app made — a server-side process
  // (the automated pipeline, see lib/pipelineStatus.tsx) polled rather than
  // awaited directly. `entry.id` is likewise the stable per-type key
  // ("automated-pipeline"); combined with `entry.startedAt` (unique per
  // real run) to derive that run's own storage key, so repeat polls of
  // the SAME run update one entry in place while a genuinely new run
  // (different startedAt) gets its own history row. Idempotent: calling
  // it repeatedly with the same snapshot (e.g. every poll while nothing's
  // changed) is a no-op, and won't resurrect a run the user already
  // dismissed.
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
  // Monotonic counter used to turn track()'s caller-supplied (stable,
  // per-action-TYPE) id into a unique-per-invocation storage key — two
  // calls with the same type id, even back to back, get distinct keys
  // and therefore distinct history entries. This also makes the old
  // per-id "token" staleness guard unnecessary: since each call now owns
  // its own key, a resolving promise can never clobber a different
  // call's entry the way two same-typed calls sharing one key used to.
  const runSeq = useRef(0);
  // Storage keys that have been explicitly dismissed. A run's key already
  // encodes its own identity (see track()/syncEntry()), so remembering
  // "this exact key was dismissed" is enough to stop a poller from
  // resurrecting it the next time it re-observes the same server-side
  // finished state — no per-run bookkeeping needed beyond the key itself.
  const dismissedKeys = useRef<Set<string>>(new Set());

  const clearTimer = useCallback((key: string) => {
    if (timers.current[key]) {
      clearTimeout(timers.current[key]);
      delete timers.current[key];
    }
  }, []);

  const dismiss = useCallback(
    (key: string) => {
      clearTimer(key);
      dismissedKeys.current.add(key);
      setEntries((prev) => {
        if (!(key in prev)) return prev;
        const next = { ...prev };
        delete next[key];
        return next;
      });
    },
    [clearTimer]
  );

  const track = useCallback(
    <T,>(id: string, label: string, promise: Promise<T>, opts?: { href?: string }): Promise<T> => {
      const key = `${id}-${++runSeq.current}`;
      setEntries((prev) => ({
        ...prev,
        [key]: { id: key, label, href: opts?.href, status: "running", startedAt: Date.now(), seen: true },
      }));

      const scheduleAutoClear = () => {
        timers.current[key] = setTimeout(() => dismiss(key), FINISHED_TTL_MS);
      };

      return promise.then(
        (result) => {
          setEntries((prev) => ({
            ...prev,
            [key]: { ...prev[key], status: "done", finishedAt: Date.now(), seen: false },
          }));
          scheduleAutoClear();
          return result;
        },
        (err) => {
          setEntries((prev) => ({
            ...prev,
            [key]: {
              ...prev[key],
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
    [dismiss]
  );

  const syncEntry = useCallback(
    (entry: SyncedActivityEntry) => {
      // entry.startedAt is set once, server-side, when a real run starts
      // (Workspace.pipeline_started_at) and never changes for that run —
      // combined with the caller's stable type id, this is already a
      // unique, stable-for-the-run key: repeat polls of the SAME run
      // land on the same key, a genuinely new run gets a new one.
      const key = `${entry.id}-${entry.startedAt}`;
      // A dismissed run shouldn't reappear just because the poller
      // observes the exact same server-side state again.
      if (entry.status !== "running" && dismissedKeys.current.has(key)) {
        return;
      }
      setEntries((prev) => {
        const existing = prev[key];
        const isNewFinish = entry.status !== "running" && (!existing || existing.status === "running");
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
          clearTimer(key);
          timers.current[key] = setTimeout(() => dismiss(key), FINISHED_TTL_MS);
        }
        return { ...prev, [key]: { ...entry, id: key, seen } };
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
