"use client";

import { Autocomplete as AutocompletePrimitive } from "@base-ui/react/autocomplete";
import { ChevronDownIcon } from "lucide-react";

import { cn } from "@/lib/utils";

type AutocompleteProps = {
  value: string;
  onValueChange: (value: string) => void;
  options: string[];
  placeholder?: string;
  disabled?: boolean;
  emptyMessage?: string;
  className?: string;
};

/** A text input with a styled suggestion popup — pick an option or type freely. */
export function Autocomplete({
  value,
  onValueChange,
  options,
  placeholder,
  disabled,
  emptyMessage = "Sin coincidencias",
  className,
}: AutocompleteProps) {
  return (
    <AutocompletePrimitive.Root
      items={options}
      value={value}
      onValueChange={(next) => onValueChange(next)}
      openOnInputClick
    >
      <div className="relative">
        <AutocompletePrimitive.Input
          placeholder={placeholder}
          disabled={disabled}
          className={cn(
            "h-8 w-full rounded-md border border-input bg-transparent pr-7 pl-2.5 text-xs outline-none",
            "focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50",
            "disabled:cursor-not-allowed disabled:opacity-50",
            className,
          )}
        />
        <ChevronDownIcon className="pointer-events-none absolute top-1/2 right-2 size-3.5 -translate-y-1/2 text-muted-foreground" />
      </div>
      <AutocompletePrimitive.Portal>
        <AutocompletePrimitive.Positioner sideOffset={4} className="z-50">
          <AutocompletePrimitive.Popup
            className={cn(
              "max-h-60 w-(--anchor-width) overflow-y-auto rounded-lg bg-popover p-1",
              "text-popover-foreground shadow-md ring-1 ring-foreground/10",
            )}
          >
            <AutocompletePrimitive.Empty className="px-2 py-1.5 text-xs text-muted-foreground">
              {emptyMessage}
            </AutocompletePrimitive.Empty>
            <AutocompletePrimitive.List>
              {(item: string) => (
                <AutocompletePrimitive.Item
                  key={item}
                  value={item}
                  className={cn(
                    "flex w-full cursor-default items-center rounded-md px-2 py-1.5 text-xs",
                    "outline-none select-none data-highlighted:bg-accent data-highlighted:text-accent-foreground",
                  )}
                >
                  {item}
                </AutocompletePrimitive.Item>
              )}
            </AutocompletePrimitive.List>
          </AutocompletePrimitive.Popup>
        </AutocompletePrimitive.Positioner>
      </AutocompletePrimitive.Portal>
    </AutocompletePrimitive.Root>
  );
}
