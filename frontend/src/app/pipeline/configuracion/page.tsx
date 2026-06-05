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

import { useLayoutEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, ExternalLink, Folder, Network, Play } from "lucide-react";
import { toast } from "sonner";

import { BRCHistoryCard } from "@/components/config/brc-history-card";
import { BRCResultsCard } from "@/components/config/brc-results-card";
import { RulesPanel } from "@/components/config/rules-editor";
import { ColumnDeletionCard } from "@/components/inspection/column-deletion-card";
import { RelationshipsGraph } from "@/components/inspection/relationships-graph";
import { SelectionPreviewCard } from "@/components/inspection/selection-preview-card";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { JobProgressPanel } from "@/components/jobs/job-progress";
import { useUpstreamSelection } from "@/components/pipeline-step/use-upstream-selection";
import { Button } from "@/components/ui/button";
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
  brcProfilingReportUrl,
  createBrc,
  getBrcProfiling,
  listBrcs,
  type BRCProfilingReports,
  type BRCSummary,
} from "@/lib/brc";
import { extractDetail } from "@/lib/errors";
import { STORAGE_KEYS } from "@/lib/storage-keys";

const CONFIGURACION_OUTLINE = [
  { id: "columnas", label: "Crear / eliminar columnas", level: 1 },
  { id: "columnas-derivadas", label: "Columnas derivadas", level: 2 },
  { id: "columnas-eliminar", label: "Eliminar columnas", level: 2 },
  { id: "reglas-logicas", label: "Reglas lógicas / de negocio", level: 1 },
  { id: "reglas-logicas-editor", label: "Editor de reglas", level: 2 },
  { id: "resultados", label: "Resultados", level: 1 },
  { id: "datos-preprocesados", label: "Datos preprocesados", level: 2 },
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
  const bannerRef = useRef<HTMLDivElement | null>(null);
  const [bannerHeight, setBannerHeight] = useState<number>(0);
  const [scrollHeight, setScrollHeight] = useState<number>(0);
  useLayoutEffect(() => {
    const el = bannerRef.current;
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
      const h = Math.round(el.getBoundingClientRect().height);
      setBannerHeight((prev) => (prev === h ? prev : h));
      if (scrollParent) {
        const sh = Math.round(scrollParent.getBoundingClientRect().height);
        setScrollHeight((prev) => (prev === sh ? prev : sh));
      }
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    if (scrollParent) ro.observe(scrollParent);
    return () => ro.disconnect();
  }, []);

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
  const { selectedId: activeBrcId, setSelectedId: setActiveBrcId } =
    useUpstreamSelection(completedBrcs, "brc_id", STORAGE_KEYS.brc);
  const activeBrc = useMemo(
    () => brcRuns.find((r) => r.brc_id === activeBrcId),
    [brcRuns, activeBrcId],
  );
  const inProgressBrc = useMemo(
    () => brcRuns.find((r) => !TERMINAL_STATUSES.has(r.status)),
    [brcRuns],
  );

  const launchBrcMutation = useMutation({
    mutationFn: async () => {
      if (!inspectionId) throw new Error("Selecciona una carga de datos.");
      return createBrc({
        inspection_id: inspectionId,
        enable_profiling: true,
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

  // Right-rail Profiling tab: when there is an active BRC run, prefer its
  // profiling (new columns only) over the inspection's. Falls back to the
  // inspection profiling when no run is active or it has no reports.
  const brcProfilingQuery = useQuery({
    queryKey: ["brc", "profiling", activeBrcId],
    enabled: !!activeBrcId,
    queryFn: () => getBrcProfiling(activeBrcId),
  });

  return (
    <WizardShell
      currentSlug="configuracion"
      canAdvance
      outline={CONFIGURACION_OUTLINE}
    >
      {/* Sticky banner — same visual treatment as the Inspección banner.
          No bottom margin so the right rail sits flush against the banner;
          the main column adds its own top spacing below. */}
      <div
        ref={bannerRef}
        className="sticky top-0 z-20 -mx-8 -mt-6 border-b bg-background/95 px-8 py-4 backdrop-blur supports-[backdrop-filter]:bg-background/80"
      >
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0 space-y-2">
            <h1 className="text-2xl font-semibold tracking-tight">
              Configuración y reglas de negocio
            </h1>
            {completedInspections.length === 0 ? (
              <p className="text-sm text-destructive">
                No hay cargas de datos completadas. Vuelve al paso{" "}
                <b>Carga de Datos</b>.
              </p>
            ) : (
              <div className="flex flex-wrap items-center gap-2 text-sm">
                <span className="text-muted-foreground">Carga de Datos:</span>
                <select
                  value={inspectionId}
                  onChange={(e) => setInspectionId(e.target.value)}
                  className="min-w-[16rem] max-w-full rounded-md border bg-background px-2 py-1 font-mono text-xs"
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
          </div>
          {inspection && (
            <div className="min-w-[18rem] flex-1 space-y-2">
              <div className="flex items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  onClick={() => launchBrcMutation.mutate()}
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
                      : "Aplicar reglas y preprocesar"}
                </Button>
                {activeBrc && !inProgressBrc && (
                  <span className="text-xs text-muted-foreground">
                    Activa:{" "}
                    <span className="font-mono">
                      {activeBrc.brc_name || activeBrc.brc_id}
                    </span>
                  </span>
                )}
              </div>
              {inProgressBrc && (
                <JobProgressPanel
                  status={inProgressBrc.status}
                  progress={inProgressBrc.progress}
                  startedAtMs={inProgressBrc.started_at_ms ?? null}
                />
              )}
              {Object.keys(inspection.tables ?? {}).length > 0 && (
                <p className="text-xs">
                  <span className="text-muted-foreground">Tablas: </span>
                  <span className="font-mono">
                    {Object.keys(inspection.tables ?? {}).join(", ")}
                  </span>
                </p>
              )}
            </div>
          )}
        </div>
      </div>

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
      <div className="flex items-start gap-0">
        <div className="min-w-0 w-3/5 shrink-0 space-y-6 pr-6 pt-6">
          <WorkflowGroup
            id="columnas"
            label="Crear / eliminar columnas"
            defaultOpen={false}
            className="scroll-mt-24"
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
            defaultOpen={false}
            className="scroll-mt-24"
          >
            <div id="reglas-logicas-editor" className="scroll-mt-24">
              <RulesPanel
                mode="logical"
                autodetect={autodetectQuery.data ?? null}
                defaultOpen
              />
            </div>
          </WorkflowGroup>

          <WorkflowGroup
            id="resultados"
            label="Resultados"
            defaultOpen={false}
            className="scroll-mt-24"
          >
            <div id="datos-preprocesados" className="scroll-mt-24">
              <BRCResultsCard
                brc={activeBrc ?? null}
                isLoading={brcRunsQuery.isLoading}
              />
            </div>
          </WorkflowGroup>

          <WorkflowGroup
            id="historial"
            label="Historial"
            defaultOpen={false}
            className="scroll-mt-24"
          >
            <div id="ejecuciones-previas" className="scroll-mt-24">
              <BRCHistoryCard
                runs={brcRuns}
                activeBrcId={activeBrcId || null}
                onSelectActive={setActiveBrcId}
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

        <aside
          className="min-w-0 w-2/5 shrink-0 self-stretch border-l border-[#e3e9f4] bg-background pl-6 dark:border-[#23335b]"
          style={{
            position: "sticky",
            top: bannerHeight,
            alignSelf: "flex-start",
            // Pin the rail's height to exactly the visible area below the
            // banner inside the scroll container — internal viewers scroll
            // inside the tabs. Falls back to the viewport-based estimate
            // before the scroll container is measured.
            height: scrollHeight
              ? `${scrollHeight - bannerHeight}px`
              : `calc(100vh - ${bannerHeight}px)`,
          }}
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
            activeBrcId={activeBrcId || null}
            brcProfilingData={brcProfilingQuery.data}
            brcProfilingIsLoading={brcProfilingQuery.isLoading}
          />
        </aside>
      </div>
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
  activeBrcId,
  brcProfilingData,
  brcProfilingIsLoading,
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
  activeBrcId: string | null;
  brcProfilingData: BRCProfilingReports | undefined;
  brcProfilingIsLoading: boolean;
}) {
  const hasBrcProfiling = !!brcProfilingData?.reports?.length;
  // User-controlled preference. Reset whenever the active run changes by
  // keying the state on the active id (mounting a fresh useState picks the
  // sensible default for the new run without violating no-set-in-effect).
  return (
    <SidePanelTabsBody
      key={activeBrcId ?? "no-brc"}
      defaultProfilingSource={hasBrcProfiling ? "brc" : "upload"}
      hasInspection={hasInspection}
      previews={previews}
      previewsHasSelection={previewsHasSelection}
      previewsIsLoading={previewsIsLoading}
      previewsIsError={previewsIsError}
      inspectionId={inspectionId}
      profilingData={profilingData}
      profilingIsLoading={profilingIsLoading}
      profilingIsError={profilingIsError}
      autodetectData={autodetectData}
      autodetectIsLoading={autodetectIsLoading}
      autodetectIsError={autodetectIsError}
      activeBrcId={activeBrcId}
      brcProfilingData={brcProfilingData}
      brcProfilingIsLoading={brcProfilingIsLoading}
      hasBrcProfiling={hasBrcProfiling}
    />
  );
}

function SidePanelTabsBody({
  defaultProfilingSource,
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
  activeBrcId,
  brcProfilingData,
  brcProfilingIsLoading,
  hasBrcProfiling,
}: {
  defaultProfilingSource: "upload" | "brc";
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
  activeBrcId: string | null;
  brcProfilingData: BRCProfilingReports | undefined;
  brcProfilingIsLoading: boolean;
  hasBrcProfiling: boolean;
}) {
  const [profilingSource, setProfilingSource] = useState<"upload" | "brc">(
    defaultProfilingSource,
  );
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
          <div className="flex h-full min-h-0 flex-col gap-2">
            {hasBrcProfiling && (
              <div className="flex items-center gap-2 text-[11px]">
                <span className="text-muted-foreground">Fuente:</span>
                <select
                  value={profilingSource}
                  onChange={(e) =>
                    setProfilingSource(e.target.value as "upload" | "brc")
                  }
                  className="rounded-md border bg-background px-2 py-0.5 text-[11px]"
                >
                  <option value="upload">Datos de la carga</option>
                  <option value="brc">Tras reglas (columnas nuevas)</option>
                </select>
              </div>
            )}
            {profilingSource === "brc" && activeBrcId ? (
              <BrcCompactProfilingViewer
                brcId={activeBrcId}
                data={brcProfilingData}
                isLoading={brcProfilingIsLoading}
              />
            ) : (
              <CompactProfilingViewer
                inspectionId={inspectionId}
                data={profilingData}
                isLoading={profilingIsLoading}
                isError={profilingIsError}
              />
            )}
          </div>
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
        <select
          value={activeReport?.table ?? ""}
          onChange={(e) => setActive(e.target.value)}
          className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 font-mono text-xs"
        >
          {reports.map((r) => (
            <option key={r.table} value={r.table}>
              {r.table}
            </option>
          ))}
        </select>
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

// Same layout as CompactProfilingViewer but reads from the BRC run's
// profiling endpoint. Kept separate so the inspection viewer above stays
// unchanged.
function BrcCompactProfilingViewer({
  brcId,
  data,
  isLoading,
}: {
  brcId: string;
  data: BRCProfilingReports | undefined;
  isLoading: boolean;
}) {
  const reports = useMemo(() => data?.reports ?? [], [data?.reports]);
  const [active, setActive] = useState<string>("");
  const activeReport = useMemo(() => {
    if (!reports.length) return undefined;
    return reports.find((r) => r.table === active) ?? reports[0];
  }, [reports, active]);

  if (isLoading) return <Skeleton className="h-64 w-full" />;
  if (!reports.length) {
    return (
      <EmptyHint>
        Esta ejecución no tiene informes de profiling. Lanza otra ejecución
        con profiling activado.
      </EmptyHint>
    );
  }

  const url = activeReport && brcProfilingReportUrl(brcId, activeReport.table);

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex items-center gap-2">
        <select
          value={activeReport?.table ?? ""}
          onChange={(e) => setActive(e.target.value)}
          className="min-w-0 flex-1 rounded-md border bg-background px-2 py-1 font-mono text-xs"
        >
          {reports.map((r) => (
            <option key={r.table} value={r.table}>
              {r.table}
            </option>
          ))}
        </select>
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
        <div className="relative min-h-0 w-full flex-1 overflow-hidden rounded-md border bg-white">
          <iframe
            title={`BRC profiling report ${activeReport?.table ?? ""}`}
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
