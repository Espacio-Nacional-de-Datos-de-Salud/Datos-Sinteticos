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

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { BookOpen, Play, Sparkles, Trash2, XCircle } from "lucide-react";

import { ConfigPanel } from "@/components/config/config-drawer";
import { EditableName } from "@/components/jobs/editable-name";
import { ActiveJobCard } from "@/components/pipeline-step/active-job-card";
import { TimeProfilingPanel } from "@/components/pipeline-step/time-profiling-panel";
import { DownloadMenu } from "@/components/pipeline-step/download-menu";
import { HistoryCard, type HistoryColumn } from "@/components/pipeline-step/history-card";
import { useArtifactLifecycle } from "@/components/pipeline-step/use-artifact-lifecycle";
import { useUpstreamSelection } from "@/components/pipeline-step/use-upstream-selection";
import { WizardConfirmDialogs } from "@/components/pipeline-step/wizard-confirm-dialogs";
import { RulesBanner } from "@/components/config/rules-banner";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { ENTRENAMIENTO_INSTRUCTIONS } from "@/components/training/instructions-content";
import { NamePromptDialog } from "@/components/ui/name-prompt-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import {
  api,
  API_BASE_URL,
  type InspectionSummary,
  type ModelSummary,
} from "@/lib/api";
import { statusBadgeVariant, translateStatus } from "@/lib/job-status";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { listBrcs } from "@/lib/brc";
import { cn } from "@/lib/utils";

type StartInput = { inspection_id: string; brc_id?: string };

const ENTRENAMIENTO_OUTLINE = [
  { id: "preparacion", label: "Preparación", level: 1 },
  { id: "reglas-preprocesamiento", label: "Reglas de preprocesamiento", level: 2 },
  { id: "nuevo-entrenamiento", label: "Nuevo entrenamiento", level: 2 },
  { id: "configuracion-modelo", label: "Configuración del modelo", level: 2 },
  { id: "ejecutar-entrenamiento", label: "Ejecutar entrenamiento", level: 2 },
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

  // Instructions manual state — mirrors the wiring on the Inspección page so
  // the manual panel, the help banner and the section toggles stay in sync.
  const [instructionsOpen, setInstructionsOpen] = useState(false);

  // Page banner height — the manual's sticky "Resumen" block is sized to
  // match it so the two banners look the same height.
  const bannerRef = useRef<HTMLDivElement | null>(null);
  const [bannerHeight, setBannerHeight] = useState<number | undefined>();
  useLayoutEffect(() => {
    const el = bannerRef.current;
    if (!el) return;
    const update = () => {
      // Round to whole pixels — a fractional height feeds the panel's
      // overview block and would jitter, retriggering measurement endlessly.
      const h = Math.round(el.getBoundingClientRect().height);
      setBannerHeight((prev) => (prev === h ? prev : h));
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

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

  // Training source toggle: either train from a raw upload (rules.yaml applied
  // live during training) or from a completed BRC run (preprocessed parquet
  // already on disk). The choice gates which dropdown is shown and is
  // remembered across reloads so the user's intent isn't silently overwritten
  // by the auto-defaulting that used to pick the most recent BRC.
  type TrainingSource = "upload" | "brc";
  const [trainingSource, setTrainingSource] = useState<TrainingSource>("upload");
  useEffect(() => {
    const stored = window.localStorage.getItem(STORAGE_KEYS.trainingSource);
    if (stored === "upload" || stored === "brc") setTrainingSource(stored);
  }, []);
  const updateTrainingSource = useCallback((value: TrainingSource) => {
    setTrainingSource(value);
    window.localStorage.setItem(STORAGE_KEYS.trainingSource, value);
  }, []);

  // List ALL completed BRCs (across uploads). When the user is in BRC mode,
  // the dropdown shows every completed run; the originating upload is derived
  // from the BRC itself so we don't need a separate upload selector.
  const brcsQuery = useQuery({
    queryKey: ["brc", "list", "all"],
    queryFn: () => listBrcs(),
  });
  const completedBrcs = useMemo(
    () => (brcsQuery.data ?? []).filter((r) => r.status === "completed"),
    [brcsQuery.data],
  );
  const { selectedId: selectedBrcId, setSelectedId: setSelectedBrcId } =
    useUpstreamSelection(completedBrcs, "brc_id", STORAGE_KEYS.brc);

  const selectedBrc = useMemo(
    () => completedBrcs.find((b) => b.brc_id === selectedBrcId) ?? null,
    [completedBrcs, selectedBrcId],
  );

  // Effective inspection_id sent to the API: in upload mode it's the picked
  // upload; in BRC mode it's the upload that owns the selected BRC.
  const effectiveInspectionId =
    trainingSource === "brc"
      ? selectedBrc?.inspection_id ?? ""
      : selectedInspectionId;
  const effectiveBrcId = trainingSource === "brc" ? selectedBrcId : "";

  const inspectionNameById = useMemo(() => {
    const map: Record<string, string> = {};
    for (const i of inspectionsQuery.data ?? []) {
      map[i.inspection_id] = i.inspection_name || i.inspection_id;
    }
    return map;
  }, [inspectionsQuery.data]);



  const columns: HistoryColumn<ModelSummary>[] = [
    {
      key: "name",
      header: "Nombre",
      width: "24%",
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
      width: "11%",
      render: (m) => (
        <Badge
          variant={statusBadgeVariant(m.status)}
          className={cn(m.status === "completed" && "!bg-blue-500/20 !text-blue-400")}
        >
          {translateStatus(m.status)}
        </Badge>
      ),
    },
    {
      key: "tables",
      header: "Tablas / Entrada",
      width: "26%",
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
      width: "13%",
      align: "right",
      render: (m) => (
        <span className="tabular-nums">
          {m.train_size != null ? m.train_size.toLocaleString() : "—"}
        </span>
      ),
    },
    {
      key: "accuracy",
      header: "Precisión",
      width: "13%",
      align: "right",
      render: (m) => (
        <span className="tabular-nums">
          {m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : "—"}
        </span>
      ),
    },
  ];

  return (
    <WizardShell
      currentSlug="entrenamiento"
      canAdvance={lc.hasCompleted}
      outline={ENTRENAMIENTO_OUTLINE}
      instructions={ENTRENAMIENTO_INSTRUCTIONS}
      instructionsOpen={instructionsOpen}
      instructionsSections={openSections}
      onInstructionsToggleSection={toggleSection}
      onInstructionsClose={() => setInstructionsOpen(false)}
      onInstructionsMeasure={handleHelpMeasure}
      instructionsBannerHeight={bannerHeight}
    >
      <div className="space-y-6">
        <div
          ref={bannerRef}
          className="sticky top-0 z-20 -mx-8 -mt-6 border-b bg-background/95 px-8 py-4 backdrop-blur supports-[backdrop-filter]:bg-background/80"
        >
          <h1 className="text-2xl font-semibold tracking-tight">Entrenamiento</h1>
          <p className="text-sm text-muted-foreground">
            Lanza un entrenamiento a partir de una carga de datos completada.
            Puedes encadenar varios entrenamientos; cada uno aparecerá en el
            catálogo de abajo y estará disponible en el paso de{" "}
            <b>Generación</b>.
          </p>
          {lc.activeId && lc.active && (
            <div className="mt-3 flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Nombre:</span>
              <EditableName
                name={lc.active.model_name || lc.active.model_id}
                existingNames={lc.list.map((x) => x.model_name || x.model_id)}
                onSave={(name) => lc.rename(lc.active!.model_id, name)}
                size="sm"
              />
            </div>
          )}
          {!instructionsOpen && (
            // Yellow "Manual de instrucciones" button on the banner's right
            // edge — matches the placement and styling used on the
            // Inspección page so the manual UX feels consistent across the
            // wizard.
            <button
              type="button"
              onClick={() => setInstructionsOpen(true)}
              aria-label="Abrir manual de instrucciones"
              className="absolute right-8 top-1/2 flex -translate-y-1/2 items-center gap-2 rounded-lg bg-[#FFDB00] px-4 py-2.5 text-sm font-bold text-[#00215C] shadow-md transition-colors hover:bg-[#f0cf00]"
            >
              <BookOpen className="h-5 w-5" />
              Manual de instrucciones
            </button>
          )}
        </div>

        <WorkflowGroup
          id="preparacion"
          label="Preparación"
          open={openSections.preparacion ?? true}
          onOpenChange={(o) => setSectionOpen("preparacion", o)}
          className="scroll-mt-24"
          style={helpGap("preparacion")}
        >
          <div id="nuevo-entrenamiento" className="scroll-mt-24">
            <Card>
              <CardContent className="flex flex-col gap-3 p-4">
                <div className="flex flex-col gap-3 md:flex-row md:items-end">
                  <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
                    <Sparkles className="h-5 w-5" />
                  </div>
                  <div className="min-w-0 flex-1 space-y-2">
                    <div className="flex items-center gap-2">
                      <Label>Nuevo entrenamiento</Label>
                      <Tooltip content="Elige primero la fuente: datos cargados (las reglas de rules.yaml se aplican en vivo durante el entrenamiento) o una ejecución del histórico de Configuración (BRC) cuyo dataset ya tiene las reglas PRE aplicadas." />
                    </div>
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
                              "rounded px-3 py-1.5 font-medium transition-colors disabled:opacity-50",
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
                          </button>
                        );
                      })}
                    </div>
                    {trainingSource === "upload" ? (
                      inspectionsQuery.isLoading ? (
                        <Skeleton className="h-9 w-full" />
                      ) : completedInspections.length === 0 ? (
                        <p className="text-sm text-destructive">
                          No hay cargas de datos completadas. Vuelve al paso{" "}
                          <b>Carga de Datos</b>.
                        </p>
                      ) : (
                        <select
                          id="inspection-select"
                          value={selectedInspectionId}
                          onChange={(e) => setSelectedInspectionId(e.target.value)}
                          className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs"
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
                        </select>
                      )
                    ) : brcsQuery.isLoading ? (
                      <Skeleton className="h-9 w-full" />
                    ) : completedBrcs.length === 0 ? (
                      <p className="text-sm text-destructive">
                        No hay ejecuciones BRC completadas. Crea una en{" "}
                        <b>Configuración</b> o entrena desde datos cargados.
                      </p>
                    ) : (
                      <select
                        id="brc-select"
                        value={selectedBrcId}
                        onChange={(e) => setSelectedBrcId(e.target.value)}
                        className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs"
                      >
                        {completedBrcs.map((b) => {
                          const uploadLabel =
                            inspectionNameById[b.inspection_id] || b.inspection_id;
                          return (
                            <option key={b.brc_id} value={b.brc_id}>
                              {b.brc_name || b.brc_id}
                              {b.rules_count ? ` · ${b.rules_count} regla(s)` : ""}
                              {` · ${uploadLabel}`}
                            </option>
                          );
                        })}
                      </select>
                    )}
                  </div>
                </div>
                {trainingSource === "brc" && (
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
            <ConfigPanel configId="mostly_ai" />
          </div>

          <div id="ejecutar-entrenamiento" className="scroll-mt-24">
            <Card>
              <CardContent className="flex flex-col gap-2 p-4 md:flex-row md:items-center">
                <div className="flex-1 flex items-start gap-2">
                  <p className="text-sm text-muted-foreground pt-0.5">
                    Configura los parámetros del modelo y haz clic en ejecutar.
                  </p>
                  <Tooltip content="El entrenamiento creará un modelo de machine learning basado en los datos de la carga de datos seleccionada. Este modelo aprenderá patrones y será usado para generar datos sintéticos en el siguiente paso." side="left" />
                </div>
                <Button
                  type="button"
                  disabled={!effectiveInspectionId || lc.isStarting || lc.isRunning}
                  onClick={() => setStartDialogOpen(true)}
                >
                  <Play className="mr-2 h-4 w-4" />
                  {lc.isStarting
                    ? "Iniciando…"
                    : lc.isRunning
                      ? "Entrenamiento en curso…"
                      : "Iniciar entrenamiento"}
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
                      {lc.active.accuracy != null && (
                        <span className="tabular-nums">
                          Precisión: {(lc.active.accuracy * 100).toFixed(2)}%
                        </span>
                      )}
                    </div>
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
              onSelect={(id) => lc.setActiveId(id)}
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
              "Se eliminarán TODOS los modelos, incluidos los completados correctamente. Esta acción no se puede deshacer.",
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
        deleteConflict={lc.deleteConflict}
        onDeleteConflictCascade={() => lc.resolveDeleteConflict("cascade")}
        onDeleteConflictForce={() => lc.resolveDeleteConflict("force")}
        onDeleteConflictDismiss={lc.dismissDeleteConflict}
      />
    </WizardShell>
  );
}
