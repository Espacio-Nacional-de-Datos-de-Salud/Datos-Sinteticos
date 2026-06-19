"use client";

// Drop-in replacement for a plain native <select>. Native select popups are
// rendered by the OS and can't be styled, so they look inconsistent (notably
// poorly sized on Windows). This wrapper keeps the familiar `<option>`-children
// API but renders the Base UI <Select> underneath, giving an identical custom
// popup on every platform.
//
// Migrating a call site is mechanical:
//   <select value={v} onChange={(e) => set(e.target.value)} className={C}>
//     <option value="">…</option>
//     {items.map((i) => <option key={i} value={i}>{i}</option>)}
//   </select>
// becomes:
//   <NativeSelect value={v} onValueChange={set} className={C}>
//     …same <option> children…
//   </NativeSelect>

import * as React from "react";

import { cn } from "@/lib/utils";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

type ParsedOption = {
  value: string;
  label: React.ReactNode;
  disabled?: boolean;
};

// Recursively collect <option> elements, looking through fragments and arrays
// (e.g. a placeholder option followed by {list.map(...)}).
function collectOptions(
  children: React.ReactNode,
  acc: ParsedOption[],
): void {
  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) return;
    if (child.type === React.Fragment) {
      collectOptions(
        (child.props as { children?: React.ReactNode }).children,
        acc,
      );
      return;
    }
    if (child.type === "option") {
      const p = child.props as {
        value?: string | number;
        children?: React.ReactNode;
        disabled?: boolean;
      };
      acc.push({
        value: String(p.value ?? ""),
        label: p.children,
        disabled: p.disabled,
      });
    }
  });
}

export function NativeSelect({
  value,
  onValueChange,
  children,
  className,
  id,
  disabled,
  placeholder,
  "aria-label": ariaLabel,
}: {
  value: string;
  onValueChange: (value: string) => void;
  children: React.ReactNode;
  className?: string;
  id?: string;
  disabled?: boolean;
  "aria-label"?: string;
  /** Shown when `value` matches no option. If an empty-value <option> exists,
   * its label is used instead (matching native behaviour). */
  placeholder?: React.ReactNode;
}) {
  const options: ParsedOption[] = [];
  collectOptions(children, options);

  // value -> label map so <SelectValue> renders the chosen option's label
  // rather than the raw value string.
  const items = Object.fromEntries(options.map((o) => [o.value, o.label]));

  return (
    <Select
      items={items}
      value={value}
      onValueChange={(v) => onValueChange((v as string | null) ?? "")}
      disabled={disabled}
    >
      <SelectTrigger id={id} aria-label={ariaLabel} className={cn("w-full", className)}>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
      <SelectContent>
        {options.map((o, i) => (
          <SelectItem key={`${o.value}-${i}`} value={o.value} disabled={o.disabled}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
