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
import { AdvancedBadge, ADVANCED_CARD_CLASS } from "@/components/ui/advanced-section";
import { NativeSelect } from "@/components/ui/native-select";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import {
  AlertOctagon,
  AlertTriangle,
  CalendarClock,
  Droplet,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import {
  ENCODING_TYPES,
  ENCODING_TYPE_LABELS,
  type Autodetect,
} from "@/lib/api";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { typeBadgeClass, type AutodetectQuery } from "./utils";

// Per-`kind` styling so each flagged column reads at a glance instead of every
// warning sharing one amber triangle. The legend below the header explains the
// icons that actually appear for the current inspection.
type WarningMeta = {
  Icon: LucideIcon;
  label: string;
  // Solid color block behind the icon so it reads as a clear status dot.
  badgeClass: string;
  // Chip border + tint, with a thick colored left accent to draw the eye.
  chipClass: string;
};

const WARNING_META: Record<string, WarningMeta> = {
  incompatible_type_mix: {
    Icon: AlertOctagon,
    label: "Tipo incompatible · excluida por defecto",
    badgeClass: "bg-red-600 text-white",
    chipClass: "border-red-500 border-l-4 bg-red-50 dark:bg-red-950/40",
  },
  high_null_fraction: {
    Icon: Droplet,
    label: "Alta proporción de nulos",
    badgeClass: "bg-amber-500 text-white",
    chipClass: "border-amber-500 border-l-4 bg-amber-50 dark:bg-amber-950/40",
  },
  date_composition_candidate: {
    Icon: CalendarClock,
    label: "Posible fecha compuesta",
    badgeClass: "bg-sky-600 text-white",
    chipClass: "border-sky-500 border-l-4 bg-sky-50 dark:bg-sky-950/40",
  },
  ambiguous_date_format: {
    Icon: AlertTriangle,
    label: "Formato de fecha ambiguo",
    badgeClass: "bg-amber-500 text-white",
    chipClass: "border-amber-500 border-l-4 bg-amber-50 dark:bg-amber-950/40",
  },
};

const DEFAULT_WARNING_META: WarningMeta = {
  Icon: AlertTriangle,
  label: "Atención",
  badgeClass: "bg-amber-500 text-white",
  chipClass: "border-amber-500 border-l-4 bg-amber-50 dark:bg-amber-950/40",
};

const warningMeta = (kind: string): WarningMeta =>
  WARNING_META[kind] ?? DEFAULT_WARNING_META;

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
  const [pendingExclusion, setPendingExclusion] = useState<{
    table: string;
    col: string;
  } | null>(null);

  const warningsByColumn = new Map(
    (draft?.warnings ?? []).map((w) => [`${w.table}::${w.column}`, w]),
  );
  const warningCount = draft?.warnings?.length ?? 0;
  // Distinct kinds present, in a stable order, to drive the legend.
  const presentKinds = Object.keys(WARNING_META).filter((kind) =>
    (draft?.warnings ?? []).some((w) => w.kind === kind),
  );
  const isExcludedFromTraining = (table: string, col: string) =>
    (draft?.excluded_columns?.[table] ?? []).includes(col);

  return (
    <Card className={ADVANCED_CARD_CLASS}>
      <CardHeader className="flex flex-row items-start justify-between gap-2 space-y-0">
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">Tipos de Codificación</CardTitle>
            <AdvancedBadge tooltip="Avanzado y opcional: revisa y ajusta el tipo de codificación detectado para cada columna." />
            {warningCount > 0 && (
              <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/70 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-950/30 dark:text-amber-400">
                <AlertTriangle className="h-3 w-3" />
                {warningCount}{" "}
                {warningCount === 1 ? "columna marcada" : "columnas marcadas"}
              </span>
            )}
          </div>
          <CardDescription>
            Edita el tipo MostlyAI de cada columna. <strong>Usa el icono de papelera
              para excluir una columna.</strong>
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
          {presentKinds.length > 0 && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-md border bg-muted/40 px-3 py-2 text-[11px] text-muted-foreground">
              <span className="font-medium text-foreground">Leyenda</span>
              {presentKinds.map((kind) => {
                const meta = warningMeta(kind);
                return (
                  <span key={kind} className="inline-flex items-center gap-1.5">
                    <span
                      className={
                        "flex h-4 w-4 items-center justify-center rounded " +
                        meta.badgeClass
                      }
                    >
                      <meta.Icon className="h-3 w-3" />
                    </span>
                    {meta.label}
                  </span>
                );
              })}
            </div>
          )}
          {draft &&
            Object.entries(draft.encoding_types).map(([table, columns]) => (
              <div key={table}>
                <h3 className="mb-2 font-mono text-sm font-medium">{table}</h3>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(columns).map(([col, type]) => {
                    const warning = warningsByColumn.get(`${table}::${col}`);
                    const meta = warning ? warningMeta(warning.kind) : null;
                    const excluded = isExcludedFromTraining(table, col);
                    return (
                      <label
                        key={col}
                        className={
                          "flex items-center gap-2 rounded-md border bg-card px-2 py-1 text-xs " +
                          (meta ? meta.chipClass + " " : "") +
                          (excluded ? "opacity-60" : "")
                        }
                      >
                        {warning && meta && (
                          <Tooltip content={warning.message} side="top">
                            <span
                              className={
                                "flex h-5 w-5 items-center justify-center rounded shadow-sm " +
                                meta.badgeClass
                              }
                            >
                              <meta.Icon className="h-3.5 w-3.5" />
                            </span>
                          </Tooltip>
                        )}
                        <span
                          className={
                            "font-mono " + (excluded ? "line-through" : "")
                          }
                        >
                          {col}
                        </span>
                        <NativeSelect
                          value={type}
                          disabled={excluded}
                          onValueChange={(v) => updateType(table, col, v)}
                          className={
                            "h-6 w-auto rounded px-1.5 text-[10px] font-medium " +
                            typeBadgeClass(type)
                          }
                        >
                          {ENCODING_TYPES.map((t) => (
                            <option key={t} value={t}>
                              {ENCODING_TYPE_LABELS[t] ?? t}
                            </option>
                          ))}
                        </NativeSelect>
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
                            setPendingExclusion({ table, col });
                          }}
                          className="ml-auto rounded p-0.5 text-muted-foreground/60 hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
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
      <ConfirmDialog
        open={pendingExclusion !== null}
        title="Excluir columna permanentemente"
        description={
          pendingExclusion
            ? `'${pendingExclusion.col}' se eliminará del esquema y de los datos preprocesados de forma inmediata. Esta acción no se puede revertir con «Restaurar autodetectado»; para recuperarla tendrás que relanzar la carga.`
            : ""
        }
        confirmLabel="Excluir columna"
        onConfirm={() => {
          if (pendingExclusion) {
            onExcludeColumn(pendingExclusion.table, pendingExclusion.col);
          }
          setPendingExclusion(null);
        }}
        onCancel={() => setPendingExclusion(null)}
      />
    </Card>
  );
}
