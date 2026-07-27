import * as React from "react";

import { cn } from "@/lib/utils";

// Exported so non-div elements that need the same look (e.g. a Next.js
// Link acting as a clickable card) can share one source of truth instead
// of re-typing this string.
export const cardClassName = "rounded-lg border border-border bg-paper-raised p-4";

export function Card({
  className,
  interactive,
  ...props
}: React.ComponentProps<"div"> & { interactive?: boolean }) {
  return (
    <div
      className={cn(cardClassName, interactive && "transition-colors hover:bg-black/[0.02]", className)}
      {...props}
    />
  );
}
