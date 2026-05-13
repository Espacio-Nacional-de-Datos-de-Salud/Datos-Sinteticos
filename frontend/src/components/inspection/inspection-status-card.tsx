"use client";

import { JobProgressPanel } from "@/components/jobs/job-progress";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import type { InspectionSummary } from "@/lib/api";

// Live status of the inspection that is currently active in this session
// (the one whose id is in localStorage / page state). Shown above the results
// area so the user can watch progress while the run is in flight.
export function InspectionStatusCard({
  inspectionId,
  inspection,
  isLoading,
  isError,
}: {
  inspectionId: string | null;
  inspection: InspectionSummary | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Inspección actual</CardTitle>
        <CardDescription>
          Estado de la inspección activa en esta sesión.
          {inspectionId && (
            <span
              className="ml-2 font-mono text-xs"
              suppressHydrationWarning
            >
              id: {inspectionId}
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>
        {!inspectionId && (
          <p className="text-sm text-muted-foreground">
            Aún no has iniciado una inspección en esta sesión.
          </p>
        )}
        {inspectionId && isLoading && <Skeleton className="h-20 w-full" />}
        {inspectionId && isError && (
          <p className="text-sm text-destructive">
            No se pudo cargar el estado de la inspección.
          </p>
        )}
        {inspection && (
          <div className="space-y-3 text-sm">
            <JobProgressPanel
              status={inspection.status}
              progress={inspection.progress}
              timestamp={inspection.timestamp}
            />
            {inspection.file_paths.length > 0 && (
              <p className="text-xs text-muted-foreground">
                {inspection.file_paths.length} fichero(s) en la inspección.
              </p>
            )}
            {inspection.status === "completed" &&
              Object.keys(inspection.tables ?? {}).length > 0 && (
                <p className="text-xs">
                  <span className="text-muted-foreground">Tablas: </span>
                  <span className="font-mono">
                    {Object.keys(inspection.tables).join(", ")}
                  </span>
                </p>
              )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
