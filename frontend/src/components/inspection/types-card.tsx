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
import { Tooltip } from "@/components/ui/tooltip";
import { AlertTriangle } from "lucide-react";
import {
  ENCODING_TYPES,
  ENCODING_TYPE_LABELS,
  type Autodetect,
} from "@/lib/api";
import { ColumnExclusionHint } from "./column-exclusion-hint";
import { typeBadgeClass, type AutodetectQuery } from "./utils";

export function TypesCard({
  query,
  draft,
  setDraft,
  dirtyVsSaved,
  differsFromOriginal,
  originalAvailable,
  onSave,
  onRestoreAutodetected,
  onDiscardChanges,
  isSaving,
  onExcludeColumn,
  isExcluding,
  onToggleTrainingExclusion,
  isTogglingExclusion,
}: {
  query: AutodetectQuery;
  draft: Autodetect | null;
  setDraft: (value: Autodetect | null) => void;
  dirtyVsSaved: boolean;
  differsFromOriginal: boolean;
  originalAvailable: boolean;
  onSave: () => void;
  onRestoreAutodetected: () => void;
  onDiscardChanges: () => void;
  isSaving: boolean;
  onExcludeColumn: (table: string, col: string) => void;
  isExcluding: boolean;
  onToggleTrainingExclusion: (
    table: string,
    col: string,
    excluded: boolean,
  ) => void;
  isTogglingExclusion: boolean;
}) {
  const updateType = (table: string, column: string, type: string) => {
    if (!draft) return;
    const next = structuredClone(draft);
    next.encoding_types[table][column] = type;
    setDraft(next);
  };

  const [expanded, setExpanded] = useState(false);

  const warningsByColumn = new Map(
    (draft?.warnings ?? []).map((w) => [`${w.table}::${w.column}`, w]),
  );
  const warningCount = draft?.warnings?.length ?? 0;
  const isExcludedFromTraining = (table: string, col: string) =>
    (draft?.excluded_columns?.[table] ?? []).includes(col);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">Tipos de Codificación</CardTitle>
            <ColumnExclusionHint compact immediate />
            {warningCount > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/70 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-950/30 dark:text-amber-400">
                <AlertTriangle className="h-3 w-3" />
                {warningCount}{" "}
                {warningCount === 1 ? "columna marcada" : "columnas marcadas"}
              </span>
            )}
          </div>
          <CardDescription>
            Edita el tipo MostlyAI de cada columna. Usa × para excluir una
            columna.
          </CardDescription>
        </div>
        <CollapseToggle
          open={expanded}
          onToggle={() => setExpanded((v) => !v)}
          ariaLabel={expanded ? "Contraer tipos" : "Expandir tipos"}
        />
      </CardHeader>
      {expanded && (
        <CardContent className="space-y-6">
          {query.isLoading && <Skeleton className="h-24 w-full" />}
          {query.isError && (
            <p className="text-sm text-destructive">
              No se pudo cargar autodetect.json.
            </p>
          )}
          {draft &&
            Object.entries(draft.encoding_types).map(([table, columns]) => (
              <div key={table}>
                <h3 className="mb-2 font-mono text-sm font-medium">{table}</h3>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(columns).map(([col, type]) => {
                    const warning = warningsByColumn.get(`${table}::${col}`);
                    const excluded = isExcludedFromTraining(table, col);
                    return (
                      <label
                        key={col}
                        className={
                          "flex items-center gap-2 rounded-md border bg-card px-2 py-1 text-xs " +
                          (warning
                            ? "border-amber-500/70 bg-amber-50 dark:bg-amber-950/30 "
                            : "") +
                          (excluded ? "opacity-60" : "")
                        }
                      >
                        {warning && (
                          <Tooltip content={warning.message} side="top">
                            <AlertTriangle className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
                          </Tooltip>
                        )}
                        <span
                          className={
                            "font-mono " + (excluded ? "line-through" : "")
                          }
                        >
                          {col}
                        </span>
                        <select
                          value={type}
                          disabled={excluded}
                          onChange={(e) =>
                            updateType(table, col, e.target.value)
                          }
                          className={
                            "rounded border px-1.5 py-0.5 text-[10px] font-medium focus:outline-none focus:ring-1 focus:ring-ring disabled:opacity-50 " +
                            typeBadgeClass(type)
                          }
                        >
                          {ENCODING_TYPES.map((t) => (
                            <option key={t} value={t}>
                              {ENCODING_TYPE_LABELS[t] ?? t}
                            </option>
                          ))}
                        </select>
                        {warning && (
                          <span
                            className="flex items-center gap-1 text-[10px] text-muted-foreground"
                            title="Excluir esta columna del entreno (reversible)"
                          >
                            <input
                              type="checkbox"
                              checked={excluded}
                              disabled={isTogglingExclusion}
                              onChange={(e) =>
                                onToggleTrainingExclusion(
                                  table,
                                  col,
                                  e.target.checked,
                                )
                              }
                              className="h-3 w-3 accent-amber-600"
                            />
                            Excluir
                          </span>
                        )}
                        <button
                          type="button"
                          title={`Excluir '${col}' del esquema y los datos preprocesados`}
                          disabled={isExcluding}
                          onClick={(e) => {
                            e.preventDefault();
                            onExcludeColumn(table, col);
                          }}
                          className="ml-auto rounded p-0.5 text-muted-foreground/60 hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                        >
                          ×
                        </button>
                      </label>
                    );
                  })}
                </div>
              </div>
            ))}
          {draft && (
            <div className="flex flex-wrap items-center justify-end gap-2 rounded-md border bg-muted/40 px-3 py-2">
              <span className="mr-auto text-xs text-muted-foreground">
                {dirtyVsSaved
                  ? "Hay cambios sin guardar en tipos."
                  : differsFromOriginal
                    ? "Tipos modificados respecto a la autodetección."
                    : "Tipos sincronizados con la autodetección."}
              </span>
              {differsFromOriginal && originalAvailable && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={onRestoreAutodetected}
                >
                  Restaurar autodetectado
                </Button>
              )}
              {dirtyVsSaved && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={onDiscardChanges}
                >
                  Descartar cambios
                </Button>
              )}
              <Button
                type="button"
                size="sm"
                onClick={onSave}
                disabled={!dirtyVsSaved || isSaving}
              >
                {isSaving ? "Guardando…" : "Guardar tipos"}
              </Button>
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
