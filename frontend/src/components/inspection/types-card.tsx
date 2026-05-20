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
import { ENCODING_TYPES, type Autodetect } from "@/lib/api";
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
}) {
  const updateType = (table: string, column: string, type: string) => {
    if (!draft) return;
    const next = structuredClone(draft);
    next.encoding_types[table][column] = type;
    setDraft(next);
  };

  const [expanded, setExpanded] = useState(false);

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">Tipos de Codificación</CardTitle>
            <ColumnExclusionHint compact immediate />
          </div>
          <CardDescription>
            Edita el tipo MostlyAI de cada columna. Usa × para excluir una columna.
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
                  {Object.entries(columns).map(([col, type]) => (
                    <label
                      key={col}
                      className="flex items-center gap-2 rounded-md border bg-card px-2 py-1 text-xs"
                    >
                      <span className="font-mono">{col}</span>
                      <select
                        value={type}
                        onChange={(e) => updateType(table, col, e.target.value)}
                        className={
                          "rounded border px-1.5 py-0.5 text-[10px] font-medium focus:outline-none focus:ring-1 focus:ring-ring " +
                          typeBadgeClass(type)
                        }
                      >
                        {ENCODING_TYPES.map((t) => (
                          <option key={t} value={t}>
                            {t.replace("TABULAR_", "")}
                          </option>
                        ))}
                      </select>
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
                  ))}
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
