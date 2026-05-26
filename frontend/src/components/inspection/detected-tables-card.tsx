"use client";

import { useMemo } from "react";
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

// Headline result of a finished inspection: rows-per-table summary. The
// status while a run is in flight is shown separately in
// InspectionStatusCard, and the inspection name is edited at the page top.
export function DetectedTablesCard({
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

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Tablas Detectadas</CardTitle>
        <CardDescription>
          Resumen de tablas y nº de filas tras la inspección.
          {inspectionId && (
            <span className="ml-2 font-mono text-xs" suppressHydrationWarning>
              id: {inspectionId}
            </span>
          )}
        </CardDescription>
      </CardHeader>
      <CardContent>{content}</CardContent>
    </Card>
  );
}
