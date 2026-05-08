// Generación — step 5 of the pipeline wizard.
//
// Picks a completed trained model and generates synthetic data from it.
// The model list comes from GET /models/ and we filter to status=completed
// so the user never tries to simulate from a broken/in-progress run. The
// active simulation id is remembered in localStorage so the next step
// (Auditoría) can pick it up.

"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import axios from "axios";
import { Play, Wand2, Download, SlidersHorizontal, Trash2, XCircle } from "lucide-react";
import {
  ConditionalGenerationDrawer,
  EMPTY_CONDITIONAL_CONFIG,
  buildConditionalPayload,
  isConditionalConfigActive,
  type ConditionalConfig,
} from "@/components/generation/conditional-config";
import { JobProgressPanel } from "@/components/jobs/job-progress";
import { EditableName } from "@/components/jobs/editable-name";
import { RulesBanner } from "@/components/config/rules-banner";
import {
  API_BASE_URL,
  api,
  type ModelSummary,
  type SimulationJob,
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
import { Input } from "@/components/ui/input";
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

const MODEL_STORAGE_KEY = "ends.pipeline.currentModelId";
const SIMULATION_STORAGE_KEY = "ends.pipeline.currentSimulationId";

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

export default function GeneracionPage() {
  const queryClient = useQueryClient();
  const [selectedModelId, setSelectedModelId] = useState<string>("");
  const [sampleSize, setSampleSize] = useState<string>("");
  const [syntheticDataFileFormat, setSyntheticDataFileFormat] =
    useState<string>("csv");
  const [simulationId, setSimulationId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [conditionalOpen, setConditionalOpen] = useState(false);
  const [conditionalConfig, setConditionalConfig] = useState<ConditionalConfig>(
    EMPTY_CONDITIONAL_CONFIG,
  );

  useEffect(() => {
    const stored = window.localStorage.getItem(SIMULATION_STORAGE_KEY);
    if (stored) setSimulationId(stored);
    const m = window.localStorage.getItem(MODEL_STORAGE_KEY);
    if (m) setSelectedModelId(m);
    setHydrated(true);
  }, []);

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const { data } = await api.get<ModelSummary[]>("/models/");
      return data;
    },
  });

  const completedModels = useMemo(
    () => (modelsQuery.data ?? []).filter((m) => m.status === "completed"),
    [modelsQuery.data],
  );

  // When models load, default the select to the last-used model if it is
  // still completed, otherwise the most recent completed one.
  useEffect(() => {
    if (!hydrated || completedModels.length === 0) return;
    if (
      selectedModelId &&
      completedModels.some((m) => m.model_id === selectedModelId)
    ) {
      return;
    }
    setSelectedModelId(completedModels[0].model_id);
  }, [hydrated, completedModels, selectedModelId]);

  const simulationsQuery = useQuery({
    queryKey: ["simulations"],
    queryFn: async () => {
      const { data } = await api.get<SimulationSummary[]>("/simulations/");
      return data;
    },
  });

  const activeSimQuery = useQuery({
    queryKey: ["simulation", simulationId],
    enabled: !!simulationId,
    queryFn: async () => {
      const { data } = await api.get<SimulationSummary>(
        `/simulations/${simulationId}`,
      );
      return data;
    },
    refetchInterval: (query) =>
      query.state.data?.status === "in_progress" ? 2000 : false,
  });

  const activeStatus = activeSimQuery.data?.status;
  useEffect(() => {
    if (activeStatus && activeStatus !== "in_progress") {
      queryClient.invalidateQueries({ queryKey: ["simulations"] });
    }
  }, [activeStatus, queryClient]);

  const startSim = useMutation({
    mutationFn: async () => {
      if (!selectedModelId) throw new Error("No hay modelo seleccionado.");
      const body: Record<string, unknown> = { model_id: selectedModelId };
      const n = Number.parseInt(sampleSize, 10);
      if (Number.isFinite(n) && n > 0) body.sample_size = n;
      body.synthetic_data_file_format = syntheticDataFileFormat;
      const conditional = buildConditionalPayload(conditionalConfig);
      if (conditional) body.conditional = conditional;
      const { data } = await api.post<SimulationJob>("/simulations/", body);
      return data;
    },
    onSuccess: (job) => {
      window.localStorage.setItem(SIMULATION_STORAGE_KEY, job.simulation_id);
      setSimulationId(job.simulation_id);
      toast.success(`Generación iniciada: ${job.simulation_id}`);
      queryClient.invalidateQueries({ queryKey: ["simulations"] });
    },
    onError: (err) => {
      toast.error(`No se pudo iniciar la generación: ${extractDetail(err)}`);
    },
  });

  const cancelSim = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post(`/simulations/${id}/cancel`);
      return data;
    },
    onSuccess: () => {
      toast.success("Cancelación solicitada");
      queryClient.invalidateQueries({ queryKey: ["simulation", simulationId] });
      queryClient.invalidateQueries({ queryKey: ["simulations"] });
    },
    onError: (err) => {
      toast.error(`No se pudo cancelar: ${extractDetail(err)}`);
    },
  });

  const deleteSimulation = useMutation({
    mutationFn: async (id: string) => {
      await api.delete(`/simulations/${id}`);
    },
    onSuccess: (_data, id) => {
      toast.success(`Generación eliminada: ${id}`);
      if (simulationId === id) {
        setSimulationId(null);
        window.localStorage.removeItem(SIMULATION_STORAGE_KEY);
      }
      queryClient.invalidateQueries({ queryKey: ["simulations"] });
    },
    onError: (err) => {
      toast.error(`No se pudo eliminar: ${extractDetail(err)}`);
    },
  });

  const cleanupSimulations = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete("/simulations/cleanup");
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(n > 0 ? `${n} generación(es) limpiada(s)` : "Nada que limpiar");
      queryClient.invalidateQueries({ queryKey: ["simulations"] });
    },
    onError: (err) => {
      toast.error(`Error en limpieza: ${extractDetail(err)}`);
    },
  });

  const purgeSimulationsMutation = useMutation({
    mutationFn: async () => {
      const { data } = await api.delete("/simulations/purge");
      return data as { deleted_ids: string[] };
    },
    onSuccess: (result) => {
      const n = result.deleted_ids?.length ?? 0;
      toast.success(`${n} generación(es) eliminada(s)`);
      queryClient.invalidateQueries({ queryKey: ["simulations"] });
    },
    onError: (err) => {
      toast.error(`Error al purgar: ${extractDetail(err)}`);
    },
  });

  const renameSimulation = useMutation({
    mutationFn: async ({ id, name }: { id: string; name: string }) => {
      await api.patch(`/simulations/${id}/name`, { name });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["simulations"] });
    },
  });

  const simulations = simulationsQuery.data ?? [];
  const hasCompleted = useMemo(
    () =>
      simulations.some((s) => s.status === "completed") ||
      activeSimQuery.data?.status === "completed",
    [simulations, activeSimQuery.data],
  );
  const isRunning = activeSimQuery.data?.status === "in_progress";

  return (
    <WizardShell currentSlug="generacion" canAdvance={hasCompleted}>
      <div className="mx-auto max-w-5xl space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Generación</h1>
            <p className="text-sm text-muted-foreground">
              Genera datos sintéticos a partir de un modelo entrenado.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setConditionalOpen(true)}
          >
            <SlidersHorizontal className="mr-2 h-4 w-4" />
            Configurar generación condicional
            {isConditionalConfigActive(conditionalConfig) && (
              <Badge variant="secondary" className="ml-2">
                activa
              </Badge>
            )}
          </Button>
        </div>

        <ConditionalGenerationDrawer
          open={conditionalOpen}
          modelId={selectedModelId}
          config={conditionalConfig}
          onChange={setConditionalConfig}
          onClose={() => setConditionalOpen(false)}
        />

        <RulesBanner />

        <div className="grid gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="items-center text-center">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/10 text-primary">
                <Wand2 className="h-5 w-5" />
              </div>
              <CardTitle>Nueva generación</CardTitle>
              <CardDescription>
                Escoge un modelo completado y el nº de filas a simular.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-1">
                <Label htmlFor="model-select">Modelo</Label>
                {modelsQuery.isLoading ? (
                  <Skeleton className="h-9 w-full" />
                ) : completedModels.length === 0 ? (
                  <p className="text-sm text-destructive">
                    No hay modelos entrenados completados. Vuelve al paso{" "}
                    <b>Entrenamiento</b>.
                  </p>
                ) : (
                  <select
                    id="model-select"
                    value={selectedModelId}
                    onChange={(e) => setSelectedModelId(e.target.value)}
                    className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs"
                  >
                    {completedModels.map((m) => (
                      <option key={m.model_id} value={m.model_id}>
                        {m.model_name || m.model_id}
                        {m.tables ? ` · ${m.tables}` : ""}
                        {m.train_size != null
                          ? ` · ${m.train_size.toLocaleString()} filas`
                          : ""}
                      </option>
                    ))}
                  </select>
                )}
              </div>

              <div className="space-y-1">
                <Label htmlFor="sample-size">Tamaño de muestra</Label>
                <Input
                  id="sample-size"
                  type="number"
                  min={1}
                  inputMode="numeric"
                  placeholder="Por defecto del modelo"
                  value={sampleSize}
                  onChange={(e) => setSampleSize(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">
                  Déjalo vacío para usar el tamaño por defecto del modelo.
                </p>
              </div>

              <div className="space-y-1">
                <Label htmlFor="synthetic-format">Formato de salida</Label>
                <select
                  id="synthetic-format"
                  value={syntheticDataFileFormat}
                  onChange={(e) => setSyntheticDataFileFormat(e.target.value)}
                  className="w-full rounded-md border bg-background px-3 py-2 text-sm"
                >
                  <option value="csv">CSV</option>
                  <option value="parquet">Parquet</option>
                </select>
                <p className="text-xs text-muted-foreground">
                  La auditoría puede leer tanto CSV como Parquet.
                </p>
              </div>

              <Button
                type="button"
                className="w-full"
                disabled={!selectedModelId || startSim.isPending || isRunning}
                onClick={() => startSim.mutate()}
              >
                <Play className="mr-2 h-4 w-4" />
                {startSim.isPending
                  ? "Iniciando…"
                  : isRunning
                    ? "Generación en curso…"
                    : "Iniciar generación"}
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Generación actual</CardTitle>
              <CardDescription>
                Estado de la última generación iniciada.
                {simulationId && (
                  <span
                    className="ml-2 font-mono text-xs"
                    suppressHydrationWarning
                  >
                    id: {simulationId}
                  </span>
                )}
              </CardDescription>
              {activeSimQuery.data && (
                <EditableName
                  name={activeSimQuery.data.simulation_name || activeSimQuery.data.simulation_id}
                  existingNames={simulations.map((x) => x.simulation_name || x.simulation_id)}
                  onSave={(name) =>
                    renameSimulation.mutateAsync({ id: activeSimQuery.data!.simulation_id, name })
                  }
                />
              )}
            </CardHeader>
            <CardContent className="space-y-3">
              {!simulationId && (
                <p className="text-sm text-muted-foreground">
                  Aún no has iniciado una generación en esta sesión.
                </p>
              )}
              {simulationId && activeSimQuery.isLoading && (
                <Skeleton className="h-20 w-full" />
              )}
              {activeSimQuery.data && (
                <div className="space-y-3 text-sm">
                  <JobProgressPanel
                    status={activeSimQuery.data.status}
                    progress={activeSimQuery.data.progress}
                    timestamp={activeSimQuery.data.timestamp}
                  />
                  {activeSimQuery.data.model_id && (
                    <p>
                      <span className="text-muted-foreground">Modelo: </span>
                      <span className="font-mono text-xs">
                        {activeSimQuery.data.model_id}
                      </span>
                    </p>
                  )}
                  {activeSimQuery.data.sample_size != null && (
                    <p>
                      <span className="text-muted-foreground">Filas: </span>
                      <span className="tabular-nums">
                        {activeSimQuery.data.sample_size.toLocaleString()}
                      </span>
                    </p>
                  )}
                  <div className="flex flex-wrap gap-2 pt-1">
                    {isRunning && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        disabled={cancelSim.isPending}
                        onClick={() =>
                          simulationId && cancelSim.mutate(simulationId)
                        }
                      >
                        Cancelar
                      </Button>
                    )}
                    {activeSimQuery.data.status === "completed" && (
                      <a
                        href={`${API_BASE_URL}/simulations/${simulationId}/download/synthetic-dataset`}
                      >
                        <Button type="button" size="sm" variant="outline">
                          <Download className="mr-2 h-4 w-4" />
                          Descargar datos sintéticos
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
              <CardTitle className="text-base">Generaciones</CardTitle>
              <CardDescription>
                Catálogo completo de generaciones en el servidor.
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={cleanupSimulations.isPending || simulations.length === 0}
                onClick={() => setConfirmCleanup(true)}
              >
                <Trash2 className="mr-2 h-3.5 w-3.5" />
                Limpiar sesiones incompletas
              </Button>
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={purgeSimulationsMutation.isPending || simulations.length === 0}
                onClick={() => setConfirmPurge(true)}
              >
                <Trash2 className="mr-2 h-3.5 w-3.5" />
                Limpiar todas las sesiones
              </Button>
            </div>
          </CardHeader>
          <CardContent>
            {simulationsQuery.isLoading && <Skeleton className="h-24 w-full" />}
            {simulationsQuery.isError && (
              <p className="text-sm text-destructive">
                No se pudo cargar el catálogo de generaciones.
              </p>
            )}
            {simulationsQuery.data && simulations.length === 0 && (
              <p className="text-sm text-muted-foreground">
                Todavía no hay generaciones.
              </p>
            )}
            {simulations.length > 0 && (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nombre</TableHead>
                    <TableHead>Estado</TableHead>
                    <TableHead>Modelo</TableHead>
                    <TableHead className="text-right">Tamaño</TableHead>
                    <TableHead />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {simulations.map((s) => (
                    <TableRow key={s.simulation_id}>
                      <TableCell>
                        <div className="space-y-0.5">
                          <p className="font-mono text-[10px] text-muted-foreground">
                            {s.simulation_id}
                          </p>
                          <EditableName
                            name={s.simulation_name || s.simulation_id}
                            existingNames={simulations.map(
                              (x) => x.simulation_name || x.simulation_id,
                            )}
                            onSave={(name) =>
                              renameSimulation.mutateAsync({
                                id: s.simulation_id,
                                name,
                              })
                            }
                          />
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge variant={statusBadgeVariant(s.status)}>
                          {s.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {s.model_id ?? "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {s.sample_size != null
                          ? s.sample_size.toLocaleString()
                          : "—"}
                      </TableCell>
                      <TableCell className="text-right">
                        {s.status === "in_progress" ? (
                          <button
                            type="button"
                            aria-label="Cancelar generación"
                            disabled={cancelSim.isPending}
                            onClick={() => cancelSim.mutate(s.simulation_id)}
                            className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                          >
                            <XCircle className="h-3.5 w-3.5" />
                          </button>
                        ) : (
                          <button
                            type="button"
                            aria-label="Eliminar generación"
                            disabled={deleteSimulation.isPending}
                            onClick={() => setConfirmDelete(s.simulation_id)}
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
        title="¿Eliminar generación?"
        description="Se borrarán permanentemente la carpeta de la generación y todos sus datos sintéticos. Esta acción no se puede deshacer."
        confirmLabel="Eliminar"
        onConfirm={() => {
          if (confirmDelete) deleteSimulation.mutate(confirmDelete);
          setConfirmDelete(null);
        }}
        onCancel={() => setConfirmDelete(null)}
      />
      <ConfirmDialog
        open={confirmCleanup}
        title="¿Limpiar generaciones?"
        description="Se borrarán permanentemente las carpetas vacías y las ejecuciones huérfanas. Esta acción no se puede deshacer."
        confirmLabel="Limpiar"
        onConfirm={() => {
          cleanupSimulations.mutate();
          setConfirmCleanup(false);
        }}
        onCancel={() => setConfirmCleanup(false)}
      />
      <ConfirmDialog
        open={confirmPurge}
        title="¿Purgar todas las generaciones?"
        description="Se eliminarán TODAS las generaciones, incluidas las completadas correctamente. Esta acción no se puede deshacer."
        confirmLabel="Purgar"
        onConfirm={() => {
          purgeSimulationsMutation.mutate();
          setConfirmPurge(false);
        }}
        onCancel={() => setConfirmPurge(false)}
      />
    </WizardShell>
  );
}
