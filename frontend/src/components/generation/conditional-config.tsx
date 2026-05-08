"use client";

import { useEffect, useMemo } from "react";
import { useQueries, useQuery } from "@tanstack/react-query";
import { Plus, Settings, Trash2, X } from "lucide-react";
import {
  api,
  type FilePreview,
  getModelColumnValues,
  getModelColumns,
  type ModelColumns,
} from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export type SeedEntry = { column: string; value: string };
export type DistributionEntry = { value: string; weight: string };

export type ConditionalConfig = {
  table: string;
  seeds: SeedEntry[];
  distributionField: string;
  distribution: DistributionEntry[];
};

export const EMPTY_CONDITIONAL_CONFIG: ConditionalConfig = {
  table: "",
  seeds: [],
  distributionField: "",
  distribution: [],
};

export function isConditionalConfigActive(cfg: ConditionalConfig): boolean {
  const hasSeeds = cfg.seeds.some(
    (s) => s.column.trim() !== "" && s.value.trim() !== "",
  );
  const hasDistribution =
    cfg.distributionField.trim() !== "" &&
    cfg.distribution.some(
      (d) => d.value.trim() !== "" && d.weight.trim() !== "",
    );
  return hasSeeds || hasDistribution;
}

type Props = {
  open: boolean;
  modelId: string;
  pendingFilePaths?: string[];
  config: ConditionalConfig;
  onChange: (next: ConditionalConfig) => void;
  onClose: () => void;
};

const SELECT_CLASS =
  "h-9 w-full rounded-md border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

export function ConditionalGenerationDrawer({
  open,
  modelId,
  pendingFilePaths,
  config,
  onChange,
  onClose,
}: Props) {
  const columnsQuery = useQuery({
    queryKey: ["model-columns", modelId],
    enabled: open && !!modelId,
    queryFn: () => getModelColumns(modelId),
  });

  const pendingKey = useMemo(
    () => [...(pendingFilePaths ?? [])].sort().join("|"),
    [pendingFilePaths],
  );
  const previewQuery = useQuery({
    queryKey: ["files", "preview", "rows", pendingKey],
    enabled: open && !!pendingKey,
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
        tableMap[column] = Array.from(values).slice(0, 20);
      });
    }
    return map;
  }, [previewQuery.data]);

  const columnsByTable: ModelColumns = useMemo(() => {
    if (Object.keys(columnsQuery.data ?? {}).length > 0) return columnsQuery.data ?? {};
    return previewColumnsByTable;
  }, [columnsQuery.data, previewColumnsByTable]);
  const tableNames = useMemo(
    () => Object.keys(columnsByTable),
    [columnsByTable],
  );
  const activeTable = config.table || tableNames[0] || "";

  // Default to the first table once columns load.
  useEffect(() => {
    if (!open) return;
    if (!config.table && tableNames.length > 0) {
      onChange({ ...config, table: tableNames[0] });
    }
  }, [open, config, tableNames, onChange]);

  const tableColumns = activeTable ? columnsByTable[activeTable] ?? [] : [];
  // Columns referenced in seeds + distribution drive the value-dropdown queries.
  const valueQueryColumns = useMemo(() => {
    const cols = new Set<string>();
    for (const s of config.seeds) if (s.column) cols.add(s.column);
    if (config.distributionField) cols.add(config.distributionField);
    return Array.from(cols);
  }, [config.seeds, config.distributionField]);

  const valueQueries = useQueries({
    queries: valueQueryColumns.map((column) => ({
      queryKey: ["model-column-values", modelId, activeTable, column],
      enabled: open && !!modelId && !!activeTable && !!column,
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

  if (!open) return null;

  const setTable = (table: string) =>
    onChange({
      ...config,
      table,
      seeds: config.seeds.map((s) => ({ ...s, column: "", value: "" })),
      distributionField: "",
      distribution: [],
    });

  const updateSeed = (idx: number, patch: Partial<SeedEntry>) => {
    const seeds = config.seeds.map((s, i) =>
      i === idx ? { ...s, ...patch } : s,
    );
    onChange({ ...config, seeds });
  };
  const addSeed = () =>
    onChange({ ...config, seeds: [...config.seeds, { column: "", value: "" }] });
  const removeSeed = (idx: number) =>
    onChange({ ...config, seeds: config.seeds.filter((_, i) => i !== idx) });

  const updateDist = (idx: number, patch: Partial<DistributionEntry>) => {
    const distribution = config.distribution.map((d, i) =>
      i === idx ? { ...d, ...patch } : d,
    );
    onChange({ ...config, distribution });
  };
  const addDist = () =>
    onChange({
      ...config,
      distribution: [...config.distribution, { value: "", weight: "" }],
    });
  const removeDist = (idx: number) =>
    onChange({
      ...config,
      distribution: config.distribution.filter((_, i) => i !== idx),
    });

  const clearAll = () => onChange({ ...EMPTY_CONDITIONAL_CONFIG, table: activeTable });

  // A column already used as a seed shouldn't be reusable for another seed
  // or as the distribution field — same with the distribution column itself.
  const usedSeedColumns = new Set(
    config.seeds.map((s) => s.column).filter(Boolean),
  );

  const renderColumnSelect = (
    id: string,
    value: string,
    onSelect: (column: string) => void,
    excludeColumns: Set<string>,
  ) => (
    <select
      id={id}
      value={value}
      onChange={(e) => onSelect(e.target.value)}
      className={SELECT_CLASS}
      disabled={tableColumns.length === 0}
    >
      <option value="">Selecciona columna…</option>
      {tableColumns.map((column) => (
        <option
          key={column}
          value={column}
          disabled={excludeColumns.has(column) && column !== value}
        >
          {column}
        </option>
      ))}
    </select>
  );

  const renderValueSelect = (
    id: string,
    column: string,
    value: string,
    onSelect: (next: string) => void,
  ) => {
    const options = column ? valuesByColumn[column] ?? [] : [];
    const idx = column ? valueQueryColumns.indexOf(column) : -1;
    const isLoading = idx >= 0 && valueQueries[idx]?.isLoading;
    const hasOption = !value || options.includes(value);
    return (
      <div className="flex flex-col gap-1">
        <select
          id={id}
          value={hasOption ? value : ""}
          onChange={(e) => onSelect(e.target.value)}
          className={SELECT_CLASS}
          disabled={!column || isLoading}
        >
          <option value="">
            {!column
              ? "Elige columna primero"
              : isLoading
                ? "Cargando valores…"
                : options.length === 0
                  ? "Sin valores"
                  : "Selecciona valor…"}
          </option>
          {options.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
        {column && !hasOption && (
          <p className="text-[10px] text-muted-foreground">
            Valor actual «{value}» no está entre los más frecuentes; se usará tal
            cual.
          </p>
        )}
      </div>
    );
  };

  return (
    <>
      <div
        className="fixed inset-0 z-40 bg-black/50"
        onClick={onClose}
        aria-hidden
      />
      <aside
        role="dialog"
        aria-label="Configurar generación condicional"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l bg-background shadow-xl"
      >
        <header className="flex items-start justify-between gap-4 border-b p-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Settings className="h-4 w-4" />
              <span>Generación condicional</span>
            </div>
            <h2 className="mt-1 text-lg font-semibold">
              Fija atributos o distribuciones para la simulación
            </h2>
            <p className="mt-1 text-sm text-muted-foreground">
              Genera muestras condicionadas a valores concretos (semilla) o a
              una distribución sobre una columna categórica. Déjalo vacío para
              una generación libre.
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

        <div className="flex-1 space-y-6 overflow-y-auto p-4">
          {!modelId && (pendingFilePaths?.length ?? 0) === 0 && (
            <p className="text-sm text-destructive">
              Selecciona un modelo existente o añade un paso de entrenamiento con archivos.
            </p>
          )}

          {!modelId && (pendingFilePaths?.length ?? 0) > 0 && (
            <p className="text-sm text-muted-foreground">
              Usando el esquema detectado en los archivos del paso de entrenamiento de este job.
              Hasta que exista un modelo sólo se pueden sugerir columnas y algunos valores de ejemplo.
            </p>
          )}

          {modelId && columnsQuery.isLoading && (
            <p className="text-sm text-muted-foreground">
              Cargando columnas del modelo…
            </p>
          )}

          {!modelId && previewQuery.isLoading && (
            <p className="text-sm text-muted-foreground">
              Detectando tablas y columnas desde los archivos del job…
            </p>
          )}

          {modelId && columnsQuery.isError && (
            <p className="text-sm text-destructive">
              No se pudieron cargar las columnas del modelo.
            </p>
          )}

          {!modelId && previewQuery.isError && (
            <p className="text-sm text-destructive">
              No se pudo detectar el esquema de los archivos de entrenamiento.
            </p>
          )}

          {tableNames.length > 0 && (
            <>
              {tableNames.length > 1 && (
                <section className="space-y-2">
                  <Label className="text-xs" htmlFor="cond-table">
                    Tabla
                  </Label>
                  <select
                    id="cond-table"
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
                </section>
              )}

              <section className="space-y-3">
                <div>
                  <h3 className="text-sm font-semibold">Valores fijos (seed)</h3>
                  <p className="text-xs text-muted-foreground">
                    Cada fila generada tendrá estas columnas con el valor
                    indicado.
                  </p>
                </div>
                <div className="space-y-3 rounded-md border p-3">
                  {config.seeds.length === 0 && (
                    <p className="text-xs text-muted-foreground">
                      Sin valores fijos. Añade uno para empezar.
                    </p>
                  )}
                  {config.seeds.map((seed, idx) => {
                    const exclude = new Set(usedSeedColumns);
                    exclude.delete(seed.column);
                    if (config.distributionField) {
                      exclude.add(config.distributionField);
                    }
                    return (
                      <div
                        key={idx}
                        className="grid grid-cols-[1fr_1fr_auto] items-end gap-2"
                      >
                        <div>
                          <Label className="text-xs" htmlFor={`seed-col-${idx}`}>
                            Columna
                          </Label>
                          {renderColumnSelect(
                            `seed-col-${idx}`,
                            seed.column,
                            (column) =>
                              updateSeed(idx, { column, value: "" }),
                            exclude,
                          )}
                        </div>
                        <div>
                          <Label className="text-xs" htmlFor={`seed-val-${idx}`}>
                            Valor
                          </Label>
                          {renderValueSelect(
                            `seed-val-${idx}`,
                            seed.column,
                            seed.value,
                            (value) => updateSeed(idx, { value }),
                          )}
                        </div>
                        <button
                          type="button"
                          aria-label="Eliminar fila"
                          onClick={() => removeSeed(idx)}
                          className="rounded p-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    );
                  })}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={addSeed}
                    disabled={tableColumns.length === 0}
                  >
                    <Plus className="mr-2 h-3.5 w-3.5" />
                    Añadir valor fijo
                  </Button>
                </div>
              </section>

              <section className="space-y-3">
                <div>
                  <h3 className="text-sm font-semibold">
                    Distribución sobre una columna
                  </h3>
                  <p className="text-xs text-muted-foreground">
                    Opcional. Reparte las filas según pesos sobre los valores
                    indicados.
                  </p>
                </div>
                <div className="space-y-3 rounded-md border p-3">
                  <div>
                    <Label className="text-xs" htmlFor="dist-field">
                      Columna a distribuir
                    </Label>
                    <select
                      id="dist-field"
                      value={config.distributionField}
                      onChange={(e) =>
                        onChange({
                          ...config,
                          distributionField: e.target.value,
                          distribution: [],
                        })
                      }
                      className={SELECT_CLASS}
                      disabled={tableColumns.length === 0}
                    >
                      <option value="">— ninguna —</option>
                      {tableColumns.map((column) => (
                        <option
                          key={column}
                          value={column}
                          disabled={
                            usedSeedColumns.has(column) &&
                            column !== config.distributionField
                          }
                        >
                          {column}
                        </option>
                      ))}
                    </select>
                    <p className="mt-1 text-[11px] text-muted-foreground">
                      Esta columna no debe aparecer en los valores fijos.
                    </p>
                  </div>

                  {config.distributionField && (
                    <>
                      {config.distribution.length === 0 && (
                        <p className="text-xs text-muted-foreground">
                          Sin pesos. Añade categorías y sus proporciones.
                        </p>
                      )}
                      {config.distribution.map((entry, idx) => (
                        <div
                          key={idx}
                          className="grid grid-cols-[1fr_1fr_auto] items-end gap-2"
                        >
                          <div>
                            <Label className="text-xs" htmlFor={`dist-val-${idx}`}>
                              Valor
                            </Label>
                            {renderValueSelect(
                              `dist-val-${idx}`,
                              config.distributionField,
                              entry.value,
                              (value) => updateDist(idx, { value }),
                            )}
                          </div>
                          <div>
                            <Label className="text-xs" htmlFor={`dist-w-${idx}`}>
                              Peso (%)
                            </Label>
                            <Input
                              id={`dist-w-${idx}`}
                              type="number"
                              min={0}
                              value={entry.weight}
                              onChange={(e) =>
                                updateDist(idx, { weight: e.target.value })
                              }
                              placeholder="p.ej. 50"
                            />
                          </div>
                          <button
                            type="button"
                            aria-label="Eliminar fila"
                            onClick={() => removeDist(idx)}
                            className="rounded p-2 text-muted-foreground hover:bg-destructive/10 hover:text-destructive"
                          >
                            <Trash2 className="h-3.5 w-3.5" />
                          </button>
                        </div>
                      ))}
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        onClick={addDist}
                      >
                        <Plus className="mr-2 h-3.5 w-3.5" />
                        Añadir categoría
                      </Button>
                    </>
                  )}
                </div>
              </section>
            </>
          )}
        </div>

        <footer className="flex items-center justify-between gap-2 border-t p-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={clearAll}
            disabled={!isConditionalConfigActive(config)}
          >
            Limpiar todo
          </Button>
          <Button type="button" size="sm" onClick={onClose}>
            Hecho
          </Button>
        </footer>
      </aside>
    </>
  );
}

export function buildConditionalPayload(
  cfg: ConditionalConfig,
): Record<string, unknown> | null {
  if (!isConditionalConfigActive(cfg)) return null;

  const seed: Record<string, string | number> = {};
  for (const { column, value } of cfg.seeds) {
    const col = column.trim();
    const val = value.trim();
    if (!col || !val) continue;
    const asNumber = Number(val);
    seed[col] = val !== "" && Number.isFinite(asNumber) ? asNumber : val;
  }

  const payload: Record<string, unknown> = { seed };
  if (cfg.table) payload.table = cfg.table;
  const field = cfg.distributionField.trim();
  const dist: Record<string, number> = {};
  for (const { value, weight } of cfg.distribution) {
    const v = value.trim();
    const w = Number(weight);
    if (!v || !Number.isFinite(w)) continue;
    dist[v] = w;
  }
  if (field && Object.keys(dist).length > 0) {
    payload.distribution_field = field;
    payload.distribution = dist;
  }
  return payload;
}
