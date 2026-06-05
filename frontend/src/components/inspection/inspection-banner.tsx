"use client";

import { JobProgressPanel } from "@/components/jobs/job-progress";
import { EditableName } from "@/components/jobs/editable-name";
import type { InspectionSummary } from "@/lib/api";

// Full-width sticky header for the Inspección page. Pinned to the top of the
// scroll container so the user always sees which inspection is active, its
// status and the tables involved while scrolling through the wizard.
export function InspectionBanner({
  inspectionId,
  inspection,
  isLoading,
  isError,
  existingNames,
  onRename,
  actions,
  rootRef,
}: {
  inspectionId: string | null;
  inspection: InspectionSummary | undefined;
  isLoading: boolean;
  isError: boolean;
  existingNames: string[];
  onRename: (id: string, name: string) => void;
  /** Optional controls rendered at the banner's top-right (e.g. manual flap). */
  actions?: React.ReactNode;
  /** Ref to the banner root, for measuring its height. */
  rootRef?: React.Ref<HTMLDivElement>;
}) {
  const tables = Object.keys(inspection?.tables ?? {});

  return (
    <div
      ref={rootRef}
      className="sticky top-0 z-20 -mx-8 -mt-6 mb-6 border-b bg-background/95 px-8 py-4 backdrop-blur supports-[backdrop-filter]:bg-background/80"
    >
      {actions && (
        <div className="absolute right-8 top-1/2 -translate-y-1/2">{actions}</div>
      )}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0 space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">Carga de Datos</h1>
          {inspectionId && inspection ? (
            <div className="flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Nombre:</span>
              <EditableName
                name={inspection.inspection_name || inspection.inspection_id}
                existingNames={existingNames}
                onSave={async (name) => onRename(inspectionId, name)}
                size="sm"
              />
              <span className="font-mono text-xs text-muted-foreground" suppressHydrationWarning>
                id: {inspectionId}
              </span>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              Aún no has iniciado una carga de datos en esta sesión.
            </p>
          )}
        </div>

        {inspectionId && inspection && (
          <div className="min-w-[16rem] flex-1 space-y-2">
            <JobProgressPanel
              status={inspection.status}
              progress={inspection.progress}
              startedAtMs={inspection.started_at_ms ?? null}
            />
            {inspection.file_paths.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {inspection.file_paths.length} fichero(s) en la carga de datos.
              </p>
            )}
            {tables.length > 0 && (
              <p className="text-xs">
                <span className="text-muted-foreground">Tablas: </span>
                <span className="font-mono">{tables.join(", ")}</span>
              </p>
            )}
          </div>
        )}
      </div>

      {inspectionId && isLoading && (
        <p className="mt-2 text-xs text-muted-foreground">Cargando estado…</p>
      )}
      {inspectionId && isError && (
        <p className="mt-2 text-xs text-destructive">
          No se pudo cargar el estado de la carga de datos.
        </p>
      )}
    </div>
  );
}
