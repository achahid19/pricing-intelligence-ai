import { Info, Wand2 } from "lucide-react";

// Shared between AssistantWidget (floating popup) and the full-page
// /assistant view — both read from the same AssistantChatProvider
// conversation, so the suggestion pools stay in one place too rather than
// risking the two surfaces drifting apart.

// Read-only questions the 3 read tools can answer directly — safe to
// suggest with no risk of surprising the user with a write proposal.
export const INFO_SUGGESTIONS = [
  "How many saved competitors do I have?",
  "What's in my product catalog?",
  "Which competitors haven't been auto-matched yet?",
  "When was my last report generated?",
  "What's my current business context?",
];

// Each of these routes to one of the 5 write tools — always surfaces as a
// proposal card the user still has to approve, never runs on click alone.
export const ACTION_SUGGESTIONS = [
  "Search the web for new competitors",
  "Generate a new report now",
  "Auto-match my top competitor's products",
  "Update my business context",
];

// Shown only in the empty state, before the first message — a small,
// deliberately mixed starter set rather than the full pools above, so a
// first-time visitor sees the two kinds of thing it can do side by side.
export const STARTER_SUGGESTIONS: { type: "info" | "action"; text: string }[] = [
  { type: "info", text: INFO_SUGGESTIONS[0] },
  { type: "action", text: ACTION_SUGGESTIONS[0] },
  { type: "info", text: INFO_SUGGESTIONS[1] },
  { type: "action", text: ACTION_SUGGESTIONS[1] },
];

export function SuggestionChip({ type, text, onClick }: { type: "info" | "action"; text: string; onClick: () => void }) {
  const Icon = type === "info" ? Info : Wand2;
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1.5 rounded-full border border-border bg-paper-raised px-3 py-1.5 text-left text-xs font-medium text-ink transition-colors hover:border-accent/40 hover:bg-accent/5 hover:text-accent"
    >
      <Icon className="size-3.5 shrink-0 text-slate-soft" />
      {text}
    </button>
  );
}
