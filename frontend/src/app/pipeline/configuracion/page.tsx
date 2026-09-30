// Configuración — step 3 of the pipeline wizard.
//
// Sits between Profiling and Entrenamiento and is the place where the user
// will eventually configure the synthetic-data run. For now the main column
// is intentionally a tall placeholder so the scrolling layout can be
// verified; the work happens in the static right rail, which surfaces three
// read-only viewers off the most recently completed inspection, each in its
// own tab:
//   1. Tablas         — same component used in Inspección > "Vista previa
//                       de la selección".
//   2. Profiling      — compact ydata-profiling viewer (one report at a time,
//                       picked via a small <select> — full size is too tall
//                       for the rail; the iframe is sized to fill the box).
//   3. Relaciones     — the Mermaid ER diagram from Inspección > Relaciones
//                       detectadas.
//
// The right rail occupies ~40% of the page width with a thin grey divider,
// matching the "Manual de instrucciones" panel on the Inspección page.
//
// All three viewers read from the inspection persisted by the Inspección
// page via STORAGE_KEYS.inspection, falling back to the most recent
// completed inspection.

"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, ExternalLink, Folder, Network, Play } from "lucide-react";
import { toast } from "sonner";

import { BRCHistoryCard } from "@/components/config/brc-history-card";
import { BRCResultsCard } from "@/components/config/brc-results-card";
import { RulesBanner } from "@/components/config/rules-banner";
import { RulesLibraryBar } from "@/components/config/rules-library-bar";
import { RulesPanel } from "@/components/config/rules-editor";
import { ColumnDeletionCard } from "@/components/inspection/column-deletion-card";
import { RelationshipsGraph } from "@/components/inspection/relationships-graph";
import { SelectionPreviewCard } from "@/components/inspection/selection-preview-card";
import { SideRail } from "@/components/layout/side-rail";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WizardBanner, WIZARD_BANNER_HEIGHT } from "@/components/layout/wizard-banner";
import { AdvancedBadge } from "@/components/ui/advanced-section";
import { cn } from "@/lib/utils";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { JobProgressPanel } from "@/components/jobs/job-progress";
import { EditableName } from "@/components/jobs/editable-name";
import { ActiveRunName } from "@/components/jobs/active-run-name";
import { NamePromptDialog } from "@/components/ui/name-prompt-dialog";
import { useUpstreamSelection } from "@/components/pipeline-step/use-upstream-selection";
import { useConfirmSelect } from "@/components/pipeline-step/use-confirm-select";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import {
  api,
  API_BASE_URL,
  type Autodetect,
  type FilePreview,
  type InspectionSummary,
  type ProfilingReports,
} from "@/lib/api";
import {
  createBrc,
  listBrcs,
  renameBrc,
  type BRCSummary,
} from "@/lib/brc";
import { extractDetail } from "@/lib/errors";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { useManualOpen } from "@/lib/use-manual-open";
import { CONFIGURACION_INSTRUCTIONS } from "@/components/config/instructions-content";

const CONFIGURACION_OUTLINE = [
  { id: "biblioteca-reglas", label: "Biblioteca de reglas", level: 1 },
  { id: "columnas", label: "Crear / eliminar columnas", level: 1 },
  { id: "columnas-derivadas", label: "Columnas derivadas", level: 2 },
  { id: "columnas-eliminar", label: "Eliminar columnas", level: 2 },
  { id: "reglas-logicas", label: "Reglas lógicas / de negocio", level: 1 },
  { id: "reglas-logicas-editor", label: "Editor de reglas", level: 2 },
  { id: "resultados", label: "Preprocesamiento de datos", level: 1 },
  { id: "ejecucion-preprocesamiento", label: "Ejecución de preprocesamiento", level: 2 },
  { id: "resumen-cambios", label: "Resumen de cambios aplicados", level: 2 },
  { id: "datos-preprocesados", label: "Visualización de datos", level: 2 },
  { id: "historial", label: "Historial", level: 1 },
  { id: "ejecuciones-previas", label: "Ejecuciones previas", level: 2 },
] as const;

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

export default function ConfiguracionPage() {
  // Banner height — measured the same way as Inspección so the right-side
  // rail can pin its top edge just below the banner. We also measure the
  // height of the page's scroll container (the WizardShell's `scrollRef`
  // ancestor) so the rail can size itself to exactly that visible area —
  // using `100vh` would overflow because the app Header and wizard footer
  // sit outside the scroll container.
  // The banner is the shared fixed-height WizardBanner now, so its height is a
  // known constant (no measurement needed). We still measure the scroll
  // container height so the side rail can size itself to exactly the visible
  // area below the banner.
  const bannerHeight = WIZARD_BANNER_HEIGHT;
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const [scrollHeight, setScrollHeight] = useState<number>(0);
  // Instructions manual — opened from the banner. While open it takes over the
  // right-hand column (replacing the side rail), rendered by WizardShell as the
  // same collapsible, section-aligned panel used on Carga de Datos. The open
  // state is shared across pipeline pages so the manual stays open as the user
  // navigates, like a book they left open.
  const [instructionsOpen, setInstructionsOpen] = useManualOpen();
  useLayoutEffect(() => {
    const el = bodyRef.current;
    if (!el) return;
    // Walk up to the nearest scrollable ancestor — that's WizardShell's
    // `scrollRef` div (`overflow-auto`).
    let scrollParent: HTMLElement | null = el.parentElement;
    while (scrollParent && scrollParent !== document.body) {
      const overflowY = getComputedStyle(scrollParent).overflowY;
      if (overflowY === "auto" || overflowY === "scroll") break;
      scrollParent = scrollParent.parentElement;
    }
    const update = () => {
      if (scrollParent) {
        const sh = Math.round(scrollParent.getBoundingClientRect().height);
        setScrollHeight((prev) => (prev === sh ? prev : sh));
      }
    };
    update();
    const ro = new ResizeObserver(update);
    if (scrollParent) ro.observe(scrollParent);
    return () => ro.disconnect();
  }, []);

  // Open/collapsed state per page section — shared between the WorkflowGroups
  // and the help panel so the two collapse in sync (same pattern as Carga de
  // Datos). Defaults match each WorkflowGroup's previous `defaultOpen`.
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    "reglas-banner": false,
    "biblioteca-reglas": false,
    columnas: false,
    "reglas-logicas": false,
    resultados: false,
    historial: false,
  });
  // When a section opens, scroll the page to it — runs after the section has
  // expanded in the DOM.
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
  // spacer height ("resumen") and the per-section deficit when a help block is
  // taller than its page section.
  const [helpReserve, setHelpReserve] = useState<Record<string, number>>({});
  const handleHelpMeasure = useCallback(
    (reserve: Record<string, number>) => setHelpReserve(reserve),
    [],
  );
  // When true, the name dialog is open; the run launches once the user confirms
  // (with an optional functional name), mirroring "Iniciar carga de datos".
  const [startDialog, setStartDialog] = useState(false);
  // Clean slate on entry: the live rules editor is backed by the shared
  // rules.yaml, so stale rules from a previous upload would otherwise greet the
  // user. On every entry we reset rules.yaml to empty before showing the live
  // rules UI; `clearedOnEntry` gates that UI so the user never sees a flash of
  // the previous rules. Past rule sets remain reachable via the library / BRC
  // history (see RulesLibraryBar).
  const [clearedOnEntry, setClearedOnEntry] = useState(false);
  // When a help block is taller than its section, add the extra space as a
  // bottom margin — blank background between sections, not inside the box.
  const helpGap = (id: string): React.CSSProperties | undefined =>
    instructionsOpen && (openSections[id] ?? true) && helpReserve[id]
      ? { marginBottom: helpReserve[id] + 16 }
      : undefined;

  // Pull the last completed inspection — same pattern as Profiling/Entrenamiento.
  const inspectionsQuery = useQuery({
    queryKey: ["inspections"],
    queryFn: async () => {
      const { data } = await api.get<InspectionSummary[]>("/inspections/");
      return data;
    },
  });
  const completedInspections = useMemo(
    () =>
      [...(inspectionsQuery.data ?? [])]
        .filter((insp) => insp.status === "completed")
        .sort((a, b) => (b.timestamp ?? "").localeCompare(a.timestamp ?? "")),
    [inspectionsQuery.data],
  );
  const { selectedId: inspectionId, setSelectedId: setInspectionId } =
    useUpstreamSelection(
      completedInspections,
      "inspection_id",
      STORAGE_KEYS.inspection,
    );
  const inspection = completedInspections.find(
    (insp) => insp.inspection_id === inspectionId,
  );
  const inspectionNameById = useMemo(
    () =>
      Object.fromEntries(
        (inspectionsQuery.data ?? []).map((insp) => [
          insp.inspection_id,
          insp.inspection_name || insp.inspection_id,
        ]),
      ),
    [inspectionsQuery.data],
  );

  // Preview rows for the inspection's source files — feeds the table viewer.
  const filePaths = useMemo(
    () => inspection?.file_paths ?? [],
    [inspection?.file_paths],
  );
  const previewKey = useMemo(() => [...filePaths].sort().join("|"), [filePaths]);
  const previewQuery = useQuery({
    queryKey: ["files", "preview", "rows", previewKey],
    enabled: filePaths.length > 0,
    queryFn: async () => {
      const { data } = await api.post<FilePreview[]>("/files/preview", {
        paths: filePaths,
        sample_rows: 50,
        include_total: true,
      });
      return data;
    },
  });

  // Autodetect schema — drives the ER diagram in the relationships viewer.
  const autodetectQuery = useQuery({
    queryKey: ["autodetect", inspectionId],
    enabled: !!inspectionId,
    queryFn: async () => {
      const { data } = await api.get<Autodetect>(
        `/inspections/${inspectionId}/autodetect`,
      );
      return data;
    },
  });

  // ydata-profiling reports for the inspection.
  const profilingQuery = useQuery({
    queryKey: ["profiling-reports", inspectionId],
    enabled: !!inspectionId,
    queryFn: async () => {
      const { data } = await api.get<ProfilingReports>(
        `/inspections/${inspectionId}/profiling`,
      );
      return data;
    },
  });

  // BRC runs are a global history, like the rest of the wizard histories.
  // The upload selector above only controls which source upload a new run is
  // launched from; historical runs show their source upload in the table.
  const queryClient = useQueryClient();
  const brcRunsQuery = useQuery({
    queryKey: ["brc", "list"],
    queryFn: () => listBrcs(),
    refetchInterval: (q) => {
      const runs = (q.state.data as BRCSummary[] | undefined) ?? [];
      return runs.some((r) => !TERMINAL_STATUSES.has(r.status)) ? 2000 : false;
    },
  });
  const brcRuns = useMemo(() => brcRunsQuery.data ?? [], [brcRunsQuery.data]);
  const completedBrcs = useMemo(
    () => brcRuns.filter((r) => r.status === "completed"),
    [brcRuns],
  );
  // The active BRC configuration is NOT auto-selected on entry: each visit
  // starts with no past configuration shown (Resultados / Resumen de cambios
  // empty), matching the other steps. It's set explicitly when a run is
  // launched, or when the user picks a past run from the history (confirmed via
  // `selectRun` below). The setter always writes through to localStorage so
  // subsequent steps (Entrenamiento, Generación, Auditoría) pick up the
  // selected BRC without an explicit auto-select on this page.
  const [activeBrcId, setActiveBrcIdState] = useState<string>("");
  const setActiveBrcId = useCallback(
    (id: string) => {
      if (id) window.localStorage.setItem(STORAGE_KEYS.brc, id);
      else window.localStorage.removeItem(STORAGE_KEYS.brc);
      setActiveBrcIdState(id);
    },
    [],
  );
  const activeBrc = useMemo(
    () => brcRuns.find((r) => r.brc_id === activeBrcId),
    [brcRuns, activeBrcId],
  );
  const inProgressBrc = useMemo(
    () => brcRuns.find((r) => !TERMINAL_STATUSES.has(r.status)),
    [brcRuns],
  );

  const launchBrcMutation = useMutation({
    mutationFn: async (name?: string) => {
      if (!inspectionId) throw new Error("Selecciona una carga de datos.");
      return createBrc({
        inspection_id: inspectionId,
        enable_profiling: true,
        ...(name ? { name } : {}),
      });
    },
    onSuccess: (job) => {
      toast.success("Aplicando reglas…");
      // Optimistically select the new run so the banner progress shows up
      // even before the next poll lands.
      setActiveBrcId(job.brc_id);
      queryClient.invalidateQueries({
        queryKey: ["brc", "list"],
      });
    },
    onError: (err) =>
      toast.error(`No se pudo lanzar la ejecución: ${extractDetail(err)}`),
  });

  // Rename the active configuration (BRC). The same name shows in the History
  // table (also editable there) and in the upstream selectors of the following
  // steps, so all three stay in sync via the shared ["brc", "list"] query.
  const renameBrcMutation = useMutation({
    mutationFn: ({ brcId, name }: { brcId: string; name: string }) =>
      renameBrc(brcId, name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["brc", "list"] });
    },
    onError: (err) =>
      toast.error(`No se pudo renombrar: ${extractDetail(err)}`),
  });

  // Reset the live rules.yaml to empty once per page entry. We deliberately
  // ignore failures here (e.g. backend offline) and still render the editor so
  // the page is never blocked — the worst case is the previous rules linger.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        await api.delete("/configs/rules");
      } catch {
        // Fall through: render the editor regardless of reset outcome.
      }
      if (cancelled) return;
      queryClient.invalidateQueries({ queryKey: ["config", "rules"] });
      queryClient.invalidateQueries({ queryKey: ["rules-banner"] });
      queryClient.invalidateQueries({ queryKey: ["rules-compliance"] });
      setClearedOnEntry(true);
    })();
    return () => {
      cancelled = true;
    };
  }, [queryClient]);

  // Clean slate for column deletions too: they live on the inspection metadata
  // (rules_excluded_columns), not rules.yaml, so the reset above doesn't touch
  // them. Clear them once per entry, for the upload that resolves first — same
  // "blank on entry" semantics as the logical rules. Past deletions remain
  // recoverable via the library / BRC history (RulesLibraryBar).
  const exclusionsClearedRef = useRef(false);
  useEffect(() => {
    if (!inspectionId || exclusionsClearedRef.current) return;
    exclusionsClearedRef.current = true;
    (async () => {
      try {
        await api.put(
          `/inspections/${inspectionId}/autodetect/rules-exclusions`,
          { excluded_columns: {} },
        );
      } catch {
        // Non-fatal: leave any existing deletions in place on failure.
      }
      queryClient.invalidateQueries({ queryKey: ["autodetect", inspectionId] });
    })();
  }, [inspectionId, queryClient]);

  // Reset the Preparación to a clean slate — the same "blank on entry" clearing
  // applied to the live rules and column deletions, reused when the user jumps
  // to a past configuration from the history (which discards unsaved editing).
  const resetPreparation = useCallback(async () => {
    try {
      await api.delete("/configs/rules");
    } catch {
      // Non-fatal: keep going so the rest of the reset still runs.
    }
    queryClient.invalidateQueries({ queryKey: ["config", "rules"] });
    queryClient.invalidateQueries({ queryKey: ["rules-banner"] });
    queryClient.invalidateQueries({ queryKey: ["rules-compliance"] });
    if (inspectionId) {
      try {
        await api.put(`/inspections/${inspectionId}/autodetect/rules-exclusions`, {
          excluded_columns: {},
        });
      } catch {
        // Non-fatal: leave any existing deletions in place on failure.
      }
      queryClient.invalidateQueries({ queryKey: ["autodetect", inspectionId] });
    }
  }, [queryClient, inspectionId]);

  // Selecting a past configuration from the history loads its results (Resumen
  // de cambios / datos preprocesados) and resets the live editing — gated
  // behind a confirmation dialog.
  const selectRun = useConfirmSelect((id) => {
    setActiveBrcId(id);
    void resetPreparation();
  }, activeBrcId || null);

  return (
    <WizardShell
      currentSlug="configuracion"
      canAdvance
      outline={CONFIGURACION_OUTLINE}
      instructions={CONFIGURACION_INSTRUCTIONS}
      instructionsOpen={instructionsOpen}
      instructionsSections={openSections}
      onInstructionsToggleSection={toggleSection}
      onInstructionsClose={() => setInstructionsOpen(false)}
      onInstructionsMeasure={handleHelpMeasure}
      instructionsBannerHeight={WIZARD_BANNER_HEIGHT}
    >
      <WizardBanner
        title="Configuración y reglas de negocio"
        titleBadge={
          <AdvancedBadge tooltip="Paso avanzado y opcional: define reglas de negocio que se aplican a los datos antes de entrenar. Puedes saltártelo." />
        }
        subtitle={
          <>
            Define restricciones lógicas sobre tus datos antes de entrenar el
            modelo: relaciones entre columnas, columnas derivadas o eliminación
            de campos irrelevantes. Este paso es{" "}
            <span className="font-medium text-foreground">
              completamente opcional
            </span>{" "}
            — puedes avanzar al entrenamiento sin configurar ninguna regla.
          </>
        }
        instructionsOpen={instructionsOpen}
        onOpenManual={() => setInstructionsOpen(true)}
        info={
          <ActiveRunName
            label="de la configuración"
            name={
              activeBrc && !inProgressBrc
                ? activeBrc.brc_name || activeBrc.brc_id
                : null
            }
            placeholder="configuración aún no aplicada"
            existingNames={brcRuns.map((r) => r.brc_name || r.brc_id)}
            onSave={
              activeBrc
                ? async (name) => {
                    await renameBrcMutation.mutateAsync({
                      brcId: activeBrc.brc_id,
                      name,
                    });
                  }
                : undefined
            }
          />
        }
      />

      {/* Two-column body: scrollable main + sticky right rail. The rail takes
          exactly 40% of the wizard content area (the area between the app
          sidebar / page outline and the page's right edge) and the main
          column the remaining 60%, with `w-3/5` / `w-2/5` instead of flex
          basis so neither column resizes based on the tab content's
          intrinsic width. Thin grey divider on the left of the rail, matching
          the "Manual de instrucciones" panel on Inspección. The main column
          owns the visual gap below the banner via `pt-6`, so the rail starts
          flush against the banner and its sticky position is its natural
          position — no first-scroll jump. */}
      <div ref={bodyRef} className="flex items-start gap-0">
        <div
          className={cn(
            // The whole Reglas de negocio step is advanced/optional, but the
            // "avanzado" cue already lives in the title badge + sidebar, so the
            // working area itself stays a plain column — no wrapping box.
            "min-w-0 flex-1 space-y-6",
            // Reserve a gap before the side rail; when the manual is open the
            // rail is gone and WizardShell's panel provides its own divider.
            instructionsOpen ? "" : "mr-6",
          )}
        >
          {/* Carga de Datos selector — moved out of the banner so the top bar
              stays consistent with the other steps. It sits right before the
              live rules panel since that panel reads the cumplimiento against
              the selected carga de datos. */}
          {completedInspections.length === 0 ? (
            <p className="text-sm text-destructive">
              No hay cargas de datos completadas. Vuelve al paso{" "}
              <b>Carga de Datos</b>.
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="text-muted-foreground">Carga de Datos:</span>
              <NativeSelect
                value={inspectionId}
                onValueChange={setInspectionId}
                className="h-8 w-auto min-w-[16rem] max-w-full rounded-md px-2 font-mono text-xs"
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
              {inspection && (
                <span
                  className="font-mono text-xs text-muted-foreground"
                  suppressHydrationWarning
                >
                  id: {inspection.inspection_id}
                </span>
              )}
            </div>
          )}

          {clearedOnEntry ? (
            <>
              <div id="reglas-banner" className="scroll-mt-24" style={helpGap("reglas-banner")}>
                <RulesBanner
                  title="Reglas de negocio"
                  inspectionId={inspectionId || null}
                  forceLiveRules
                />
              </div>
              <div
                id="biblioteca-reglas"
                className="scroll-mt-24"
                style={helpGap("biblioteca-reglas")}
              >
                <RulesLibraryBar
                  inspectionId={inspectionId || null}
                  currentExcludedColumns={
                    autodetectQuery.data?.rules_excluded_columns ?? {}
                  }
                  completedBrcs={completedBrcs}
                />
              </div>
            </>
          ) : (
            <Skeleton className="h-24 w-full" />
          )}

          <WorkflowGroup
            id="columnas"
            label="Crear / eliminar columnas"
            open={openSections.columnas ?? false}
            onOpenChange={(o) => setSectionOpen("columnas", o)}
            className="scroll-mt-24"
            style={helpGap("columnas")}
          >
            <div id="columnas-derivadas" className="scroll-mt-24">
              <RulesPanel
                mode="derived"
                autodetect={autodetectQuery.data ?? null}
              />
            </div>
            <div id="columnas-eliminar" className="mt-4 scroll-mt-24">
              <ColumnDeletionCard
                inspectionId={inspectionId || null}
                autodetect={autodetectQuery.data}
                isLoading={autodetectQuery.isLoading}
                isError={autodetectQuery.isError}
                defaultOpen={false}
              />
            </div>
          </WorkflowGroup>

          <WorkflowGroup
            id="reglas-logicas"
            label="Reglas lógicas / de negocio"
            open={openSections["reglas-logicas"] ?? false}
            onOpenChange={(o) => setSectionOpen("reglas-logicas", o)}
            className="scroll-mt-24"
            style={helpGap("reglas-logicas")}
          >
            <div id="reglas-logicas-editor" className="scroll-mt-24">
              <RulesPanel
                mode="logical"
                title="Editor de reglas"
                autodetect={autodetectQuery.data ?? null}
                defaultOpen
              />
            </div>
          </WorkflowGroup>

          <WorkflowGroup
            id="resultados"
            label="Preprocesamiento de datos"
            open={openSections.resultados ?? false}
            onOpenChange={(o) => setSectionOpen("resultados", o)}
            className="scroll-mt-24"
            style={helpGap("resultados")}
          >
            <div id="ejecucion-preprocesamiento" className="scroll-mt-24">
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">
                    Ejecución de preprocesamiento
                  </CardTitle>
                  <CardDescription>
                    Aplica las columnas derivadas, las exclusiones y las reglas
                    lógicas configuradas, y genera el dataset preprocesado.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => setStartDialog(true)}
                      disabled={
                        !inspectionId ||
                        launchBrcMutation.isPending ||
                        !!inProgressBrc
                      }
                    >
                      <Play className="mr-1.5 h-3.5 w-3.5" />
                      {launchBrcMutation.isPending
                        ? "Lanzando…"
                        : inProgressBrc
                          ? "Ejecución en curso…"
                          : "Aplicar cambios configurados"}
                    </Button>
                    {activeBrc && !inProgressBrc && (
                      <div className="flex items-center gap-2 text-xs">
                        <span className="text-muted-foreground">Configuración activa:</span>
                        <EditableName
                          name={activeBrc.brc_name || activeBrc.brc_id}
                          existingNames={brcRuns.map((r) => r.brc_name || r.brc_id)}
                          onSave={async (name) => {
                            await renameBrcMutation.mutateAsync({
                              brcId: activeBrc.brc_id,
                              name,
                            });
                          }}
                        />
                      </div>
                    )}
                  </div>
                  {inProgressBrc && (
                    <JobProgressPanel
                      status={inProgressBrc.status}
                      progress={inProgressBrc.progress}
                      startedAtMs={inProgressBrc.started_at_ms ?? null}
                      errorMessage={inProgressBrc.error_message}
                    />
                  )}
                </CardContent>
              </Card>
            </div>

            {activeBrc && (
              <div id="resumen-cambios" className="mt-4 scroll-mt-24">
                <RulesBanner
                  brcId={activeBrc.brc_id}
                  title="Resumen de cambios aplicados"
                />
              </div>
            )}

            <div id="datos-preprocesados" className="mt-4 scroll-mt-24">
              <BRCResultsCard
                brc={activeBrc ?? null}
                isLoading={brcRunsQuery.isLoading}
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
            <div id="ejecuciones-previas" className="scroll-mt-24">
              <BRCHistoryCard
                runs={brcRuns}
                activeBrcId={activeBrcId || null}
                onSelectActive={selectRun.request}
                inspectionNameById={inspectionNameById}
                isLoading={brcRunsQuery.isLoading}
                isError={brcRunsQuery.isError}
                errorMessage={
                  brcRunsQuery.error instanceof Error
                    ? brcRunsQuery.error.message
                    : undefined
                }
              />
            </div>
          </WorkflowGroup>
        </div>

        {/* Right column: the collapsible + drag-resizable side rail with the
            Tablas / Profiling / Relaciones viewers. Hidden while the manual is
            open — then WizardShell renders the instructions panel in its place,
            occupying the same right-hand column. Height is pinned to exactly the
            visible area below the banner inside the scroll container — internal
            viewers scroll inside. Falls back to the viewport-based estimate
            before the scroll container is measured. */}
        {!instructionsOpen && (
          <SideRail
            storageKey="ends.ui.configRail"
            title="Resumen de la carga seleccionada"
            top={bannerHeight}
            height={
              scrollHeight
                ? `${scrollHeight - bannerHeight}px`
                : `calc(100vh - ${bannerHeight}px)`
            }
          >
            <SidePanelTabs
              hasInspection={!!inspection}
              previews={previewQuery.data ?? []}
              previewsHasSelection={filePaths.length > 0}
              previewsIsLoading={previewQuery.isLoading}
              previewsIsError={previewQuery.isError}
              inspectionId={inspectionId || null}
              profilingData={profilingQuery.data}
              profilingIsLoading={profilingQuery.isLoading}
              profilingIsError={profilingQuery.isError}
              autodetectData={autodetectQuery.data}
              autodetectIsLoading={autodetectQuery.isLoading}
              autodetectIsError={autodetectQuery.isError}
            />
          </SideRail>
        )}
      </div>

      <ConfirmDialog
        open={selectRun.pendingId !== null}
        title="¿Ver una configuración anterior?"
        description="Se cargarán sus resultados y se descartarán los cambios sin guardar en la preparación (reglas en vivo y eliminación de columnas), que volverá a sus valores por defecto."
        confirmLabel="Ver configuración"
        onConfirm={selectRun.confirm}
        onCancel={selectRun.cancel}
      />
      <NamePromptDialog
        open={startDialog}
        title="Aplicar cambios configurados"
        description="Asigna un nombre funcional a esta configuración para identificarla más fácilmente. Puedes dejarlo en blanco y editarlo después."
        confirmLabel="Aplicar cambios configurados"
        onConfirm={(name) => {
          launchBrcMutation.mutate(name || undefined);
          setStartDialog(false);
        }}
        onCancel={() => setStartDialog(false)}
      />
    </WizardShell>
  );
}

// The three-tab side panel. Lifted into its own component so the layout
// shell above stays readable; everything below is plain presentation that
// reads the queries the page already kicked off.
function SidePanelTabs({
  hasInspection,
  previews,
  previewsHasSelection,
  previewsIsLoading,
  previewsIsError,
  inspectionId,
  profilingData,
  profilingIsLoading,
  profilingIsError,
  autodetectData,
  autodetectIsLoading,
  autodetectIsError,
}: {
  hasInspection: boolean;
  previews: FilePreview[];
  previewsHasSelection: boolean;
  previewsIsLoading: boolean;
  previewsIsError: boolean;
  inspectionId: string | null;
  profilingData: ProfilingReports | undefined;
  profilingIsLoading: boolean;
  profilingIsError: boolean;
  autodetectData: Autodetect | undefined;
  autodetectIsLoading: boolean;
  autodetectIsError: boolean;
}) {
  return (
    <Tabs defaultValue="tablas" className="flex h-full flex-col pt-4">
      <TabsList className="w-full">
        <TabsTrigger value="tablas" className="flex items-center gap-1.5">
          <Folder className="h-3.5 w-3.5" />
          Tablas
        </TabsTrigger>
        <TabsTrigger value="profiling" className="flex items-center gap-1.5">
          <BarChart3 className="h-3.5 w-3.5" />
          Profiling
        </TabsTrigger>
        <TabsTrigger value="relaciones" className="flex items-center gap-1.5">
          <Network className="h-3.5 w-3.5" />
          Relaciones
        </TabsTrigger>
      </TabsList>

      {/* The shared scroll container for the three panels. Tabs swap content
          inside it so the rail's overflow behaviour is consistent across tabs. */}
      <TabsContent value="tablas" className="min-h-0 flex-1 overflow-y-auto pt-3">
        {!hasInspection ? (
          <EmptyHint>No hay cargas de datos completadas todavía.</EmptyHint>
        ) : (
          // Scope a smaller type scale to the table viewer so more of the
          // sample fits in the rail without changing the shared component.
          // The arbitrary variants shrink every nested utility text size
          // (text-sm → 11px, text-xs → 10px, [10px] → 9px) and the table cells.
          <div className="text-[11px] [&_.text-sm]:text-[11px] [&_.text-xs]:text-[10px] [&_.text-\[10px\]]:text-[9px] [&_.text-\[11px\]]:text-[10px] [&_td]:py-1 [&_th]:py-1">
            <SelectionPreviewCard
              previews={previews}
              hasSelection={previewsHasSelection}
              isLoading={previewsIsLoading}
              isError={previewsIsError}
              csvDelimiter=","
              excludedColumns={{}}
              onToggleColumn={() => {
                /* read-only in this viewer */
              }}
              readOnly
            />
          </div>
        )}
      </TabsContent>

      <TabsContent value="profiling" className="min-h-0 flex-1 overflow-hidden pt-3">
        {!hasInspection ? (
          <EmptyHint>No hay cargas de datos completadas todavía.</EmptyHint>
        ) : (
          <CompactProfilingViewer
            inspectionId={inspectionId}
            data={profilingData}
            isLoading={profilingIsLoading}
            isError={profilingIsError}
          />
        )}
      </TabsContent>

      <TabsContent value="relaciones" className="min-h-0 flex-1 overflow-y-auto pt-3">
        {!hasInspection ? (
          <EmptyHint>No hay cargas de datos completadas todavía.</EmptyHint>
        ) : autodetectIsLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : autodetectIsError || !autodetectData ? (
          <p className="text-sm text-destructive">
            No se pudo cargar el esquema autodetectado.
          </p>
        ) : (
          <div className="overflow-hidden [&_.text-sm]:text-[11px] [&_.text-xs]:text-[10px]">
            <RelationshipsGraph autodetect={autodetectData} direction="LR" />
          </div>
        )}
      </TabsContent>
    </Tabs>
  );
}

// Narrow-column profiling viewer. The full ProfilingCard uses h-[70vh] which
// dwarfs the rail; here we keep one report visible at a time (picked from a
// <select>) and size the iframe to fill its box rather than the viewport.
function CompactProfilingViewer({
  inspectionId,
  data,
  isLoading,
  isError,
}: {
  inspectionId: string | null;
  data: ProfilingReports | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  const reports = useMemo(() => data?.reports ?? [], [data?.reports]);
  const [active, setActive] = useState<string>("");
  // Default to the first report once the data arrives.
  const activeReport = useMemo(() => {
    if (!reports.length) return undefined;
    return reports.find((r) => r.table === active) ?? reports[0];
  }, [reports, active]);

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (isError) {
    return (
      <p className="text-sm text-destructive">
        No se pudieron cargar los informes de profiling.
      </p>
    );
  }
  if (!reports.length || !inspectionId) {
    return (
      <EmptyHint>
        Esta carga de datos no tiene informes de profiling. Lanza otra
        carga de datos con la casilla &quot;Generar informes de profiling&quot;
        activada.
      </EmptyHint>
    );
  }

  const url =
    activeReport &&
    `${API_BASE_URL}/inspections/${inspectionId}/profiling/${encodeURIComponent(activeReport.table)}`;

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex items-center gap-2">
        <NativeSelect
          value={activeReport?.table ?? ""}
          onValueChange={setActive}
          className="h-8 w-auto min-w-0 flex-1 rounded-md px-2 font-mono text-xs"
        >
          {reports.map((r) => (
            <option key={r.table} value={r.table}>
              {r.table}
            </option>
          ))}
        </NativeSelect>
        <span
          className="shrink-0 rounded border border-dashed px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-muted-foreground"
          title="Profiling sobre los datos preprocesados, antes de aplicar reglas de negocio"
        >
          pre-reglas
        </span>
        {url && (
          <a href={url} target="_blank" rel="noreferrer">
            <Button variant="outline" size="sm" type="button">
              <ExternalLink className="mr-1.5 h-3.5 w-3.5" />
              Abrir
            </Button>
          </a>
        )}
      </div>
      {url && (
        // Sized to fill the tab's available height/width exactly so the
        // report stays within the rail; the iframe handles its own internal
        // scroll for the (much taller) profile content. The iframe is also
        // CSS-zoomed out (scale 0.65) so a much wider/longer chunk of the
        // ydata-profiling layout is visible at once — we can't reach inside
        // the sandboxed document to change fonts, so we scale it from the
        // outside and oversize the iframe (1/0.65 ≈ 153.85%) to compensate
        // for the shrink. Sandboxed exactly as in ProfilingCard.
        <div className="relative min-h-0 w-full flex-1 overflow-hidden rounded-md border bg-white">
          <iframe
            title={`Profiling report ${activeReport?.table ?? ""}`}
            src={url}
            sandbox="allow-scripts allow-same-origin allow-popups"
            style={{
              width: "153.85%",
              height: "153.85%",
              transform: "scale(0.65)",
              transformOrigin: "top left",
              border: 0,
              background: "white",
            }}
          />
        </div>
      )}
    </div>
  );
}

function EmptyHint({ children }: { children: React.ReactNode }) {
  return (
    <p className="rounded-md border border-dashed px-3 py-4 text-xs text-muted-foreground">
      {children}
    </p>
  );
}
