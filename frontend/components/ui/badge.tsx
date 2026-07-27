import * as React from "react";

import { cn } from "@/lib/utils";

const TONE_CLASS = {
  good: "bg-good/10 text-good",
  danger: "bg-danger/10 text-danger",
  accent: "bg-accent/10 text-accent",
  neutral: "bg-slate/10 text-slate",
} as const;

export type BadgeTone = keyof typeof TONE_CLASS;

export function Badge({
  tone = "neutral",
  className,
  ...props
}: React.ComponentProps<"span"> & { tone?: BadgeTone }) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium",
        TONE_CLASS[tone],
        className
      )}
      {...props}
    />
  );
}
