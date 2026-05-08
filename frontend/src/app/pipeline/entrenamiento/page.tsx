// Entrenamiento — step 4 of the pipeline wizard.
//
// Launches a training run from a completed inspection. The user picks which
// inspection to train from; the mostly_ai and rules configs are edited via
// the "Configurar" drawer (which writes to mostly_ai.yaml / rules.yaml that
// the backend reads by default).
//
// Multiple trainings can be launched back-to-back; each completed model
// shows up in the catalog table at the bottom and becomes selectable in
// the Generación step.

"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import axios from "axios";
import {
  ExternalLink,
  FileText,
  Play,
  Settings,
  Sparkles,
  Trash2,
  XCircle,
} from "lucide-react";
import { ConfigDrawer } from "@/components/config/config-drawer";
import { JobProgressPanel } from "@/components/jobs/job-progress";
import { EditableName } from "@/components/jobs/editable-name";
import { RulesBanner } from "@/components/config/rules-banner";
import {
  api,
  API_BASE_URL,
  type InspectionSummary,
  type ModelSummary,
  type TrainingJob,
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

const INSPECTION_STORAGE_KEY = "ends.pipeline.currentInspectionId";
const MODEL_STORAGE_KEY = "ends.pipeline.currentModelId";

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

export default function EntrenamientoPage() {
  const queryClient = useQueryClient();
  const [selectedInspectionId, setSelectedInspectionId] = useState<string>("");
  const [modelId, setModelId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [configOpen, setConfigOpen] = useState(false);

  useEffect(() => {
    const m = window.localStorage.getItem(MODEL_STORAGE_KEY);
    if (m) setModelId(m);
    const insp = window.localStorage.getItem(INSPECTION_STORAGE_KEY);
    if (insp) setSelectedInspectionId(insp);
    setHydrated(true);
  }, []);

  const inspectionsQuery = useQuery({
    queryKey: ["inspections"],
    queryFn: async () => {
      const { data } = await api.get<InspectionSummary[]>("/inspections/");
      return data;
    },
  });

  const completedInspections = useMemo(
    () =>
      (inspectionsQuery.data ?? []).filter((i) => i.status === "completed"),
    [inspectionsQuery.data],
  );

  // Default the inspection select to the last-used one if it is still a
  // completed inspection, else to the most recent completed one.
  useEffect(() => {
    if (!hydrated || completedInspections.length === 0) return;
    if (
      selectedInspectionId &&
      completedInspections.some(
        (i) => i.inspection_id === selectedInspectionId,
      )
    ) {
      return;
    }
    setSelectedInspectionId(completedInspections[0].inspection_id);
  }, [hydrated, completedInspections, selectedInspectionId]);

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const { data } = await api.get<ModelSummary[]>("/models/");
      return data;
    },
  });

  const activeModelQuery = useQuery({
    queryKey: ["model", modelId],
    enabled: !!modelId,
    queryFn: async () => {
      const { data } = await api.get<ModelSummary>(`/models/${modelId}`);
      return data;
    },
    refetchInterval: (query) =>
      query.state.data?.status === "in_progress" ? 2000 : false,
  });

  const activeStatus = activeModelQuery.data?.status;
  useEffect(() => {
    if (activeStatus && activeStatus !== "in_progress") {
      queryClient.invalidateQueries({ queryKey: ["models"] });
    }
  }, [activeStatus, queryClient]);

  const startTraining = useMutation({
    mutationFn: async () => {
      if (!selectedInspectionId)
        throw new Error("No hay inspección seleccionada.");
      const { data } = await api.post<TrainingJob>("/models/", {
        inspection_id: selectedInspectionId,
      });
      return data;
    },
    onSuccess: (job) => {
      window.localStorage.setItem(MODEL_STORAGE_KEY, job.model_id);
      setModelId(job.model_id);
      toast.success(`Entrenamiento iniciado: ${job.model_id}`);
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (err) => {
      toast.error(`No se pudo iniciar el entrenamiento: ${extractDetail(err)}`);
    },
  });

  const cancelTraining = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post(`/models/${id}/cancel`);
      return data;
    },
    onSuccess: () => {
      toast.success("Cancelación solicitada");
      queryClient.invalidateQueries({ queryKey: ["model", modelId] });
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (err) => {
      toast.error(`No se pudo cancelar: ${extractDetail(err)}`);
    },
  });

  const deleteModel = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/models/${id}`);
    },
    onSuccess: (_data, id) => {
      toast.success(`Modelo eliminado: ${id}`);
      if (modelId === id) {
        setModelId(null);
        window.localStorage.removeItem(MODEL_STORAGE_KEY);
      }
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (err) => {
      toast.error(`No se pudo eliminar: ${extractDetail(err)}`);
    },
  });

  const cleanupModels = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete("/models/cleanup");
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(n > 0 ? `${n} modelo(s) limpiado(s)` : "Nada que limpiar");
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (err) => {
      toast.error(`Error en limpieza: ${extractDetail(err)}`);
    },
  });

  const purgeModelsMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete("/models/purge");
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(`${n} modelo(s) eliminado(s)`);
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
    onError: (err) => {
      toast.error(`Error al purgar: ${extractDetail(err)}`);
    },
  });

  const renameModel = useMutation({
    mutationFn: async ({ id, name }: { id: string; name: string }) => {
      await api.patch(`/models/${id}/name`, { name });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["models"] });
    },
  });

  const openReport = (model: ModelSummary) => {
    if (!model.qa_report_filename) {
      toast.info("No hay informes de calidad disponibles para este modelo.");
      return;
    }
    const url = `${API_BASE_URL}/models/${model.model_id}/reports/${model.qa_report_filename}`;
    window.open(url, "_blank");
  };

  const models = modelsQuery.data ?? [];
  const hasCompleted = useMemo(
    () =>
      models.some((m) => m.status === "completed") ||
      activeModelQuery.data?.status === "completed",
    [models, activeModelQuery.data],
  );

  const isRunning = activeModelQuery.data?.status === "in_progress";

  return (
    <WizardShell currentSlug="entrenamiento" canAdvance={hasCompleted}>
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Entrenamiento
            </h1>
            <p className="text-sm text-muted-foreground">
              Lanza un entrenamiento a partir de una inspección completada.
              Puedes encadenar varios entrenamientos; cada uno aparecerá en el
              catálogo de abajo y estará disponible en el paso de{" "}
              <b>Generación</b>.
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

        <ConfigDrawer
          configId="mostly_ai"
          open={configOpen}
          onClose={() => setConfigOpen(false)}
        />

        <RulesBanner inspectionId={selectedInspectionId || null} />

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="items-center text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Sparkles className="h-5 w-5" />
              </div>
              <CardTitle>Nuevo entrenamiento</CardTitle>
              <CardDescription>
                Escoge inspección, configuración y lanza.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="inspection-select">Inspección</Label>
                {inspectionsQuery.isLoading ? (
                  <Skeleton className="h-9 w-full" />
                ) : completedInspections.length === 0 ? (
                  <p className="text-sm text-destructive">
                    No hay inspecciones completadas. Vuelve al paso{" "}
                    <b>Inspección</b>.
                  </p>
                ) : (
                  <select
                    id="inspection-select"
                    value={selectedInspectionId}
                    onChange={(e) => setSelectedInspectionId(e.target.value)}
                    className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs"
                  >
                    {completedInspections.map((i) => {
                      const tableSummary = Object.keys(i.tables ?? {}).join(
                        ", ",
                      );
                      return (
                        <option key={i.inspection_id} value={i.inspection_id}>
                          {i.inspection_name || i.inspection_id}
                          {tableSummary ? ` · ${tableSummary}` : ""}
                        </option>
                      );
                    })}
                  </select>
                )}
              </div>

              <Button
                type="button"
                className="w-full"
                disabled={
                  !selectedInspectionId ||
                  startTraining.isPending ||
                  isRunning
                }
                onClick={() => startTraining.mutate()}
              >
                <Play className="mr-2 h-4 w-4" />
                {startTraining.isPending
                  ? "Iniciando…"
                  : isRunning
                    ? "Entrenamiento en curso…"
                    : "Iniciar entrenamiento"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Entrenamiento actual</CardTitle>
              <CardDescription>
                Estado del último entrenamiento iniciado desde esta sesión.
                {modelId && (
                  <span
                    className="ml-2 font-mono text-xs"
                    suppressHydrationWarning
                  >
                    id: {modelId}
                  </span>
                )}
              </CardDescription>
              {activeModelQuery.data && (
                <EditableName
                  name={activeModelQuery.data.model_name || activeModelQuery.data.model_id}
                  existingNames={models.map((x) => x.model_name || x.model_id)}
                  onSave={(name) =>
                    renameModel.mutateAsync({ id: activeModelQuery.data!.model_id, name })
                  }
                />
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {!modelId && (
                <p className="text-sm text-muted-foreground">
                  Aún no has iniciado un entrenamiento en esta sesión.
                </p>
              )}
              {modelId && activeModelQuery.isLoading && (
                <Skeleton className="h-20 w-full" />
              )}
              {modelId && activeModelQuery.isError && (
                <p className="text-sm text-destructive">
                  No se pudo cargar el estado del modelo.
                </p>
              )}
              {activeModelQuery.data && (
                <div className="space-y-3 text-sm">
                  <JobProgressPanel
                    status={activeModelQuery.data.status}
                    progress={activeModelQuery.data.progress}
                    timestamp={activeModelQuery.data.timestamp}
                  />
                  {activeModelQuery.data.tables && (
                    <p>
                      <span className="text-muted-foreground">Tablas: </span>
                      <span className="font-mono text-xs">
                        {activeModelQuery.data.tables}
                      </span>
                    </p>
                  )}
                  {activeModelQuery.data.train_size != null && (
                    <p>
                      <span className="text-muted-foreground">Filas: </span>
                      <span className="tabular-nums">
                        {activeModelQuery.data.train_size.toLocaleString()}
                      </span>
                    </p>
                  )}
                  {activeModelQuery.data.accuracy != null && (
                    <p>
                      <span className="text-muted-foreground">Precisión: </span>
                      <span className="tabular-nums">
                        {(activeModelQuery.data.accuracy * 100).toFixed(2)}%
                      </span>
                    </p>
                  )}
                  {isRunning && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={cancelTraining.isPending}
                      onClick={() =>
                        modelId && cancelTraining.mutate(modelId)
                      }
                    >
                      Cancelar entrenamiento
                    </Button>
                  )}
                  {activeModelQuery.data.status === "completed" && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      className="w-full"
                      onClick={() => activeModelQuery.data && openReport(activeModelQuery.data)}
                    >
                      <FileText className="mr-2 h-4 w-4" />
                      Ver informe de calidad
                    </Button>
                  )}
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader className="flex-row items-start justify-between space-y-0">
            <div>
              <CardTitle className="text-base">Modelos entrenados</CardTitle>
              <CardDescription>
                Catálogo completo de modelos disponibles en el servidor.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={cleanupModels.isPending || models.length === 0}
                onClick={() => setConfirmCleanup(true)}
              >
                <Trash2 className="mr-2 h-3.5 w-3.5" />
                Limpiar sesiones incompletas
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={purgeModelsMutation.isPending || models.length === 0}
                onClick={() => setConfirmPurge(true)}
              >
                <Trash2 className="mr-2 h-3.5 w-3.5" />
                Limpiar todas las sesiones
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {modelsQuery.isLoading && <Skeleton className="h-24 w-full" />}
            {modelsQuery.isError && (
              <p className="text-sm text-destructive">
                No se pudo cargar el catálogo de modelos.
              </p>
            )}
            {modelsQuery.data && models.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Todavía no hay modelos entrenados.
              </p>
            )}
            {models.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nombre</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Tablas</TableHead>
                    <TableHead className="text-right">Filas</TableHead>
                    <TableHead className="text-right">Precisión</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {models.map((m) => (
                    <TableRow key={m.model_id}>
                      <TableCell>
                        <div className="space-y-0.5">
                          <p className="font-mono text-[10px] text-muted-foreground">
                            {m.model_id}
                          </p>
                          <EditableName
                            name={m.model_name || m.model_id}
                            existingNames={models.map(
                              (x) => x.model_name || x.model_id,
                            )}
                            onSave={(name) =>
                              renameModel.mutateAsync({ id: m.model_id, name })
                            }
                          />
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusBadgeVariant(m.status)}>
                          {m.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {m.tables || "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {m.train_size != null
                          ? m.train_size.toLocaleString()
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {m.accuracy != null
                          ? `${(m.accuracy * 100).toFixed(1)}%`
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex items-center justify-end gap-1">
                          {m.status === "completed" && (
                            <button
                              type="button"
                              aria-label="Ver informe"
                              onClick={() => openReport(m)}
                              className="rounded p-1 text-muted-foreground hover:bg-primary/10 hover:text-primary"
                            >
                              <FileText className="h-3.5 w-3.5" />
                            </button>
                          )}
                          {m.status === "in_progress" ? (
                            <button
                              type="button"
                              aria-label="Cancelar modelo"
                              disabled={cancelTraining.isPending}
                              onClick={() => cancelTraining.mutate(m.model_id)}
                              className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                            >
                              <XCircle className="h-3.5 w-3.5" />
                            </button>
                          ) : (
                            <button
                              type="button"
                              aria-label="Eliminar modelo"
                              disabled={deleteModel.isPending}
                              onClick={() => setConfirmDelete(m.model_id)}
                              className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>
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
        title="¿Eliminar modelo?"
        description="Se borrarán permanentemente la carpeta del modelo y todos sus artefactos. Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        onConfirm={() => {
          if (confirmDelete) deleteModel.mutate(confirmDelete);
          setConfirmDelete(null);
        }}
        onCancel={() => setConfirmDelete(null)}
      />
      <ConfirmDialog
        open={confirmCleanup}
        title="¿Limpiar modelos?"
        description="Se borrarán permanentemente las carpetas vacías y las ejecuciones huérfanas. Esta acción no se puede deshacer."
        confirmLabel="Limpiar"
        onConfirm={() => {
          cleanupModels.mutate();
          setConfirmCleanup(false);
        }}
        onCancel={() => setConfirmCleanup(false)}
      />
      <ConfirmDialog
        open={confirmPurge}
        title="¿Purgar todos los modelos?"
        description="Se eliminarán TODOS los modelos, incluidos los completados correctamente. Esta acción no se puede deshacer."
        confirmLabel="Purgar"
        onConfirm={() => {
          purgeModelsMutation.mutate();
          setConfirmPurge(false);
        }}
        onCancel={() => setConfirmPurge(false)}
      />
    </WizardShell>
  );
}
