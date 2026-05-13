"use client";

// One entry in the "Ejecuciones recientes" list in the left rail. Click to
// open the full PipelineRunDialog. Status drives only the dot colour — the
// rest of the row is uniform so very-long pipeline ids stay legible.

import { Eye } from "lucide-react";

import type { PipelineSummary } from "@/lib/api";
import { cn } from "@/lib/utils";

export function RunRow({
  run,
  onClick,
}: {
  run: PipelineSummary;
  onClick: () => void;
}) {
  const color =
    run.status === "completed"
      ? "bg-emerald-500"
      : run.status === "failed"
        ? "bg-red-500"
        : run.status === "in_progress"
          ? "bg-amber-500"
          : run.status === "partial"
            ? "bg-amber-400"
            : "bg-muted-foreground";
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent/60"
      >
        <div className="flex items-center gap-2 truncate">
          <span className={cn("inline-block h-1.5 w-1.5 shrink-0 rounded-full", color)} />
          <span className="truncate font-mono">{run.pipeline_id}</span>
        </div>
        <Eye className="h-3 w-3 shrink-0 text-muted-foreground" />
      </button>
    </li>
  );
}
