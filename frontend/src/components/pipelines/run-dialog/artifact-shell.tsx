"use client";

// Shared chrome for the model / simulation / evaluation artifact cards in
// the run-dialog Jobs tab: a labelled header strip with action buttons on
// the right and a stack of stat rows in the body.

import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export function ArtifactShell({
  label,
  color,
  children,
  actions,
}: {
  label: string;
  color: string;
  children: ReactNode;
  actions: ReactNode;
}) {
  return (
    <div className="space-y-2 rounded-md border border-border bg-background p-3">
      <div className="flex items-center justify-between gap-2">
        <Badge variant="secondary" className={cn("text-[9px] capitalize", color)}>
          {label}
        </Badge>
        <div className="flex flex-wrap items-center gap-1.5">{actions}</div>
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

export function ArtifactStat({
  label,
  value,
}: {
  label: string;
  value: ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-[11px]">
      <span className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground">
        {label}
      </span>
      <span className="truncate text-right font-medium">{value}</span>
    </div>
  );
}
