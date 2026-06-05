"use client";

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { BarChart3 } from "lucide-react";

import { ProfilingCard } from "@/components/inspection/profiling-card";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { useUpstreamSelection } from "@/components/pipeline-step/use-upstream-selection";
import { api, type InspectionSummary, type ProfilingReports } from "@/lib/api";
import { statusBadgeVariant, translateStatus } from "@/lib/job-status";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { cn } from "@/lib/utils";

const PROFILING_OUTLINE = [
  { id: "preparacion", label: "Preparación", level: 1 },
  { id: "seleccion-inspeccion", label: "Carga de Datos a visualizar", level: 2 },
  { id: "inspeccion-activa", label: "Carga de datos activa", level: 2 },
  { id: "resultados", label: "Resultados", level: 1 },
  { id: "informes-profiling", label: "Informes de profiling", level: 2 },
] as const;

export default function ProfilingPage() {
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
        .filter((inspection) => inspection.status === "completed")
        .sort((a, b) => (b.timestamp ?? "").localeCompare(a.timestamp ?? "")),
    [inspectionsQuery.data],
  );

  const { selectedId: selectedInspectionId, setSelectedId: setSelectedInspectionId } =
    useUpstreamSelection(completedInspections, "inspection_id", STORAGE_KEYS.inspection);

  const selectedInspection = completedInspections.find(
    (inspection) => inspection.inspection_id === selectedInspectionId,
  );

  const profilingQuery = useQuery({
    queryKey: ["profiling-reports", selectedInspectionId],
    enabled: !!selectedInspectionId,
    queryFn: async () => {
      const { data } = await api.get<ProfilingReports>(
        `/inspections/${selectedInspectionId}/profiling`,
      );
      return data;
    },
  });

  return (
    <WizardShell currentSlug="profiling" canAdvance outline={PROFILING_OUTLINE}>
      <div className="space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Profiling</h1>
          <p className="text-sm text-muted-foreground">
            Consulta y descarga los informes de profiling generados para cargas de datos completadas.
          </p>
        </div>

        <WorkflowGroup id="preparacion" label="Preparación" defaultOpen className="scroll-mt-24">
          <div id="seleccion-inspeccion" className="scroll-mt-24">
            <Card>
              <CardContent className="flex flex-col gap-4 p-4 md:flex-row md:items-end">
              <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
                <BarChart3 className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1 space-y-1">
                <Label htmlFor="profiling-inspection-select">Carga de Datos a visualizar</Label>
                {inspectionsQuery.isLoading ? (
                  <Skeleton className="h-9 w-full" />
                ) : completedInspections.length === 0 ? (
                  <p className="text-sm text-destructive">
                    No hay cargas de datos completadas con resultados disponibles todavía.
                  </p>
                ) : (
                  <select
                    id="profiling-inspection-select"
                    value={selectedInspectionId}
                    onChange={(event) => setSelectedInspectionId(event.target.value)}
                    className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs"
                  >
                    {completedInspections.map((inspection) => {
                      const tableSummary = Object.keys(inspection.tables ?? {}).join(", ");
                      return (
                        <option key={inspection.inspection_id} value={inspection.inspection_id}>
                          {inspection.inspection_name || inspection.inspection_id}
                          {tableSummary ? ` · ${tableSummary}` : ""}
                        </option>
                      );
                    })}
                  </select>
                )}
              </div>
            </CardContent>
            </Card>
          </div>

          {selectedInspection && (
            <div id="inspeccion-activa" className="scroll-mt-24">
              <Card>
              <CardContent className="flex flex-wrap items-center gap-x-6 gap-y-3 p-4 text-sm">
                <div>
                  <span className="text-muted-foreground">Carga de datos activa: </span>
                  <span className="font-medium">
                    {selectedInspection.inspection_name || selectedInspection.inspection_id}
                  </span>
                </div>
                <Badge
                  variant={statusBadgeVariant(selectedInspection.status)}
                  className={cn(
                    selectedInspection.status === "completed" && "!bg-blue-500/20 !text-blue-400"
                  )}
                >
                  {translateStatus(selectedInspection.status)}
                </Badge>
                <div className="text-muted-foreground">
                  {Object.keys(selectedInspection.tables ?? {}).length} tabla(s)
                </div>
                <div className="font-mono text-xs text-muted-foreground">
                  {selectedInspection.inspection_id}
                </div>
              </CardContent>
              </Card>
            </div>
          )}
        </WorkflowGroup>

        <WorkflowGroup id="resultados" label="Resultados" className="scroll-mt-24">
          <div id="informes-profiling" className="scroll-mt-24">
            <ProfilingCard
            inspectionId={selectedInspectionId || null}
            query={{
              data: profilingQuery.data,
              isLoading: profilingQuery.isLoading,
              isError: profilingQuery.isError,
            }}
            />
          </div>
        </WorkflowGroup>
      </div>
    </WizardShell>
  );
}
