"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Plus, RotateCcw, SlidersHorizontal, Trash2 } from "lucide-react";
import {
  api,
  type ColumnKind,
  type FilePreview,
  getModelColumnTypes,
  getModelColumnValues,
  getModelColumns,
  type ModelColumns,
  type ModelColumnTypes,
} from "@/lib/api";
import { Autocomplete } from "@/components/ui/autocomplete";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { CollapseToggle } from "@/components/ui/collapse-toggle";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SELECT_CLASS } from "@/lib/ui";

// A "condition" constrains one column of the table being generated. The modes
// mirror the backend conditional-generation API:
//   fixed       — every row gets the same value
//   categorical — values follow target proportions
//   numeric     — values are drawn from a range (uniform) or bell curve (normal)
//   daterange   — datetime values drawn uniformly between two dates
export type ConditionMode = "fixed" | "categorical" | "numeric" | "daterange";
export type NumericGenerator = "uniform" | "normal";
export type WeightEntry = { value: string; weight: string };

export type Condition = {
  column: string;
  mode: ConditionMode;
  // fixed
  value: string;
  // categorical
  weights: WeightEntry[];
  // numeric
  generator: NumericGenerator;
  min: string;
  max: string;
  mean: string;
  std: string;
  integer: boolean;
  // daterange
  start: string;
  end: string;
};

export type ConditionalConfig = {
  table: string;
  conditions: Condition[];
};

export function emptyCondition(): Condition {
  return {
    column: "",
    mode: "fixed",
    value: "",
    weights: [{ value: "", weight: "" }],
    generator: "uniform",
    min: "",
    max: "",
    mean: "",
    std: "",
    integer: false,
    start: "",
    end: "",
  };
}

export const EMPTY_CONDITIONAL_CONFIG: ConditionalConfig = {
  table: "",
  conditions: [],
};

const MODE_LABEL: Record<ConditionMode, string> = {
  fixed: "Valor fijo",
  categorical: "Proporciones",
  numeric: "Rango numérico",
  daterange: "Rango de fechas",
};

// Which constraint modes make sense for each column kind. `unknown` (no
// encoding metadata yet) permits everything so the UI never blocks the user.
const ALLOWED_MODES: Record<ColumnKind | "unknown", ConditionMode[]> = {
  numeric: ["fixed", "categorical", "numeric"],
  datetime: ["fixed", "categorical", "daterange"],
  categorical: ["fixed", "categorical"],
  unknown: ["fixed", "categorical", "numeric", "daterange"],
};

function isConditionUsable(c: Condition): boolean {
  if (!c.column.trim()) return false;
  if (c.mode === "fixed") return c.value.trim() !== "";
  if (c.mode === "categorical") {
    return c.weights.some(
      (w) => w.value.trim() !== "" && w.weight.trim() !== "",
    );
  }
  if (c.mode === "daterange") return c.start.trim() !== "" && c.end.trim() !== "";
  // numeric
  return c.min.trim() !== "" && c.max.trim() !== "";
}

export function isConditionalConfigActive(cfg: ConditionalConfig): boolean {
  return cfg.conditions.some(isConditionUsable);
}

/** Min/max of a column's values, read as numbers; null if any value isn't numeric. */
function numericRange(values: string[]): { min: number; max: number } | null {
  if (values.length === 0) return null;
  const nums: number[] = [];
  for (const v of values) {
    const n = Number(v);
    if (v.trim() === "" || !Number.isFinite(n)) return null;
    nums.push(n);
  }
  return { min: Math.min(...nums), max: Math.max(...nums) };
}

/** Earliest/latest of a column's values parsed as dates (YYYY-MM-DD); null if unparseable. */
function dateRange(values: string[]): { min: string; max: string } | null {
  const times: number[] = [];
  for (const v of values) {
    const t = Date.parse(v);
    if (Number.isFinite(t)) times.push(t);
  }
  if (times.length === 0) return null;
  const iso = (t: number) => new Date(t).toISOString().slice(0, 10);
  return { min: iso(Math.min(...times)), max: iso(Math.max(...times)) };
}

type BodyProps = {
  active: boolean;
  modelId: string;
  pendingFilePaths?: string[];
  config: ConditionalConfig;
  onChange: (next: ConditionalConfig) => void;
  onSave?: () => void;
};

type PanelProps = {
  modelId: string;
  pendingFilePaths?: string[];
  config: ConditionalConfig;
  onChange: (next: ConditionalConfig) => void;
  className?: string;
  defaultOpen?: boolean;
};


function ConditionalConfigBody({
  active,
  modelId,
  pendingFilePaths,
  config,
  onChange,
  onSave,
}: BodyProps) {
  const columnsQuery = useQuery({
    queryKey: ["model-columns", modelId],
    enabled: active && !!modelId,
    queryFn: () => getModelColumns(modelId),
  });

  const typesQuery = useQuery({
    queryKey: ["model-column-types", modelId],
    enabled: active && !!modelId,
    queryFn: () => getModelColumnTypes(modelId),
  });

  const pendingKey = useMemo(
    () => [...(pendingFilePaths ?? [])].sort().join("|"),
    [pendingFilePaths],
  );
  const previewQuery = useQuery({
    queryKey: ["files", "preview", "rows", pendingKey],
    enabled: active && !!pendingKey,
    queryFn: async () => {
      const { data } = await api.post<FilePreview[]>("/files/preview", {
        paths: pendingFilePaths ?? [],
        sample_rows: 5,
      });
      return data;
    },
  });

  const previewColumnsByTable = useMemo(() => {
    const map: ModelColumns = {};
    for (const preview of previewQuery.data ?? []) {
      map[preview.table] = preview.columns;
    }
    return map;
  }, [previewQuery.data]);

  const previewValuesByTable = useMemo(() => {
    const map: Record<string, Record<string, string[]>> = {};
    for (const preview of previewQuery.data ?? []) {
      const tableMap = (map[preview.table] ??= {});
      preview.columns.forEach((column, columnIdx) => {
        const values = new Set(tableMap[column] ?? []);
        for (const row of preview.rows ?? []) {
          const raw = row[columnIdx];
          if (typeof raw === "string" && raw.trim() !== "") values.add(raw);
        }
        tableMap[column] = Array.from(values).slice(0, 50);
      });
    }
    return map;
  }, [previewQuery.data]);

  const columnsByTable: ModelColumns = useMemo(() => {
    if (Object.keys(columnsQuery.data ?? {}).length > 0)
      return columnsQuery.data ?? {};
    return previewColumnsByTable;
  }, [columnsQuery.data, previewColumnsByTable]);
  const tableNames = useMemo(() => Object.keys(columnsByTable), [columnsByTable]);
  const activeTable = config.table || tableNames[0] || "";

  useEffect(() => {
    if (!active) return;
    if (!config.table && tableNames.length > 0) {
      onChange({ ...config, table: tableNames[0] });
    }
  }, [active, config, tableNames, onChange]);

  const tableColumns = activeTable ? columnsByTable[activeTable] ?? [] : [];

  const typesByColumn: Record<string, ColumnKind> = useMemo(() => {
    const all: ModelColumnTypes = typesQuery.data ?? {};
    return all[activeTable] ?? {};
  }, [typesQuery.data, activeTable]);
  const kindOf = (column: string): ColumnKind | "unknown" =>
    typesByColumn[column] ?? "unknown";

  const valueQueryColumns = useMemo(() => {
    const cols = new Set<string>();
    for (const c of config.conditions) if (c.column) cols.add(c.column);
    return Array.from(cols);
  }, [config.conditions]);

  const valueQueries = useQueries({
    queries: valueQueryColumns.map((column) => ({
      queryKey: ["model-column-values", modelId, activeTable, column],
      enabled: active && !!modelId && !!activeTable && !!column,
      queryFn: () => getModelColumnValues(modelId, activeTable, column),
      staleTime: 5 * 60 * 1000,
    })),
  });
  const valuesByColumn = useMemo(() => {
    const map: Record<string, string[]> = {
      ...(previewValuesByTable[activeTable] ?? {}),
    };
    valueQueryColumns.forEach((column, idx) => {
      const data = valueQueries[idx]?.data;
      if (data) map[column] = data;
    });
    return map;
  }, [activeTable, previewValuesByTable, valueQueryColumns, valueQueries]);

  const usedColumns = new Set(
    config.conditions.map((c) => c.column).filter(Boolean),
  );

  const setTable = (table: string) =>
    onChange({ ...config, table, conditions: [] });

  const updateCondition = (idx: number, patch: Partial<Condition>) =>
    onChange({
      ...config,
      conditions: config.conditions.map((c, i) =>
        i === idx ? { ...c, ...patch } : c,
      ),
    });

  const addCondition = () =>
    onChange({ ...config, conditions: [...config.conditions, emptyCondition()] });

  const removeCondition = (idx: number) =>
    onChange({
      ...config,
      conditions: config.conditions.filter((_, i) => i !== idx),
    });

  const restoreAll = () => onChange({ ...config, conditions: [] });

  // Picking a column resets mode-specific state and, when possible, prefills a
  // sensible range from the column's observed values.
  const pickColumn = (idx: number, column: string) => {
    const values = valuesByColumn[column] ?? [];
    const kind = kindOf(column);
    const allowed = ALLOWED_MODES[kind];
    const numeric = numericRange(values);
    const dates = dateRange(values);
    const base = emptyCondition();
    updateCondition(idx, {
      ...base,
      column,
      mode: allowed.includes(config.conditions[idx]?.mode ?? "fixed")
        ? config.conditions[idx].mode
        : "fixed",
      min: numeric ? String(numeric.min) : "",
      max: numeric ? String(numeric.max) : "",
      start: dates ? dates.min : "",
      end: dates ? dates.max : "",
    });
  };

  // Single field for picking a value: a styled suggestion popup for regular
  // columns (pick one or type freely), a calendar for datetime columns.
  const renderValueField = (
    column: string,
    value: string,
    onSelect: (next: string) => void,
  ) => {
    if (kindOf(column) === "datetime") {
      return (
        <Input
          type="date"
          value={value}
          onChange={(e) => onSelect(e.target.value)}
          disabled={!column}
          className="h-8 text-xs"
        />
      );
    }
    return (
      <Autocomplete
        value={value}
        onValueChange={onSelect}
        options={column ? valuesByColumn[column] ?? [] : []}
        disabled={!column}
        placeholder={column ? "Elige o escribe un valor" : "Elige columna primero"}
      />
    );
  };

  const renderConditionDetail = (c: Condition, idx: number) => {
    if (c.mode === "fixed") {
      return (
        <div className="space-y-1">
          <Label className="text-xs text-muted-foreground">
            Todas las filas tendrán este valor
          </Label>
          {renderValueField(c.column, c.value, (value) =>
            updateCondition(idx, { value }),
          )}
        </div>
      );
    }

    if (c.mode === "categorical") {
      const total = c.weights.reduce((sum, w) => {
        const n = Number(w.weight);
        return sum + (Number.isFinite(n) && n > 0 ? n : 0);
      }, 0);
      const updateWeight = (wIdx: number, patch: Partial<WeightEntry>) =>
        updateCondition(idx, {
          weights: c.weights.map((w, i) =>
            i === wIdx ? { ...w, ...patch } : w,
          ),
        });
      return (
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">
            Reparte las filas entre estos valores (los pesos se normalizan solos)
          </Label>
          {c.weights.map((w, wIdx) => {
            const pct =
              total > 0 && Number(w.weight) > 0
                ? Math.round((Number(w.weight) / total) * 100)
                : null;
            return (
              <div
                key={wIdx}
                className="grid grid-cols-[1fr_4.5rem_2.5rem_auto] items-center gap-2"
              >
                {renderValueField(c.column, w.value, (value) =>
                  updateWeight(wIdx, { value }),
                )}
                <Input
                  type="number"
                  min={0}
                  value={w.weight}
                  onChange={(e) => updateWeight(wIdx, { weight: e.target.value })}
                  placeholder="peso"
                  className="h-8 text-xs"
                />
                <span className="text-xs tabular-nums text-muted-foreground">
                  {pct != null ? `${pct}%` : "—"}
                </span>
                <button
                  type="button"
                  aria-label="Quitar valor"
                  onClick={() =>
                    updateCondition(idx, {
                      weights: c.weights.filter((_, i) => i !== wIdx),
                    })
                  }
                  disabled={c.weights.length <= 1}
                  className="rounded p-1.5 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-30"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={() =>
              updateCondition(idx, {
                weights: [...c.weights, { value: "", weight: "" }],
              })
            }
          >
            <Plus className="mr-1.5 h-3.5 w-3.5" />
            Añadir valor
          </Button>
        </div>
      );
    }

    if (c.mode === "daterange") {
      return (
        <div className="space-y-2">
          <Label className="text-xs text-muted-foreground">
            Genera fechas dentro de este intervalo
          </Label>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <Label className="text-[11px]">Desde</Label>
              <Input
                type="date"
                value={c.start}
                onChange={(e) => updateCondition(idx, { start: e.target.value })}
                className="h-8 text-xs"
              />
            </div>
            <div>
              <Label className="text-[11px]">Hasta</Label>
              <Input
                type="date"
                value={c.end}
                onChange={(e) => updateCondition(idx, { end: e.target.value })}
                className="h-8 text-xs"
              />
            </div>
          </div>
        </div>
      );
    }

    // numeric
    return (
      <div className="space-y-2">
        <Label className="text-xs text-muted-foreground">
          Genera valores numéricos dentro de un rango
        </Label>
        <div className="grid grid-cols-2 gap-2">
          <div>
            <Label className="text-[11px]">Mínimo</Label>
            <Input
              type="number"
              value={c.min}
              onChange={(e) => updateCondition(idx, { min: e.target.value })}
              placeholder="p.ej. 18"
              className="h-8 text-xs"
            />
          </div>
          <div>
            <Label className="text-[11px]">Máximo</Label>
            <Input
              type="number"
              value={c.max}
              onChange={(e) => updateCondition(idx, { max: e.target.value })}
              placeholder="p.ej. 80"
              className="h-8 text-xs"
            />
          </div>
        </div>
        <div>
          <Label className="text-[11px]">¿Cómo se reparten los valores?</Label>
          <select
            value={c.generator}
            onChange={(e) =>
              updateCondition(idx, {
                generator: e.target.value as NumericGenerator,
              })
            }
            className={SELECT_CLASS}
          >
            <option value="uniform">Uniforme — todos por igual en el rango</option>
            <option value="normal">
              Normal — concentrados alrededor de una media
            </option>
          </select>
        </div>
        {c.generator === "normal" && (
          <div className="grid grid-cols-2 gap-2 rounded-md bg-muted/40 p-2">
            <div>
              <Label className="text-[11px]">Media</Label>
              <Input
                type="number"
                value={c.mean}
                onChange={(e) => updateCondition(idx, { mean: e.target.value })}
                placeholder="p.ej. 40"
                className="h-8 text-xs"
              />
            </div>
            <div>
              <Label className="text-[11px]">Desviación típica</Label>
              <Input
                type="number"
                min={0}
                value={c.std}
                onChange={(e) => updateCondition(idx, { std: e.target.value })}
                placeholder="p.ej. 12"
                className="h-8 text-xs"
              />
            </div>
          </div>
        )}
        <label className="flex items-center gap-2 text-xs text-muted-foreground">
          <input
            type="checkbox"
            checked={c.integer}
            onChange={(e) => updateCondition(idx, { integer: e.target.checked })}
            className="h-3.5 w-3.5"
          />
          Solo números enteros
        </label>
      </div>
    );
  };

  const noSchema = !modelId && (pendingFilePaths?.length ?? 0) === 0;
  const loadingSchema =
    (!!modelId && columnsQuery.isLoading) ||
    (!modelId && previewQuery.isLoading);

  return (
    <div className="flex flex-col">
      <div className="space-y-4 p-4">
        {noSchema && (
          <p className="text-sm text-destructive">
            Selecciona un modelo entrenado para poder condicionar la generación.
          </p>
        )}
        {loadingSchema && (
          <p className="text-sm text-muted-foreground">Cargando columnas…</p>
        )}

        {tableNames.length > 1 && (
          <div className="space-y-1">
            <Label className="text-xs">Tabla</Label>
            <select
              value={activeTable}
              onChange={(e) => setTable(e.target.value)}
              className={SELECT_CLASS}
            >
              {tableNames.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </div>
        )}

        {config.conditions.length === 0 && tableNames.length > 0 && (
          <p className="text-sm text-muted-foreground">
            Sin condiciones: la generación es libre. Añade una para fijar el
            valor de una columna o controlar su distribución.
          </p>
        )}

        <div className="space-y-3">
          {config.conditions.map((c, idx) => {
            const exclude = new Set(usedColumns);
            exclude.delete(c.column);
            const allowed = ALLOWED_MODES[kindOf(c.column)];
            return (
              <div key={idx} className="space-y-3 rounded-lg border bg-card p-3">
                <div className="flex items-center gap-2">
                  <select
                    value={c.column}
                    onChange={(e) => pickColumn(idx, e.target.value)}
                    className={SELECT_CLASS}
                    disabled={tableColumns.length === 0}
                  >
                    <option value="">Elige una columna…</option>
                    {tableColumns.map((column) => (
                      <option
                        key={column}
                        value={column}
                        disabled={exclude.has(column)}
                      >
                        {column}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    aria-label="Eliminar condición"
                    onClick={() => removeCondition(idx)}
                    className="shrink-0 rounded p-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>

                {c.column && (
                  <div className="flex flex-wrap gap-1.5">
                    {allowed.map((mode) => (
                      <button
                        key={mode}
                        type="button"
                        onClick={() => updateCondition(idx, { mode })}
                        className={
                          "rounded-full border px-3 py-1 text-xs transition-colors " +
                          (c.mode === mode
                            ? "border-primary bg-primary/10 text-primary"
                            : "border-input text-muted-foreground hover:bg-accent")
                        }
                      >
                        {MODE_LABEL[mode]}
                      </button>
                    ))}
                  </div>
                )}

                {c.column && renderConditionDetail(c, idx)}
              </div>
            );
          })}
        </div>

        {tableNames.length > 0 && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={addCondition}
            disabled={tableColumns.length === 0}
          >
            <Plus className="mr-2 h-3.5 w-3.5" />
            Añadir condición
          </Button>
        )}
      </div>

      <footer className="flex items-center justify-between gap-2 border-t p-4">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={restoreAll}
          disabled={config.conditions.length === 0}
        >
          <RotateCcw className="mr-2 h-3.5 w-3.5" />
          Restaurar
        </Button>
        {onSave && (
          <Button type="button" size="sm" onClick={onSave}>
            Guardar
          </Button>
        )}
      </footer>
    </div>
  );
}

const HEADER_TITLE = "Condicionar la generación";
const HEADER_HINT =
  "Fija el valor de una columna o controla su distribución. Si lo dejas vacío, la generación es libre.";

export function ConditionalConfigPanel({
  modelId,
  pendingFilePaths,
  config,
  onChange,
  className,
  defaultOpen = false,
}: PanelProps) {
  const [open, setOpen] = useState(defaultOpen);
  const active = isConditionalConfigActive(config);
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <SlidersHorizontal className="h-3.5 w-3.5" />
            <span>Opcional</span>
            {active && (
              <span className="rounded-full bg-primary/10 px-2 py-0.5 text-[10px] text-primary">
                activa
              </span>
            )}
          </div>
          <CardTitle className="text-base">{HEADER_TITLE}</CardTitle>
          <CardDescription>{HEADER_HINT}</CardDescription>
        </div>
        <CollapseToggle
          open={open}
          onToggle={() => setOpen((v) => !v)}
          ariaLabel={open ? "Contraer" : "Expandir"}
        />
      </CardHeader>
      {open && (
        <CardContent className="p-0">
          <ConditionalConfigBody
            active
            modelId={modelId}
            pendingFilePaths={pendingFilePaths}
            config={config}
            onChange={onChange}
            onSave={() => setOpen(false)}
          />
        </CardContent>
      )}
    </Card>
  );
}

type ConditionPayload =
  | { column: string; mode: "fixed"; value: string | number }
  | { column: string; mode: "categorical"; weights: Record<string, number> }
  | {
      column: string;
      mode: "numeric";
      generator: NumericGenerator;
      min: number;
      max: number;
      integer: boolean;
      mean?: number;
      std?: number;
    }
  | { column: string; mode: "daterange"; start: string; end: string };

/** Convert the editor config into the `conditional` payload the API expects. */
export function buildConditionalPayload(
  cfg: ConditionalConfig,
): Record<string, unknown> | null {
  if (!isConditionalConfigActive(cfg)) return null;

  const conditions: ConditionPayload[] = [];
  for (const c of cfg.conditions) {
    if (!isConditionUsable(c)) continue;
    const column = c.column.trim();

    if (c.mode === "fixed") {
      const raw = c.value.trim();
      const asNumber = Number(raw);
      conditions.push({
        column,
        mode: "fixed",
        value: raw !== "" && Number.isFinite(asNumber) ? asNumber : raw,
      });
    } else if (c.mode === "categorical") {
      const weights: Record<string, number> = {};
      for (const w of c.weights) {
        const value = w.value.trim();
        const weight = Number(w.weight);
        if (!value || !Number.isFinite(weight) || weight <= 0) continue;
        weights[value] = weight;
      }
      if (Object.keys(weights).length > 0) {
        conditions.push({ column, mode: "categorical", weights });
      }
    } else if (c.mode === "daterange") {
      conditions.push({
        column,
        mode: "daterange",
        start: c.start.trim(),
        end: c.end.trim(),
      });
    } else {
      const min = Number(c.min);
      const max = Number(c.max);
      if (!Number.isFinite(min) || !Number.isFinite(max)) continue;
      const payload: ConditionPayload = {
        column,
        mode: "numeric",
        generator: c.generator,
        min,
        max,
        integer: c.integer,
      };
      if (c.generator === "normal") {
        const mean = Number(c.mean);
        const std = Number(c.std);
        if (!Number.isFinite(mean) || !Number.isFinite(std)) continue;
        payload.mean = mean;
        payload.std = std;
      }
      conditions.push(payload);
    }
  }

  if (conditions.length === 0) return null;
  const payload: Record<string, unknown> = { conditions };
  if (cfg.table) payload.table = cfg.table;
  return payload;
}
