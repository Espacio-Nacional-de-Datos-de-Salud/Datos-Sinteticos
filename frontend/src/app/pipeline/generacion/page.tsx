// Generación — step 5 of the pipeline wizard.
//
// Picks a completed trained model and generates synthetic data from it.
// The model list comes from GET /models/ and we filter to status=completed
// so the user never tries to simulate from a broken/in-progress run. The
// active simulation id is remembered in localStorage so the next step
// (Auditoría) can pick it up.
//
// Shared lifecycle wiring lives under @/components/pipeline-step. The
// kind-specific bits owned here: the sample-size + format form fields, the
// conditional-generation drawer, and the per-row metadata in the active
// status card and history table.

"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Play, Trash2, Wand2, XCircle } from "lucide-react";

import {
  ConditionalConfigPanel,
  EMPTY_CONDITIONAL_CONFIG,
  buildConditionalPayload,
  type ConditionalConfig,
} from "@/components/generation/conditional-config";
import { EditableName } from "@/components/jobs/editable-name";
import { ActiveJobCard } from "@/components/pipeline-step/active-job-card";
import { HistoryCard, type HistoryColumn } from "@/components/pipeline-step/history-card";
import { useArtifactLifecycle } from "@/components/pipeline-step/use-artifact-lifecycle";
import { useUpstreamSelection } from "@/components/pipeline-step/use-upstream-selection";
import { WizardConfirmDialogs } from "@/components/pipeline-step/wizard-confirm-dialogs";
import { RulesBanner } from "@/components/config/rules-banner";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  API_BASE_URL,
  type ModelSummary,
  type SimulationSummary,
} from "@/lib/api";
import { statusBadgeVariant } from "@/lib/job-status";
import { STORAGE_KEYS } from "@/lib/storage-keys";

type StartInput = {
  model_id: string;
  sampleSize: string;
  syntheticDataFileFormat: string;
  conditional: ConditionalConfig;
};

export default function GeneracionPage() {
  const [sampleSize, setSampleSize] = useState<string>("");
  const [syntheticDataFileFormat, setSyntheticDataFileFormat] = useState<string>("csv");
  const [conditionalConfig, setConditionalConfig] = useState<ConditionalConfig>(
    EMPTY_CONDITIONAL_CONFIG,
  );
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);

  const lc = useArtifactLifecycle<SimulationSummary, StartInput>({
    apiPath: "/simulations",
    listKey: "simulations",
    itemKey: "simulation",
    storageKey: STORAGE_KEYS.simulation,
    idField: "simulation_id",
    buildStartBody: (input) => {
      const body: Record<string, unknown> = { model_id: input.model_id };
      const n = Number.parseInt(input.sampleSize, 10);
      if (Number.isFinite(n) && n > 0) body.sample_size = n;
      body.synthetic_data_file_format = input.syntheticDataFileFormat;
      const conditional = buildConditionalPayload(input.conditional);
      if (conditional) body.conditional = conditional;
      return body;
    },
    labels: {
      startedToast: (id) => `Generación iniciada: ${id}`,
      startErrorPrefix: "No se pudo iniciar la generación",
      cancelErrorPrefix: "No se pudo cancelar",
      deletedToast: (id) => `Generación eliminada: ${id}`,
      deleteErrorPrefix: "No se pudo eliminar",
      cleanupOkToast: (n) => `${n} generación(es) limpiada(s)`,
      cleanupNoopToast: "Nada que limpiar",
      cleanupErrorPrefix: "Error en limpieza",
      purgeOkToast: (n) => `${n} generación(es) eliminada(s)`,
      purgeErrorPrefix: "Error al purgar",
    },
  });

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const { data } = await api.get<ModelSummary[]>("/models/");
      return data;
    },
  });
  const completedModels = (modelsQuery.data ?? []).filter(
    (m) => m.status === "completed",
  );
  const { selectedId: selectedModelId, setSelectedId: setSelectedModelId } =
    useUpstreamSelection(completedModels, "model_id", STORAGE_KEYS.model);

  // Outside the Entrenamiento page itself we always show the upstream model
  // by its functional name, never its id — same rule applies wherever a step
  // references an artefact produced by a previous step.
  const labelForModelId = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of modelsQuery.data ?? []) {
      map.set(m.model_id, m.model_name || m.model_id);
    }
    return (id: string | null | undefined): string =>
      id ? map.get(id) ?? id : "—";
  }, [modelsQuery.data]);

  const columns: HistoryColumn<SimulationSummary>[] = [
    {
      key: "name",
      header: "Nombre",
      width: "28%",
      render: (s) => (
        <div className="space-y-0.5">
          <p
            className="truncate font-mono text-[10px] text-muted-foreground"
            title={s.simulation_id}
          >
            {s.simulation_id}
          </p>
          <EditableName
            name={s.simulation_name || s.simulation_id}
            existingNames={lc.list.map((x) => x.simulation_name || x.simulation_id)}
            onSave={(name) => lc.rename(s.simulation_id, name)}
          />
        </div>
      ),
    },
    {
      key: "status",
      header: "Estado",
      width: "12%",
      render: (s) => <Badge variant={statusBadgeVariant(s.status)}>{s.status}</Badge>,
    },
    {
      key: "model",
      header: "Modelo",
      width: "30%",
      render: (s) => (
        <span className="block truncate font-mono text-xs" title={s.model_id ?? ""}>
          {labelForModelId(s.model_id)}
        </span>
      ),
    },
    {
      key: "size",
      header: "Tamaño",
      width: "18%",
      align: "right",
      render: (s) => (
        <span className="tabular-nums">
          {s.sample_size != null ? s.sample_size.toLocaleString() : "—"}
        </span>
      ),
    },
  ];

  return (
    <WizardShell currentSlug="generacion" canAdvance={lc.hasCompleted}>
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Generación</h1>
          <p className="text-sm text-muted-foreground">
            Genera datos sintéticos a partir de un modelo entrenado.
          </p>
        </div>

        <WorkflowGroup label="Preparación">
          <RulesBanner />

          <Card>
            <CardContent className="grid gap-3 p-4 md:grid-cols-[auto_1fr_180px_140px_auto] md:items-end">
              <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
                <Wand2 className="h-5 w-5" />
              </div>
              <div className="min-w-0 space-y-1">
                <Label htmlFor="model-select">Modelo</Label>
                {modelsQuery.isLoading ? (
                  <Skeleton className="h-9 w-full" />
                ) : completedModels.length === 0 ? (
                  <p className="text-sm text-destructive">
                    No hay modelos completados. Vuelve a <b>Entrenamiento</b>.
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
                  placeholder="Por defecto"
                  value={sampleSize}
                  onChange={(e) => setSampleSize(e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label htmlFor="synthetic-format">Formato</Label>
                <select
                  id="synthetic-format"
                  value={syntheticDataFileFormat}
                  onChange={(e) => setSyntheticDataFileFormat(e.target.value)}
                  className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                >
                  <option value="csv">CSV</option>
                  <option value="parquet">Parquet</option>
                </select>
              </div>
              <Button
                type="button"
                disabled={!selectedModelId || lc.isStarting || lc.isRunning}
                onClick={() =>
                  lc.start({
                    model_id: selectedModelId,
                    sampleSize,
                    syntheticDataFileFormat,
                    conditional: conditionalConfig,
                  })
                }
              >
                <Play className="mr-2 h-4 w-4" />
                {lc.isStarting
                  ? "Iniciando…"
                  : lc.isRunning
                    ? "En curso…"
                    : "Iniciar generación"}
              </Button>
            </CardContent>
          </Card>

          <ConditionalConfigPanel
            modelId={selectedModelId}
            config={conditionalConfig}
            onChange={setConditionalConfig}
          />
        </WorkflowGroup>

        <WorkflowGroup label="Resultados">
          <ActiveJobCard
            id={lc.activeId}
            title="Generación actual"
            description="Estado de la última generación iniciada."
            isLoading={lc.activeQuery.isLoading}
            isError={lc.activeQuery.isError}
            errorMessage="No se pudo cargar el estado de la generación."
            active={lc.active}
            activeName={lc.active?.simulation_name || lc.active?.simulation_id}
            existingNames={lc.list.map((x) => x.simulation_name || x.simulation_id)}
            onRename={
              lc.active
                ? (name) => lc.rename(lc.active!.simulation_id, name)
                : undefined
            }
            metadata={
              lc.active && (
                <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted-foreground">
                  {lc.active.model_id && (
                    <span>
                      Modelo:{" "}
                      <span className="font-mono" title={lc.active.model_id}>
                        {labelForModelId(lc.active.model_id)}
                      </span>
                    </span>
                  )}
                  {lc.active.sample_size != null && (
                    <span className="tabular-nums">
                      Filas: {lc.active.sample_size.toLocaleString()}
                    </span>
                  )}
                </div>
              )
            }
            actions={
              <>
                {lc.isRunning && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    disabled={lc.isCancelling}
                    onClick={() => lc.activeId && lc.cancel(lc.activeId)}
                  >
                    Cancelar
                  </Button>
                )}
                {lc.active?.status === "completed" && lc.activeId && (
                  <a
                    href={`${API_BASE_URL}/simulations/${lc.activeId}/download/synthetic-dataset`}
                  >
                    <Button type="button" size="sm" variant="outline">
                      <Download className="mr-2 h-4 w-4" />
                      Descargar datos sintéticos
                    </Button>
                  </a>
                )}
              </>
            }
          />
        </WorkflowGroup>

        <WorkflowGroup label="Historial">
          <HistoryCard
            title="Generaciones"
            description="Catálogo completo de generaciones en el servidor."
            items={lc.list}
            isLoading={lc.listQuery.isLoading}
            isError={lc.listQuery.isError}
            errorMessage="No se pudo cargar el catálogo de generaciones."
            emptyMessage="Todavía no hay generaciones."
            columns={columns}
            actionsWidth="12%"
            collapseLabel="generaciones"
            onCleanup={() => setConfirmCleanup(true)}
            onPurge={() => setConfirmPurge(true)}
            isCleaning={lc.isCleaning}
            isPurging={lc.isPurging}
            actionsCell={(s) =>
              s.status === "in_progress" ? (
                <button
                  type="button"
                  aria-label="Cancelar generación"
                  disabled={lc.isCancelling}
                  onClick={() => lc.cancel(s.simulation_id)}
                  className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                >
                  <XCircle className="h-3.5 w-3.5" />
                </button>
              ) : (
                <button
                  type="button"
                  aria-label="Eliminar generación"
                  disabled={lc.isDeleting}
                  onClick={() => setConfirmDeleteId(s.simulation_id)}
                  className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              )
            }
          />
        </WorkflowGroup>
      </div>

      <WizardConfirmDialogs
        texts={{
          delete: {
            title: "¿Eliminar generación?",
            description:
              "Se borrarán permanentemente la carpeta de la generación y todos sus datos sintéticos. Esta acción no se puede deshacer.",
          },
          cleanup: {
            title: "¿Limpiar generaciones?",
            description:
              "Se borrarán permanentemente las carpetas vacías y las ejecuciones huérfanas. Esta acción no se puede deshacer.",
          },
          purge: {
            title: "¿Purgar todas las generaciones?",
            description:
              "Se eliminarán TODAS las generaciones, incluidas las completadas correctamente. Esta acción no se puede deshacer.",
          },
        }}
        confirmDeleteId={confirmDeleteId}
        setConfirmDeleteId={setConfirmDeleteId}
        onDelete={lc.remove}
        confirmCleanup={confirmCleanup}
        setConfirmCleanup={setConfirmCleanup}
        onCleanup={lc.cleanup}
        confirmPurge={confirmPurge}
        setConfirmPurge={setConfirmPurge}
        onPurge={lc.purge}
      />
    </WizardShell>
  );
}
