"use client";

// Bridges the automated discover→match→report pipeline (reporting/
// service.py's run_full_pipeline, triggered server-side by a first-ever
// product import or the scheduler — see catalog/router.py and reporting/
// scheduler.py) into the same activity registry every other action uses.
// That pipeline runs entirely server-side with no frontend promise to
// wrap in track() — without this, there is genuinely no way for a user to
// know it started, is still running, or how it ended; confirmed as a real,
// silent gap live on 2026-08-10. Polling GET /workspace/me (already the
// cheapest, most-fetched endpoint in this app) is the pragmatic fit here:
// this app has no websocket/SSE infrastructure, and the scheduler itself
// already leans on a similar polling cadence for the same reason.
import { useEffect, useRef } from "react";

import { api } from "@/lib/api";
import { useActivity } from "@/lib/activity";

const POLL_INTERVAL_MS = 15 * 1000;
const ENTRY_ID = "automated-pipeline";

const LABEL_BY_TRIGGER: Record<string, string> = {
  onboarding: "Automated setup — competitors, matching & first report",
  scheduled: "Automated pipeline refresh",
  manual: "Report generation",
};

export function PipelineStatusPoller() {
  const { syncEntry } = useActivity();
  // Avoids piling up overlapping requests if one poll is ever slower than
  // the interval (e.g. a slow model mid-pipeline) — skip a tick rather
  // than queue another.
  const inFlight = useRef(false);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      if (inFlight.current) return;
      inFlight.current = true;
      try {
        const ws = await api.workspace.me();
        if (cancelled || !ws.pipeline_status || !ws.pipeline_started_at) return;
        const status = ws.pipeline_status === "running" ? "running" : ws.pipeline_status === "completed" ? "done" : "error";
        syncEntry({
          id: ENTRY_ID,
          label: LABEL_BY_TRIGGER[ws.pipeline_trigger_source ?? ""] ?? "Automated pipeline",
          href: ws.pipeline_status === "completed" && ws.pipeline_report_id ? `/reports/${ws.pipeline_report_id}` : undefined,
          status,
          startedAt: new Date(ws.pipeline_started_at).getTime(),
          finishedAt: ws.pipeline_finished_at ? new Date(ws.pipeline_finished_at).getTime() : undefined,
          errorMessage: ws.pipeline_error_message ?? undefined,
          children: ws.pipeline_substeps ?? undefined,
        });
      } catch {
        // A failed status check isn't itself pipeline news — just skip
        // this tick and try again next interval.
      } finally {
        inFlight.current = false;
      }
    }

    poll();
    const interval = setInterval(poll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [syncEntry]);

  return null;
}
