"use client";

import { AlertCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";
import { statusBadgeVariant, translateStatus } from "@/lib/job-status";
import { cn } from "@/lib/utils";

// Status pill shared by every pipeline page (active card + history tables).
// When a run failed and the backend attached a reason, the pill gains a small
// alert icon and reveals that reason on hover — keeping the failure detail one
// gesture away without cluttering the row with an always-on error block.
export function StatusBadge({
  status,
  errorMessage,
  className,
}: {
  status: string;
  errorMessage?: string | null;
  className?: string;
}) {
  const hasReason = status === "failed" && Boolean(errorMessage);

  const badge = (
    <Badge
      variant={statusBadgeVariant(status)}
      className={cn(hasReason && "cursor-help gap-1", className)}
    >
      {translateStatus(status) || "—"}
      {hasReason && <AlertCircle className="h-3 w-3" />}
    </Badge>
  );

  if (!hasReason) return badge;

  return (
    <Tooltip content={errorMessage as string} side="top">
      {badge}
    </Tooltip>
  );
}
