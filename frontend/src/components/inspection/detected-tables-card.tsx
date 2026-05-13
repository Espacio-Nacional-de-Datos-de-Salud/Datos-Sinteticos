"use client";

import { useMemo } from "react";
import { EditableName } from "@/components/jobs/editable-name";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { InspectionSummary } from "@/lib/api";

// Headline result of a finished inspection: rows-per-table summary, plus
// rename + reset controls. The status while a run is in flight is shown
// separately in InspectionStatusCard.
export function DetectedTablesCard({
  inspectionId,
  inspection,
  isLoading,
  isError,
  inspections,
  onRename,
  onReset,
}: {
  inspectionId: string | null;
  inspection: InspectionSummary | undefined;
  isLoading: boolean;
  isError: boolean;
  inspections: InspectionSummary[];
  onRename: (id: string, name: string) => Promise<void>;
  onReset: () => void;
}) {
  const content = useMemo(() => {
    if (!inspectionId) {
      return (
        <p className="text-sm text-muted-foreground">
          Selecciona archivos e inicia la inspección para ver los resultados.
        </p>
      );
    }
    if (isLoading) return <Skeleton className="h-24 w-full" />;
    if (isError) return null;
    if (!inspection) return null;
    if (inspection.status === "in_progress") {
      return (
        <p className="text-sm text-muted-foreground">
          Procesando… Esto puede tardar unos segundos.
        </p>
      );
    }
    if (inspection.status === "failed") {
      return (
        <p className="text-sm text-destructive">
          La inspección falló. Revisa los logs del backend.
        </p>
      );
    }
    const tables = Object.entries(inspection.tables ?? {});
    if (tables.length === 0) {
      return (
        <p className="text-sm text-muted-foreground">
          Inspección completada pero sin tablas detectadas.
        </p>
      );
    }
    return (
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Tabla</TableHead>
            <TableHead className="text-right">Filas</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {tables.map(([name, rows]) => (
            <TableRow key={name}>
              <TableCell className="font-mono text-xs">{name}</TableCell>
              <TableCell className="text-right tabular-nums">
                {rows.toLocaleString()}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    );
  }, [inspectionId, inspection, isLoading, isError]);

  const active = inspectionId
    ? inspections.find((x) => x.inspection_id === inspectionId)
    : undefined;
  const allNames = inspections.map((x) => x.inspection_name || x.inspection_id);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Tablas Detectadas</CardTitle>
          <CardDescription>
            Resumen de tablas y nº de filas tras la inspección.
            {inspectionId && (
              <span
                className="ml-2 font-mono text-xs"
                suppressHydrationWarning
              >
                id: {inspectionId}
              </span>
            )}
          </CardDescription>
          {inspectionId && active && (
            <EditableName
              name={active.inspection_name || active.inspection_id}
              existingNames={allNames}
              onSave={(name) => onRename(inspectionId, name)}
            />
          )}
        </div>
        {inspectionId && (
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={onReset}
          >
            Nueva inspección
          </Button>
        )}
      </CardHeader>
      <CardContent>{content}</CardContent>
    </Card>
  );
}
