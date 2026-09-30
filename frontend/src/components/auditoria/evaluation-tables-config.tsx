"use client";

// EvaluationTablesConfig
// ─────────────────────────────────────────────────────────────────────────────
// Configuration section for an evaluation. The evaluation is single-table (each
// table is assessed independently and gets its own report), so the user picks
// WHICH tables to evaluate and configures each one.
//
// Layout: a table picker at the top, then tabs:
//   • "Global"  — the shared evaluation config (evaluation.yaml). Editing it
//                 applies to every table that still inherits it.
//   • one per selected table — the SAME config form (ControlledSchemaForm),
//                 seeded from Global; any field can be overridden per table.
//
// A table inherits Global until its tab is edited; from then on it carries its
// own full config (a "Restablecer a global" button drops the override). The
// emitted payload sends, per table, the effective config object — its override,
// or the current Global config while still inheriting.

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import yaml from "js-yaml";
import { RotateCcw } from "lucide-react";

import { ConfigPanel, ControlledSchemaForm } from "@/components/config/config-drawer";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { api, getSimulationColumns, type ConfigContent } from "@/lib/api";
import { cn } from "@/lib/utils";

export interface TableEvalConfig {
  table: string;
  config: Record<string, unknown>;
}

const GLOBAL_TAB = "__global__";

/**
 * Seed a per-table config from the global one. Global-able settings (which
 * metrics to run, bins, exact-match, execution flags, utility_tests) are
 * inherited. The column-referencing fields are inherited too, but reconciled
 * against the columns that actually exist in `tableColumns`: a global value
 * pointing at a column this table doesn't have is dropped (it would error or be
 * silently skipped), while one that does exist is kept so the user doesn't have
 * to re-pick it per table. When `tableColumns` is unknown, fall back to blanking
 * those fields (the previous safe default).
 *
 * Utility tests are NOT touched: each test already names its own target table
 * and the evaluator filters them per table, so the global list is inherited
 * as-is and each table picks up the tests that target it.
 */
function seedFromGlobal(
  global: Record<string, unknown>,
  tableColumns?: string[],
): Record<string, unknown> {
  const next = structuredClone(global) as Record<string, unknown>;
  const metrics = { ...((next.metrics as Record<string, unknown>) ?? {}) };
  const cols = tableColumns ? new Set(tableColumns) : undefined;
  const keep = (column: unknown): boolean =>
    !cols || (typeof column === "string" && cols.has(column));

  const tstr = metrics.tstr;
  if (tstr && typeof tstr === "object") {
    const target = (tstr as Record<string, unknown>).target_column;
    metrics.tstr = {
      ...(tstr as Record<string, unknown>),
      target_column: keep(target) ? target : "",
    };
  }

  const sensitive = metrics.sensitive_columns;
  metrics.sensitive_columns = Array.isArray(sensitive)
    ? sensitive.filter(keep)
    : [];

  const subsets = metrics.quasi_identifier_subsets;
  if (subsets && typeof subsets === "object" && !Array.isArray(subsets)) {
    const reconciled: Record<string, unknown> = {};
    for (const [name, columns] of Object.entries(subsets as Record<string, unknown>)) {
      const kept = Array.isArray(columns) ? columns.filter(keep) : [];
      if (kept.length > 0) reconciled[name] = kept;
    }
    metrics.quasi_identifier_subsets = reconciled;
  } else {
    metrics.quasi_identifier_subsets = {};
  }

  next.metrics = metrics;
  return next;
}

export function EvaluationTablesConfig({
  simulationId,
  motherTable,
  activeAxis,
  onAxisChange,
  onChange,
}: {
  simulationId: string;
  motherTable: string | null;
  activeAxis?: string;
  onAxisChange?: (axis: string) => void;
  onChange: (configs: TableEvalConfig[]) => void;
}) {
  const columnsQuery = useQuery({
    queryKey: ["simulation-columns", simulationId],
    queryFn: () => getSimulationColumns(simulationId),
    enabled: Boolean(simulationId),
  });
  const configQuery = useQuery({
    queryKey: ["config", "evaluation"],
    queryFn: async () => {
      const { data } = await api.get<ConfigContent>("/configs/evaluation");
      return data;
    },
  });

  const tables = useMemo(() => Object.keys(columnsQuery.data ?? {}), [columnsQuery.data]);
  // The shared base every inheriting table uses; refreshed when the Global tab
  // saves (it invalidates the ["config","evaluation"] query).
  const globalBase = useMemo<Record<string, unknown>>(() => {
    try {
      return (yaml.load(configQuery.data?.content ?? "") as Record<string, unknown>) ?? {};
    } catch {
      return {};
    }
  }, [configQuery.data]);

  // What an un-tweaked table uses: global-able settings inherited, column-
  // referencing fields reconciled against that table's columns (see
  // seedFromGlobal). Memoized per table so each tab/payload entry reuses it.
  const seedCache = useMemo(
    () => new Map<string, Record<string, unknown>>(),
    [globalBase, columnsQuery.data],
  );
  const seedForTable = useCallback(
    (table: string) => {
      const cached = seedCache.get(table);
      if (cached) return cached;
      const seed = seedFromGlobal(globalBase, columnsQuery.data?.[table]);
      seedCache.set(table, seed);
      return seed;
    },
    [seedCache, globalBase, columnsQuery.data],
  );

  // Which tables to evaluate (default: the master table). A table without an
  // `overrides` entry inherits the current Global config.
  const [selected, setSelected] = useState<string[]>([]);
  const [overrides, setOverrides] = useState<Record<string, Record<string, unknown>>>({});
  const [activeTab, setActiveTab] = useState<string>(GLOBAL_TAB);

  // Seed the default selection once tables load.
  const seededRef = useRef(false);
  useEffect(() => {
    if (seededRef.current || tables.length === 0) return;
    seededRef.current = true;
    setSelected(
      motherTable && tables.includes(motherTable) ? [motherTable] : [tables[0]],
    );
  }, [tables, motherTable]);

  const toggleTable = (table: string) =>
    setSelected((prev) =>
      prev.includes(table) ? prev.filter((t) => t !== table) : [...prev, table],
    );

  const setTableOverride = (table: string, next: Record<string, unknown>) =>
    setOverrides((prev) => ({ ...prev, [table]: next }));

  const resetTableToGlobal = (table: string) =>
    setOverrides((prev) => {
      const next = { ...prev };
      delete next[table];
      return next;
    });

  // Emit the effective per-table config payload whenever it changes.
  const payload = useMemo<TableEvalConfig[]>(
    () =>
      selected
        .filter((t) => tables.includes(t))
        .map((table) => ({ table, config: overrides[table] ?? seedForTable(table) })),
    [selected, tables, overrides, seedForTable],
  );
  const lastSentRef = useRef<string>("");
  const payloadJson = JSON.stringify(payload);
  useEffect(() => {
    if (payloadJson !== lastSentRef.current) {
      lastSentRef.current = payloadJson;
      onChange(payload);
    }
  }, [payloadJson, payload, onChange]);

  // Derive the editing context so a stale selection falls back to Global
  // without an effect (avoids setState-in-effect cascading renders).
  const editing =
    activeTab === GLOBAL_TAB || tables.includes(activeTab) ? activeTab : GLOBAL_TAB;

  if (columnsQuery.isLoading || configQuery.isLoading) {
    return <Skeleton className="h-48 w-full" />;
  }
  if (columnsQuery.isError || tables.length === 0) {
    return (
      <p className="text-sm text-destructive">
        No se pudieron cargar las tablas de la generación.
      </p>
    );
  }

  const activeCount = selected.filter((t) => tables.includes(t)).length;

  return (
    <div className="space-y-2">
      <div>
        <Label>Configuración de la evaluación</Label>
        <p className="text-xs text-muted-foreground">
          La evaluación es por tabla (un informe por tabla). Marca las tablas a evaluar y
          selecciona una para revisar o ajustar su configuración; por defecto todas heredan
          la configuración global.
        </p>
      </div>

      <div className="flex flex-col gap-4 md:flex-row">
        {/* Single place to see/switch the table being configured and toggle it. */}
        <div className="shrink-0 space-y-1 rounded-md border p-1.5 md:w-64">
          <SelectorRow
            label="Global"
            hint="base común"
            active={editing === GLOBAL_TAB}
            onSelect={() => setActiveTab(GLOBAL_TAB)}
          />
          <div className="px-2 pb-0.5 pt-2 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
            Tablas a evaluar ({activeCount})
          </div>
          {tables.map((table) => (
            <SelectorRow
              key={table}
              label={table}
              mono
              active={editing === table}
              checked={selected.includes(table)}
              onCheck={() => toggleTable(table)}
              onSelect={() => setActiveTab(table)}
              isMother={table === motherTable}
              personalized={Boolean(overrides[table])}
            />
          ))}
        </div>

        {/* Config for the selected context. */}
        <div className="min-w-0 flex-1">
          {editing === GLOBAL_TAB ? (
            <ConfigPanel
              configId="evaluation"
              contextId={simulationId}
              defaultOpen
              activeGroup={activeAxis}
              onGroupChange={onAxisChange}
            />
          ) : (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border bg-muted/30 px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-semibold">Configuración de</span>
                  <span className="font-mono text-sm">{editing}</span>
                  <Badge variant="outline" className="text-[10px]">
                    {overrides[editing] ? "Personalizado" : "Heredando global"}
                  </Badge>
                  {!selected.includes(editing) && (
                    <Badge
                      variant="outline"
                      className="border-amber-500/60 text-[10px] text-amber-700 dark:text-amber-400"
                    >
                      No se evaluará
                    </Badge>
                  )}
                </div>
                {overrides[editing] && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => resetTableToGlobal(editing)}
                  >
                    <RotateCcw className="mr-2 h-3.5 w-3.5" />
                    Restablecer a global
                  </Button>
                )}
              </div>
              <div className="rounded-md border p-4">
                <ControlledSchemaForm
                  configId="evaluation"
                  contextId={simulationId}
                  scopeTable={editing}
                  value={overrides[editing] ?? seedForTable(editing)}
                  onChange={(next) => setTableOverride(editing, next)}
                  activeGroup={activeAxis}
                  onGroupChange={onAxisChange}
                />
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

/** One row in the table selector: optional "evaluate" checkbox + click-to-edit. */
function SelectorRow({
  label,
  hint,
  mono,
  active,
  checked,
  onCheck,
  onSelect,
  isMother,
  personalized,
}: {
  label: string;
  hint?: string;
  mono?: boolean;
  active: boolean;
  checked?: boolean;
  onCheck?: () => void;
  onSelect: () => void;
  isMother?: boolean;
  personalized?: boolean;
}) {
  return (
    <div
      className={cn(
        "flex items-center gap-2 rounded px-2 py-1.5",
        active ? "bg-primary/10 ring-1 ring-primary/40" : "hover:bg-muted",
      )}
    >
      {onCheck && (
        <input
          type="checkbox"
          className="h-3.5 w-3.5 shrink-0"
          checked={checked}
          onChange={onCheck}
          aria-label={`Evaluar ${label}`}
        />
      )}
      <button
        type="button"
        onClick={onSelect}
        className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
      >
        <span className={cn("truncate text-sm", mono && "font-mono", active && "font-semibold")}>
          {label}
        </span>
        {isMother && (
          <span className="rounded bg-primary/15 px-1 text-[9px] font-semibold uppercase text-primary">
            maestra
          </span>
        )}
        {hint && <span className="text-[10px] text-muted-foreground">{hint}</span>}
        {personalized && (
          <span
            className="ml-auto shrink-0 text-[10px] text-muted-foreground"
            title="Tiene ajustes propios"
          >
            ✎
          </span>
        )}
      </button>
    </div>
  );
}
