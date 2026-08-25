import { Sparkles, X } from "lucide-react";

// Shown when POST /workspace/review-context flags the workspace's own
// free-text fields (objectives_note, the industry "Other" override) as not
// plausibly related to competitor/pricing intelligence — see settings/
// page.tsx's two trigger points (first AI key saved, business context
// edited). Deliberately NOT the same component as AiProviderRequiredNotice
// (that one is a persistent boolean-gated block, never dismissible) —
// dismissal here is local/session-only, not persisted, since the whole
// point is it re-checks on every future edit rather than going silent
// forever after one dismissal.
export function ContextReviewNotice({ note, onDismiss }: { note: string; onDismiss: () => void }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-accent/30 bg-accent/5 px-4 py-3 text-sm text-ink">
      <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" />
      <p className="flex-1">{note}</p>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss"
        className="shrink-0 rounded p-0.5 text-slate-soft transition-colors hover:text-ink"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}
