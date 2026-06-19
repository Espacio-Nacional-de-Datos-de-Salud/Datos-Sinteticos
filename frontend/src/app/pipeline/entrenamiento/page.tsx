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
//
// All shared lifecycle wiring (queries / mutations / confirm dialogs /
// history table) lives under @/components/pipeline-step. This file owns
// only the kind-specific bits: the form, the per-row metadata, the
// downloadable artefacts, and the Spanish copy.

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Play, Sparkles, Trash2, XCircle } from "lucide-react";

import { ConfigPanel } from "@/components/config/config-drawer";
import { EditableName } from "@/components/jobs/editable-name";
import { ActiveRunName } from "@/components/jobs/active-run-name";
import { ActiveJobCard } from "@/components/pipeline-step/active-job-card";
import { TimeProfilingPanel } from "@/components/pipeline-step/time-profiling-panel";
import {
  CurrentConfigSummary,
  TrainingConfigSummary,
} from "@/components/pipeline-step/training-config-summary";
import { DownloadMenu } from "@/components/pipeline-step/download-menu";
import { HistoryCard, type HistoryColumn } from "@/components/pipeline-step/history-card";
import { useConfirmSelect } from "@/components/pipeline-step/use-confirm-select";
import { useArtifactLifecycle } from "@/components/pipeline-step/use-artifact-lifecycle";
import { useUpstreamSelection } from "@/components/pipeline-step/use-upstream-selection";
import { WizardConfirmDialogs } from "@/components/pipeline-step/wizard-confirm-dialogs";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { RulesBanner } from "@/components/config/rules-banner";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WizardBanner, WIZARD_BANNER_HEIGHT } from "@/components/layout/wizard-banner";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { getEntrenamientoInstructions } from "@/components/training/instructions-content";
import { NamePromptDialog } from "@/components/ui/name-prompt-dialog";
import { StatusBadge } from "@/components/jobs/status-badge";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import {
  api,
  getTrainingPreflight,
  type ConfigContent,
  type InspectionSummary,
  type ModelSummary,
} from "@/lib/api";
import yaml from "js-yaml";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { listBrcs, totalRuleCount } from "@/lib/brc";
import { cn } from "@/lib/utils";
import { useManualOpen } from "@/lib/use-manual-open";

type StartInput = { inspection_id: string; brc_id?: string };

interface MostlyAiConfig {
  model_settings?: {
    per_table?: Record<string, unknown>;
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

const ENTRENAMIENTO_OUTLINE = [
  { id: "preparacion", label: "Configuración", level: 1 },
  { id: "nuevo-entrenamiento", label: "Selector de reglas", level: 2 },
  { id: "reglas-preprocesamiento", label: "Reglas de negocio", level: 2 },
  { id: "configuracion-modelo", label: "Configuración del modelo", level: 2 },
  { id: "ejecutar-entrenamiento", label: "Ejecución del entrenamiento", level: 2 },
  { id: "resultados", label: "Resultados", level: 1 },
  { id: "entrenamiento-actual", label: "Entrenamiento actual", level: 2 },
  { id: "historial", label: "Historial", level: 1 },
  { id: "modelos-entrenados", label: "Modelos entrenados", level: 2 },
] as const;

export default function EntrenamientoPage() {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [startDialogOpen, setStartDialogOpen] = useState(false);

  // Instructions manual state — shared across pipeline pages via localStorage
  // so the panel stays open as the user navigates between steps.
  const [instructionsOpen, setInstructionsOpen] = useManualOpen();

  // Open/collapsed state per page section — shared between the WorkflowGroups
  // and the help panel so the two collapse in sync.
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    preparacion: true,
    resultados: true,
    historial: false,
  });
  // When a section opens, scroll the page to it — same UX as the main page
  // section toggles. Runs after the section has expanded in the DOM.
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

  // Space the manual asks the page to reserve, keyed by id: the overview
  // spacer height ("resumen") and the per-section deficit when a help block
  // is taller than its page section.
  const [helpReserve, setHelpReserve] = useState<Record<string, number>>({});
  const handleHelpMeasure = useCallback(
    (reserve: Record<string, number>) => setHelpReserve(reserve),
    [],
  );
  // When a help block is taller than its section, add the extra space as a
  // bottom margin — blank background between sections, not inside the box.
  const helpGap = (id: string): React.CSSProperties | undefined =>
    instructionsOpen && (openSections[id] ?? true) && helpReserve[id]
      ? { marginBottom: helpReserve[id] + 16 }
      : undefined;

  const lc = useArtifactLifecycle<ModelSummary, StartInput>({
    apiPath: "/models",
    listKey: "models",
    itemKey: "model",
    storageKey: STORAGE_KEYS.model,
    idField: "model_id",
    buildStartBody: (input) => ({
      inspection_id: input.inspection_id,
      ...(input.brc_id ? { brc_id: input.brc_id } : {}),
    }),
    labels: {
      startedToast: (id) => `Entrenamiento iniciado: ${id}`,
      startErrorPrefix: "No se pudo iniciar el entrenamiento",
      cancelErrorPrefix: "No se pudo cancelar",
      deletedToast: (id) => `Modelo eliminado: ${id}`,
      deleteErrorPrefix: "No se pudo eliminar",
      cleanupOkToast: (n) => `${n} modelo(s) limpiado(s)`,
      cleanupNoopToast: "Nada que limpiar",
      cleanupErrorPrefix: "Error en limpieza",
      purgeOkToast: (n) => `${n} modelo(s) eliminado(s)`,
      purgeErrorPrefix: "Error al purgar",
    },
  });

  const inspectionsQuery = useQuery({
    queryKey: ["inspections"],
    queryFn: async () => {
      const { data } = await api.get<InspectionSummary[]>("/inspections/");
      return data;
    },
  });
  const completedInspections = (inspectionsQuery.data ?? []).filter(
    (i) => i.status === "completed",
  );

  const { selectedId: selectedInspectionId, setSelectedId: setSelectedInspectionId } =
    useUpstreamSelection(completedInspections, "inspection_id", STORAGE_KEYS.inspection);

  const entrenamientoInstructions = useMemo(
    () => getEntrenamientoInstructions(),
    [],
  );

  type TrainingSource = "upload" | "brc";
  // Default to training from a preprocessed configuration with its business
  // rules applied ("brc"); fall back to a plain upload only when no completed
  // BRC exists (handled by the auto-select effect below).
  const [trainingSource, setTrainingSource] = useState<TrainingSource>("brc");
  const updateTrainingSource = useCallback((value: TrainingSource) => {
    setTrainingSource(value);
  }, []);

  const brcsQuery = useQuery({
    queryKey: ["brc", "list", "all"],
    queryFn: () => listBrcs(),
  });
  const completedBrcs = useMemo(
    () => (brcsQuery.data ?? []).filter((r) => r.status === "completed"),
    [brcsQuery.data],
  );
  const [selectedBrcId, setSelectedBrcId] = useState<string>("");
  useEffect(() => {
    if (completedBrcs.length === 0) return;
    if (selectedBrcId && completedBrcs.some((b) => b.brc_id === selectedBrcId)) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSelectedBrcId(completedBrcs[0].brc_id);
  }, [completedBrcs, selectedBrcId]);

  const selectedBrc = useMemo(
    () => completedBrcs.find((b) => b.brc_id === selectedBrcId) ?? null,
    [completedBrcs, selectedBrcId],
  );

  const autoSourceSettled = useRef(false);
  useEffect(() => {
    if (autoSourceSettled.current) return;
    if (inspectionsQuery.isLoading || brcsQuery.isLoading) return;

    const latestInspection = completedInspections[0] ?? null;
    const latestBrc = completedBrcs[0] ?? null;
    if (!latestInspection && !latestBrc) return; // nothing completed yet; wait

    // Prefer training from a configuration with rules applied (brc) whenever one
    // exists; only fall back to a plain upload when there are no completed BRCs.
    if (latestBrc) {
      // BRC selection is kept on the latest run by the effect above.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setTrainingSource("brc");
    } else if (latestInspection) {
      setTrainingSource("upload");
      setSelectedInspectionId(latestInspection.inspection_id);
    }
    autoSourceSettled.current = true;
  }, [
    inspectionsQuery.isLoading,
    brcsQuery.isLoading,
    completedInspections,
    completedBrcs,
    setSelectedInspectionId,
  ]);

  const effectiveSource: TrainingSource = trainingSource;

  // Effective inspection_id sent to the API: in upload mode it's the picked
  // upload; in BRC mode it's the upload that owns the selected BRC.
  const effectiveInspectionId =
    effectiveSource === "brc"
      ? selectedBrc?.inspection_id ?? ""
      : selectedInspectionId;
  const effectiveBrcId = effectiveSource === "brc" ? selectedBrcId : "";

  const inspectionNameById = useMemo(() => {
    const map: Record<string, string> = {};
    for (const i of inspectionsQuery.data ?? []) {
      map[i.inspection_id] = i.inspection_name || i.inspection_id;
    }
    return map;
  }, [inspectionsQuery.data]);

  // Table names of the upload being trained, so the model config can offer
  // guided per-table overrides instead of free-text table names.
  const effectiveTableNames = useMemo(() => {
    const inspection = (inspectionsQuery.data ?? []).find(
      (i) => i.inspection_id === effectiveInspectionId,
    );
    return Object.keys(inspection?.tables ?? {});
  }, [inspectionsQuery.data, effectiveInspectionId]);

  // Row count of the largest table in the selected upload — used to auto-size
  // the training batch when a configuration preset is applied.
  const effectiveRowCount = useMemo(() => {
    const inspection = (inspectionsQuery.data ?? []).find(
      (i) => i.inspection_id === effectiveInspectionId,
    );
    const counts = Object.values(inspection?.tables ?? {});
    return counts.length > 0 ? Math.max(...counts) : undefined;
  }, [inspectionsQuery.data, effectiveInspectionId]);

  // Known blockers for "this upload + the current model config". Refreshed
  // whenever the config panel saves, so the warning (and the disabled launch
  // button) always reflect what the training would actually read.
  const queryClient = useQueryClient();
  const preflightQuery = useQuery({
    queryKey: ["training-preflight", effectiveInspectionId],
    enabled: !!effectiveInspectionId,
    queryFn: () => getTrainingPreflight(effectiveInspectionId),
  });
  const preflightIssues = preflightQuery.data ?? [];
  const refreshPreflight = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["training-preflight"] }),
    [queryClient],
  );

  // Reset the training per-table settings on page entry so they always start clean,
  // matching the "blank on entry" behavior of logical rules and column exclusions.
  const [clearedOnEntry, setClearedOnEntry] = useState(false);
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const { data } = await api.get<ConfigContent>("/configs/mostly_ai");
        if (cancelled) return;
        const parsed = (yaml.load(data.content) as MostlyAiConfig) ?? {};
        if (parsed.model_settings && parsed.model_settings.per_table !== undefined) {
          delete parsed.model_settings.per_table;
          const content = yaml.dump(parsed, { lineWidth: 100, noRefs: true });
          await api.put("/configs/mostly_ai", { content });
        }
      } catch (err) {
        console.error("Failed to reset training per-table settings on mount:", err);
      }
      if (cancelled) return;
      queryClient.invalidateQueries({ queryKey: ["config", "mostly_ai"] });
      queryClient.invalidateQueries({ queryKey: ["training-preflight"] });
      setClearedOnEntry(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [queryClient]);

  // Changing the data source after entry resets the model config to its default
  // template, as if the page had just been opened. A preset bakes data-derived
  // values into mostly_ai.yaml (notably the auto-sized batch, plus per-table
  // overrides), so carrying them over to a different dataset would be wrong.
  // Remounting the config panel (via `configResetKey`) also returns the mode
  // selector to "Libre" and unlocks the fields.
  const [configResetKey, setConfigResetKey] = useState(0);
  const settledSelectionRef = useRef<string | null>(null);
  const effectiveSelectionKey = `${effectiveSource}:${effectiveBrcId}:${effectiveInspectionId}`;
  useEffect(() => {
    if (!effectiveInspectionId) return; // wait until a source is settled
    // First settled selection is the page-entry state — don't reset over it.
    if (settledSelectionRef.current === null) {
      settledSelectionRef.current = effectiveSelectionKey;
      return;
    }
    if (settledSelectionRef.current === effectiveSelectionKey) return;
    settledSelectionRef.current = effectiveSelectionKey;
    let cancelled = false;
    (async () => {
      try {
        // Delete the override so the backend recreates it from the template.
        await api.delete("/configs/mostly_ai");
      } catch (err) {
        console.error("Failed to reset model config on source change:", err);
      }
      if (cancelled) return;
      queryClient.invalidateQueries({ queryKey: ["config", "mostly_ai"] });
      queryClient.invalidateQueries({ queryKey: ["training-preflight"] });
      setConfigResetKey((k) => k + 1);
    })();
    return () => {
      cancelled = true;
    };
  }, [effectiveSelectionKey, effectiveInspectionId, queryClient]);

  // Reset the Preparación form to its defaults — used when the user jumps to a
  // past model from the history, which discards whatever they were configuring.
  const resetPreparation = useCallback(async () => {
    setTrainingSource(completedBrcs.length > 0 ? "brc" : "upload");
    setSelectedBrcId(completedBrcs[0]?.brc_id ?? "");
    setSelectedInspectionId(completedInspections[0]?.inspection_id ?? "");
    try {
      const { data } = await api.get<ConfigContent>("/configs/mostly_ai");
      const parsed = (yaml.load(data.content) as MostlyAiConfig) ?? {};
      if (parsed.model_settings && parsed.model_settings.per_table !== undefined) {
        delete parsed.model_settings.per_table;
        const content = yaml.dump(parsed, { lineWidth: 100, noRefs: true });
        await api.put("/configs/mostly_ai", { content });
      }
    } catch (err) {
      console.error("Failed to reset per-table settings:", err);
    }
    queryClient.invalidateQueries({ queryKey: ["config", "mostly_ai"] });
    queryClient.invalidateQueries({ queryKey: ["training-preflight"] });
  }, [completedBrcs, completedInspections, setSelectedInspectionId, queryClient]);

  // Selecting a past model from the history loads its results and resets the
  // preparation form — gated behind a confirmation dialog.
  const selectRun = useConfirmSelect((id) => {
    lc.setActiveId(id);
    void resetPreparation();
  }, lc.activeId);

  const columns: HistoryColumn<ModelSummary>[] = [
    {
      key: "name",
      header: "Nombre",
      width: "16%",
      render: (m) => (
        <div className="space-y-0.5">
          <p
            className="truncate font-mono text-[10px] text-muted-foreground"
            title={m.model_id}
          >
            {m.model_id}
          </p>
          <EditableName
            name={m.model_name || m.model_id}
            existingNames={lc.list.map((x) => x.model_name || x.model_id)}
            onSave={(name) => lc.rename(m.model_id, name)}
          />
        </div>
      ),
    },
    {
      key: "status",
      header: "Estado",
      width: "14%",
      render: (m) => (
        <StatusBadge
          status={m.status}
          errorMessage={m.error_message}
          className={cn(m.status === "completed" && "!bg-blue-500/20 !text-blue-400")}
        />
      ),
    },
    {
      key: "tables",
      header: "Tablas / Entrada",
      width: "18%",
      render: (m) => {
        const brcLabel = m.brc_id ? (m.brc_name || m.brc_id) : null;
        return (
          <div className="space-y-0.5 min-w-0">
            <span className="block truncate font-mono text-xs" title={m.tables || ""}>
              {m.tables || "—"}
            </span>
            <span
              className="block truncate text-[10px] font-medium text-muted-foreground"
              title={brcLabel ?? (m.inspection_id || undefined)}
            >
              {brcLabel ?? m.inspection_id ?? "—"}
            </span>
          </div>
        );
      },
    },
    {
      key: "rows",
      header: "Filas",
      width: "6%",
      align: "right",
      render: (m) => (
        <span className="tabular-nums">
          {m.train_size != null ? m.train_size.toLocaleString() : "—"}
        </span>
      ),
    },
  ];

  return (
    <WizardShell
      currentSlug="entrenamiento"
      canAdvance={lc.hasCompleted}
      outline={ENTRENAMIENTO_OUTLINE}
      instructions={entrenamientoInstructions}
      instructionsOpen={instructionsOpen}
      instructionsSections={openSections}
      onInstructionsToggleSection={toggleSection}
      onInstructionsClose={() => setInstructionsOpen(false)}
      onInstructionsMeasure={handleHelpMeasure}
      instructionsBannerHeight={WIZARD_BANNER_HEIGHT}
    >
      <WizardBanner
        title="Entrenamiento"
        subtitle={
          <>
            Lanza un entrenamiento a partir de una carga de datos completada.
            Puedes encadenar varios entrenamientos; cada uno aparecerá en el
            catálogo de abajo y estará disponible en el paso de{" "}
            <b>Generación</b>.
          </>
        }
        instructionsOpen={instructionsOpen}
        onOpenManual={() => setInstructionsOpen(true)}
        info={
          <ActiveRunName
            label="del modelo"
            name={
              lc.activeId && lc.active
                ? lc.active.model_name || lc.active.model_id
                : null
            }
            placeholder="entrenamiento aún no iniciado"
            existingNames={lc.list.map((x) => x.model_name || x.model_id)}
            onSave={
              lc.active
                ? async (name) => lc.rename(lc.active!.model_id, name)
                : undefined
            }
          />
        }
      />
      <div className="space-y-6">
        <WorkflowGroup
          id="preparacion"
          label="Configuración"
          open={openSections.preparacion ?? true}
          onOpenChange={(o) => setSectionOpen("preparacion", o)}
          className="scroll-mt-24"
          style={helpGap("preparacion")}
        >
          <div id="nuevo-entrenamiento" className="scroll-mt-24">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Selector de reglas</CardTitle>
                <CardDescription>
                  Elige sobre qué datos se entrenará el modelo: una configuración ya preprocesada con sus reglas de negocio aplicadas, o los datos preprocesados de la carga sin reglas. Selecciona después el conjunto concreto en el desplegable.
                </CardDescription>
              </CardHeader>
              <CardContent className="flex flex-col gap-3 p-4 pt-0">
                <div className="flex flex-col gap-3 md:flex-row md:items-end">
                  <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1 space-y-2">
                    <div
                      role="radiogroup"
                      aria-label="Fuente del entrenamiento"
                      className="inline-flex rounded-md border bg-background p-0.5 text-xs"
                    >
                      {([
                        { value: "upload", label: "Datos preprocesados" },
                        { value: "brc", label: "Datos preprocesados + Reglas aplicadas" },
                      ] as const).map((opt) => {
                        const active = trainingSource === opt.value;
                        const disabled =
                          opt.value === "brc" && completedBrcs.length === 0;
                        return (
                          <button
                            key={opt.value}
                            type="button"
                            role="radio"
                            aria-checked={active}
                            disabled={disabled}
                            onClick={() => updateTrainingSource(opt.value)}
                            className={cn(
                              "flex items-center gap-1.5 rounded px-3 py-1.5 font-medium transition-colors disabled:opacity-50",
                              active
                                ? "bg-primary text-primary-foreground"
                                : "text-muted-foreground hover:bg-muted",
                            )}
                            title={
                              disabled
                                ? "No hay ejecuciones BRC completadas todavía."
                                : undefined
                            }
                          >
                            {opt.label}
                            {opt.value === "brc" && (
                              <span
                                onClick={(e) => e.stopPropagation()}
                                className="flex items-center"
                              >
                                <Tooltip
                                  content="Avanzado · usa una configuración de reglas de negocio aplicadas"
                                  side="top"
                                >
                                  <Sparkles
                                    className={cn(
                                      "h-3.5 w-3.5 shrink-0",
                                      active ? "opacity-80" : "text-violet-400",
                                    )}
                                  />
                                </Tooltip>
                              </span>
                            )}
                          </button>
                        );
                      })}
                    </div>
                    {effectiveSource === "upload" ? (
                      inspectionsQuery.isLoading ? (
                        <Skeleton className="h-9 w-full" />
                      ) : completedInspections.length === 0 ? (
                        <p className="text-sm text-destructive">
                          No hay cargas de datos completadas. Vuelve al paso{" "}
                          <b>Carga de Datos</b>.
                        </p>
                      ) : (
                        <NativeSelect
                          id="inspection-select"
                          value={selectedInspectionId}
                          onValueChange={setSelectedInspectionId}
                          className="h-9 rounded-md px-3 font-mono text-xs"
                        >
                          {completedInspections.map((i) => {
                            const tableSummary = Object.keys(i.tables ?? {}).join(", ");
                            return (
                              <option key={i.inspection_id} value={i.inspection_id}>
                                {i.inspection_name || i.inspection_id}
                                {tableSummary ? ` · ${tableSummary}` : ""}
                              </option>
                            );
                          })}
                        </NativeSelect>
                      )
                    ) : brcsQuery.isLoading ? (
                      <Skeleton className="h-9 w-full" />
                    ) : completedBrcs.length === 0 ? (
                      <p className="text-sm text-destructive">
                        No hay ejecuciones BRC completadas. Crea una en{" "}
                        <b>Configuración</b> o entrena desde datos cargados.
                      </p>
                    ) : (
                      <NativeSelect
                        id="brc-select"
                        value={selectedBrcId}
                        onValueChange={setSelectedBrcId}
                        className="h-9 rounded-md px-3 font-mono text-xs"
                      >
                        {completedBrcs.map((b) => {
                          const uploadLabel =
                            inspectionNameById[b.inspection_id] || b.inspection_id;
                          const total = totalRuleCount(b);
                          return (
                            <option key={b.brc_id} value={b.brc_id}>
                              {b.brc_name || b.brc_id}
                              {total ? ` · ${total} regla(s)` : ""}
                              {` · ${uploadLabel}`}
                            </option>
                          );
                        })}
                      </NativeSelect>
                    )}
                  </div>
                </div>
                {effectiveSource === "brc" && (
                  <div id="reglas-preprocesamiento" className="scroll-mt-24">
                    <RulesBanner
                      brcId={selectedBrcId || null}
                      title="Reglas de negocio"
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div id="configuracion-modelo" className="scroll-mt-24">
            {clearedOnEntry ? (
              <ConfigPanel
                key={configResetKey}
                configId="mostly_ai"
                tableNames={effectiveTableNames}
                presetRowCount={effectiveRowCount}
                onSaved={refreshPreflight}
              />
            ) : (
              <Skeleton className="h-64 w-full" />
            )}
          </div>

          <div id="ejecutar-entrenamiento" className="scroll-mt-24">
            <Card>
              <CardHeader>
                <CardTitle className="text-base">
                  Ejecución del entrenamiento
                </CardTitle>
                <CardDescription>
                  Revisa la configuración del modelo y lanza el entrenamiento
                  sobre los datos seleccionados. El modelo aprenderá los patrones
                  y se usará para generar datos sintéticos en el siguiente paso.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                {preflightIssues.length > 0 && (
                  <div className="space-y-2 rounded-md border border-amber-500/50 bg-amber-500/10 p-3">
                    <div className="flex items-center gap-2 text-sm font-semibold text-amber-600 dark:text-amber-400">
                      <AlertTriangle className="h-4 w-4 shrink-0" />
                      Esta configuración hará fallar el entrenamiento
                    </div>
                    {preflightIssues.map((issue) => (
                      <div key={issue.id} className="text-xs text-foreground/90">
                        <span className="font-medium">
                          {issue.title}
                          {issue.tables.length > 0 && (
                            <span className="font-mono font-normal">
                              {" "}
                              ({issue.tables.join(", ")})
                            </span>
                          )}
                          .
                        </span>{" "}
                        {issue.guidance}
                      </div>
                    ))}
                    <p className="text-[11px] text-muted-foreground">
                      Corrige la configuración del modelo (arriba) y guarda para
                      volver a comprobar.
                    </p>
                  </div>
                )}
                <CurrentConfigSummary />
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    type="button"
                    disabled={
                      !effectiveInspectionId ||
                      lc.isStarting ||
                      lc.isRunning ||
                      preflightIssues.length > 0
                    }
                    onClick={() => setStartDialogOpen(true)}
                  >
                    <Play className="mr-2 h-4 w-4" />
                    {lc.isStarting
                      ? "Iniciando…"
                      : lc.isRunning
                        ? "Entrenamiento en curso…"
                        : "Iniciar entrenamiento"}
                  </Button>
                  <Tooltip content="El entrenamiento creará un modelo de machine learning basado en los datos seleccionados. Este modelo aprenderá patrones y será usado para generar datos sintéticos en el siguiente paso." />
                </div>
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
          <div id="entrenamiento-actual" className="scroll-mt-24">
            <ActiveJobCard
              id={lc.activeId}
              title="Entrenamiento actual"
              description="Estado del último entrenamiento iniciado desde esta sesión."
              isLoading={lc.activeQuery.isLoading}
              isError={lc.activeQuery.isError}
              errorMessage="No se pudo cargar el estado del modelo."
              active={lc.active}
              metadata={
                lc.active && (
                  <div className="space-y-3">
                    <div className="flex items-center gap-2 text-sm">
                      <span className="text-muted-foreground">Nombre:</span>
                      <EditableName
                        name={lc.active.model_name || lc.active.model_id}
                        existingNames={lc.list.map(
                          (x) => x.model_name || x.model_id,
                        )}
                        onSave={(name) => lc.rename(lc.active!.model_id, name)}
                        size="sm"
                      />
                    </div>
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted-foreground">
                      {lc.active.tables && (
                        <span>
                          Tablas:{" "}
                          <span className="font-mono">{lc.active.tables}</span>
                        </span>
                      )}
                      {lc.active.train_size != null && (
                        <span className="tabular-nums">
                          Filas: {lc.active.train_size.toLocaleString()}
                        </span>
                      )}
                    </div>
                    {lc.activeId && (
                      <TrainingConfigSummary modelId={lc.activeId} />
                    )}
                    {lc.active.status === "completed" && lc.activeId && (
                      <TimeProfilingPanel kind="models" id={lc.activeId} />
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
                      Cancelar entrenamiento
                    </Button>
                  )}

                </>
              }
            />
          </div>


        </WorkflowGroup>

        <WorkflowGroup
          id="historial"
          label="Historial"
          open={openSections.historial ?? false}
          onOpenChange={(o) => setSectionOpen("historial", o)}
          className="scroll-mt-24"
          style={helpGap("historial")}
        >
          <div id="modelos-entrenados" className="scroll-mt-24">
            <HistoryCard
              title="Modelos entrenados"
              description="Catálogo completo de modelos disponibles en el servidor. Haz click para cargar un modelo pasado y ver su estado."
              items={lc.list}
              isLoading={lc.listQuery.isLoading}
              isError={lc.listQuery.isError}
              errorMessage="No se pudo cargar el catálogo de modelos."
              emptyMessage="Todavía no hay modelos entrenados."
              columns={columns}
              actionsWidth="13%"
              onCleanup={() => setConfirmCleanup(true)}
              onPurge={() => setConfirmPurge(true)}
              isCleaning={lc.isCleaning}
              isPurging={lc.isPurging}
              activeId={lc.activeId}
              getRowId={(m) => m.model_id}
              getTimestamp={(m) => m.timestamp}
              getDuration={(m) => m.duration_seconds}
              onSelect={selectRun.request}
              actionsCell={(m) => (
                <>

                  {m.status === "completed" && (
                    <DownloadMenu
                      ariaLabel="Descargar modelo"
                      options={[
                        {
                          label: "Modelo (generador)",
                          href: `/models/${m.model_id}/download/generator`,
                        },
                        {
                          label: "Carpeta completa",
                          href: `/models/${m.model_id}/download`,
                        },
                      ]}
                    />
                  )}
                  {m.status === "in_progress" ? (
                    <button
                      type="button"
                      aria-label="Cancelar modelo"
                      disabled={lc.isCancelling}
                      onClick={() => lc.cancel(m.model_id)}
                      className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                    >
                      <XCircle className="h-3.5 w-3.5" />
                    </button>
                  ) : (
                    <button
                      type="button"
                      aria-label="Eliminar modelo"
                      disabled={lc.isDeleting}
                      onClick={() => setConfirmDeleteId(m.model_id)}
                      className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  )}
                </>
              )}
            />
          </div>
        </WorkflowGroup>
      </div>

      <NamePromptDialog
        open={startDialogOpen}
        title="Iniciar entrenamiento"
        description="Asigna un nombre funcional a este modelo para identificarlo más fácilmente. Puedes dejarlo en blanco y editarlo después."
        confirmLabel="Iniciar entrenamiento"
        onConfirm={(name) => {
          lc.start(
            {
              inspection_id: effectiveInspectionId,
              brc_id: effectiveBrcId || undefined,
            },
            name || undefined,
          );
          setStartDialogOpen(false);
        }}
        onCancel={() => setStartDialogOpen(false)}
      />

      <ConfirmDialog
        open={selectRun.pendingId !== null}
        title="¿Ver un entrenamiento anterior?"
        description="Se cargarán sus resultados y se descartarán los cambios sin guardar en la preparación, que volverá a sus valores por defecto."
        confirmLabel="Ver entrenamiento"
        onConfirm={selectRun.confirm}
        onCancel={selectRun.cancel}
      />

      <WizardConfirmDialogs
        texts={{
          delete: {
            title: "¿Eliminar modelo?",
            description:
              "Se borrarán permanentemente la carpeta del modelo y todos sus artefactos. Esta acción no se puede deshacer.",
          },
          cleanup: {
            title: "¿Limpiar modelos?",
            description:
              "Se borrarán permanentemente las carpetas vacías y las ejecuciones huérfanas. Esta acción no se puede deshacer.",
          },
          purge: {
            title: "¿Purgar todos los modelos?",
            description:
              "Se eliminarán TODOS los modelos, incluidos los completados correctamente. ¿Quieres eliminar también sus generaciones y evaluaciones asociadas, o dejarlas huérfanas? Esta acción no se puede deshacer.",
            cascadeLabel: "Purgar modelos y sus dependencias",
            orphanLabel: "Purgar solo modelos (dejar generaciones huérfanas)",
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
