"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { JobProgress } from "@/lib/api";
import { statusBadgeVariant, translateStatus } from "@/lib/job-status";
import { cn, formatDuration } from "@/lib/utils";

// Single source of truth for the in-progress elapsed counter:
// `started_at_ms` is computed backend-side by parsing the run folder name
// (always UTC, set once at run creation, never rewritten). We tick Date.now()
// against it. No string parsing, no timezone heuristics, no sanity-check
// fallbacks — if the field is missing the timer simply isn't shown.

export function JobProgressPanel({
  status,
  progress,
  startedAtMs,
}: {
  status: string;
  progress: JobProgress | null | undefined;
  startedAtMs?: number | null;
}) {
  const isRunning = status === "in_progress";

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!isRunning) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isRunning]);

  const elapsedSeconds =
    startedAtMs != null ? Math.max(0, Math.floor((now - startedAtMs) / 1000)) : null;

  // Backend semantics: `step` = phases COMPLETED. The phase currently running
  // is therefore phase (step+1). A run never persists step==total because the
  // status flips to `completed` first.
  const total = progress?.total ?? 0;
  const stepDone = progress?.step ?? 0;
  const currentPhase = Math.min(stepDone + 1, Math.max(total, 1));
  const pct = total > 0 ? Math.min(100, Math.round((stepDone / total) * 100)) : 0;

  return (
    <div className="space-y-2 text-sm">
      <div className="flex items-center gap-2">
        <span className="text-muted-foreground">Estado:</span>
        <Badge
          variant={statusBadgeVariant(status)}
          className={cn(status === "completed" && "!bg-blue-500/20 !text-blue-400")}
        >
          {translateStatus(status)}
        </Badge>
        {isRunning && elapsedSeconds != null && (
          <span className="ml-auto text-xs text-muted-foreground tabular-nums">
            {formatDuration(elapsedSeconds)}
          </span>
        )}
      </div>

      {isRunning && total > 0 && (
        <>
          <div className="flex items-baseline justify-between gap-2">
            <span className="truncate text-xs text-muted-foreground">
              {progress?.label || "Procesando"}
            </span>
            <span className="text-xs tabular-nums text-muted-foreground">
              Paso {currentPhase} de {total}
            </span>
          </div>
          <Progress value={pct} />
        </>
      )}

      {isRunning && total === 0 && (
        <p className="text-xs text-muted-foreground">
          Procesando… (sin progreso detallado)
        </p>
      )}
    </div>
  );
}
