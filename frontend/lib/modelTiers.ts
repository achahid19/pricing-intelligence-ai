import type { ModelTier } from "@/lib/api";

export const TIER_ORDER: ModelTier[] = ["low", "medium", "high"];

export const TIER_LABEL: Record<ModelTier, string> = {
  low: "Low cost",
  medium: "Medium cost",
  high: "High cost",
};

export const TIER_BADGE_CLASS: Record<ModelTier, string> = {
  low: "bg-good/10 text-good",
  medium: "bg-slate/10 text-slate",
  high: "bg-accent/10 text-accent",
};
