"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { JobProgress } from "@/lib/api";

function statusBadgeVariant(
  status: string,
): "default" | "secondary" | "outline" | "destructive" {
  if (status === "completed") return "default";
  if (status === "in_progress") return "secondary";
  if (status === "failed" || status === "cancelled") return "destructive";
  return "outline";
}

// Parses the YYYYMMDD_HHMMSS timestamp the backend stamps on jobs (local time).
function parseJobTimestamp(ts: string | undefined | null): Date | null {
  if (!ts) return null;
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/.exec(ts);
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m;
  return new Date(
    Number(y),
    Number(mo) - 1,
    Number(d),
    Number(h),
    Number(mi),
    Number(s),
  );
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s.toString().padStart(2, "0")}s`;
}

export function JobProgressPanel({
  status,
  progress,
  timestamp,
}: {
  status: string;
  progress: JobProgress | null;
  timestamp?: string;
}) {
  const startedAt = parseJobTimestamp(timestamp);
  const isRunning = status === "in_progress";

  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!isRunning) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [isRunning]);

  const elapsedSeconds = startedAt
    ? Math.max(0, Math.floor((now - startedAt.getTime()) / 1000))
    : null;

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
        <Badge variant={statusBadgeVariant(status)}>{status}</Badge>
        {elapsedSeconds != null && isRunning && (
          <span className="ml-auto text-xs text-muted-foreground tabular-nums">
            {formatElapsed(elapsedSeconds)}
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
