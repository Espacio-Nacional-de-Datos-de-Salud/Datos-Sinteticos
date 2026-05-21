"use client";

import { useEffect, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Progress } from "@/components/ui/progress";
import type { JobProgress } from "@/lib/api";
import { statusBadgeVariant, translateStatus } from "@/lib/job-status";
import { cn } from "@/lib/utils";

// Parses the YYYYMMDD_HHMMSS timestamp the backend stamps on jobs (now in UTC).
function parseJobTimestamp(ts: string | undefined | null): Date | null {
  if (!ts) return null;
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/.exec(ts);
  if (!m) return null;
  const [, y, mo, d, h, mi, s] = m;
  // Backend now sends UTC timestamps, so use Date.UTC to create a proper Date
  const timestamp = Date.UTC(
    Number(y),
    Number(mo) - 1,  // Month is 0-indexed in JS
    Number(d),
    Number(h),
    Number(mi),
    Number(s),
  );
  const parsed = new Date(timestamp);

  // Sanity check: if parsed date is in the future, it's likely malformed
  if (parsed.getTime() > Date.now()) {
    console.warn("[JobProgressPanel] Parsed timestamp is in the future:", ts, parsed);
    return null;
  }
  return parsed;
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
  timestamp_ms,
}: {
  status: string;
  progress: JobProgress | null | undefined;
  timestamp?: string;
  timestamp_ms?: number;
}) {
  // Prefer milliseconds timestamp (timezone-agnostic) over string timestamp
  const startedAt = timestamp_ms
    ? new Date(timestamp_ms)
    : parseJobTimestamp(timestamp);
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

  // Sanity check: if elapsed time is unreasonable (> 24 hours), likely a timezone/parsing issue
  const displayedSeconds = elapsedSeconds && elapsedSeconds > 86400
    ? null
    : elapsedSeconds;

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
        {displayedSeconds != null && isRunning && (
          <span className="ml-auto text-xs text-muted-foreground tabular-nums">
            {formatElapsed(displayedSeconds)}
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
