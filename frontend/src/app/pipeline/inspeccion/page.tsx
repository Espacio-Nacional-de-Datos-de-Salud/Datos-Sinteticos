// Inspección — step 2 of the pipeline wizard.
//
// Assumes raw files already exist on the server under backend/data/ (true
// upload lives in Ingesta, not yet implemented). Here we pick files, launch
// an inspection run, poll it to completion, then visualise the autodetected
// schema: primary keys, foreign keys, and per-column encoding types.
//
// Flow:
//   1. GET /files/                                -> server-side file list.
//   2. User selects one or more files.
//   3. Click "Iniciar Inspección" -> POST /inspections/.
//   4. Poll GET /inspections/{id} every 2s until status leaves in_progress.
//   5. On completion, GET /inspections/{id}/autodetect and render the
//      detected relationships + encoding types.
//
// All cards live under @/components/inspection. The data layer (queries,
// mutations, draft state, dirty/diff memos) is encapsulated in
// `useInspeccionPage`. This file owns nothing but UI state — selected files,
// excluded columns, and confirm-dialog flags — plus the layout that wires
// everything together.

"use client";

import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { PreprocessedPreviewCard } from "@/components/inspection/preprocessed-preview-card";
import { DetectedTablesCard } from "@/components/inspection/detected-tables-card";
import { FilePickerCard } from "@/components/inspection/file-picker-card";
import { HistoryCard } from "@/components/inspection/history-card";
import { InspectionBanner } from "@/components/inspection/inspection-banner";
import { ProfilingCard } from "@/components/inspection/profiling-card";
import { RelationshipsCard } from "@/components/inspection/relationships-card";
import { SelectionPreviewCard } from "@/components/inspection/selection-preview-card";
import { TypesCard } from "@/components/inspection/types-card";
import { useInspeccionPage } from "@/components/inspection/use-inspeccion-page";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WIZARD_BANNER_HEIGHT } from "@/components/layout/wizard-banner";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { JobProgressPanel } from "@/components/jobs/job-progress";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Tooltip } from "@/components/ui/tooltip";
import { NamePromptDialog } from "@/components/ui/name-prompt-dialog";
import { DeleteConflictDialog } from "@/components/pipeline-step/delete-conflict-dialog";
import { PurgeChoiceDialog } from "@/components/pipeline-step/purge-choice-dialog";
import { INSPECCION_INSTRUCTIONS } from "@/components/inspection/instructions-content";
import { api, API_BASE_URL, type FilePreview, type ProfilingReports } from "@/lib/api";
import { useManualOpen } from "@/lib/use-manual-open";
import { useConfirmSelect } from "@/components/pipeline-step/use-confirm-select";

const INSPECCION_OUTLINE = [
  { id: "preparacion", label: "Selección de ficheros", level: 1 },
  { id: "seleccion-ficheros", label: "Seleccionar ficheros", level: 2 },
  { id: "visualizacion-columnas", label: "Visualización y eliminación de columnas", level: 2 },
  { id: "ejecutar-carga", label: "Ejecución de la carga", level: 2 },
  { id: "resultados", label: "Autodetección", level: 1 },
  { id: "tablas-detectadas", label: "Tablas detectadas", level: 2 },
  { id: "relaciones-detectadas", label: "Relaciones detectadas", level: 2 },
  { id: "tipos-codificacion", label: "Tipos de codificación", level: 2 },
  { id: "datos-preprocesados", label: "Datos preprocesados", level: 1 },
  { id: "visualizacion-datos", label: "Visualización de datos", level: 2 },
  { id: "profiling", label: "Perfilado", level: 1 },
  { id: "informes-profiling", label: "Informes de perfilado", level: 2 },
  { id: "historial", label: "Historial", level: 1 },
  { id: "inspecciones-previas", label: "Cargas de Datos previas", level: 2 },
] as const;

export default function InspeccionPage() {
  const insp = useInspeccionPage();

  // UI-only state. Selection drives both the file picker and the preview
  // card; excluded columns are only meaningful at start time but the user
  // toggles them per-table from the preview card, hence parent ownership.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [csvDelimiter, setCsvDelimiter] = useState(",");
  // Profiling toggle for the launch — moved out of the file picker so the
  // "Iniciar inspección" action can sit below the selection preview.
  const [enableProfiling, setEnableProfiling] = useState(true);
  const [excludedColumns, setExcludedColumns] = useState<Record<string, Set<string>>>({});
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);
  // When true, the name dialog is open; the launch proceeds once the user
  // confirms a name.
  const [startDialog, setStartDialog] = useState(false);

  // Instructions manual state. Shared across pipeline pages so the manual
  // stays open as the user navigates, like a book they left open.
  const [instructionsOpen, setInstructionsOpen] = useManualOpen();
  // Open/collapsed state per page section — shared between the WorkflowGroups
  // and the help panel so the two collapse in sync.
  const [openSections, setOpenSections] = useState<Record<string, boolean>>({
    preparacion: true,
    resultados: true,
    "datos-preprocesados": false,
    profiling: false,
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

  // Server-files browsing is an advanced convenience: besides uploading their
  // own files, users can browse files already present on the server. The upload
  // component signals it as an optional/advanced option.
  const allowServerFiles = true;

  // Quick preview (columns + first rows) for the currently-selected files,
  // so the user can sanity-check what will be inspected before committing.
  // Sorted+joined so identical selection sets reuse the cache.
  const selectedKey = useMemo(
    () => Array.from(selected).sort().join("|"),
    [selected],
  );
  const selectedPreviewQuery = useQuery({
    queryKey: ["files", "preview", "rows", selectedKey, csvDelimiter],
    enabled: selected.size > 0,
    queryFn: async () => {
      const { data } = await api.post<FilePreview[]>("/files/preview", {
        paths: Array.from(selected),
        sample_rows: 50,
        include_total: true,
        csv_delimiter: csvDelimiter,
      });
      return data;
    },
  });

  // Profiling reports for the active inspection — powers the standalone
  // "Profiling" drawer (same card as the Profiling page, wired to the active
  // carga de datos instead of a separate dropdown selection).
  const profilingQuery = useQuery({
    queryKey: ["inspections", insp.inspectionId, "profiling-reports"],
    enabled: !!insp.inspectionId && insp.isCompleted,
    queryFn: async () => {
      const { data } = await api.get<ProfilingReports>(
        `/inspections/${insp.inspectionId}/profiling`,
      );
      return data;
    },
  });

  const toggleSelected = (path: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });
  };

  // After "Borrar uploads" succeeds, drop any /uploads/ paths from selection
  // so the start button can't fire against now-deleted files.
  const clearUploadsFromSelection = () => {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const p of prev) if (p.includes("/uploads/")) next.delete(p);
      return next;
    });
  };

  // Reset the Preparación form to its defaults — used when the user jumps to a
  // past run from the history, which discards whatever they were setting up.
  const resetPreparation = useCallback(() => {
    setSelected(new Set());
    setCsvDelimiter(",");
    setEnableProfiling(true);
    setExcludedColumns({});
  }, []);

  // Selecting a past carga de datos from the history loads its results and
  // resets the preparation form — gated behind a confirmation dialog.
  const selectRun = useConfirmSelect((id) => {
    insp.selectActive(id);
    resetPreparation();
  }, insp.inspectionId);

  // The file picker's start button opens the name dialog; the actual launch
  // happens once the user confirms (with an optional functional name).
  const confirmStart = (name: string) => {
    if (!startDialog) return;
    const excluded: Record<string, string[]> = {};
    for (const [table, cols] of Object.entries(excludedColumns)) {
      if (cols.size > 0) excluded[table] = Array.from(cols);
    }
    insp.startInspection({
      filePaths: Array.from(selected),
      enableProfiling,
      csvDelimiter,
      excludedColumns: excluded,
      name: name || undefined,
    });
    // Clear column exclusions after launch so the next selection starts fresh.
    setExcludedColumns({});
    setStartDialog(false);
  };

  return (
    <WizardShell
      currentSlug="inspeccion"
      canAdvance={insp.isCompleted}
      outline={INSPECCION_OUTLINE}
      instructions={INSPECCION_INSTRUCTIONS}
      instructionsOpen={instructionsOpen}
      instructionsSections={openSections}
      onInstructionsToggleSection={toggleSection}
      onInstructionsClose={() => setInstructionsOpen(false)}
      onInstructionsMeasure={handleHelpMeasure}
      instructionsBannerHeight={WIZARD_BANNER_HEIGHT}
    >
      <InspectionBanner
        inspectionId={insp.inspectionId}
        inspection={insp.inspectionQuery.data}
        existingNames={(insp.inspectionsQuery.data ?? []).map(
          (x) => x.inspection_name || x.inspection_id,
        )}
        onRename={insp.renameInspection}
        instructionsOpen={instructionsOpen}
        onOpenManual={() => setInstructionsOpen(true)}
      />
      <div className="space-y-6">
        <WorkflowGroup
          id="preparacion"
          label="Selección de ficheros"
          open={openSections.preparacion ?? true}
          onOpenChange={(o) => setSectionOpen("preparacion", o)}
          className="scroll-mt-24"
          style={helpGap("preparacion")}
        >
          <div className="space-y-4">
            <div id="seleccion-ficheros" className="scroll-mt-24">
              <FilePickerCard
                selected={selected}
                onToggleSelected={toggleSelected}
                onSelectionChange={setSelected}
                onClearUploadsFromSelection={clearUploadsFromSelection}
                allowServerFiles={allowServerFiles}
                csvDelimiter={csvDelimiter}
                onCsvDelimiterChange={setCsvDelimiter}
              />
            </div>

            <div id="visualizacion-columnas" className="scroll-mt-24">
              <SelectionPreviewCard
                previews={selected.size > 0 ? (selectedPreviewQuery.data ?? []) : []}
                hasSelection={selected.size > 0}
                isLoading={selected.size > 0 && selectedPreviewQuery.isLoading}
                isError={selected.size > 0 && selectedPreviewQuery.isError}
                csvDelimiter={csvDelimiter}
                excludedColumns={excludedColumns}
                onToggleColumn={(table, col) => {
                  setExcludedColumns((prev) => {
                    const next = { ...prev };
                    const set = new Set(next[table] ?? []);
                    if (set.has(col)) set.delete(col);
                    else set.add(col);
                    next[table] = set;
                    return next;
                  });
                }}
              />
            </div>

            <Card id="ejecutar-carga" className="scroll-mt-24">
              <CardHeader>
                <CardTitle className="text-base">Ejecución de la carga</CardTitle>
                <CardDescription>
                  Elige las opciones de análisis e inicia la carga de datos.
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-3">
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="h-4 w-4"
                    checked={enableProfiling}
                    onChange={(e) => setEnableProfiling(e.target.checked)}
                  />
                  <span>Generar informes de perfilado</span>
                </label>

                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    size="sm"
                    disabled={selected.size === 0 || insp.isStarting}
                    onClick={() => setStartDialog(true)}
                  >
                    {insp.isStarting
                      ? "Iniciando…"
                      : `Iniciar Carga de Datos (${selected.size})`}
                  </Button>
                  <Tooltip content="Analiza los archivos seleccionados para detectar automáticamente tablas, relaciones y tipos de datos. El sistema identificará claves primarias, foráneas y otros patrones en tus datos." side="right" />
                </div>

                {/* Run progress lives here (not in the banner) so the top bar
                    stays consistent with the other wizard steps. */}
                {insp.inspectionId && insp.inspectionQuery.data && (
                  <div className="space-y-1">
                    <JobProgressPanel
                      status={insp.inspectionQuery.data.status}
                      progress={insp.inspectionQuery.data.progress}
                      startedAtMs={insp.inspectionQuery.data.started_at_ms ?? null}
                      errorMessage={insp.inspectionQuery.data.error_message}
                    />
                    {insp.inspectionQuery.data.file_paths.length > 0 && (
                      <p className="text-xs text-muted-foreground">
                        {insp.inspectionQuery.data.file_paths.length} fichero(s)
                        en la carga de datos.
                      </p>
                    )}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>
        </WorkflowGroup>

        <WorkflowGroup
          id="resultados"
          label="Autodetección"
          open={openSections.resultados ?? true}
          onOpenChange={(o) => setSectionOpen("resultados", o)}
          className="scroll-mt-24"
          style={helpGap("resultados")}
        >
          <div id="tablas-detectadas" className="scroll-mt-24">
            <DetectedTablesCard
              inspectionId={insp.inspectionId}
              inspection={insp.inspectionQuery.data}
              isLoading={insp.inspectionQuery.isLoading}
              isError={insp.inspectionQuery.isError}
            />
          </div>

          {insp.isCompleted && (
            <>
              <div id="relaciones-detectadas" className="scroll-mt-24">
                <RelationshipsCard
                  query={insp.autodetectQuery}
                  draft={insp.draft}
                  setDraft={insp.setDraft}
                  originalAvailable={insp.originalAvailable}
                  {...insp.relationships}
                />
              </div>
              <div id="tipos-codificacion" className="scroll-mt-24">
                <TypesCard
                  query={insp.autodetectQuery}
                  draft={insp.draft}
                  setDraft={insp.setDraft}
                  originalAvailable={insp.originalAvailable}
                  {...insp.types}
                />
              </div>
            </>
          )}
        </WorkflowGroup>

        <WorkflowGroup
          id="datos-preprocesados"
          label="Datos preprocesados"
          open={openSections["datos-preprocesados"] ?? false}
          onOpenChange={(o) => setSectionOpen("datos-preprocesados", o)}
          className="scroll-mt-24"
          style={helpGap("datos-preprocesados")}
        >
          <div id="visualizacion-datos" className="scroll-mt-24">
            {insp.isCompleted && insp.inspectionId ? (
              <PreprocessedPreviewCard inspectionId={insp.inspectionId} />
            ) : (
              <p className="text-sm text-muted-foreground">
                Inicia y completa una carga de datos para ver los datos
                preprocesados.
              </p>
            )}
          </div>
        </WorkflowGroup>

        <WorkflowGroup
          id="profiling"
          label="Perfilado"
          open={openSections.profiling ?? false}
          onOpenChange={(o) => setSectionOpen("profiling", o)}
          className="scroll-mt-24"
          style={helpGap("profiling")}
        >
          <div id="informes-profiling" className="scroll-mt-24">
            <ProfilingCard
              inspectionId={
                insp.isCompleted ? (insp.inspectionId ?? null) : null
              }
              query={{
                data: profilingQuery.data,
                isLoading: profilingQuery.isLoading,
                isError: profilingQuery.isError,
              }}
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
          <div id="inspecciones-previas" className="scroll-mt-24">
            <HistoryCard
              inspections={insp.inspectionsQuery.data ?? []}
              isLoading={insp.inspectionsQuery.isLoading}
              isError={insp.inspectionsQuery.isError}
              activeId={insp.inspectionId}
              onSelect={selectRun.request}
              onDelete={(id) => setConfirmDelete(id)}
              onRename={insp.renameInspection}
              onCleanup={() => setConfirmCleanup(true)}
              onPurge={() => setConfirmPurge(true)}
              onCancel={insp.cancelInspection}
              isDeleting={insp.isDeleting}
              isCleaning={insp.isCleaning}
              isPurging={insp.isPurging}
              isCancelling={insp.isCancelling}
            />
          </div>
        </WorkflowGroup>

        <ConfirmDialog
          open={selectRun.pendingId !== null}
          title="¿Ver una carga de datos anterior?"
          description="Se cargarán sus resultados y se descartarán los cambios sin guardar en la preparación, que volverá a sus valores por defecto."
          confirmLabel="Ver carga de datos"
          onConfirm={selectRun.confirm}
          onCancel={selectRun.cancel}
        />
        <NamePromptDialog
          open={startDialog}
          title="Iniciar carga de datos"
          description="Asigna un nombre funcional a esta carga de datos para identificarla más fácilmente. Puedes dejarlo en blanco y editarlo después."
          confirmLabel="Iniciar carga de datos"
          onConfirm={confirmStart}
          onCancel={() => setStartDialog(false)}
        />
        <ConfirmDialog
          open={confirmDelete !== null}
          title="¿Eliminar carga de datos?"
          description="Se borrarán permanentemente la carpeta y todos sus artefactos (metadatos, profiling, etc.). Esta acción no se puede deshacer."
          confirmLabel="Eliminar"
          onConfirm={() => {
            if (confirmDelete) insp.deleteInspection(confirmDelete);
            setConfirmDelete(null);
          }}
          onCancel={() => setConfirmDelete(null)}
        />
        <PurgeChoiceDialog
          open={confirmPurge}
          title="¿Purgar todas las cargas de datos?"
          description="Se eliminarán TODAS las cargas de datos, incluidas las completadas correctamente. ¿Quieres eliminar también sus reglas de negocio, modelos, generaciones y evaluaciones asociadas, o dejarlas huérfanas? Esta acción no se puede deshacer."
          cascadeLabel="Purgar todo (cargas y dependencias)"
          orphanLabel="Purgar solo cargas (dejar dependencias huérfanas)"
          onCascade={() => {
            insp.purgeInspections(true);
            setConfirmPurge(false);
          }}
          onOrphan={() => {
            insp.purgeInspections(false);
            setConfirmPurge(false);
          }}
          onCancel={() => setConfirmPurge(false)}
        />
        <ConfirmDialog
          open={confirmCleanup}
          title="¿Limpiar cargas de datos?"
          description="Se borrarán permanentemente las carpetas vacías, las ejecuciones huérfanas y los duplicados exactos (mismos ficheros, ejecución más antigua). Esta acción no se puede deshacer."
          confirmLabel="Limpiar"
          onConfirm={() => {
            insp.cleanupInspections();
            setConfirmCleanup(false);
          }}
          onCancel={() => setConfirmCleanup(false)}
        />
        <DeleteConflictDialog
          open={insp.deleteConflict != null}
          message={insp.deleteConflict?.message ?? ""}
          onCascade={() => insp.resolveDeleteConflict("cascade")}
          onForce={() => insp.resolveDeleteConflict("force")}
          onCancel={insp.dismissDeleteConflict}
        />
      </div>
    </WizardShell>
  );
}
