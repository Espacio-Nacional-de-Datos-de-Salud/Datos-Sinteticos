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

import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Play, Trash2, Wand2, XCircle, AlertTriangle } from "lucide-react";
import { Tooltip } from "@/components/ui/tooltip";
import { NativeSelect } from "@/components/ui/native-select";
import { getGeneracionInstructions } from "@/components/generation/instructions-content";
import yaml from "js-yaml";
import { getBrcRulesSnapshot } from "@/lib/brc";

import { DatasetPreviewCard } from "@/components/dataset/dataset-preview-card";
import {
  ConditionalConfigPanel,
  EMPTY_CONDITIONAL_CONFIG,
  buildConditionalPayload,
  type ConditionalConfig,
} from "@/components/generation/conditional-config";
import {
  TableSampleSizesEditor,
  type FixedTarget,
} from "@/components/generation/table-sample-sizes-editor";
import { SimulationSchemaDiagram } from "@/components/generation/simulation-schema-diagram";
import { EditableName } from "@/components/jobs/editable-name";
import { ActiveRunName } from "@/components/jobs/active-run-name";
import { ActiveJobCard } from "@/components/pipeline-step/active-job-card";
import { TimeProfilingPanel } from "@/components/pipeline-step/time-profiling-panel";
import { DownloadMenu } from "@/components/pipeline-step/download-menu";
import { HistoryCard, type HistoryColumn } from "@/components/pipeline-step/history-card";
import { useConfirmSelect } from "@/components/pipeline-step/use-confirm-select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useArtifactLifecycle } from "@/components/pipeline-step/use-artifact-lifecycle";
import { useUpstreamSelection } from "@/components/pipeline-step/use-upstream-selection";
import { WizardConfirmDialogs } from "@/components/pipeline-step/wizard-confirm-dialogs";
import { RulesBanner } from "@/components/config/rules-banner";
import { SanityReportCard } from "@/components/generation/sanity-report-card";
import { RejectionSamplingCard } from "@/components/generation/rejection-sampling-card";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WizardBanner, WIZARD_BANNER_HEIGHT } from "@/components/layout/wizard-banner";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { NamePromptDialog } from "@/components/ui/name-prompt-dialog";
import { StatusBadge } from "@/components/jobs/status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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
import { toast } from "sonner";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { cn } from "@/lib/utils";
import { useManualOpen } from "@/lib/use-manual-open";

type StartInput = {
  model_id: string;
  sampleSize: string;
  tableSampleSizes: Record<string, number> | null;
  fixedTarget: FixedTarget | null;
  maxAttempts: string;
  overgenerateFactor: string;
  hasRejectionSampling: boolean;
  syntheticDataFileFormat: string;
  conditional: ConditionalConfig;
};

const GENERACION_OUTLINE = [
  { id: "preparacion", label: "Preparación", level: 1 },
  { id: "nueva-generacion", label: "Selección de modelo", level: 2 },
  { id: "reglas-preprocesamiento", label: "Reglas de negocio", level: 2 },
  { id: "configuracion-volumen", label: "Configuración de volumen", level: 2 },
  { id: "condiciones", label: "Condicionar la generación", level: 2 },
  { id: "ejecutar-generacion", label: "Ejecutar generación", level: 2 },
  { id: "resultados", label: "Resultados", level: 1 },
  { id: "generacion-actual", label: "Generación actual", level: 2 },
  { id: "datos-sinteticos", label: "Datos sintéticos", level: 2 },
  { id: "historial", label: "Historial", level: 1 },
  { id: "generaciones", label: "Generaciones", level: 2 },
] as const;

export default function GeneracionPage() {
  const generacionInstructions = useMemo(
    () => getGeneracionInstructions(),
    [],
  );
  const [sampleSize, setSampleSize] = useState<string>("");
  const [syntheticDataFileFormat, setSyntheticDataFileFormat] = useState<string>("csv");
  const [tableSampleSizes, setTableSampleSizes] = useState<Record<string, number> | null>(null);
  const [fixedTarget, setFixedTarget] = useState<FixedTarget | null>(null);
  // Sampling knobs (only sent when oversampling can occur). Defaults favor
  // overgeneration over retries: each retry restarts the engine (slow), while a
  // bigger batch is nearly free.
  const [maxAttempts, setMaxAttempts] = useState<string>("2");
  const [overgenerateFactor, setOvergenerateFactor] = useState<string>("3");
  const [conditionalConfig, setConditionalConfig] = useState<ConditionalConfig>(
    EMPTY_CONDITIONAL_CONFIG,
  );
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [startDialogOpen, setStartDialogOpen] = useState(false);

  // Instructions manual state — shared across pipeline pages via localStorage
  // so the panel stays open as the user navigates between steps.
  const [instructionsOpen, setInstructionsOpen] = useManualOpen();
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    preparacion: true,
    resultados: true,
    historial: false,
  });
  const scrollToSection = useCallback((id: string) => {
    requestAnimationFrame(() =>
      requestAnimationFrame(() => {
        document
          .getElementById(id)
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      }),
    );
  }, []);
  const toggleSection = useCallback(
    (id: string) =>
      setOpenSections((p) => {
        const next = !(p[id] ?? true);
        if (next) scrollToSection(id);
        return { ...p, [id]: next };
      }),
    [scrollToSection],
  );
  const setSectionOpen = useCallback(
    (id: string, open: boolean) => {
      if (open) scrollToSection(id);
      setOpenSections((p) => ({ ...p, [id]: open }));
    },
    [scrollToSection],
  );
  const [helpReserve, setHelpReserve] = useState<Record<string, number>>({});
  const handleHelpMeasure = useCallback(
    (reserve: Record<string, number>) => setHelpReserve(reserve),
    [],
  );
  const helpGap = (id: string): React.CSSProperties | undefined =>
    instructionsOpen && (openSections[id] ?? true) && helpReserve[id]
      ? { marginBottom: helpReserve[id] + 16 }
      : undefined;

  const lc = useArtifactLifecycle<SimulationSummary, StartInput>({
    apiPath: "/simulations",
    listKey: "simulations",
    itemKey: "simulation",
    storageKey: STORAGE_KEYS.simulation,
    idField: "simulation_id",
    buildStartBody: (input) => {
      const body: Record<string, unknown> = { model_id: input.model_id };
      if (input.fixedTarget) {
        // Fixing a child table's row count: the mother floats, so no
        // sample_size / table_sample_sizes may accompany it (API rejects both).
        body.fixed_target = input.fixedTarget;
      } else if (input.tableSampleSizes && Object.keys(input.tableSampleSizes).length > 0) {
        body.table_sample_sizes = input.tableSampleSizes;
      } else {
        const n = Number.parseInt(input.sampleSize, 10);
        if (Number.isFinite(n) && n > 0) body.sample_size = n;
      }
      body.synthetic_data_file_format = input.syntheticDataFileFormat;
      // The sampling knobs only matter when oversampling can occur: a child
      // target always oversimulates; a fixed mother only with rejection rules.
      if (input.fixedTarget || input.hasRejectionSampling) {
        const attempts = Number.parseInt(input.maxAttempts, 10);
        if (Number.isFinite(attempts) && attempts >= 1) body.max_attempts = attempts;
        const factor = Number.parseFloat(input.overgenerateFactor);
        if (Number.isFinite(factor) && factor >= 1) body.overgenerate_factor = factor;
      }
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

  // Reset the Preparación form to its defaults — used when the user jumps to a
  // past generation from the history, which discards whatever they were setting
  // up (sample sizes, sampling knobs, conditional config, selected model).
  const resetPreparation = useCallback(() => {
    setSampleSize("");
    setSyntheticDataFileFormat("csv");
    setTableSampleSizes(null);
    setFixedTarget(null);
    setMaxAttempts("2");
    setOvergenerateFactor("3");
    setConditionalConfig(EMPTY_CONDITIONAL_CONFIG);
    setSelectedModelId(completedModels[0]?.model_id ?? "");
  }, [completedModels, setSelectedModelId]);

  // Selecting a past generation from the history loads its results and resets
  // the preparation form — gated behind a confirmation dialog.
  const selectRun = useConfirmSelect((id) => {
    lc.setActiveId(id);
    resetPreparation();
  }, lc.activeId);
  const originalSizes = selectedModel?.training_table_sizes || {};
  const subjectTables = selectedModel?.subject_tables || [];

  const brcId = selectedModel?.brc_id;
  const brcRulesQuery = useQuery({
    queryKey: ["brc-rules-snapshot", brcId ?? null],
    enabled: !!brcId,
    queryFn: async () => {
      const yamlText = await getBrcRulesSnapshot(brcId!);
      try {
        const parsed = (yaml.load(yamlText) as { rules?: any[] }) ?? {};
        return parsed.rules ?? [];
      } catch {
        return [];
      }
    },
  });

  const hasRejectionSampling = useMemo(() => {
    if (!brcRulesQuery.data) return false;
    return brcRulesQuery.data.some((r: any) => r.rejection_sampling === true);
  }, [brcRulesQuery.data]);


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
      width: "16%",
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
      width: "14%",
      render: (s) => (
        <StatusBadge
          status={s.status}
          errorMessage={s.error_message}
          className={cn(s.status === "completed" && "!bg-blue-500/20 !text-blue-400")}
        />
      ),
    },
    {
      key: "model",
      header: "Modelo",
      width: "13%",
      render: (s) => (
        <span className="block truncate font-mono text-xs" title={s.model_id ?? ""}>
          {labelForModelId(s.model_id)}
        </span>
      ),
    },
    {
      key: "trainingTables",
      header: "Tablas",
      width: "11%",
      render: (s) => {
        const sizes = s.training_table_sizes ?? {};
        const names = Object.keys(sizes);
        // Fall back to the synthetic table names when the linked model card no
        // longer carries training sizes (e.g. the model was deleted).
        const labels = names.length > 0 ? names : s.tables ? s.tables.split(", ") : [];
        if (labels.length === 0) {
          return <span className="text-xs text-muted-foreground">—</span>;
        }
        const tooltip = (names.length > 0
          ? names.map((n) => `${n}: ${sizes[n].toLocaleString()} filas`)
          : labels
        ).join("\n");
        return (
          <span className="block truncate font-mono text-xs" title={tooltip}>
            {labels.join(", ")}
          </span>
        );
      },
    },
    {
      key: "size",
      header: "Tamaño",
      width: "9%",
      align: "right",
      render: (s) => {
        const size = s.target_table_rows ?? s.mother_table_size ?? s.sample_size;
        const title = s.target_table
          ? `Filas objetivo de ${s.target_table} (maestra libre)`
          : s.mother_table
            ? `Filas de ${s.mother_table}`
            : undefined;
        return (
          <span className="tabular-nums" title={title}>
            {size != null ? size.toLocaleString() : "—"}
          </span>
        );
      },
    },
  ];

  return (
    <WizardShell
      currentSlug="generacion"
      canAdvance={lc.hasCompleted}
      outline={GENERACION_OUTLINE}
      instructions={generacionInstructions}
      instructionsOpen={instructionsOpen}
      instructionsSections={openSections}
      onInstructionsToggleSection={toggleSection}
      onInstructionsClose={() => setInstructionsOpen(false)}
      onInstructionsMeasure={handleHelpMeasure}
      instructionsBannerHeight={WIZARD_BANNER_HEIGHT}
    >
      <WizardBanner
        title="Generación"
        subtitle="Genera datos sintéticos a partir de un modelo entrenado."
        instructionsOpen={instructionsOpen}
        onOpenManual={() => setInstructionsOpen(true)}
        info={
          <ActiveRunName
            label="de la simulación"
            name={
              lc.activeId && lc.active
                ? lc.active.simulation_name || lc.active.simulation_id
                : null
            }
            placeholder="simulación aún no iniciada"
            existingNames={lc.list.map((x) => x.simulation_name || x.simulation_id)}
            onSave={
              lc.active
                ? async (name) => lc.rename(lc.active!.simulation_id, name)
                : undefined
            }
          />
        }
      />
      <div className="space-y-6">
        <WorkflowGroup
          id="preparacion"
          label="Preparación"
          open={openSections.preparacion ?? true}
          onOpenChange={(o) => setSectionOpen("preparacion", o)}
          className="scroll-mt-24"
          style={helpGap("preparacion")}
        >
          <div id="nueva-generacion" className="scroll-mt-24">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Selección de modelo</CardTitle>
              </CardHeader>
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
                      <NativeSelect
                        id="model-select"
                        value={selectedModelId}
                        onValueChange={(v) => {
                          setSelectedModelId(v);
                          lc.setActiveId(null);
                        }}
                        className="h-9 rounded-md px-3 font-mono text-xs"
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
                      </NativeSelect>
                    )}
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Label htmlFor="synthetic-format">Formato</Label>
                      <Tooltip content="Selecciona el formato en el que deseas descargar los datos sintéticos. CSV es universal y fácil de procesar; Parquet es más compacto y eficiente." />
                    </div>
                    <NativeSelect
                      id="synthetic-format"
                      value={syntheticDataFileFormat}
                      onValueChange={setSyntheticDataFileFormat}
                      className="h-9 rounded-md px-3 text-sm"
                    >
                      <option value="csv">CSV</option>
                      <option value="parquet">Parquet</option>
                    </NativeSelect>
                  </div>
                </div>

                {selectedModel?.brc_id && (
                  <div id="reglas-preprocesamiento" className="scroll-mt-24">
                    <RulesBanner brcId={selectedModel.brc_id} title="Reglas de negocio" />
                  </div>
                )}
                {selectedModelId && Object.keys(originalSizes).length > 0 && (
                  <div id="configuracion-volumen" className="scroll-mt-24">
                    <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-[#26467a] dark:text-[#9db4dc]">
                      Configuración de volumen
                    </h3>
                    <TableSampleSizesEditor
                      key={selectedModelId}
                      originalSizes={originalSizes}
                      subjectTables={subjectTables}
                      value={tableSampleSizes}
                      onChange={setTableSampleSizes}
                      fixedTarget={fixedTarget}
                      onFixedTargetChange={setFixedTarget}
                      hasRejectionRules={hasRejectionSampling}
                      maxAttempts={maxAttempts}
                      onMaxAttemptsChange={setMaxAttempts}
                      overgenerateFactor={overgenerateFactor}
                      onOvergenerateFactorChange={setOvergenerateFactor}
                      allowFixedTarget
                    />
                  </div>
                )}
                {/* Oversampling warning, right below the knobs it refers to.
                    Shown only when oversampling will actually run: a fixed
                    child target, or rejection-sampling rules. Mother fixed +
                    no rules = single exact pass, nothing to warn about. */}
                {(fixedTarget != null || hasRejectionSampling) && (
                  <div className="rounded-md border border-amber-300 bg-amber-50/50 p-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/20 dark:text-amber-300">
                    <div className="flex items-start gap-2">
                      <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
                      <div className="space-y-1">
                        <p className="font-semibold text-xs uppercase tracking-wider text-amber-700 dark:text-amber-400">
                          {hasRejectionSampling
                            ? "Muestreo por rechazo activo"
                            : "Sobresimulación activa"}
                        </p>
                        <p className="text-xs text-muted-foreground leading-relaxed text-amber-800/90 dark:text-amber-300/90">
                          {hasRejectionSampling && fixedTarget != null
                            ? `Hay reglas con muestreo por rechazo y el objetivo de filas está fijado en ${fixedTarget.table}: se sobresimulará la tabla maestra (descartando filas que incumplan) hasta alcanzar el objetivo, reintentando si hace falta. La generación puede tardar más.`
                            : hasRejectionSampling
                              ? "Esta generación incluye al menos una regla de negocio con muestreo por rechazo activado. Esto hará que potencialmente tarde más porque intentará hacer cumplir la regla y el target de filas, lo que usualmente hace que se reintente la simulación."
                              : `El objetivo de filas está fijado en la tabla hija ${fixedTarget!.table}: la maestra se sobresimulará (y se reintentará si hace falta) hasta alcanzarlo, por lo que la generación puede tardar más.`}
                        </p>
                        <p className="text-[11px] text-muted-foreground leading-relaxed text-amber-800/80 dark:text-amber-300/80 mt-1">
                          Puedes ajustar la <b>sobregeneración</b> y los <b>reintentos máximos</b> justo arriba. Sube primero la sobregeneración: simular más filas de golpe es mucho más rápido que reintentar (cada reintento rearranca el motor).
                        </p>
                      </div>
                    </div>
                  </div>
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

          <div id="ejecutar-generacion" className="scroll-mt-24 space-y-3">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Ejecutar generación</CardTitle>
              </CardHeader>
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
                  onClick={() => setStartDialogOpen(true)}
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

        <WorkflowGroup
          id="resultados"
          label="Resultados"
          open={openSections.resultados ?? true}
          onOpenChange={(o) => setSectionOpen("resultados", o)}
          className="scroll-mt-24"
          style={helpGap("resultados")}
        >
          <div id="generacion-actual" className="scroll-mt-24">
            <ActiveJobCard
              id={lc.activeId}
              title="Generación actual"
              description="Estado de la última generación iniciada."
              isLoading={lc.activeQuery.isLoading}
              isError={lc.activeQuery.isError}
              errorMessage="No se pudo cargar el estado de la generación."
              active={lc.active}
              metadata={
                lc.active && (
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted-foreground">
                      {lc.active.model_id && (
                        <span>
                          Modelo:{" "}
                          <span className="font-mono" title={lc.active.model_id}>
                            {labelForModelId(lc.active.model_id)}
                          </span>
                        </span>
                      )}
                      {(lc.active.target_table_rows ??
                        lc.active.mother_table_size ??
                        lc.active.sample_size) != null && (
                        <span
                          className="tabular-nums"
                          title={
                            lc.active.target_table
                              ? `Filas objetivo de ${lc.active.target_table} (maestra libre)`
                              : lc.active.mother_table
                                ? `Filas de ${lc.active.mother_table}`
                                : undefined
                          }
                        >
                          Filas{lc.active.target_table ? ` de ${lc.active.target_table}` : ""}:{" "}
                          {(
                            lc.active.target_table_rows ??
                            lc.active.mother_table_size ??
                            lc.active.sample_size
                          )?.toLocaleString()}
                        </span>
                      )}
                    </div>
                    {lc.active.status === "completed" &&
                      lc.activeId &&
                      Object.keys(lc.active.training_table_sizes ?? {}).length > 0 && (
                        <SimulationSchemaDiagram
                          simulationId={lc.activeId}
                          fallbackSizes={lc.active.training_table_sizes}
                          relationships={lc.active.relationships ?? []}
                        />
                      )}
                    {lc.active.status === "completed" && lc.activeId && (
                      <TimeProfilingPanel kind="simulations" id={lc.activeId} />
                    )}
                    {lc.active.status === "completed" && lc.activeId && (
                      <SanityReportCard simulationId={lc.activeId} />
                    )}
                    {lc.active.status === "completed" && lc.activeId && (
                      <RejectionSamplingCard simulationId={lc.activeId} />
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

        <WorkflowGroup
          id="historial"
          label="Historial"
          open={openSections.historial ?? false}
          onOpenChange={(o) => setSectionOpen("historial", o)}
          className="scroll-mt-24"
          style={helpGap("historial")}
        >
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
              onCleanup={() => setConfirmCleanup(true)}
              onPurge={() => setConfirmPurge(true)}
              isCleaning={lc.isCleaning}
              isPurging={lc.isPurging}
              activeId={lc.activeId}
              getRowId={(s) => s.simulation_id}
              getTimestamp={(s) => s.timestamp}
              getDuration={(s) => s.duration_seconds}
              onSelect={selectRun.request}
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
                  <>
                    {s.status === "completed" && (
                      <DownloadMenu
                        ariaLabel="Descargar generación"
                        options={[
                          {
                            label: "Dataset sintético",
                            href: `/simulations/${s.simulation_id}/download/synthetic-dataset`,
                          },
                          {
                            label: "Carpeta completa",
                            href: `/simulations/${s.simulation_id}/download`,
                          },
                        ]}
                      />
                    )}
                    <button
                      type="button"
                      aria-label="Eliminar generación"
                      disabled={lc.isDeleting}
                      onClick={() => setConfirmDeleteId(s.simulation_id)}
                      className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </>
                )
              }
            />
          </div>
        </WorkflowGroup>
      </div>

      <NamePromptDialog
        open={startDialogOpen}
        title="Iniciar generación"
        description="Asigna un nombre funcional a esta generación para identificarla más fácilmente. Puedes dejarlo en blanco y editarlo después."
        confirmLabel="Iniciar generación"
        onConfirm={(name) => {
          lc.start(
            {
              model_id: selectedModelId,
              sampleSize,
              tableSampleSizes,
              fixedTarget,
              maxAttempts,
              overgenerateFactor,
              hasRejectionSampling,
              syntheticDataFileFormat,
              conditional: conditionalConfig,
            },
            name || undefined,
          );
          setStartDialogOpen(false);
        }}
        onCancel={() => setStartDialogOpen(false)}
      />

      <ConfirmDialog
        open={selectRun.pendingId !== null}
        title="¿Ver una generación anterior?"
        description="Se cargarán sus resultados y se descartarán los cambios sin guardar en la preparación, que volverá a sus valores por defecto."
        confirmLabel="Ver generación"
        onConfirm={selectRun.confirm}
        onCancel={selectRun.cancel}
      />

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
              "Se eliminarán TODAS las generaciones, incluidas las completadas correctamente. ¿Quieres eliminar también sus evaluaciones asociadas, o dejarlas huérfanas? Esta acción no se puede deshacer.",
            cascadeLabel: "Purgar generaciones y sus evaluaciones",
            orphanLabel: "Purgar solo generaciones (dejar evaluaciones huérfanas)",
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
        onPurge={() => lc.purge(false)}
        onPurgeCascade={() => lc.purge(true)}
        deleteConflict={lc.deleteConflict}
        onDeleteConflictCascade={() => lc.resolveDeleteConflict("cascade")}
        onDeleteConflictForce={() => lc.resolveDeleteConflict("force")}
        onDeleteConflictDismiss={lc.dismissDeleteConflict}
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
      collapsible={true}
      defaultOpen={false}
    />
  );
}
