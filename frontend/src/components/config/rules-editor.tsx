// Side drawer to edit backend/config/rules.yaml with a structured form.
//
// Rules drive preprocessing, so this editor lives on the Inspección page.
// Available tables/columns come from the active inspection's autodetect; if
// none is available the form falls back to free-text inputs.

"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import axios from "axios";
import yaml from "js-yaml";
import { Plus, RotateCcw, Save, Settings, Trash2, X } from "lucide-react";
import {
  api,
  type Autodetect,
  type ConfigContent,
  type FilePreview,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";

type Props = {
  open: boolean;
  onClose: () => void;
  // Schema source for table/column dropdowns. Pass the autodetect of the
  // active inspection. Optional — if absent, the form uses free-text fields.
  autodetect?: Autodetect | null;
  // Paths of files already uploaded but not necessarily inspected. The editor
  // fetches their headers so dropdowns can offer pending tables too.
  pendingFilePaths?: string[];
  // ID of the rules config to edit (e.g. "rules" or "rules/custom.yaml")
  configId?: string;
  // Callback when rules are successfully saved
  onSaved?: () => void;
};

export type RuleType =
  | "date_inequality"
  | "numeric_inequality"
  | "semantic_ranking_consistency"
  | "semantic_proportional_consistency"
  | "foreign_keys_consistency_rule";

type Rule = {
  type: RuleType;
  table_origin?: string;
  origin_col?: string;
  table_target?: string;
  target_col?: string;
  aux_col?: string;
  source_col?: string;
  referenced_table?: string;
  constraint?: string | number | null;
  constraint_operator?: ">=" | "<=";
};

type RulesFile = { rules: Rule[] };

const RULE_TYPE_LABELS: Record<RuleType, string> = {
  date_inequality: "Desigualdad de fechas",
  numeric_inequality: "Desigualdad numérica",
  semantic_ranking_consistency: "Consistencia semántica (ranking)",
  semantic_proportional_consistency: "Consistencia semántica (proporcional)",
  foreign_keys_consistency_rule: "Consistencia de claves foráneas",
};

const RULE_TYPE_HELP: Record<RuleType, string> = {
  date_inequality:
    "Garantiza que una fecha objetivo cumpla un orden (≥ o ≤) respecto a una fecha origen o una constante.",
  numeric_inequality:
    "Garantiza que un valor numérico objetivo cumpla un orden (≥ o ≤) respecto a un origen o constante.",
  semantic_ranking_consistency:
    "Restringe qué combinaciones (origen, objetivo) son válidas en un categórico, con intervalos equiespaciados.",
  semantic_proportional_consistency:
    "Como el ranking, pero los intervalos respetan la frecuencia real de cada categoría.",
  foreign_keys_consistency_rule:
    "Reconstruye una FK redundante copiando el valor desde la tabla padre marcada como contexto.",
};

function extractDetail(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: string } | undefined)?.detail;
    return detail ?? err.message;
  }
  if (err instanceof Error) return err.message;
  return "Error desconocido";
}

function summarizeRule(r: Rule): string {
  const left = [r.table_origin, r.origin_col].filter(Boolean).join(".");
  const right = [r.table_target, r.target_col].filter(Boolean).join(".");
  if (r.type === "date_inequality" || r.type === "numeric_inequality") {
    const op = r.constraint_operator ?? ">=";
    const bound = r.origin_col
      ? left
      : r.constraint != null
        ? String(r.constraint)
        : "?";
    return `${right} ${op} ${bound}`;
  }
  if (r.type === "foreign_keys_consistency_rule") {
    return `${right} ← ${r.table_origin ?? "?"}.${r.source_col ?? r.target_col ?? "?"}`;
  }
  return `${left} → ${right}`;
}

export function RulesEditor({
  open,
  onClose,
  autodetect,
  pendingFilePaths,
  configId = "rules",
  onSaved,
}: Props) {
  const queryClient = useQueryClient();
  const [rules, setRules] = useState<Rule[]>([]);
  const [draftYaml, setDraftYaml] = useState<string>("");
  const [yamlMode, setYamlMode] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  const [adding, setAdding] = useState(false);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  const configQuery = useQuery({
    queryKey: ["config", configId],
    enabled: open,
    queryFn: async () => {
      const { data } = await api.get<ConfigContent>(`/configs/${encodeURIComponent(configId)}`);
      return data;
    },
  });

  // Pull headers for files that the user has uploaded but not yet inspected,
  // so the dropdowns can offer pending tables/columns alongside autodetected
  // ones. Sorted+joined into the cache key so identical sets reuse the cache.
  const pendingKey = useMemo(
    () => [...(pendingFilePaths ?? [])].sort().join("|"),
    [pendingFilePaths],
  );
  const previewQuery = useQuery({
    queryKey: ["files", "preview", "schema", pendingKey],
    enabled: open && (pendingFilePaths?.length ?? 0) > 0,
    queryFn: async () => {
      const { data } = await api.post<FilePreview[]>("/files/preview", {
        paths: pendingFilePaths ?? [],
        sample_rows: 0,
      });
      return data;
    },
  });

  useEffect(() => {
    if (!open || !configQuery.data) return;
    try {
      const parsed = (yaml.load(configQuery.data.content) as RulesFile) ?? {
        rules: [],
      };
      queueMicrotask(() => {
        setRules(parsed.rules ?? []);
        setDraftYaml(configQuery.data.content);
        setParseError(null);
      });
    } catch (e) {
      queueMicrotask(() => {
        setParseError(e instanceof Error ? e.message : String(e));
      });
    }
  }, [open, configQuery.data]);

  // Merge autodetect (inspected) and file previews (uploaded but pending).
  // Autodetect wins on column ordering for tables present in both, since
  // it reflects the post-preprocessing schema the rules will run against.
  const columnsByTable = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const p of previewQuery.data ?? []) {
      m[p.table] = [...p.columns];
    }
    for (const [t, cols] of Object.entries(autodetect?.encoding_types ?? {})) {
      m[t] = Object.keys(cols);
    }
    return m;
  }, [autodetect, previewQuery.data]);

  const tableNames = useMemo(
    () => Object.keys(columnsByTable).sort(),
    [columnsByTable],
  );

  const buildYaml = (rs: Rule[]): string =>
    yaml.dump(
      {
        rules: rs.map((r) => {
          // Prune undefined/empty optional fields so the YAML stays clean.
          const out: Record<string, unknown> = { type: r.type };
          for (const [k, v] of Object.entries(r)) {
            if (k === "type") continue;
            if (v === undefined || v === "" || v === null) continue;
            out[k] = v;
          }
          return out;
        }),
      },
      { lineWidth: 100, noRefs: true },
    );

  const switchToYaml = () => {
    setDraftYaml(buildYaml(rules));
    setYamlMode(true);
  };
  const switchToForm = () => {
    try {
      const parsed = (yaml.load(draftYaml) as RulesFile) ?? { rules: [] };
      setRules(parsed.rules ?? []);
      setYamlMode(false);
      setParseError(null);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : String(e));
    }
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const content = yamlMode ? draftYaml : buildYaml(rules);
      const { data } = await api.put<ConfigContent>(`/configs/${encodeURIComponent(configId)}`, {
        content,
      });
      return data;
    },
    onSuccess: () => {
      toast.success("Reglas guardadas");
      queryClient.invalidateQueries({ queryKey: ["config", configId] });
      if (onSaved) onSaved();
      onClose();
    },
    onError: (err) => toast.error(`No se pudo guardar: ${extractDetail(err)}`),
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      await api.delete(`/configs/${encodeURIComponent(configId)}`);
    },
    onSuccess: () => {
      toast.success("Reglas restauradas");
      queryClient.invalidateQueries({ queryKey: ["config", configId] });
    },
    onError: (err) => toast.error(`No se pudo restaurar: ${extractDetail(err)}`),
  });

  const onAddRule = (rule: Rule) => {
    setRules((prev) => [...prev, rule]);
    setAdding(false);
  };
  const onUpdateRule = (idx: number, rule: Rule) => {
    setRules((prev) => prev.map((r, i) => (i === idx ? rule : r)));
    setEditingIndex(null);
  };
  const onDeleteRule = (idx: number) => {
    setRules((prev) => prev.filter((_, i) => i !== idx));
  };

  if (!open) return null;

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/50"
        onClick={onClose}
        aria-hidden
      />
      <aside
        role="dialog"
        aria-label="Editor de reglas"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-2xl flex-col border-l bg-background shadow-xl"
      >
        <header className="flex items-start justify-between gap-4 border-b p-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Settings className="h-4 w-4" />
              <span className="font-mono">{configId.split("/").pop() || "rules.yaml"}</span>
            </div>
            <h2 className="mt-1 text-lg font-semibold">
              Reglas de preprocesamiento
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Definen restricciones que el modelo debe respetar (orden de
              fechas, consistencia entre categóricas, etc.). Se aplican durante
              la inspección y la generación.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Cerrar"
            className="rounded p-1 text-muted-foreground hover:bg-accent"
          >
            <X className="h-4 w-4" />
          </button>
        </header>

        <div className="flex items-center justify-between border-b px-4 py-2 text-xs">
          <button
            type="button"
            onClick={yamlMode ? switchToForm : switchToYaml}
            className="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            {yamlMode ? "Volver al editor visual" : "Editar como YAML"}
          </button>
          {tableNames.length === 0 && !yamlMode && (
            <span className="text-muted-foreground">
              Ejecuta una inspección para autocompletar tablas y columnas.
            </span>
          )}
          {parseError && (
            <span className="text-destructive">YAML inválido: {parseError}</span>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {configQuery.isLoading && <Skeleton className="h-64 w-full" />}
          {configQuery.isError && (
            <p className="text-sm text-destructive">
              No se pudo cargar rules.yaml: {extractDetail(configQuery.error)}
            </p>
          )}
          {configQuery.data && yamlMode && (
            <textarea
              value={draftYaml}
              onChange={(e) => setDraftYaml(e.target.value)}
              spellCheck={false}
              className="h-[60vh] w-full rounded-md border bg-muted/30 p-3 font-mono text-xs"
            />
          )}
          {configQuery.data && !yamlMode && (
            <div className="space-y-3">
              {rules.length === 0 && !adding && (
                <p className="text-sm text-muted-foreground">
                  No hay reglas definidas todavía.
                </p>
              )}
              {rules.map((r, idx) =>
                editingIndex === idx ? (
                  <RuleForm
                    key={idx}
                    initial={r}
                    tableNames={tableNames}
                    columnsByTable={columnsByTable}
                    onCancel={() => setEditingIndex(null)}
                    onSubmit={(rule) => onUpdateRule(idx, rule)}
                  />
                ) : (
                  <RuleCard
                    key={idx}
                    rule={r}
                    onEdit={() => setEditingIndex(idx)}
                    onDelete={() => onDeleteRule(idx)}
                  />
                ),
              )}
              {adding && (
                <RuleForm
                  tableNames={tableNames}
                  columnsByTable={columnsByTable}
                  onCancel={() => setAdding(false)}
                  onSubmit={onAddRule}
                />
              )}
              {!adding && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => setAdding(true)}
                  disabled={editingIndex !== null}
                >
                  <Plus className="mr-2 h-4 w-4" />
                  Añadir regla
                </Button>
              )}
            </div>
          )}
        </div>

        <footer className="flex items-center justify-between gap-2 border-t p-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setConfirmReset(true)}
            disabled={resetMutation.isPending}
          >
            <RotateCcw className="mr-2 h-4 w-4" />
            Restaurar todo
          </Button>
          <div className="flex gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Cancelar
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={saveMutation.isPending || !!parseError}
              onClick={() => saveMutation.mutate()}
            >
              <Save className="mr-2 h-4 w-4" />
              {saveMutation.isPending ? "Guardando…" : "Guardar"}
            </Button>
          </div>
        </footer>
      </aside>

      <ConfirmDialog
        open={confirmReset}
        title="¿Restaurar reglas?"
        description={`Se sobrescribirá ${configId.split("/").pop()} con la plantilla por defecto. Tus cambios se perderán.`}
        confirmLabel="Restaurar"
        onConfirm={() => {
          resetMutation.mutate();
          setConfirmReset(false);
        }}
        onCancel={() => setConfirmReset(false)}
      />
    </>
  );
}

function RuleCard({
  rule,
  onEdit,
  onDelete,
}: {
  rule: Rule;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-md border bg-card p-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="text-[10px]">
              {RULE_TYPE_LABELS[rule.type] ?? rule.type}
            </Badge>
          </div>
          <p className="mt-1 truncate font-mono text-xs">{summarizeRule(rule)}</p>
          {rule.aux_col && (
            <p className="mt-1 text-[11px] text-muted-foreground">
              col. auxiliar: <span className="font-mono">{rule.aux_col}</span>
            </p>
          )}
        </div>
        <div className="flex shrink-0 gap-1">
          <button
            type="button"
            onClick={onEdit}
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
            aria-label="Editar"
          >
            <Settings className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
            aria-label="Eliminar regla"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}

function RuleForm({
  initial,
  tableNames,
  columnsByTable,
  onCancel,
  onSubmit,
}: {
  initial?: Rule;
  tableNames: string[];
  columnsByTable: Record<string, string[]>;
  onCancel: () => void;
  onSubmit: (rule: Rule) => void;
}) {
  const [draft, setDraft] = useState<Rule>(
    initial ?? {
      type: "date_inequality",
      constraint_operator: ">=",
    },
  );

  const update = (patch: Partial<Rule>) =>
    setDraft((prev) => ({ ...prev, ...patch }));

  const showInequality =
    draft.type === "date_inequality" || draft.type === "numeric_inequality";
  const showFK = draft.type === "foreign_keys_consistency_rule";

  const valid =
    !!draft.table_target &&
    !!draft.target_col &&
    (showFK
      ? !!draft.table_origin
      : !!draft.table_origin && !!draft.origin_col);

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-3">
      <div>
        <Label className="text-xs">Tipo de regla</Label>
        <select
          value={draft.type}
          onChange={(e) =>
            update({ type: e.target.value as RuleType, origin_col: undefined })
          }
          className="mt-1 h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm"
        >
          {(Object.keys(RULE_TYPE_LABELS) as RuleType[]).map((t) => (
            <option key={t} value={t}>
              {RULE_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
        <p className="mt-1 text-[11px] text-muted-foreground">
          {RULE_TYPE_HELP[draft.type]}
        </p>
      </div>

      {showInequality ? (
        <div className="grid grid-cols-[1fr_auto_1fr] items-start gap-2">
          <TableColumnPicker
            label="Tabla objetivo"
            table={draft.table_target}
            column={draft.target_col}
            tableNames={tableNames}
            columnsByTable={columnsByTable}
            onChangeTable={(t) =>
              update({ table_target: t, target_col: undefined })
            }
            onChangeColumn={(c) => update({ target_col: c })}
            columnLabel="Columna objetivo"
          />

          <div className="flex flex-col items-center space-y-2">
            <div className="pointer-events-none invisible">
              <Label className="text-xs">_</Label>
              <div className="mt-1 h-8" />
            </div>
            <div>
              <Label className="text-xs invisible">_</Label>
              <select
                aria-label="Operador"
                value={draft.constraint_operator ?? ">="}
                onChange={(e) =>
                  update({
                    constraint_operator: e.target.value as ">=" | "<=",
                  })
                }
                className="mt-1 block h-8 w-12 rounded-lg border border-input bg-background text-center text-lg font-semibold leading-none"
              >
                <option value=">=">≥</option>
                <option value="<=">≤</option>
              </select>
            </div>
          </div>

          <div className="space-y-2">
            <TableColumnPicker
              label="Tabla origen"
              table={draft.table_origin}
              column={draft.origin_col}
              tableNames={tableNames}
              columnsByTable={columnsByTable}
              onChangeTable={(t) =>
                update({ table_origin: t, origin_col: undefined })
              }
              onChangeColumn={(c) => update({ origin_col: c })}
              columnLabel="Columna origen"
            />
            <div>
              <Label className="text-xs">Constante (opcional)</Label>
              <Input
                type={draft.type === "numeric_inequality" ? "number" : "text"}
                value={draft.constraint == null ? "" : String(draft.constraint)}
                onChange={(e) =>
                  update({
                    constraint: e.target.value === "" ? null : e.target.value,
                  })
                }
                placeholder={
                  draft.type === "date_inequality" ? "p. ej. 2020-01-01" : ""
                }
                className="mt-1"
              />
              <p className="mt-1 text-[11px] text-muted-foreground">
                Alternativa a la columna origen.
              </p>
            </div>
          </div>

          <div className="col-span-3">
            <Label className="text-xs">Columna auxiliar (opcional)</Label>
            <Input
              value={draft.aux_col ?? ""}
              onChange={(e) =>
                update({ aux_col: e.target.value || undefined })
              }
              placeholder="auto-generada si vacío"
              className="mt-1"
            />
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <TableColumnPicker
            label="Tabla origen"
            table={draft.table_origin}
            column={showFK ? undefined : draft.origin_col}
            tableNames={tableNames}
            columnsByTable={columnsByTable}
            onChangeTable={(t) =>
              update({ table_origin: t, origin_col: undefined })
            }
            onChangeColumn={showFK ? undefined : (c) => update({ origin_col: c })}
            columnLabel="Columna origen"
          />
          <TableColumnPicker
            label="Tabla objetivo"
            table={draft.table_target}
            column={draft.target_col}
            tableNames={tableNames}
            columnsByTable={columnsByTable}
            onChangeTable={(t) =>
              update({ table_target: t, target_col: undefined })
            }
            onChangeColumn={(c) => update({ target_col: c })}
            columnLabel="Columna objetivo"
          />
        </div>
      )}

      {showFK && (
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="text-xs">Columna fuente (opcional)</Label>
            <Input
              value={draft.source_col ?? ""}
              onChange={(e) =>
                update({ source_col: e.target.value || undefined })
              }
              placeholder="por defecto = columna objetivo"
              className="mt-1"
            />
          </div>
          <div>
            <Label className="text-xs">Tabla referenciada (opcional)</Label>
            <Input
              value={draft.referenced_table ?? ""}
              onChange={(e) =>
                update({ referenced_table: e.target.value || undefined })
              }
              className="mt-1"
            />
          </div>
        </div>
      )}

      <div className="flex justify-end gap-2 pt-1">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Cancelar
        </Button>
        <Button
          type="button"
          size="sm"
          disabled={!valid}
          onClick={() => onSubmit(draft)}
        >
          {initial ? "Actualizar" : "Añadir"}
        </Button>
      </div>
    </div>
  );
}

function TableColumnPicker({
  label,
  columnLabel,
  table,
  column,
  tableNames,
  columnsByTable,
  onChangeTable,
  onChangeColumn,
}: {
  label: string;
  columnLabel: string;
  table?: string;
  column?: string;
  tableNames: string[];
  columnsByTable: Record<string, string[]>;
  onChangeTable: (t: string) => void;
  onChangeColumn?: (c: string) => void;
}) {
  const cols = table ? (columnsByTable[table] ?? []) : [];
  const hasSchema = tableNames.length > 0;
  return (
    <div className="space-y-2">
      <div>
        <Label className="text-xs">{label}</Label>
        {hasSchema ? (
          <select
            value={table ?? ""}
            onChange={(e) => onChangeTable(e.target.value)}
            className="mt-1 h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm"
          >
            <option value="">— elegir —</option>
            {tableNames.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        ) : (
          <Input
            value={table ?? ""}
            onChange={(e) => onChangeTable(e.target.value)}
            placeholder="nombre de tabla"
            className="mt-1"
          />
        )}
      </div>
      {onChangeColumn && (
        <div>
          <Label className="text-xs">{columnLabel}</Label>
          {hasSchema && cols.length > 0 ? (
            <select
              value={column ?? ""}
              onChange={(e) => onChangeColumn(e.target.value)}
              className="mt-1 h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm"
            >
              <option value="">— elegir —</option>
              {cols.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          ) : (
            <Input
              value={column ?? ""}
              onChange={(e) => onChangeColumn(e.target.value)}
              placeholder="nombre de columna"
              className="mt-1"
            />
          )}
        </div>
      )}
    </div>
  );
}
