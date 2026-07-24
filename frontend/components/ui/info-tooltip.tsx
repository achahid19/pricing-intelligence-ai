import { Tooltip } from "@base-ui/react/tooltip";
import { Info } from "lucide-react";

export function InfoTooltip({ text }: { text: string }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger
        aria-label="More info"
        className="inline-flex size-4 items-center justify-center rounded-full text-slate-soft outline-none transition-colors hover:text-accent focus-visible:text-accent"
      >
        <Info className="size-3.5" />
      </Tooltip.Trigger>
      <Tooltip.Portal>
        <Tooltip.Positioner sideOffset={8} className="z-50">
          <Tooltip.Popup className="max-w-64 rounded-md border border-border bg-paper-raised px-3 py-2 text-xs text-ink shadow-lg">
            {text}
          </Tooltip.Popup>
        </Tooltip.Positioner>
      </Tooltip.Portal>
    </Tooltip.Root>
  );
}
