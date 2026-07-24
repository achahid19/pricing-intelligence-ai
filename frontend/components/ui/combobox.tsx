import { Combobox as ComboboxPrimitive } from "@base-ui/react/combobox";
import { Check, ChevronDown } from "lucide-react";

import { cn } from "@/lib/utils";

interface ComboboxProps {
  options: readonly string[];
  value: string | null;
  onValueChange: (value: string | null) => void;
  placeholder?: string;
  id?: string;
}

export function Combobox({ options, value, onValueChange, placeholder, id }: ComboboxProps) {
  return (
    <ComboboxPrimitive.Root items={options} value={value} onValueChange={onValueChange}>
      <ComboboxPrimitive.InputGroup className="relative">
        <ComboboxPrimitive.Input
          id={id}
          placeholder={placeholder}
          className={cn(
            "h-10 w-full rounded-md border border-border bg-paper-raised px-3 pr-9 text-sm text-ink placeholder:text-slate-soft outline-none transition-colors focus-visible:border-accent focus-visible:ring-2 focus-visible:ring-accent/20"
          )}
        />
        <ChevronDown className="pointer-events-none absolute top-1/2 right-3 size-4 -translate-y-1/2 text-slate-soft" />
      </ComboboxPrimitive.InputGroup>

      <ComboboxPrimitive.Portal>
        <ComboboxPrimitive.Positioner sideOffset={4} className="z-50">
          <ComboboxPrimitive.Popup className="max-h-64 min-w-60 overflow-auto rounded-md border border-border bg-paper-raised py-1 shadow-lg">
            <ComboboxPrimitive.Empty className="px-3 py-2 text-sm text-slate">
              No matches
            </ComboboxPrimitive.Empty>
            <ComboboxPrimitive.List>
              {(item: string) => (
                <ComboboxPrimitive.Item
                  key={item}
                  value={item}
                  className="flex cursor-pointer items-center justify-between px-3 py-2 text-sm text-ink data-[highlighted]:bg-accent/10"
                >
                  {item}
                  <ComboboxPrimitive.ItemIndicator>
                    <Check className="size-4 text-accent" />
                  </ComboboxPrimitive.ItemIndicator>
                </ComboboxPrimitive.Item>
              )}
            </ComboboxPrimitive.List>
          </ComboboxPrimitive.Popup>
        </ComboboxPrimitive.Positioner>
      </ComboboxPrimitive.Portal>
    </ComboboxPrimitive.Root>
  );
}
