"use client";

import { Trash2, XCircle } from "lucide-react";
import { DownloadMenu } from "@/components/pipeline-step/download-menu";
import { EditableName } from "@/components/jobs/editable-name";
import { Badge } from "@/components/ui/badge";
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
import { statusBadgeVariant, translateStatus } from "@/lib/job-status";
import { cn, formatDuration, formatJobDate } from "@/lib/utils";

// Catalogue of every inspection on the server. Click a row to load that
// inspection's schema/profiling into the page; the per-row × deletes (or
// cancels, if the run is in flight). Cleanup/purge buttons act on the whole
// list at once.
export function HistoryCard({
  inspections,
  isLoading,
  isError,
  activeId,
  onSelect,
  onDelete,
  onRename,
  onCleanup,
  onPurge,
  onCancel,
  isDeleting,
  isCleaning,
  isPurging,
  isCancelling,
}: {
  inspections: InspectionSummary[];
  isLoading: boolean;
  isError: boolean;
  activeId: string | null;
  onSelect: (id: string) => void;
  onDelete: (id: string) => void;
  onRename: (id: string, name: string) => Promise<void>;
  onCleanup: () => void;
  onPurge: () => void;
  onCancel: (id: string) => void;
  isDeleting: boolean;
  isCleaning: boolean;
  isPurging: boolean;
  isCancelling: boolean;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between space-y-0">
        <div>
          <CardTitle className="text-base">Inspecciones previas</CardTitle>
          <CardDescription>
            Catálogo completo de inspecciones del servidor. Haz click para cargar
            una inspección pasada y ver su esquema y profiling.
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isCleaning || inspections.length === 0}
            onClick={onCleanup}
          >
            <Trash2 className="mr-2 h-3.5 w-3.5" />
            Limpiar sesiones incompletas
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isPurging || inspections.length === 0}
            onClick={onPurge}
          >
            <Trash2 className="mr-2 h-3.5 w-3.5" />
            Limpiar todas las sesiones
          </Button>
        </div>
      </CardHeader>
      <CardContent>
          {isLoading && <Skeleton className="h-24 w-full" />}
          {isError && (
            <p className="text-sm text-destructive">
              No se pudo cargar el catálogo de inspecciones.
            </p>
          )}
          {!isLoading && !isError && inspections.length === 0 && (
            <p className="text-sm text-muted-foreground">
              Todavía no hay inspecciones.
            </p>
          )}
          {inspections.length > 0 && (
            // table-fixed + explicit column widths keep the actions cell on
            // screen even when the "Tablas" column has many or very long table
            // names — without it, whitespace-nowrap pushes the delete button off
            // to the right and forces horizontal scrolling.
            <Table className="table-fixed">
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[22%]">Nombre</TableHead>
                  <TableHead className="w-[10%]">Estado</TableHead>
                  <TableHead className="w-[24%]">Tablas</TableHead>
                  <TableHead className="w-[10%] text-right">Filas</TableHead>
                  <TableHead className="w-[9%] text-right">Tiempo</TableHead>
                  <TableHead className="w-[15%]">Fecha</TableHead>
                  <TableHead className="w-[10%]" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {inspections.map((i) => {
                  const isActive = i.inspection_id === activeId;
                  const tableNames = Object.keys(i.tables ?? {});
                  const totalRows = Object.values(i.tables ?? {}).reduce(
                    (a, b) => a + b,
                    0,
                  );
                  const allNames = inspections.map(
                    (x) => x.inspection_name || x.inspection_id,
                  );
                  return (
                    <TableRow
                      key={i.inspection_id}
                      onClick={() => onSelect(i.inspection_id)}
                      className={
                        "cursor-pointer " +
                        (isActive ? "bg-primary/5" : "hover:bg-accent")
                      }
                    >
                      <TableCell>
                        <div className="space-y-0.5">
                          <p
                            className="truncate font-mono text-[10px] text-muted-foreground"
                            title={i.inspection_id}
                          >
                            {i.inspection_id}
                          </p>
                          <EditableName
                            name={i.inspection_name || i.inspection_id}
                            existingNames={allNames}
                            onSave={(name) => onRename(i.inspection_id, name)}
                          />
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={statusBadgeVariant(i.status)}
                          className={cn(
                            i.status === "completed" && "!bg-blue-500/20 !text-blue-400"
                          )}
                        >
                          {translateStatus(i.status) || "—"}
                        </Badge>
                      </TableCell>
                      <TableCell
                        className="truncate font-mono text-xs"
                        title={tableNames.join(", ")}
                      >
                        {tableNames.length > 0 ? tableNames.join(", ") : "—"}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {totalRows > 0 ? totalRows.toLocaleString() : "—"}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-right tabular-nums text-xs text-muted-foreground">
                        {formatDuration(i.duration_seconds)}
                      </TableCell>
                      <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                        {formatJobDate(i.timestamp)}
                      </TableCell>
                      <TableCell
                        className="text-right"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <div className="flex items-center justify-end gap-1">
                          {i.status === "completed" && (
                            <DownloadMenu
                              ariaLabel="Descargar inspección"
                              options={[
                                {
                                  label: "Dataset preprocesado",
                                  href: `/inspections/${i.inspection_id}/download/preprocessed`,
                                },
                                {
                                  label: "Carpeta completa",
                                  href: `/inspections/${i.inspection_id}/download`,
                                },
                              ]}
                            />
                          )}
                          {i.status === "in_progress" ? (
                            <button
                              type="button"
                              aria-label="Cancelar inspección"
                              disabled={isCancelling}
                              onClick={() => onCancel(i.inspection_id)}
                              className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                            >
                              <XCircle className="h-3.5 w-3.5" />
                            </button>
                          ) : (
                            <button
                              type="button"
                              aria-label="Eliminar inspección"
                              disabled={isDeleting}
                              onClick={() => onDelete(i.inspection_id)}
                              className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                            >
                              <Trash2 className="h-3.5 w-3.5" />
                            </button>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
    </Card>
  );
}
