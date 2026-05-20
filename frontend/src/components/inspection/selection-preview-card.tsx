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
import type { FilePreview } from "@/lib/api";
import { ColumnExclusionHint } from "./column-exclusion-hint";
import { TableExplorerDialog } from "./table-explorer-dialog";

// Sanity-check view of the files the user has selected. Each row shows
// columns + a 50-row sample, lets the user click columns to exclude them
// before starting the inspection, and offers a "Ver completa" button to open
// the full-paginated explorer.
export function SelectionPreviewCard({
  previews,
  isLoading,
  isError,
  csvDelimiter,
  excludedColumns,
  onToggleColumn,
}: {
  previews: FilePreview[];
  isLoading: boolean;
  isError: boolean;
  csvDelimiter: string;
  excludedColumns: Record<string, Set<string>>;
  onToggleColumn: (table: string, col: string) => void;
}) {
  return (
    <Card>
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle className="text-base">Vista previa de la selección</CardTitle>
          <ColumnExclusionHint align="right" />
        </div>
        <CardDescription>
          Revisa los datos antes de inspeccionar. Expande una tabla y pulsa una
          columna para excluirla.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {isLoading && <Skeleton className="h-24 w-full" />}
        {isError && (
          <p className="text-sm text-destructive">
            No se pudo cargar la vista previa.
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
}: {
  preview: FilePreview;
  csvDelimiter: string;
  excludedCols: Set<string>;
  onToggleColumn: (col: string) => void;
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

  const excludedCount = excludedCols.size;
  const includedColumns = preview.columns.filter((c) => !excludedCols.has(c));

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
          {/* Column inclusion toggles */}
          <div className="flex flex-wrap gap-1.5 bg-muted/20 px-3 py-2">
            <span className="mr-1 self-center text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
              Columnas
            </span>
            {preview.columns.map((col) => {
              const excluded = excludedCols.has(col);
              return (
                <button
                  key={col}
                  type="button"
                  onClick={() => onToggleColumn(col)}
                  title={excluded ? `Incluir '${col}'` : `Excluir '${col}'`}
                  className={
                    "flex items-center gap-1 rounded border px-2 py-0.5 font-mono text-[11px] transition-all " +
                    (excluded
                      ? "border-red-200 bg-red-50 text-red-400 line-through dark:border-red-900 dark:bg-red-950/30 dark:text-red-500"
                      : "border-border bg-background text-foreground hover:border-primary hover:bg-primary/5")
                  }
                >
                  <span
                    className={
                      "inline-block h-2 w-2 shrink-0 rounded-full " +
                      (excluded ? "bg-red-400" : "bg-emerald-500")
                    }
                  />
                  {col}
                </button>
              );
            })}
          </div>
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
                          if (excludedCols.has(col)) return null;
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
