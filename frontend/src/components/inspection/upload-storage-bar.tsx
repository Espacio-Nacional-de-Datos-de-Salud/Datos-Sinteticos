"use client";

import type { UploadStats } from "@/lib/api";
import { formatSize } from "./utils";

// Storage usage indicator shown above the file list. The colour ramps from
// green to amber to red as the per-user upload quota fills up; >=90% adds an
// explicit warning sentence so the user understands the upload button will
// soon be disabled.
export function UploadStorageBar({ stats }: { stats: UploadStats | undefined }) {
  if (!stats) return null;

  const { used_bytes, limit_bytes } = stats;
  const pct = limit_bytes > 0 ? Math.min((used_bytes / limit_bytes) * 100, 100) : 0;

  const barColor =
    pct >= 90
      ? "bg-red-500"
      : pct >= 70
        ? "bg-amber-500"
        : "bg-emerald-500";

  const textColor =
    pct >= 90
      ? "text-red-600"
      : pct >= 70
        ? "text-amber-600"
        : "text-muted-foreground";

  return (
    <div className="flex flex-col gap-1">
      <div className="flex items-center justify-between text-xs">
        <span className={textColor}>
          {formatSize(used_bytes)} usados de {formatSize(limit_bytes)}
        </span>
        <span className={`font-medium tabular-nums ${textColor}`}>
          {pct.toFixed(0)}%
        </span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      {pct >= 90 && (
        <p className="text-xs text-red-600">
          Almacenamiento casi lleno. Borra algunos ficheros antes de subir más.
        </p>
      )}
    </div>
  );
}
