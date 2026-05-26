"use client";

// Renders the structured time-profiling report attached to a finished run.
// Each phase page mounts this inside the ActiveJobCard.metadata slot, gated on
// status === "completed". Fetches on demand from GET /{kind}/{id}/time-profiling
// — the heavy per-phase data stays out of the list response.
//
// Dev-only: hidden entirely outside dev mode (raw phase timings are noisy and
// only meaningful to engineers debugging the pipeline).

import { useState } from "react";
import { ChevronRight } from "lucide-react";
import { useQuery } from "@tanstack/react-query";

import { api, type TimeProfilingReport } from "@/lib/api";
import { useIsDev } from "@/lib/mode";
import { cn, formatDuration } from "@/lib/utils";

type Kind = "inspections" | "models" | "simulations" | "evaluations";

export function TimeProfilingPanel({
  kind,
  id,
  title = "Tiempo por fase",
}: {
  kind: Kind;
  id: string;
  title?: string;
}) {
  const isDev = useIsDev();
  const [open, setOpen] = useState(false);

  const query = useQuery({
    queryKey: ["time-profiling", kind, id],
    queryFn: async () => {
      const { data } = await api.get<TimeProfilingReport>(`/${kind}/${id}/time-profiling`);
      return data;
    },
    // Past runs never change their timing once finished.
    staleTime: Infinity,
    retry: false,
    enabled: isDev,
  });

  if (!isDev) return null;

  if (query.isLoading) {
    return (
      <div className="text-xs text-muted-foreground">Cargando tiempos…</div>
    );
  }

  // 404 is expected for older runs that finished before the structured report
  // existed — silently hide the panel in that case.
  if (query.isError || !query.data) return null;

  const { total_seconds, phases, note } = query.data;

  return (
    <div className="rounded border border-border bg-muted/40">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-2 px-3 py-2 text-left"
        aria-expanded={open}
      >
        <span className="flex items-center gap-1.5">
          <ChevronRight
            className={cn(
              "h-3.5 w-3.5 text-muted-foreground transition-transform",
              open && "rotate-90",
            )}
          />
          <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {title}
          </span>
        </span>
        <span className="font-mono text-xs tabular-nums text-muted-foreground">
          Total: {formatDuration(total_seconds)}
        </span>
      </button>

      {open && (
        <div className="border-t border-border px-3 py-2">
          {phases.length === 0 ? (
            <p className="text-xs text-muted-foreground">
              {note || "Sin fases registradas."}
            </p>
          ) : (
            <ul className="space-y-0.5">
              {phases.map((p, i) => (
                <li
                  key={`${p.depth}-${p.name}-${i}`}
                  className="flex items-baseline gap-2 py-0.5 text-xs"
                >
                  <span
                    className="shrink-0 truncate"
                    style={{ paddingLeft: `${p.depth * 14}px` }}
                    title={p.name}
                  >
                    {p.depth > 0 && (
                      <span className="text-muted-foreground/60">↳ </span>
                    )}
                    {p.name}
                  </span>
                  <span
                    aria-hidden
                    className="min-w-4 flex-1 translate-y-[-2px] border-b border-dotted border-border/70"
                  />
                  <span className="shrink-0 font-mono tabular-nums text-foreground">
                    {formatDuration(p.seconds)}
                  </span>
                  <span className="w-12 shrink-0 text-right font-mono tabular-nums text-muted-foreground">
                    {p.percent != null ? `${p.percent.toFixed(1)}%` : ""}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
