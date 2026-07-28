import { Badge, type BadgeTone } from "@/components/ui/badge";
import { InfoTooltip } from "@/components/ui/info-tooltip";

export function ConfidenceBadge({
  score,
  manualLabel = "Added manually",
  tooltip,
}: {
  score: number | null;
  manualLabel?: string;
  tooltip: string;
}) {
  if (score == null) {
    return <Badge tone="neutral">{manualLabel}</Badge>;
  }
  // A qualitative label, not the raw percentage, is the primary signal —
  // this is the AI's own self-reported confidence, not a verified or
  // calibrated metric, so presenting it as a precise number overstates its
  // authority. The percentage is still available, just de-emphasized.
  const label = score >= 75 ? "Strong match" : score >= 50 ? "Possible match" : "Weak match";
  const tone: BadgeTone = score >= 75 ? "good" : score >= 50 ? "neutral" : "accent";
  return (
    <Badge tone={tone}>
      {label}
      <span className="tabular-nums opacity-60">· {score}%</span>
      <InfoTooltip text={tooltip} />
    </Badge>
  );
}
