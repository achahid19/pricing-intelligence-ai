import { Check, X } from "lucide-react";

import { Card } from "@/components/ui/card";
import { TIER_BADGE_CLASS, TIER_LABEL } from "@/lib/modelTiers";
import type { AssistantToolCallStatus, ToolCallDisplay, ModelTier } from "@/lib/api";

// Human labels for the 8 curated tools — the AI never picks a name a user
// would recognize, so this is the one place tool_name gets translated into
// something that reads like a feature, not an internal identifier.
const TOOL_LABELS: Record<string, string> = {
  create_product: "Add product",
  run_competitor_discovery: "Search for competitors",
  auto_match_site: "Auto-match products",
  generate_report: "Generate report",
  update_business_context: "Update business context",
};

const STATUS_LABEL: Record<AssistantToolCallStatus, string> = {
  proposed: "Awaiting approval",
  executed: "Done",
  dismissed: "Dismissed",
  failed: "Failed",
};

export function ToolProposalCard({
  toolName,
  display,
  tier,
  status,
  updating,
  resultSummary,
  errorMessage,
  onApprove,
  onDismiss,
}: {
  toolName: string;
  display: ToolCallDisplay;
  tier: ModelTier;
  status: AssistantToolCallStatus;
  updating: boolean;
  resultSummary?: Record<string, unknown> | null;
  errorMessage?: string | null;
  onApprove: () => void;
  onDismiss: () => void;
}) {
  const pending = status === "proposed";
  return (
    <Card className="max-w-md">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-medium text-ink">{TOOL_LABELS[toolName] ?? toolName}</p>
            <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${TIER_BADGE_CLASS[tier]}`}>
              {TIER_LABEL[tier]}
            </span>
          </div>
          <dl className="mt-2 space-y-1 text-sm">
            {Object.entries(display).map(([key, value]) => (
              <div key={key} className="flex gap-1.5">
                <dt className="text-slate-soft">{key}:</dt>
                <dd className="min-w-0 truncate text-ink">{String(value)}</dd>
              </div>
            ))}
          </dl>
          {!pending && (
            <p
              className={`mt-2 text-xs font-medium ${
                status === "executed" ? "text-good" : status === "failed" ? "text-danger" : "text-slate-soft"
              }`}
            >
              {updating ? "Working…" : STATUS_LABEL[status]}
              {status === "failed" && errorMessage ? `: ${errorMessage}` : ""}
              {status === "executed" && resultSummary && "note" in resultSummary
                ? `: ${String(resultSummary.note)}`
                : ""}
            </p>
          )}
        </div>
        {pending && !updating && (
          <div className="flex shrink-0 gap-1.5">
            <button
              onClick={onApprove}
              aria-label="Approve"
              className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-good/10 hover:text-good"
            >
              <Check className="size-4" />
            </button>
            <button
              onClick={onDismiss}
              aria-label="Dismiss"
              className="rounded-md p-1.5 text-slate-soft transition-colors hover:bg-danger/10 hover:text-danger"
            >
              <X className="size-4" />
            </button>
          </div>
        )}
        {pending && updating && <p className="shrink-0 text-xs text-slate-soft">Working…</p>}
      </div>
    </Card>
  );
}
