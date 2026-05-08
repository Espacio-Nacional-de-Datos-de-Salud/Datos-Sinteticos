// Auditoría — step 6 (final) of the pipeline wizard.
//
// Runs the evaluation suite on a completed simulation. The only input the
// user picks is the simulation_id; the backend resolves the underlying
// model and runs the metrics configured in evaluation.yaml.

"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import axios from "axios";
import { Play, ShieldCheck, Download, Settings, Trash2, XCircle } from "lucide-react";
import { ConfigDrawer } from "@/components/config/config-drawer";
import { JobProgressPanel } from "@/components/jobs/job-progress";
import { EditableName } from "@/components/jobs/editable-name";
import { RulesBanner } from "@/components/config/rules-banner";
import {
  API_BASE_URL,
  api,
  type EvaluationJob,
  type EvaluationSummary,
  type SimulationSummary,
} from "@/lib/api";
import { WizardShell } from "@/components/layout/wizard-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";

const SIMULATION_STORAGE_KEY = "ends.pipeline.currentSimulationId";
const EVALUATION_STORAGE_KEY = "ends.pipeline.currentEvaluationId";

function statusBadgeVariant(
  status: string,
): "default" | "secondary" | "outline" | "destructive" {
  if (status === "completed") return "default";
  if (status === "in_progress") return "secondary";
  if (status === "failed" || status === "cancelled") return "destructive";
  return "outline";
}

function extractDetail(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: string } | undefined)
      ?.detail;
    return detail ?? err.message;
  }
  if (err instanceof Error) return err.message;
  return "Error desconocido";
}

export default function AuditoriaPage() {
  const queryClient = useQueryClient();
  const [selectedSimId, setSelectedSimId] = useState<string>("");
  const [evaluationId, setEvaluationId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [configOpen, setConfigOpen] = useState<boolean>(false);

  useEffect(() => {
    const stored = window.localStorage.getItem(EVALUATION_STORAGE_KEY);
    if (stored) setEvaluationId(stored);
    const s = window.localStorage.getItem(SIMULATION_STORAGE_KEY);
    if (s) setSelectedSimId(s);
    setHydrated(true);
  }, []);

  const simulationsQuery = useQuery({
    queryKey: ["simulations"],
    queryFn: async () => {
      const { data } = await api.get<SimulationSummary[]>("/simulations/");
      return data;
    },
  });

  const completedSims = useMemo(
    () =>
      (simulationsQuery.data ?? []).filter((s) => s.status === "completed"),
    [simulationsQuery.data],
  );

  useEffect(() => {
    if (!hydrated || completedSims.length === 0) return;
    if (
      selectedSimId &&
      completedSims.some((s) => s.simulation_id === selectedSimId)
    ) {
      return;
    }
    setSelectedSimId(completedSims[0].simulation_id);
  }, [hydrated, completedSims, selectedSimId]);

  const evaluationsQuery = useQuery({
    queryKey: ["evaluations"],
    queryFn: async () => {
      const { data } = await api.get<EvaluationSummary[]>("/evaluations/");
      return data;
    },
  });

  const activeEvalQuery = useQuery({
    queryKey: ["evaluation", evaluationId],
    enabled: !!evaluationId,
    queryFn: async () => {
      const { data } = await api.get<EvaluationSummary>(
        `/evaluations/${evaluationId}`,
      );
      return data;
    },
    refetchInterval: (query) =>
      query.state.data?.status === "in_progress" ? 2000 : false,
  });

  const activeStatus = activeEvalQuery.data?.status;
  useEffect(() => {
    if (activeStatus && activeStatus !== "in_progress") {
      queryClient.invalidateQueries({ queryKey: ["evaluations"] });
    }
  }, [activeStatus, queryClient]);

  const startEval = useMutation({
    mutationFn: async () => {
      if (!selectedSimId) throw new Error("No hay generación seleccionada.");
      const { data } = await api.post<EvaluationJob>("/evaluations/", {
        simulation_id: selectedSimId,
      });
      return data;
    },
    onSuccess: (job) => {
      window.localStorage.setItem(EVALUATION_STORAGE_KEY, job.evaluation_id);
      setEvaluationId(job.evaluation_id);
      toast.success(`Evaluación iniciada: ${job.evaluation_id}`);
      queryClient.invalidateQueries({ queryKey: ["evaluations"] });
    },
    onError: (err) => {
      toast.error(`No se pudo iniciar la evaluación: ${extractDetail(err)}`);
    },
  });

  const cancelEval = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post(`/evaluations/${id}/cancel`);
      return data;
    },
    onSuccess: () => {
      toast.success("Cancelación solicitada");
      queryClient.invalidateQueries({ queryKey: ["evaluation", evaluationId] });
      queryClient.invalidateQueries({ queryKey: ["evaluations"] });
    },
    onError: (err) => {
      toast.error(`No se pudo cancelar: ${extractDetail(err)}`);
    },
  });

  const deleteEvaluation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/evaluations/${id}`);
    },
    onSuccess: (_data, id) => {
      toast.success(`Evaluación eliminada: ${id}`);
      if (evaluationId === id) {
        setEvaluationId(null);
        window.localStorage.removeItem(EVALUATION_STORAGE_KEY);
      }
      queryClient.invalidateQueries({ queryKey: ["evaluations"] });
    },
    onError: (err) => {
      toast.error(`No se pudo eliminar: ${extractDetail(err)}`);
    },
  });

  const cleanupEvaluations = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete("/evaluations/cleanup");
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(n > 0 ? `${n} evaluación(es) limpiada(s)` : "Nada que limpiar");
      queryClient.invalidateQueries({ queryKey: ["evaluations"] });
    },
    onError: (err) => {
      toast.error(`Error en limpieza: ${extractDetail(err)}`);
    },
  });

  const purgeEvaluationsMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete("/evaluations/purge");
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(`${n} evaluación(es) eliminada(s)`);
      queryClient.invalidateQueries({ queryKey: ["evaluations"] });
    },
    onError: (err) => {
      toast.error(`Error al purgar: ${extractDetail(err)}`);
    },
  });

  const renameEvaluation = useMutation({
    mutationFn: async ({ id, name }: { id: string; name: string }) => {
      await api.patch(`/evaluations/${id}/name`, { name });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["evaluations"] });
    },
  });

  const evaluations = evaluationsQuery.data ?? [];
  const isRunning = activeEvalQuery.data?.status === "in_progress";

  return (
    <WizardShell currentSlug="auditoria" canAdvance={false}>
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Auditoría</h1>
            <p className="text-sm text-muted-foreground">
              Evalúa la utilidad y privacidad del dataset sintético según las
              métricas configuradas en{" "}
              <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
                evaluation.yaml
              </code>
              .
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setConfigOpen(true)}
          >
            <Settings className="mr-2 h-4 w-4" />
            Configurar
          </Button>
        </div>

        <RulesBanner />

        <ConfigDrawer
          configId="evaluation"
          contextId={selectedSimId}
          open={configOpen}
          onClose={() => setConfigOpen(false)}
        />

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="items-center text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <CardTitle>Nueva evaluación</CardTitle>
              <CardDescription>
                Escoge una generación completada para auditar.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="sim-select">Generación</Label>
                {simulationsQuery.isLoading ? (
                  <Skeleton className="h-9 w-full" />
                ) : completedSims.length === 0 ? (
                  <p className="text-sm text-destructive">
                    No hay generaciones completadas. Vuelve al paso{" "}
                    <b>Generación</b>.
                  </p>
                ) : (
                  <select
                    id="sim-select"
                    value={selectedSimId}
                    onChange={(e) => setSelectedSimId(e.target.value)}
                    className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs"
                  >
                    {completedSims.map((s) => (
                      <option key={s.simulation_id} value={s.simulation_id}>
                        {s.simulation_name || s.simulation_id}
                        {s.sample_size != null
                          ? ` · ${s.sample_size.toLocaleString()} filas`
                          : ""}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <Button
                type="button"
                className="w-full"
                disabled={!selectedSimId || startEval.isPending || isRunning}
                onClick={() => startEval.mutate()}
              >
                <Play className="mr-2 h-4 w-4" />
                {startEval.isPending
                  ? "Iniciando…"
                  : isRunning
                    ? "Evaluación en curso…"
                    : "Iniciar evaluación"}
              </Button>
              <p className="text-xs text-muted-foreground">
                Las métricas concretas a ejecutar se toman de{" "}
                <code className="font-mono">evaluation.yaml</code>. Ajusta ese
                fichero desde <b>Configuración</b>.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Evaluación actual</CardTitle>
              <CardDescription>
                Estado de la última evaluación iniciada.
                {evaluationId && (
                  <span
                    className="ml-2 font-mono text-xs"
                    suppressHydrationWarning
                  >
                    id: {evaluationId}
                  </span>
                )}
              </CardDescription>
              {activeEvalQuery.data && (
                <EditableName
                  name={activeEvalQuery.data.evaluation_name || activeEvalQuery.data.evaluation_id}
                  existingNames={evaluations.map((x) => x.evaluation_name || x.evaluation_id)}
                  onSave={(name) =>
                    renameEvaluation.mutateAsync({ id: activeEvalQuery.data!.evaluation_id, name })
                  }
                />
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {!evaluationId && (
                <p className="text-sm text-muted-foreground">
                  Aún no has iniciado una evaluación en esta sesión.
                </p>
              )}
              {evaluationId && activeEvalQuery.isLoading && (
                <Skeleton className="h-20 w-full" />
              )}
              {activeEvalQuery.data && (
                <div className="space-y-3 text-sm">
                  <JobProgressPanel
                    status={activeEvalQuery.data.status}
                    progress={activeEvalQuery.data.progress}
                    timestamp={activeEvalQuery.data.timestamp}
                  />
                  {activeEvalQuery.data.simulation_id && (
                    <p>
                      <span className="text-muted-foreground">
                        Generación:{" "}
                      </span>
                      <span className="font-mono text-xs">
                        {activeEvalQuery.data.simulation_id}
                      </span>
                    </p>
                  )}
                  {activeEvalQuery.data.model_id && (
                    <p>
                      <span className="text-muted-foreground">Modelo: </span>
                      <span className="font-mono text-xs">
                        {activeEvalQuery.data.model_id}
                      </span>
                    </p>
                  )}
                  {activeEvalQuery.data.metrics_evaluated &&
                    activeEvalQuery.data.metrics_evaluated.length > 0 && (
                      <div>
                        <p className="mb-1 text-muted-foreground">Métricas:</p>
                        <div className="flex flex-wrap gap-1">
                          {activeEvalQuery.data.metrics_evaluated.map((m) => (
                            <Badge key={m} variant="secondary">
                              {m}
                            </Badge>
                          ))}
                        </div>
                      </div>
                    )}
                  <div className="flex flex-wrap gap-2 pt-1">
                    {isRunning && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={cancelEval.isPending}
                        onClick={() =>
                          evaluationId && cancelEval.mutate(evaluationId)
                        }
                      >
                        Cancelar
                      </Button>
                    )}
                    {activeEvalQuery.data.status === "completed" && (
                      <a
                        href={`${API_BASE_URL}/evaluations/${evaluationId}/download`}
                      >
                        <Button type="button" size="sm" variant="outline">
                          <Download className="mr-2 h-4 w-4" />
                          Descargar resultados
                        </Button>
                      </a>
                    )}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Evaluaciones</CardTitle>
              <CardDescription>
                Catálogo completo de evaluaciones en el servidor.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={cleanupEvaluations.isPending || evaluations.length === 0}
                onClick={() => setConfirmCleanup(true)}
              >
                <Trash2 className="mr-2 h-3.5 w-3.5" />
                Limpiar sesiones incompletas
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={purgeEvaluationsMutation.isPending || evaluations.length === 0}
                onClick={() => setConfirmPurge(true)}
              >
                <Trash2 className="mr-2 h-3.5 w-3.5" />
                Limpiar todas las sesiones
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {evaluationsQuery.isLoading && <Skeleton className="h-24 w-full" />}
            {evaluationsQuery.isError && (
              <p className="text-sm text-destructive">
                No se pudo cargar el catálogo de evaluaciones.
              </p>
            )}
            {evaluationsQuery.data && evaluations.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Todavía no hay evaluaciones.
              </p>
            )}
            {evaluations.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nombre</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Generación</TableHead>
                    <TableHead>Modelo</TableHead>
                    <TableHead>Métricas</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {evaluations.map((e) => (
                    <TableRow key={e.evaluation_id}>
                      <TableCell>
                        <div className="space-y-0.5">
                          <p className="font-mono text-[10px] text-muted-foreground">
                            {e.evaluation_id}
                          </p>
                          <EditableName
                            name={e.evaluation_name || e.evaluation_id}
                            existingNames={evaluations.map(
                              (x) => x.evaluation_name || x.evaluation_id,
                            )}
                            onSave={(name) =>
                              renameEvaluation.mutateAsync({
                                id: e.evaluation_id,
                                name,
                              })
                            }
                          />
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusBadgeVariant(e.status)}>
                          {e.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {e.simulation_id ?? "—"}
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {e.model_id ?? "—"}
                      </TableCell>
                      <TableCell className="text-xs">
                        {e.metrics_evaluated?.length
                          ? e.metrics_evaluated.join(", ")
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        {e.status === "in_progress" ? (
                          <button
                            type="button"
                            aria-label="Cancelar evaluación"
                            disabled={cancelEval.isPending}
                            onClick={() => cancelEval.mutate(e.evaluation_id)}
                            className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                          </button>
                        ) : (
                          <button
                            type="button"
                            aria-label="Eliminar evaluación"
                            disabled={deleteEvaluation.isPending}
                            onClick={() => setConfirmDelete(e.evaluation_id)}
                            className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </CardContent>
        </Card>
      </div>

      <ConfirmDialog
        open={confirmDelete !== null}
        title="¿Eliminar evaluación?"
        description="Se borrarán permanentemente la carpeta de la evaluación y todos sus resultados. Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        onConfirm={() => {
          if (confirmDelete) deleteEvaluation.mutate(confirmDelete);
          setConfirmDelete(null);
        }}
        onCancel={() => setConfirmDelete(null)}
      />
      <ConfirmDialog
        open={confirmCleanup}
        title="¿Limpiar evaluaciones?"
        description="Se borrarán permanentemente las carpetas vacías y las ejecuciones huérfanas. Esta acción no se puede deshacer."
        confirmLabel="Limpiar"
        onConfirm={() => {
          cleanupEvaluations.mutate();
          setConfirmCleanup(false);
        }}
        onCancel={() => setConfirmCleanup(false)}
      />
      <ConfirmDialog
        open={confirmPurge}
        title="¿Purgar todas las evaluaciones?"
        description="Se eliminarán TODAS las evaluaciones, incluidas las completadas correctamente. Esta acción no se puede deshacer."
        confirmLabel="Purgar"
        onConfirm={() => {
          purgeEvaluationsMutation.mutate();
          setConfirmPurge(false);
        }}
        onCancel={() => setConfirmPurge(false)}
      />
    </WizardShell>
  );
}
