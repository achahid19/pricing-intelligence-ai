"use client";

import { EntryRow } from "@/components/ActivityIndicator";
import { Card } from "@/components/ui/card";
import { PageHeader } from "@/components/ui/page-header";
import { useActivity } from "@/lib/activity";

// The full-page counterpart to the Sidebar bell's popover (which only
// shows the 8 most recent entries in a small scrolling box) — reached via
// its "View all activity" link. Same underlying registry (see
// lib/activity.tsx), just given room to actually be read rather than
// glanced at; no separate data source, so there's nothing here that
// wasn't already tracked from wherever the action was triggered.
export default function ActivityPage() {
  const { entries, dismiss } = useActivity();
  const runningCount = entries.filter((e) => e.status === "running").length;

  return (
    <div className="mx-auto max-w-3xl px-8 py-10">
      <PageHeader
        title="Recent activity"
        description={
          runningCount > 0
            ? `${runningCount} action${runningCount === 1 ? "" : "s"} running now, plus anything recently finished.`
            : "Background actions from this session — discovery runs, matching, reports, and imports."
        }
      />

      {entries.length === 0 ? (
        <p className="mt-6 text-sm text-slate">
          Nothing yet — actions you trigger (like running discovery or generating a report) will show up here while
          they run and for a while after they finish.
        </p>
      ) : (
        <Card className="mt-6 p-2">
          <div className="space-y-0.5">
            {entries.map((entry) => (
              <EntryRow key={entry.id} entry={entry} onDismiss={dismiss} />
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}
