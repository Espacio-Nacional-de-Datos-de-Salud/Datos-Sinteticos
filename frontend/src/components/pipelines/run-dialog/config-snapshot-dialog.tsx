"use client";

// Reads the snapshots that ``PipelineTracker`` archives next to each run and
// renders a readable summary — the user shouldn't need to open files on the
// server to know what configuration ran.

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Copy, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { getPipelineRunConfigs } from "@/lib/api";
import { copyToClipboard } from "./utils";

export function PipelineConfigSnapshotDialog({
  pipelineId,
  onClose,
}: {
  pipelineId: string;
  onClose: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["pipeline-run-configs", pipelineId],
    queryFn: () => getPipelineRunConfigs(pipelineId),
  });

  const jobs = useMemo(() => {
    const raw = (data?.pipeline_config as { jobs?: unknown } | null)?.jobs;
    return Array.isArray(raw) ? (raw as Record<string, unknown>[]) : [];
  }, [data]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg border border-border bg-card shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
              Configuración del run
            </div>
            <h3 className="text-base font-semibold tracking-tight">{pipelineId}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-auto p-6">
          {isLoading && (
            <p className="text-[11px] text-muted-foreground">Cargando configuración…</p>
          )}
          {error && (
            <p className="text-[11px] text-red-600">
              No se pudo leer la configuración congelada para este run.
            </p>
          )}
          {data && (
            <>
              {data.config_path && (
                <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                    YAML lanzado
                  </div>
                  <div
                    className="truncate font-mono text-[11px]"
                    title={data.config_path}
                  >
                    {data.config_path}
                  </div>
                </div>
              )}

              {jobs.length > 0 && (
                <section className="space-y-2">
                  <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                    Trabajos ({jobs.length})
                  </div>
                  <div className="space-y-1">
                    {jobs.map((job, i) => {
                      const name = (job.name as string) ?? `trabajo_${i + 1}`;
                      const steps = [
                        job.train ? "entrenar" : null,
                        job.simulate ? "generar" : null,
                        job.evaluate ? "evaluar" : null,
                      ].filter(Boolean) as string[];
                      return (
                        <div
                          key={i}
                          className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-1.5"
                        >
                          <span className="font-mono text-[11px]">{name}</span>
                          <span className="text-[10px] text-muted-foreground">
                            {steps.length > 0 ? steps.join(" · ") : "—"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {data.general_config && (
                <section className="space-y-2">
                  <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                    Constantes generales
                  </div>
                  <div className="rounded-md border border-border bg-muted/30 p-3">
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                      {Object.entries(data.general_config).map(([k, v]) => (
                        <FragmentEntry key={k} k={k} v={v} />
                      ))}
                    </dl>
                  </div>
                </section>
              )}

              {data.pipeline_config_yaml && (
                <section className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                      pipeline_config.yaml
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        void copyToClipboard(data.pipeline_config_yaml ?? "")
                      }
                      className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                      title="Copiar YAML"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <pre className="max-h-[40vh] overflow-auto rounded-md border border-border bg-muted/30 p-3 font-mono text-[11px] leading-5">
                    {data.pipeline_config_yaml}
                  </pre>
                </section>
              )}

              {!data.pipeline_config_yaml && !data.general_config && (
                <p className="text-[11px] text-muted-foreground">
                  Esta ejecución no incluye snapshots de configuración (run anterior al
                  registro de <code>configs</code> en el pipeline_card).
                </p>
              )}
            </>
          )}
        </div>

        <footer className="flex justify-end border-t border-border bg-muted/20 px-6 py-4">
          <Button type="button" size="sm" onClick={onClose}>
            Cerrar
          </Button>
        </footer>
      </div>
    </div>
  );
}

function FragmentEntry({ k, v }: { k: string; v: unknown }) {
  const display =
    v === null || v === undefined
      ? "—"
      : typeof v === "object"
        ? JSON.stringify(v)
        : String(v);
  return (
    <>
      <dt className="font-mono text-muted-foreground">{k}</dt>
      <dd className="truncate font-mono" title={display}>
        {display}
      </dd>
    </>
  );
}
