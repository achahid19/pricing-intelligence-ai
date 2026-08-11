import Link from "next/link";
import { Sparkles } from "lucide-react";

// Shown wherever an AI feature (discovery, matching, reports, ai-describe,
// website-import discover) is otherwise unreachable because the workspace
// has no active AI provider configured yet — see lib/aiProvider.tsx. The
// action itself should also be disabled alongside this, not just
// accompanied by it, so there's nothing to click through to a 400.
export function AiProviderRequiredNotice({ action }: { action: string }) {
  return (
    <div className="flex items-start gap-2.5 rounded-lg border border-accent/30 bg-accent/5 px-4 py-3 text-sm text-ink">
      <Sparkles className="mt-0.5 size-4 shrink-0 text-accent" />
      <p>
        {action} needs an AI provider configured first —{" "}
        <Link href="/settings" className="font-medium text-accent hover:underline">
          set one up in Settings
        </Link>
        .
      </p>
    </div>
  );
}
