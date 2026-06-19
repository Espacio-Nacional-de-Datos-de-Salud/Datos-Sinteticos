"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import yaml from "js-yaml";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button, buttonVariants } from "@/components/ui/button";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import {
  brcProfilingReportUrl,
  getBrcPreview,
  getBrcProfiling,
  getBrcRulesSnapshot,
  type BRCSummary,
} from "@/lib/brc";
import { BRCTableExplorerDialog } from "@/components/config/brc-table-explorer-dialog";

// Preview of the dataset produced by a BRC run. The user has two views:
//   - Full table:        every column in the preprocessed parquet.
//   - Solo nuevas:       only the columns produced by the rules.
//
// In dev mode, the headers of the "target" columns that were marked
// drop_origin in rules.yaml are still rendered here — copied from the
// inspection's processed_data so the user can see what *would* be the
// target column — but with a warning badge and tooltip that explain they
// will be dropped during PRE and reconstructed during POST. In prod the
// view is unstyled (no badges, no warning legend) since the user does
// not care about that distinction.
type Mode = "full" | "new";

type RuleEntry = {
  type?: string;
  table_target?: string;
  target_col?: string;
  origin_col?: string;
  drop_origin?: boolean;
};

export function BRCResultsCard({
  brc,
  defaultOpen = false,
}: {
  brc: BRCSummary | null;
  /** Reserved for future loading skeleton; preview query is the actual driver today. */
  isLoading?: boolean;
  defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  const [mode, setMode] = useState<Mode>("full");
  const brcId = brc?.brc_id ?? null;

  const previewQuery = useQuery({
    queryKey: ["brc", "preview", brcId, mode],
    enabled: !!brcId && brc?.status === "completed",
    queryFn: () =>
      getBrcPreview(brcId!, {
        sample_rows: 50,
        only_new_columns: mode === "new",
        include_total: true,
      }),
    // Keep the previous mode's data on screen while the new mode loads so
    // each <TablePreview> stays mounted; otherwise it unmounts on every
    // mode switch and loses its `open` state.
    placeholderData: (prev) => prev,
  });

  // Reports list lets us only render the "Ver profiling" button on tables
  // that actually produced new columns (the BRC run skips profiling for
  // tables with no novel columns) or when the user disabled profiling.
  const profilingReportsQuery = useQuery({
    queryKey: ["brc", "profiling", brcId],
    enabled: !!brcId && brc?.status === "completed",
    queryFn: () => getBrcProfiling(brcId!),
  });

  const profilingTables = useMemo(
    () => new Set((profilingReportsQuery.data?.reports ?? []).map((r) => r.table)),
    [profilingReportsQuery.data],
  );

  const rulesSnapshotQuery = useQuery({
    queryKey: ["brc", "rules-snapshot", brcId],
    enabled: !!brcId && brc?.status === "completed",
    queryFn: () => getBrcRulesSnapshot(brcId!),
  });

  // Map of {table_target: Set<target_col>} for rules with drop_origin=true.
  // These are the "objetivo" columns that exist in the upload's parquet but
  // get replaced by an aux_col during PRE. Used to draw the dev badge.
  const droppedTargetsByTable = useMemo(() => {
    const out: Record<string, Set<string>> = {};
    const yamlText = rulesSnapshotQuery.data;
    if (!yamlText) return out;
    try {
      const parsed = yaml.load(yamlText) as { rules?: RuleEntry[] } | null;
      for (const r of parsed?.rules ?? []) {
        if (!r?.drop_origin) continue;
        const tbl = r.table_target;
        // Derived rules use origin_col as the column that's actually
        // dropped (aux_col replaces it); inequality rules drop target_col.
        const col = r.origin_col ?? r.target_col;
        if (!tbl || !col) continue;
        (out[tbl] ??= new Set()).add(col);
      }
    } catch {
      /* malformed snapshot — ignore */
    }
    return out;
  }, [rulesSnapshotQuery.data]);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div className="min-w-0 flex-1">
          <CardTitle className="text-base">Visualización de datos</CardTitle>
          <CardDescription>
            Vista del dataset que va al entreno tras aplicar las reglas
            (fase PRE). Cambia la vista entre tabla completa y solo
            columnas nuevas creadas por las reglas.
          </CardDescription>
        </div>
        <CollapseToggle
          open={open}
          onToggle={() => setOpen((v) => !v)}
          ariaLabel={open ? "Contraer resultados" : "Expandir resultados"}
        />
      </CardHeader>
      {open && (
        <CardContent className="space-y-3">
          {!brc ? (
            <p className="text-sm text-muted-foreground">
              No hay ninguna ejecución activa. Pulsa{" "}
              <b>Aplicar reglas y preprocesar</b> para generar una.
            </p>
          ) : brc.status !== "completed" ? (
            <p className="text-sm text-muted-foreground">
              La ejecución{" "}
              <span className="font-mono">{brc.brc_name || brc.brc_id}</span>{" "}
              aún no ha terminado.
            </p>
          ) : (
            <>
              {(brc.warnings?.length ?? 0) > 0 && (
                <div className="space-y-1 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-400">
                  <p className="inline-flex items-center gap-1 font-medium">
                    <AlertTriangle className="h-3 w-3" />
                    Avisos de las reglas
                  </p>
                  <ul className="list-disc space-y-0.5 pl-5">
                    {brc.warnings!.map((w, i) => (
                      <li key={i}>
                        {w.table && (
                          <span className="font-mono">
                            {w.table}
                            {w.column ? `.${w.column}` : ""}
                            {": "}
                          </span>
                        )}
                        {w.message}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="flex flex-wrap items-center gap-2 text-xs">
                <span className="text-muted-foreground">Vista:</span>
                <NativeSelect
                  value={mode}
                  onValueChange={(v) => setMode(v as Mode)}
                  className="h-7 w-auto min-w-[11rem] rounded-md px-2 text-xs"
                >
                  <option value="full">Tabla completa</option>
                  <option value="new">Solo columnas nuevas</option>
                </NativeSelect>
                <span className="ml-auto inline-flex items-center gap-1 rounded-full border border-amber-300 bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-400">
                  <AlertTriangle className="h-3 w-3" />
                  Las columnas objetivo marcadas con drop_origin se muestran pero
                  no llegan al modelo (se reconstruyen en POST).
                </span>
              </div>
              {previewQuery.isLoading && <Skeleton className="h-32 w-full" />}
              {previewQuery.isError && (
                <p className="text-sm text-destructive">
                  No se pudo cargar la previsualización.
                </p>
              )}
              {previewQuery.data && (
                <div className="space-y-4">
                  {previewQuery.data.map((preview) => (
                    <TablePreview
                      key={preview.table}
                      brcId={brcId!}
                      table={preview.table}
                      columns={preview.columns}
                      rows={preview.rows}
                      totalRows={preview.total_rows ?? null}
                      newColumns={brc.new_columns?.[preview.table] ?? []}
                      droppedTargets={
                        droppedTargetsByTable[preview.table] ?? new Set()
                      }
                      showDroppedBadge
                      hasProfiling={profilingTables.has(preview.table)}
                    />
                  ))}
                </div>
              )}
            </>
          )}
        </CardContent>
      )}
    </Card>
  );
}

function TablePreview({
  brcId,
  table,
  columns,
  rows,
  totalRows,
  newColumns,
  droppedTargets,
  showDroppedBadge,
  hasProfiling,
}: {
  brcId: string;
  table: string;
  columns: string[];
  rows: string[][];
  totalRows: number | null;
  newColumns: string[];
  droppedTargets: Set<string>;
  showDroppedBadge: boolean;
  hasProfiling: boolean;
}) {
  const newColsSet = useMemo(() => new Set(newColumns), [newColumns]);
  const [open, setOpen] = useState(false);
  const [explorerOpen, setExplorerOpen] = useState(false);
  return (
    <div className="rounded-md border bg-card">
      <div className="flex items-center justify-between gap-2 border-b px-3 py-2 text-xs">
        <div className="min-w-0 flex-1">
          <span className="font-mono font-medium">{table}</span>
          <span className="ml-2 text-muted-foreground">
            {totalRows != null ? `${totalRows.toLocaleString()} filas` : "—"}
            {` · ${columns.length} columna(s)`}
            {newColumns.length > 0
              ? ` · ${newColumns.length} nueva(s)`
              : ""}
          </span>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {hasProfiling && newColumns.length > 0 && (
            <Tooltip
              content="Abre el informe ydata-profiling de esta tabla restringido a las columnas nuevas creadas por las reglas."
              side="top"
            >
              <a
                href={brcProfilingReportUrl(brcId, table)}
                target="_blank"
                rel="noopener noreferrer"
                className={buttonVariants({ size: "sm", variant: "outline" })}
              >
                Ver perfilado de columnas nuevas
              </a>
            </Tooltip>
          )}
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
      <div className="overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b bg-muted/30">
              {columns.map((col) => {
                const isNew = newColsSet.has(col);
                const isDropped = showDroppedBadge && droppedTargets.has(col);
                return (
                  <th
                    key={col}
                    className={
                      "whitespace-nowrap px-2 py-1.5 text-left font-mono font-medium " +
                      (isNew ? "bg-emerald-50 dark:bg-emerald-950/30 " : "") +
                      (isDropped ? "bg-amber-50 dark:bg-amber-950/30 " : "")
                    }
                  >
                    <span className="inline-flex items-center gap-1">
                      {col}
                      {isNew && (
                        <Tooltip
                          content="Columna producida por una regla (aux_col, duración, diferencia, etc.)."
                          side="top"
                        >
                          <span className="rounded-sm border border-emerald-400 bg-emerald-100 px-1 text-[9px] font-semibold text-emerald-800 dark:border-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                            nueva
                          </span>
                        </Tooltip>
                      )}
                      {isDropped && (
                        <Tooltip
                          content="Columna objetivo con drop_origin=true: aparece aquí copiada de la carga, pero se elimina del esquema durante PRE y se reconstruye en POST. El modelo no la ve."
                          side="top"
                        >
                          <span className="rounded-sm border border-amber-400 bg-amber-100 px-1 text-[9px] font-semibold text-amber-800 dark:border-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
                            descartada
                          </span>
                        </Tooltip>
                      )}
                    </span>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.slice(0, 50).map((row, idx) => (
              <tr key={idx} className="border-b last:border-b-0">
                {row.map((cell, j) => (
                  <td
                    key={j}
                    className="whitespace-nowrap px-2 py-1 font-mono text-[11px]"
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      )}
      {explorerOpen && (
        <BRCTableExplorerDialog
          brcId={brcId}
          table={table}
          totalRows={totalRows}
          onClose={() => setExplorerOpen(false)}
        />
      )}
    </div>
  );
}
