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

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { RulesPanel } from "@/components/config/rules-editor";
import { DetectedTablesCard } from "@/components/inspection/detected-tables-card";
import { FilePickerCard } from "@/components/inspection/file-picker-card";
import { HistoryCard } from "@/components/inspection/history-card";
import { InspectionStatusCard } from "@/components/inspection/inspection-status-card";
import { ProfilingCard } from "@/components/inspection/profiling-card";
import { RelationshipsCard } from "@/components/inspection/relationships-card";
import { SelectionPreviewCard } from "@/components/inspection/selection-preview-card";
import { TypesCard } from "@/components/inspection/types-card";
import { useInspeccionPage } from "@/components/inspection/use-inspeccion-page";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { api, type FilePreview } from "@/lib/api";
import { ALLOW_SERVER_FILES as ALLOW_SERVER_FILES_FLAG } from "@/lib/features";
import { useIsDev } from "@/lib/mode";

export default function InspeccionPage() {
  const insp = useInspeccionPage();

  // UI-only state. Selection drives both the file picker and the preview
  // card; excluded columns are only meaningful at start time but the user
  // toggles them per-table from the preview card, hence parent ownership.
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [excludedColumns, setExcludedColumns] = useState<Record<string, Set<string>>>({});
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);

  // Server-files browsing is a dev-only convenience: in production the user
  // can only pick files they uploaded themselves. The legacy NEXT_PUBLIC_*
  // flag still acts as an override for CI / Docker, but the runtime Dev/Prod
  // toggle is the primary on/off switch now — flip it from the header.
  const isDev = useIsDev();
  const allowServerFiles = ALLOW_SERVER_FILES_FLAG || isDev;

  // Quick preview (columns + first rows) for the currently-selected files,
  // so the user can sanity-check what will be inspected before committing.
  // Sorted+joined so identical selection sets reuse the cache.
  const selectedKey = useMemo(
    () => Array.from(selected).sort().join("|"),
    [selected],
  );
  const selectedPreviewQuery = useQuery({
    queryKey: ["files", "preview", "rows", selectedKey],
    enabled: selected.size > 0,
    queryFn: async () => {
      const { data } = await api.post<FilePreview[]>("/files/preview", {
        paths: Array.from(selected),
        // 50 rows is enough to spot column drift / encoding issues without
        // tipping the request into multi-MB payloads when many files are
        // selected at once. The drill-down container scrolls past that, and
        // the "Ver completa" dialog pages through the rest server-side.
        sample_rows: 50,
        include_total: true,
      });
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

  const handleStart = (enableProfiling: boolean) => {
    // Convert excluded-columns sets to plain string arrays for the API.
    const excluded: Record<string, string[]> = {};
    for (const [table, cols] of Object.entries(excludedColumns)) {
      if (cols.size > 0) excluded[table] = Array.from(cols);
    }
    insp.startInspection({
      filePaths: Array.from(selected),
      enableProfiling,
      excludedColumns: excluded,
    });
    // Clear column exclusions after launch so the next selection starts fresh.
    setExcludedColumns({});
  };

  return (
    <WizardShell currentSlug="inspeccion" canAdvance={insp.isCompleted}>
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Inspección</h1>
          <p className="text-sm text-muted-foreground">
            Selecciona los ficheros ya disponibles en el servidor para
            autodetectar tablas, claves y tipos.
          </p>
        </div>

        <WorkflowGroup label="Preparación">
          <div
            className={
              selected.size > 0
                ? "grid gap-4 lg:grid-cols-2 lg:items-start"
                : ""
            }
          >
            <FilePickerCard
              selected={selected}
              onToggleSelected={toggleSelected}
              onSelectionChange={setSelected}
              onClearUploadsFromSelection={clearUploadsFromSelection}
              allowServerFiles={allowServerFiles}
              isStartDisabled={selected.size === 0}
              isStarting={insp.isStarting}
              onStart={handleStart}
            />

            {selected.size > 0 && (
              <SelectionPreviewCard
                previews={selectedPreviewQuery.data ?? []}
                isLoading={selectedPreviewQuery.isLoading}
                isError={selectedPreviewQuery.isError}
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
            )}
          </div>

          <RulesPanel
            autodetect={insp.autodetectQuery.data ?? null}
            pendingFilePaths={Array.from(selected)}
          />

          {insp.inspectionId && (
            <InspectionStatusCard
              inspectionId={insp.inspectionId}
              inspection={insp.inspectionQuery.data}
              isLoading={insp.inspectionQuery.isLoading}
              isError={insp.inspectionQuery.isError}
            />
          )}
        </WorkflowGroup>

        <WorkflowGroup label="Resultados">
          <DetectedTablesCard
            inspectionId={insp.inspectionId}
            inspection={insp.inspectionQuery.data}
            isLoading={insp.inspectionQuery.isLoading}
            isError={insp.inspectionQuery.isError}
            inspections={insp.inspectionsQuery.data ?? []}
            onRename={insp.renameInspection}
            onReset={insp.resetActive}
          />

          {insp.isCompleted && (
            <>
              <RelationshipsCard
                query={insp.autodetectQuery}
                draft={insp.draft}
                setDraft={insp.setDraft}
                originalAvailable={insp.originalAvailable}
                {...insp.relationships}
              />
              <TypesCard
                query={insp.autodetectQuery}
                draft={insp.draft}
                setDraft={insp.setDraft}
                originalAvailable={insp.originalAvailable}
                {...insp.types}
              />
              <ProfilingCard
                inspectionId={insp.inspectionId}
                query={insp.profilingQuery}
              />
            </>
          )}
        </WorkflowGroup>

        <WorkflowGroup label="Historial">
          <HistoryCard
            inspections={insp.inspectionsQuery.data ?? []}
            isLoading={insp.inspectionsQuery.isLoading}
            isError={insp.inspectionsQuery.isError}
            activeId={insp.inspectionId}
            onSelect={insp.selectActive}
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
        </WorkflowGroup>

        <ConfirmDialog
          open={confirmDelete !== null}
          title="¿Eliminar inspección?"
          description="Se borrarán permanentemente la carpeta y todos sus artefactos (metadatos, profiling, etc.). Esta acción no se puede deshacer."
          confirmLabel="Eliminar"
          onConfirm={() => {
            if (confirmDelete) insp.deleteInspection(confirmDelete);
            setConfirmDelete(null);
          }}
          onCancel={() => setConfirmDelete(null)}
        />
        <ConfirmDialog
          open={confirmPurge}
          title="¿Purgar todas las inspecciones?"
          description="Se eliminarán TODAS las inspecciones, incluidas las completadas correctamente. Esta acción no se puede deshacer."
          confirmLabel="Purgar"
          onConfirm={() => {
            insp.purgeInspections();
            setConfirmPurge(false);
          }}
          onCancel={() => setConfirmPurge(false)}
        />
        <ConfirmDialog
          open={confirmCleanup}
          title="¿Limpiar inspecciones?"
          description="Se borrarán permanentemente las carpetas vacías, las ejecuciones huérfanas y los duplicados exactos (mismos ficheros, ejecución más antigua). Esta acción no se puede deshacer."
          confirmLabel="Limpiar"
          onConfirm={() => {
            insp.cleanupInspections();
            setConfirmCleanup(false);
          }}
          onCancel={() => setConfirmCleanup(false)}
        />
      </div>
    </WizardShell>
  );
}
