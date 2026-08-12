"use client";

import Link from "next/link";
import { Popover } from "@base-ui/react/popover";
import { AlertCircle, Ban, Bell, CheckCircle2, Circle, Loader2, Square, X } from "lucide-react";

import { useActivity, type ActivityEntry } from "@/lib/activity";
import { cn } from "@/lib/utils";

// Exported for the full /activity page (app/(app)/activity/page.tsx) so
// the two surfaces render entries identically rather than drifting apart.
export function timeAgo(ms: number): string {
  const seconds = Math.max(0, Math.round((Date.now() - ms) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  return `${Math.round(minutes / 60)}h ago`;
}

function childIcon(status: "pending" | "done" | "error" | "cancelled") {
  if (status === "done") return <CheckCircle2 className="size-3 shrink-0 text-good" />;
  if (status === "error") return <AlertCircle className="size-3 shrink-0 text-danger" />;
  if (status === "cancelled") return <Ban className="size-3 shrink-0 text-slate-soft" />;
  return <Circle className="size-3 shrink-0 text-slate-soft" />;
}

export function EntryRow({ entry, onDismiss }: { entry: ActivityEntry; onDismiss: (id: string) => void }) {
  const icon =
    entry.status === "running" ? (
      <Loader2 className="size-4 shrink-0 animate-spin text-accent" />
    ) : entry.status === "error" ? (
      <AlertCircle className="size-4 shrink-0 text-danger" />
    ) : entry.status === "cancelled" ? (
      <Ban className="size-4 shrink-0 text-slate-soft" />
    ) : (
      <CheckCircle2 className="size-4 shrink-0 text-good" />
    );

  const children = entry.children;
  const doneCount = children?.filter((c) => c.status === "done").length ?? 0;

  const body = (
    <div className="flex min-w-0 flex-1 items-start gap-2">
      {icon}
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-ink">{entry.label}</p>
        <p className="text-xs text-slate-soft">
          {children && children.length > 0
            ? `${doneCount}/${children.length} steps`
            : entry.status === "running"
              ? "Running…"
              : entry.status === "error"
                ? (entry.errorMessage ?? "Failed")
                : entry.status === "cancelled"
                  ? "Stopped"
                  : "Done"}
          {entry.finishedAt && ` · ${timeAgo(entry.finishedAt)}`}
        </p>
      </div>
    </div>
  );

  return (
    <div className="rounded-md px-2 py-1.5 hover:bg-black/[0.03]">
      <div className="flex items-start gap-2">
        {entry.href && entry.status !== "running" ? (
          <Link href={entry.href} className="flex min-w-0 flex-1 items-start gap-2">
            {body}
          </Link>
        ) : (
          body
        )}
        {entry.status === "running" && entry.onCancel && (
          <button
            type="button"
            onClick={entry.onCancel}
            aria-label="Stop"
            title="Stop this run"
            className="shrink-0 rounded p-0.5 text-slate-soft transition-colors hover:text-danger"
          >
            <Square className="size-3.5" />
          </button>
        )}
        {entry.status !== "running" && (
          <button
            type="button"
            onClick={() => onDismiss(entry.id)}
            aria-label="Dismiss"
            className="shrink-0 rounded p-0.5 text-slate-soft transition-colors hover:text-ink"
          >
            <X className="size-3.5" />
          </button>
        )}
      </div>
      {children && children.length > 0 && (
        <div className="mt-1.5 ml-6 max-h-32 space-y-1 overflow-y-auto border-l border-border pl-2">
          {children.map((child) => (
            <div key={child.id} className="flex items-center gap-1.5">
              {childIcon(child.status)}
              <span
                className={cn(
                  "truncate text-xs",
                  child.status === "error"
                    ? "text-danger"
                    : child.status === "pending" || child.status === "cancelled"
                      ? "text-slate-soft"
                      : "text-slate"
                )}
              >
                {child.label}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// Rendered in the Sidebar's bottom row — renders nothing when there's no
// activity, so it never takes up space unless there's actually something
// to show. This is the direct fix for background work losing all
// visibility on navigation: entries live in ActivityProvider (mounted once
// in app/(app)/layout.tsx, not per-page), so they survive route changes.
export function ActivityIndicator() {
  const { entries, dismiss, markAllSeen } = useActivity();
  if (entries.length === 0) return null;

  const runningCount = entries.filter((e) => e.status === "running").length;
  const hasUnseen = entries.some((e) => e.status !== "running" && !e.seen);

  return (
    <Popover.Root onOpenChange={(open) => open && markAllSeen()}>
      <Popover.Trigger
        className={cn(
          "relative inline-flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium transition-colors",
          runningCount > 0 ? "text-accent" : "text-slate hover:bg-black/[0.03] hover:text-ink"
        )}
        aria-label="Background activity"
      >
        {runningCount > 0 ? <Loader2 className="size-4 animate-spin" /> : <Bell className="size-4" />}
        {runningCount > 0 && <span className="tabular-nums">{runningCount}</span>}
        {hasUnseen && (
          <span
            aria-hidden
            className="absolute top-1 right-1 size-1.5 rounded-full bg-danger ring-2 ring-paper-raised"
          />
        )}
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Positioner sideOffset={8} align="start" className="z-50">
          <Popover.Popup className="w-80 max-w-[90vw] rounded-lg border border-border bg-paper-raised p-2 shadow-xl">
            <p className="px-2 pb-1.5 pt-1 text-xs font-medium uppercase tracking-wide text-slate-soft">Activity</p>
            <div className="max-h-80 space-y-0.5 overflow-y-auto">
              {entries.slice(0, 8).map((entry) => (
                <EntryRow key={entry.id} entry={entry} onDismiss={dismiss} />
              ))}
            </div>
            <Link
              href="/activity"
              className="mt-1 block rounded-md px-2 py-1.5 text-center text-xs font-medium text-accent hover:bg-black/[0.03]"
            >
              View all activity →
            </Link>
          </Popover.Popup>
        </Popover.Positioner>
      </Popover.Portal>
    </Popover.Root>
  );
}
