"use client";

// Pipeline-run results viewer modal. Shown when the user clicks an entry in
// the "Ejecuciones recientes" rail. Renders a Resumen tab with progress and
// counts, plus a Jobs tab that lists per-job artifacts (model / simulation /
// evaluation) with deep-links into the wizard pages — we drop the artifact
// id into the same localStorage key the destination page reads on mount, so
// no query-string plumbing is needed.

import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { ChevronDown, ChevronRight, Eye, X } from "lucide-react";

import { JobProgressPanel } from "@/components/jobs/job-progress";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { api, type PipelineSummary } from "@/lib/api";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { cn } from "@/lib/utils";

import { EvaluationArtifactCard } from "./evaluation-artifact-card";
import { ModelArtifactCard } from "./model-artifact-card";
import { PipelineConfigSnapshotDialog } from "./config-snapshot-dialog";
import { RunTabButton, type RunTab } from "./run-tab-button";
import { SimulationArtifactCard } from "./simulation-artifact-card";
import { formatRunTimestamp } from "./utils";

// Storage keys the wizard pages already read on mount to restore the
// "currently selected" model/simulation/evaluation. We piggy-back on them so
// the "Ir a …" buttons land the user on the exact artifact this run produced.
const RUN_MODEL_STORAGE_KEY = STORAGE_KEYS.model;
const RUN_SIMULATION_STORAGE_KEY = STORAGE_KEYS.simulation;
const RUN_EVALUATION_STORAGE_KEY = STORAGE_KEYS.evaluation;

export function PipelineRunDialog({
  run,
  onClose,
}: {
  run: PipelineSummary;
  onClose: () => void;
}) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<RunTab>("summary");
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [configsOpen, setConfigsOpen] = useState(false);

  const cancelRun = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post(`/pipelines/${id}/cancel`);
      return data;
    },
    onSuccess: () => {
      toast.success("Cancelación solicitada");
      queryClient.invalidateQueries({ queryKey: ["pipeline-runs"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudo cancelar: ${msg}`);
    },
  });
  const isRunning = run.status === "in_progress";

  const counts = useMemo(() => {
    let completed = 0;
    let failed = 0;
    let other = 0;
    for (const j of run.jobs) {
      if (j.status === "completed") completed += 1;
      else if (j.status === "failed") failed += 1;
      else other += 1;
    }
    return { completed, failed, other };
  }, [run.jobs]);

  const goToModel = (id: string) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(RUN_MODEL_STORAGE_KEY, id);
    }
    onClose();
    router.push("/pipeline/entrenamiento");
  };

  const goToSimulation = (id: string) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(RUN_SIMULATION_STORAGE_KEY, id);
    }
    onClose();
    router.push("/pipeline/generacion");
  };

  const goToEvaluation = (id: string) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(RUN_EVALUATION_STORAGE_KEY, id);
    }
    onClose();
    router.push("/pipeline/auditoria");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg border border-border bg-card shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className="h-2 w-2 rounded-full"
              style={{
                backgroundColor: run.status === "completed" ? "var(--status-completed)" : "#f59e0b",
              }}
            />
            <h3 className="text-lg font-semibold tracking-tight">{run.pipeline_id}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="border-b border-border px-4">
          <div className="flex gap-1">
            <RunTabButton id="summary" label="Resumen" active={tab} onSelect={setTab} />
            <RunTabButton
              id="jobs"
              label="Trabajos"
              badge={run.jobs.length}
              active={tab}
              onSelect={setTab}
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {tab === "summary" && (
            <div className="grid gap-5">
              {isRunning && (
                <div className="rounded-md border border-border bg-muted/20 p-4">
                  <JobProgressPanel
                    status={run.status}
                    progress={run.progress}
                    startedAtMs={run.started_at_ms ?? null}
                  />
                  <div className="mt-3">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={cancelRun.isPending}
                      onClick={() => cancelRun.mutate(run.pipeline_id)}
                    >
                      Cancelar
                    </Button>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-4 rounded-md border border-border bg-muted/30 p-4">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                    Estado
                  </div>
                  <div className="text-sm font-medium capitalize">{run.status}</div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                    Iniciado
                  </div>
                  <div className="text-sm font-medium">{formatRunTimestamp(run.timestamp)}</div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-md border border-border bg-background p-3 text-center">
                  <div
                    className="text-2xl font-bold rounded px-2 py-1"
                    style={{
                      color: "var(--status-completed)",
                      backgroundColor: "var(--status-completed-bg)"
                    }}
                  >
                    {counts.completed}
                  </div>
                  <div className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground mt-2">
                    Completados
                  </div>
                </div>
                <div className="rounded-md border border-border bg-background p-3 text-center">
                  <div className="text-2xl font-bold text-red-500">{counts.failed}</div>
                  <div className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground mt-2">
                    Fallidos
                  </div>
                </div>
                <div className="rounded-md border border-border bg-background p-3 text-center">
                  <div className="text-2xl font-bold text-amber-500">{counts.other}</div>
                  <div className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground mt-2">
                    En progreso
                  </div>
                </div>
              </div>

              <div className="space-y-1">
                <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                  Configuración lanzada
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setConfigsOpen(true)}
                >
                  <Eye className="mr-1 h-3.5 w-3.5" />
                  Ver configuración
                </Button>
              </div>

              <p className="text-[11px] leading-relaxed text-muted-foreground">
                Abre la pestaña <strong>Trabajos</strong> para revisar el detalle por trabajo, o{" "}
                <strong>Artefactos</strong> para acceder rápido a los modelos y simulaciones
                producidos.
              </p>
            </div>
          )}

          {tab === "jobs" && (
            <div className="space-y-2">
              {run.jobs.length === 0 && (
                <div className="rounded-md border border-dashed border-border px-3 py-4 text-center text-[11px] text-muted-foreground">
                  Esta ejecución no registró trabajos (probablemente falló antes de completar
                  el primer paso).
                </div>
              )}
              {run.jobs.map((job, i) => {
                const jobStatus = job.status ?? "unknown";
                const statusColor =
                  jobStatus === "completed"
                    ? ""
                    : jobStatus === "failed"
                      ? "text-red-600"
                      : "text-amber-600";
                const isOpen = !!expanded[i];
                const hasArtifacts = !!(
                  job.model_id || job.simulation_id || job.evaluation_id
                );
                const previewBits = [
                  job.model_id ? `model: ${job.model_id}` : null,
                  job.simulation_id ? `sim: ${job.simulation_id}` : null,
                  job.evaluation_id ? `eval: ${job.evaluation_id}` : null,
                ].filter(Boolean) as string[];
                return (
                  <div key={i} className="rounded-md border border-border bg-background">
                    <button
                      type="button"
                      onClick={() => setExpanded((s) => ({ ...s, [i]: !s[i] }))}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/40"
                      aria-expanded={isOpen}
                    >
                      {isOpen ? (
                        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                      )}
                      <span className="text-xs font-bold">
                        {job.job_name ?? `trabajo_${i + 1}`}
                      </span>
                      <Badge
                        variant={jobStatus === "completed" ? "default" : "secondary"}
                        className={cn(
                          "ml-1 text-[9px]",
                          jobStatus === "completed" && "!bg-blue-500/20 !text-blue-400"
                        )}
                      >
                        {jobStatus === "completed" ? "Completado" : jobStatus === "failed" ? "Fallido" : "En progreso"}
                      </Badge>
                      {!isOpen && hasArtifacts && (
                        <span className="ml-2 truncate font-mono text-[10px] text-muted-foreground">
                          {previewBits.join("  ·  ")}
                        </span>
                      )}
                      {!isOpen && !hasArtifacts && (
                        <span className="ml-2 text-[10px] italic text-muted-foreground">
                          sin artefactos
                        </span>
                      )}
                    </button>
                    {isOpen && (
                      <div className="space-y-2 border-t border-border bg-muted/20 p-3">
                        {!hasArtifacts && (
                          <div className="text-[11px] text-muted-foreground">
                            Este trabajo no produjo artefactos (estado: {jobStatus}).
                          </div>
                        )}
                        {job.model_id && (
                          <ModelArtifactCard
                            modelId={job.model_id}
                            onOpen={() => goToModel(job.model_id!)}
                          />
                        )}
                        {job.simulation_id && (
                          <SimulationArtifactCard
                            simulationId={job.simulation_id}
                            onOpen={() => goToSimulation(job.simulation_id!)}
                          />
                        )}
                        {job.evaluation_id && (
                          <EvaluationArtifactCard
                            evaluationId={job.evaluation_id}
                            onOpen={() => goToEvaluation(job.evaluation_id!)}
                          />
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {configsOpen && (
            <PipelineConfigSnapshotDialog
              pipelineId={run.pipeline_id}
              onClose={() => setConfigsOpen(false)}
            />
          )}
        </div>

        <footer className="flex justify-end border-t border-border bg-muted/20 px-6 py-4">
          <Button type="button" onClick={onClose} size="sm">
            Cerrar
          </Button>
        </footer>
      </div>
    </div>
  );
}
