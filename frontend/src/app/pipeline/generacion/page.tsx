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
import { Tooltip } from "@/components/ui/tooltip";

import { DatasetPreviewCard } from "@/components/dataset/dataset-preview-card";
import {
  ConditionalConfigPanel,
  EMPTY_CONDITIONAL_CONFIG,
  buildConditionalPayload,
  type ConditionalConfig,
} from "@/components/generation/conditional-config";
import { TableSampleSizesEditor } from "@/components/generation/table-sample-sizes-editor";
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
  type FilePreview,
  type ModelSummary,
  type SimulationSummary,
} from "@/lib/api";
import { statusBadgeVariant, translateStatus } from "@/lib/job-status";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { cn } from "@/lib/utils";

type StartInput = {
  model_id: string;
  sampleSize: string;
  tableSampleSizes: Record<string, number> | null;
  syntheticDataFileFormat: string;
  conditional: ConditionalConfig;
};

const GENERACION_OUTLINE = [
  { id: "preparacion", label: "Preparación", level: 1 },
  { id: "reglas-preprocesamiento", label: "Reglas de preprocesamiento", level: 2 },
  { id: "nueva-generacion", label: "Nueva generación", level: 2 },
  { id: "condiciones", label: "Configuración condicional", level: 2 },
  { id: "ejecutar-generacion", label: "Ejecutar generación", level: 2 },
  { id: "resultados", label: "Resultados", level: 1 },
  { id: "generacion-actual", label: "Generación actual", level: 2 },
  { id: "datos-sinteticos", label: "Datos sintéticos", level: 2 },
  { id: "historial", label: "Historial", level: 1 },
  { id: "generaciones", label: "Generaciones", level: 2 },
] as const;

export default function GeneracionPage() {
  const [sampleSize, setSampleSize] = useState<string>("");
  const [syntheticDataFileFormat, setSyntheticDataFileFormat] = useState<string>("csv");
  const [tableSampleSizes, setTableSampleSizes] = useState<Record<string, number> | null>(null);
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
      if (input.tableSampleSizes && Object.keys(input.tableSampleSizes).length > 0) {
        body.table_sample_sizes = input.tableSampleSizes;
      } else {
        const n = Number.parseInt(input.sampleSize, 10);
        if (Number.isFinite(n) && n > 0) body.sample_size = n;
      }
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

  const selectedModel = completedModels.find((m) => m.model_id === selectedModelId);
  const originalSizes = selectedModel?.training_table_sizes || {};
  const subjectTables = selectedModel?.subject_tables || [];


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
      render: (s) => (
        <Badge
          variant={statusBadgeVariant(s.status)}
          className={cn(s.status === "completed" && "!bg-blue-500/20 !text-blue-400")}
        >
          {translateStatus(s.status)}
        </Badge>
      ),
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
    <WizardShell currentSlug="generacion" canAdvance={lc.hasCompleted} outline={GENERACION_OUTLINE}>
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Generación</h1>
          <p className="text-sm text-muted-foreground">
            Genera datos sintéticos a partir de un modelo entrenado.
          </p>
        </div>

        <WorkflowGroup id="preparacion" label="Preparación" defaultOpen className="scroll-mt-24">
          <div id="reglas-preprocesamiento" className="scroll-mt-24">
            <RulesBanner />
          </div>

          <div id="nueva-generacion" className="scroll-mt-24">
            <Card>
              <CardContent className="flex flex-col gap-4 p-4">
              <div className="grid gap-3 md:grid-cols-[auto_1fr_140px_auto] md:items-end">
              <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
                <Wand2 className="h-5 w-5" />
              </div>
              <div className="min-w-0 space-y-1">
                <div className="flex items-center gap-2">
                  <Label htmlFor="model-select">Modelo</Label>
                  <Tooltip content="Selecciona el modelo entrenado que será usado para generar los datos sintéticos. Puede haber varios modelos disponibles si has realizado múltiples entrenamientos." />
                </div>
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
                <div className="flex items-center gap-2">
                  <Label htmlFor="synthetic-format">Formato</Label>
                  <Tooltip content="Selecciona el formato en el que deseas descargar los datos sintéticos. CSV es universal y fácil de procesar; Parquet es más compacto y eficiente." />
                </div>
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
              </div>

              {selectedModelId && Object.keys(originalSizes).length > 0 && (
                <TableSampleSizesEditor
                  originalSizes={originalSizes}
                  subjectTables={subjectTables}
                  value={tableSampleSizes}
                  onChange={setTableSampleSizes}
                />
              )}
            </CardContent>
            </Card>
          </div>

          <div id="condiciones" className="scroll-mt-24">
            <ConditionalConfigPanel
            modelId={selectedModelId}
            config={conditionalConfig}
            onChange={setConditionalConfig}
            />
          </div>

          <div id="ejecutar-generacion" className="scroll-mt-24">
            <Card>
              <CardContent className="flex flex-col gap-2 p-4 md:flex-row md:items-center">
                <div className="flex-1 flex items-start gap-2">
                  <p className="text-sm text-muted-foreground pt-0.5">
                    Configura los parámetros de generación y haz clic en ejecutar.
                  </p>
                  <Tooltip content="Se generará un nuevo dataset sintético basado en el modelo y los parámetros que hayas configurado. El dataset estará disponible para descargar una vez que la generación se complete." side="left" />
                </div>
                <Button
                  type="button"
                  disabled={!selectedModelId || lc.isStarting || lc.isRunning}
                  onClick={() =>
                    lc.start({
                      model_id: selectedModelId,
                      sampleSize,
                      tableSampleSizes,
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
          </div>
        </WorkflowGroup>

        <WorkflowGroup id="resultados" label="Resultados" className="scroll-mt-24">
          <div id="generacion-actual" className="scroll-mt-24">
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
          </div>

          {lc.active?.status === "completed" && lc.activeId && (
            <div id="datos-sinteticos" className="scroll-mt-24">
              <SyntheticDataCard simulationId={lc.activeId} />
            </div>
          )}
        </WorkflowGroup>

        <WorkflowGroup id="historial" label="Historial" className="scroll-mt-24">
          <div id="generaciones" className="scroll-mt-24">
            <HistoryCard
            title="Generaciones"
            description="Catálogo completo de generaciones en el servidor. Haz click para cargar una generación pasada y ver sus datos sintéticos."
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
            activeId={lc.activeId}
            getRowId={(s) => s.simulation_id}
            onSelect={(id) => lc.setActiveId(id)}
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
          </div>
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

function SyntheticDataCard({ simulationId }: { simulationId: string }) {
  const tablesQuery = useQuery({
    queryKey: ["simulations", simulationId, "synthetic", "tables"],
    queryFn: async () => {
      const { data } = await api.get<string[]>(
        `/simulations/${simulationId}/synthetic`,
      );
      return data;
    },
  });

  return (
    <DatasetPreviewCard
      title="Datos sintéticos"
      description="Vista previa del dataset sintético generado por esta simulación."
      cacheKey={`simulations/${simulationId}/synthetic/preview`}
      tables={tablesQuery.data ?? []}
      isLoadingTables={tablesQuery.isLoading}
      isError={tablesQuery.isError}
      fetcher={async (table, params) => {
        const { data } = await api.get<FilePreview>(
          `/simulations/${simulationId}/synthetic/${encodeURIComponent(table)}`,
          { params },
        );
        return data;
      }}
      downloadHref={`/simulations/${simulationId}/download/synthetic-dataset`}
      emptyMessage="No hay datos sintéticos disponibles para esta generación."
    />
  );
}
