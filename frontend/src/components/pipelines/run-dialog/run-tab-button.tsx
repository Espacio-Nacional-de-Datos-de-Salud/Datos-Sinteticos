"use client";

import { cn } from "@/lib/utils";

export type RunTab = "summary" | "jobs";

export function RunTabButton({
  id,
  label,
  badge,
  active,
  onSelect,
}: {
  id: RunTab;
  label: string;
  badge?: number;
  active: RunTab;
  onSelect: (id: RunTab) => void;
}) {
  const isActive = active === id;
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      className={cn(
        "relative -mb-px border-b-2 px-3 py-2 text-xs font-medium transition-colors",
        isActive
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      <span>{label}</span>
      {badge !== undefined && (
        <span
          className={cn(
            "ml-1.5 rounded px-1.5 py-0.5 text-[9px] font-semibold",
            isActive ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground",
          )}
        >
          {badge}
        </span>
      )}
    </button>
  );
}
