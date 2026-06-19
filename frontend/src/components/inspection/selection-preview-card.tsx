"use client";

import { useState } from "react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RotateCcw, Trash2 } from "lucide-react";
import type { FilePreview } from "@/lib/api";
import { TableExplorerDialog } from "./table-explorer-dialog";

// Sanity-check view of the files the user has selected. Each row shows
// columns + a 50-row sample, lets the user click columns to exclude them
// before starting the inspection, and offers a "Ver completa" button to open
// the full-paginated explorer.
export function SelectionPreviewCard({
  previews,
  hasSelection,
  isLoading,
  isError,
  csvDelimiter,
  excludedColumns,
  onToggleColumn,
  readOnly = false,
}: {
  previews: FilePreview[];
  /** Whether the user has any files selected — drives the empty state. */
  hasSelection: boolean;
  isLoading: boolean;
  isError: boolean;
  csvDelimiter: string;
  excludedColumns: Record<string, Set<string>>;
  onToggleColumn: (table: string, col: string) => void;
  /** When true, hides the per-column exclusion toggles and the hint badge.
   *  Used by views (e.g. Configuración right rail) where the column delete
   *  action is exposed elsewhere and would be confusing to duplicate. */
  readOnly?: boolean;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base">Visualización y eliminación de columnas</CardTitle>
        </div>
        <CardDescription>
          {readOnly
            ? "Revisa los datos. Para excluir columnas usa la sección «Eliminar columnas» del cuerpo principal."
            : <>Revisa los datos antes de inspeccionar. <strong>Expande</strong> una tabla y <strong>usa el icono de papelera</strong> para <strong>excluir una columna.</strong></>}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <Skeleton className="h-24 w-full" />}
        {isError && (
          <p className="text-sm text-destructive">
            No se pudo cargar la vista previa.
          </p>
        )}
        {!isLoading && !isError && !hasSelection && (
          <p className="text-sm text-muted-foreground">
            No hay tablas seleccionadas para inspeccionar. Selecciona uno o más
            ficheros arriba.
          </p>
        )}
        {!isLoading &&
          !isError &&
          previews.map((p) => (
            <SelectionPreviewRow
              key={p.path}
              preview={p}
              csvDelimiter={csvDelimiter}
              excludedCols={excludedColumns[p.table] ?? new Set()}
              onToggleColumn={(col) => onToggleColumn(p.table, col)}
              readOnly={readOnly}
            />
          ))}
      </CardContent>
    </Card>
  );
}

function SelectionPreviewRow({
  preview,
  csvDelimiter,
  excludedCols,
  onToggleColumn,
  readOnly,
}: {
  preview: FilePreview;
  csvDelimiter: string;
  excludedCols: Set<string>;
  onToggleColumn: (col: string) => void;
  readOnly: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [explorerOpen, setExplorerOpen] = useState(false);
  // Show the file's total row count when the backend supplied it (i.e. the
  // selection-preview call asked for include_total). The 50-row sample size
  // is an implementation detail that's not useful to surface here.
  const rowsLabel =
    preview.total_rows == null
      ? `${preview.rows.length} filas en la muestra`
      : `${preview.total_rows.toLocaleString("es-ES")} filas`;

  const excludedCount = readOnly ? 0 : excludedCols.size;
  const includedColumns = readOnly
    ? preview.columns
    : preview.columns.filter((c) => !excludedCols.has(c));

  return (
    <div className="rounded-md border">
      <div className="flex items-center justify-between gap-2 px-3 py-2">
        <div className="min-w-0 flex-1">
          <h3
            className="truncate font-mono text-sm font-medium"
            title={preview.path}
          >
            {preview.table}
          </h3>
          <p className="text-xs text-muted-foreground">
            {preview.columns.length} columnas
            {excludedCount > 0 && (
              <span className="ml-1.5 inline-flex items-center rounded-full bg-amber-100 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                {excludedCount} excluida{excludedCount !== 1 ? "s" : ""}
              </span>
            )}
            {" · "}{rowsLabel}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => setExplorerOpen(true)}
          >
            Ver completa
          </Button>
          <CollapseToggle
            open={open}
            onToggle={() => setOpen((v) => !v)}
            showLabel="Ver muestra"
            ariaLabel={
              open ? "Ocultar muestra" : "Mostrar muestra de la tabla"
            }
          />
        </div>
      </div>
      {open && (
        <div className="border-t">
          {!readOnly && (
            <div className="flex flex-wrap gap-1.5 bg-muted/20 px-3 py-2">
              <span className="mr-1 self-center text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                Columnas
              </span>
              {preview.columns.map((col) => {
                const excluded = excludedCols.has(col);
                return (
                  <span
                    key={col}
                    className={
                      "flex items-center gap-1.5 rounded-md border px-2 py-1 text-xs " +
                      (excluded
                        ? "border-destructive/40 bg-destructive/5 text-muted-foreground"
                        : "bg-card")
                    }
                  >
                    <span
                      className={
                        "font-mono " + (excluded ? "line-through" : "")
                      }
                    >
                      {col}
                    </span>
                    <button
                      type="button"
                      title={excluded ? `Incluir '${col}'` : `Excluir '${col}'`}
                      onClick={() => onToggleColumn(col)}
                      className={
                        "rounded p-0.5 " +
                        (excluded
                          ? "text-muted-foreground/70 hover:bg-foreground/10 hover:text-foreground"
                          : "text-muted-foreground/60 hover:bg-destructive/10 hover:text-destructive")
                      }
                    >
                      {excluded ? (
                        <RotateCcw className="h-3.5 w-3.5" />
                      ) : (
                        <Trash2 className="h-3.5 w-3.5" />
                      )}
                    </button>
                  </span>
                );
              })}
            </div>
          )}
          {/* Data preview table */}
          <div className="max-h-[60vh] overflow-auto bg-muted/30">
            {includedColumns.length === 0 ? (
              <p className="p-3 text-xs text-muted-foreground">
                Todas las columnas excluidas — no hay datos que mostrar.
              </p>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    {includedColumns.map((c) => (
                      <TableHead key={c} className="font-mono text-xs">
                        {c}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {preview.rows.length === 0 ? (
                    <TableRow>
                      <TableCell
                        colSpan={Math.max(1, includedColumns.length)}
                        className="text-xs text-muted-foreground"
                      >
                        Sin filas para mostrar.
                      </TableCell>
                    </TableRow>
                  ) : (
                    preview.rows.map((row, i) => (
                      <TableRow key={i}>
                        {preview.columns.map((col, j) => {
                          if (!readOnly && excludedCols.has(col)) return null;
                          return (
                            <TableCell
                              key={j}
                              className="max-w-[220px] truncate font-mono text-xs"
                              title={row[j] ?? ""}
                            >
                              {row[j] ?? ""}
                            </TableCell>
                          );
                        })}
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            )}
          </div>
        </div>
      )}
      {explorerOpen && (
        <TableExplorerDialog
          path={preview.path}
          table={preview.table}
          totalRows={preview.total_rows}
          csvDelimiter={csvDelimiter}
          onClose={() => setExplorerOpen(false)}
        />
      )}
    </div>
  );
}
