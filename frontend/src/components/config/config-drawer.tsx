// Side drawer for editing one config file (e.g. backend/config/general.yaml).
//
// Schema-driven: known configs (see ./schemas.ts) get a friendly form with
// labels/help. An "Editar como YAML" toggle exposes the raw text for advanced
// users or fields not covered by the schema. Per-field reset reverts a single
// key to its example value; "Restaurar todo" deletes the real file (the
// backend recreates it from the *.example template).

"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import axios from "axios";
import yaml from "js-yaml";
import { RotateCcw, Save, Settings, X } from "lucide-react";
import { api, getSimulationColumns, type ConfigContent, type SimulationColumns } from "@/lib/api";
import {
  CONFIG_SCHEMAS,
  type ConfigSchema,
  type FieldSchema,
} from "@/components/config/schemas";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";

type Props = {
  configId: string;
  contextId?: string; // Optional simulation ID to fetch table/column metadata
  open: boolean;
  onClose: () => void;
};

type AnyRecord = Record<string, unknown>;

function extractDetail(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: string } | undefined)?.detail;
    return detail ?? err.message;
  }
  if (err instanceof Error) return err.message;
  return "Error desconocido";
}

function getByPath(obj: unknown, path: string): unknown {
  const parts = path.split(".");
  let cur: unknown = obj;
  for (const p of parts) {
    if (cur && typeof cur === "object" && p in (cur as AnyRecord)) {
      cur = (cur as AnyRecord)[p];
    } else {
      return undefined;
    }
  }
  return cur;
}

function setByPath(obj: AnyRecord, path: string, value: unknown): AnyRecord {
  const parts = path.split(".");
  const next: AnyRecord = { ...obj };
  let cur: AnyRecord = next;
  for (let i = 0; i < parts.length - 1; i++) {
    const k = parts[i];
    const child = cur[k];
    const cloned: AnyRecord =
      child && typeof child === "object" && !Array.isArray(child)
        ? { ...(child as AnyRecord) }
        : {};
    cur[k] = cloned;
    cur = cloned;
  }
  cur[parts[parts.length - 1]] = value;
  return next;
}

function deleteByPath(obj: AnyRecord, path: string): AnyRecord {
  const parts = path.split(".");
  const next: AnyRecord = { ...obj };
  let cur: AnyRecord = next;
  for (let i = 0; i < parts.length - 1; i++) {
    const k = parts[i];
    const child = cur[k];
    if (!child || typeof child !== "object" || Array.isArray(child)) return next;
    const cloned: AnyRecord = { ...(child as AnyRecord) };
    cur[k] = cloned;
    cur = cloned;
  }
  delete cur[parts[parts.length - 1]];
  return next;
}

function fieldValueToInput(value: unknown, field: FieldSchema): string {
  if (value === null || value === undefined) return "";
  if (field.kind === "boolean") return value ? "true" : "false";
  if (field.kind === "list" && Array.isArray(value)) return value.join(", ");
  if (field.kind === "checklist" && Array.isArray(value)) return value.join(",");
  if (field.kind === "json") return value ? JSON.stringify(value, null, 2) : "";
  return String(value);
}

function inputToFieldValue(raw: string, field: FieldSchema): unknown {
  if (field.kind === "boolean") return raw === "true";
  if (raw === "" && field.nullable) return null;
  if (field.kind === "number") {
    if (raw === "") return null;
    const n = Number(raw);
    return Number.isFinite(n) ? n : raw;
  }
  if (field.kind === "list") {
    if (raw === "") return field.nullable ? null : [];
    return raw.split(",").map((s) => s.trim()).filter(Boolean);
  }
  if (field.kind === "checklist") {
    if (raw === "") return field.nullable ? null : [];
    return raw.split(",").filter(Boolean);
  }
  if (field.kind === "json") {
    if (raw === "") return field.nullable ? null : [];
    try {
      return JSON.parse(raw);
    } catch {
      return raw; // Keep as string if invalid, so user can fix it
    }
  }
  return raw;
}

export function ConfigDrawer({ configId, contextId, open, onClose }: Props) {
  const queryClient = useQueryClient();
  const schema: ConfigSchema | undefined = CONFIG_SCHEMAS[configId];
  const [yamlMode, setYamlMode] = useState(false);
  const [draftYaml, setDraftYaml] = useState<string>("");
  const [draftObj, setDraftObj] = useState<AnyRecord>({});
  const [exampleObj, setExampleObj] = useState<AnyRecord>({});
  const [confirmReset, setConfirmReset] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  const configQuery = useQuery({
    queryKey: ["config", configId],
    enabled: open,
    queryFn: async () => {
      const { data } = await api.get<ConfigContent>(
        `/configs/${encodeURIComponent(configId)}`,
      );
      return data;
    },
  });

  const columnsQuery = useQuery({
    queryKey: ["simulation-columns", contextId],
    enabled: open && !!contextId,
    queryFn: () => getSimulationColumns(contextId!),
  });

  useEffect(() => {
    if (!open) return;
    if (!configQuery.data) return;
    try {
      const parsed = (yaml.load(configQuery.data.content) as AnyRecord) ?? {};
      const exampleParsed =
        (yaml.load(configQuery.data.example_content) as AnyRecord) ?? {};
      queueMicrotask(() => {
        setDraftObj(parsed);
        setDraftYaml(configQuery.data.content);
        setExampleObj(exampleParsed);
        setParseError(null);
      });
    } catch (e) {
      queueMicrotask(() => {
        setParseError(e instanceof Error ? e.message : String(e));
      });
    }
  }, [open, configQuery.data]);

  // Keep YAML and form views in sync when the user toggles modes.
  const switchToYamlMode = () => {
    setDraftYaml(yaml.dump(draftObj, { lineWidth: 100, noRefs: true }));
    setYamlMode(true);
  };
  const switchToFormMode = () => {
    try {
      const parsed = (yaml.load(draftYaml) as AnyRecord) ?? {};
      setDraftObj(parsed);
      setYamlMode(false);
      setParseError(null);
    } catch (e) {
      setParseError(e instanceof Error ? e.message : String(e));
    }
  };

  const saveMutation = useMutation({
    mutationFn: async () => {
      const content = yamlMode
        ? draftYaml
        : yaml.dump(draftObj, { lineWidth: 100, noRefs: true });
      const { data } = await api.put<ConfigContent>(
        `/configs/${encodeURIComponent(configId)}`,
        { content },
      );
      return data;
    },
    onSuccess: () => {
      toast.success("Configuración guardada");
      queryClient.invalidateQueries({ queryKey: ["config", configId] });
      onClose();
    },
    onError: (err) => {
      toast.error(`No se pudo guardar: ${extractDetail(err)}`);
    },
  });

  const resetAllMutation = useMutation({
    mutationFn: async () => {
      await api.delete(`/configs/${encodeURIComponent(configId)}`);
    },
    onSuccess: () => {
      toast.success("Configuración restaurada al valor por defecto");
      queryClient.invalidateQueries({ queryKey: ["config", configId] });
    },
    onError: (err) => {
      toast.error(`No se pudo restaurar: ${extractDetail(err)}`);
    },
  });

  const onChangeField = (field: FieldSchema, raw: string) => {
    setDraftObj((prev) => setByPath(prev, field.path, inputToFieldValue(raw, field)));
  };

  const onResetField = (field: FieldSchema) => {
    const defaultValue = getByPath(exampleObj, field.path);
    setDraftObj((prev) => setByPath(prev, field.path, defaultValue));
  };

  const onToggleGroup = (path: string, defaults: AnyRecord, on: boolean) => {
    setDraftObj((prev) =>
      on ? setByPath(prev, path, { ...defaults }) : deleteByPath(prev, path),
    );
  };

  const dirty = useMemo(() => {
    if (!configQuery.data) return false;
    if (yamlMode) return draftYaml !== configQuery.data.content;
    try {
      const original = (yaml.load(configQuery.data.content) as AnyRecord) ?? {};
      return yaml.dump(original) !== yaml.dump(draftObj);
    } catch {
      return true;
    }
  }, [configQuery.data, draftObj, draftYaml, yamlMode]);

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
        aria-label={schema?.title ?? configId}
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l bg-background shadow-xl"
      >
        <header className="flex items-start justify-between gap-4 border-b p-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Settings className="h-4 w-4" />
              <span className="font-mono">{configId}.yaml</span>
            </div>
            <h2 className="mt-1 truncate text-lg font-semibold">
              {schema?.title ?? `Configuración: ${configId}`}
            </h2>
            {schema?.description && (
              <p className="mt-1 text-sm text-muted-foreground">
                {schema.description}
              </p>
            )}
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
            onClick={yamlMode ? switchToFormMode : switchToYamlMode}
            className="text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
          >
            {yamlMode ? "Volver al formulario" : "Editar como YAML"}
          </button>
          {parseError && (
            <span className="text-destructive">YAML inválido: {parseError}</span>
          )}
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {configQuery.isLoading && <Skeleton className="h-64 w-full" />}
          {configQuery.isError && (
            <p className="text-sm text-destructive">
              No se pudo cargar la configuración: {extractDetail(configQuery.error)}
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
          {configQuery.data && !yamlMode && schema && (
            <SchemaForm
              schema={schema}
              draft={draftObj}
              onChange={onChangeField}
              onResetField={onResetField}
              onToggleGroup={onToggleGroup}
              exampleObj={exampleObj}
              simulationColumns={columnsQuery.data}
            />
          )}
          {configQuery.data && !yamlMode && !schema && (
            <p className="text-sm text-muted-foreground">
              No hay formulario para esta configuración. Usa &quot;Editar como
              YAML&quot;.
            </p>
          )}
        </div>

        <footer className="flex items-center justify-between gap-2 border-t p-4">
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => setConfirmReset(true)}
            disabled={resetAllMutation.isPending}
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
              disabled={!dirty || saveMutation.isPending || !!parseError}
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
        title="¿Restaurar configuración?"
        description="Se sobrescribirá el archivo con la plantilla por defecto. Tus cambios se perderán."
        confirmLabel="Restaurar"
        onConfirm={() => {
          resetAllMutation.mutate();
          setConfirmReset(false);
        }}
        onCancel={() => setConfirmReset(false)}
      />
    </>
  );
}

function SchemaForm({
  schema,
  draft,
  onChange,
  onResetField,
  onToggleGroup,
  exampleObj,
  simulationColumns,
}: {
  schema: ConfigSchema;
  draft: AnyRecord;
  onChange: (field: FieldSchema, raw: string) => void;
  onResetField: (field: FieldSchema) => void;
  onToggleGroup: (path: string, defaults: AnyRecord, on: boolean) => void;
  exampleObj: AnyRecord;
  simulationColumns?: SimulationColumns;
}) {
  return (
    <div className="space-y-6">
      {schema.groups.map((group) => {
        const toggle = group.toggle;
        const groupOn = toggle
          ? getByPath(draft, toggle.path) != null
          : true;
        return (
          <section key={group.title} className="space-y-3">
            <div>
              <h3 className="text-sm font-semibold">{group.title}</h3>
              {group.description && (
                <p className="text-xs text-muted-foreground">{group.description}</p>
              )}
            </div>
            <div className="space-y-3 rounded-md border p-3">
              {toggle && (
                <label className="flex items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    className="h-4 w-4"
                    checked={groupOn}
                    onChange={(e) =>
                      onToggleGroup(toggle.path, toggle.defaults, e.target.checked)
                    }
                  />
                  <span>{toggle.label}</span>
                </label>
              )}
              {toggle?.help && groupOn && (
                <p className="-mt-1 text-[11px] text-muted-foreground">
                  {toggle.help}
                </p>
              )}
              {groupOn && group.fields.map((field) => {
                const value = getByPath(draft, field.path);
                const defaultValue = getByPath(exampleObj, field.path);
                const isModified =
                  JSON.stringify(value) !== JSON.stringify(defaultValue);
                return (
                  <div key={field.path} className="grid grid-cols-[1fr_auto] gap-2">
                    <div>
                      <Label htmlFor={field.path} className="text-xs">
                        {field.label}
                      </Label>
                      <FieldControl
                        field={field}
                        value={value}
                        onChange={(raw) => onChange(field, raw)}
                        simulationColumns={simulationColumns}
                      />
                      {field.help && (
                        <p className="mt-1 text-[11px] text-muted-foreground">
                          {field.help}
                        </p>
                      )}
                    </div>
                    <button
                      type="button"
                      aria-label="Restablecer al valor por defecto"
                      title="Restablecer al valor por defecto"
                      disabled={!isModified}
                      onClick={() => onResetField(field)}
                      className="mt-5 self-start rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </button>
                  </div>
                );
              })}
            </div>
          </section>
        );
      })}
    </div>
  );
}

function FieldControl({
  field,
  value,
  onChange,
  simulationColumns,
}: {
  field: FieldSchema;
  value: unknown;
  onChange: (raw: string) => void;
  simulationColumns?: SimulationColumns;
}) {
  const raw = fieldValueToInput(value, field);
  const tableNames = useMemo(
    () => Object.keys(simulationColumns ?? {}),
    [simulationColumns],
  );
  const selectedColumns = useMemo(
    () => (raw ? raw.split(",").filter(Boolean) : []),
    [raw],
  );
  const tableForCurrentValue = useMemo(() => {
    if (!simulationColumns || tableNames.length === 0) return "";
    const firstSelected = selectedColumns[0];
    const match = tableNames.find((table) =>
      firstSelected
        ? simulationColumns[table]?.includes(firstSelected)
        : false,
    );
    return match ?? tableNames[0];
  }, [selectedColumns, simulationColumns, tableNames]);
  const [selectedTable, setSelectedTable] = useState("");
  const activeTable =
    selectedTable && tableNames.includes(selectedTable)
      ? selectedTable
      : tableForCurrentValue;
  const tableScopedColumnOptions =
    field.dynamicOptions === "columns" && simulationColumns && activeTable
      ? (simulationColumns[activeTable] ?? []).map((column) => ({
          value: column,
          label: column,
        }))
      : [];

  if (field.kind === "boolean") {
    return (
      <label className="mt-1 flex items-center gap-2 text-sm">
        <input
          id={field.path}
          type="checkbox"
          className="h-4 w-4"
          checked={raw === "true"}
          onChange={(e) => onChange(e.target.checked ? "true" : "false")}
        />
        <span className="text-muted-foreground">
          {raw === "true" ? "Activado" : "Desactivado"}
        </span>
      </label>
    );
  }

  if (field.kind === "checklist") {
    let options = field.options ?? [];
    if (field.dynamicOptions === "tables" && simulationColumns) {
      options = Object.keys(simulationColumns).map((t) => ({
        value: t,
        label: t,
      }));
    } else if (field.dynamicOptions === "columns" && simulationColumns) {
      options = tableScopedColumnOptions;
    }
 
    return (
      <div className="mt-2 space-y-2">
        {field.dynamicOptions === "columns" && tableNames.length > 0 && (
          <select
            value={activeTable}
            onChange={(e) => setSelectedTable(e.target.value)}
            className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {tableNames.map((table) => (
              <option key={table} value={table}>
                {table}
              </option>
            ))}
          </select>
        )}
        <div className="grid grid-cols-2 gap-x-4 gap-y-1">
          {options.map((opt) => (
            <label key={opt.value} className="flex items-center gap-2 text-[11px]">
              <input
                type="checkbox"
                className="h-3.5 w-3.5 rounded border-gray-300"
                checked={selectedColumns.includes(opt.value)}
                onChange={(e) => {
                  const next = e.target.checked
                    ? [...selectedColumns, opt.value]
                    : selectedColumns.filter((v) => v !== opt.value);
                  onChange(next.join(","));
                }}
              />
              <span className="truncate">{opt.label}</span>
            </label>
          ))}
        </div>
        {field.dynamicOptions === "columns" && selectedColumns.length > 0 && (
          <p className="text-[10px] text-muted-foreground">
            Seleccionadas: {selectedColumns.join(", ")}
          </p>
        )}
      </div>
    );
  }
  if (field.kind === "select" || field.dynamicOptions) {
    let options = field.options ?? [];
    if (field.dynamicOptions === "tables" && simulationColumns) {
      options = Object.keys(simulationColumns).map((t) => ({
        value: t,
        label: t,
      }));
    } else if (field.dynamicOptions === "columns" && simulationColumns) {
      options = tableScopedColumnOptions;
    }
 
    return (
      <div className="mt-1 space-y-2">
        {field.dynamicOptions === "columns" && tableNames.length > 0 && (
          <select
            value={activeTable}
            onChange={(e) => {
              setSelectedTable(e.target.value);
              onChange("");
            }}
            className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          >
            {tableNames.map((table) => (
              <option key={table} value={table}>
                {table}
              </option>
            ))}
          </select>
        )}
        <select
          id={field.path}
          value={options.some((opt) => opt.value === raw) ? raw : ""}
          onChange={(e) => onChange(e.target.value)}
          className="h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
        >
          <option value="">Seleccionar...</option>
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </div>
    );
  }

  if (field.kind === "json") {
    return (
      <textarea
        id={field.path}
        value={raw}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1 min-h-[80px] w-full rounded-md border bg-muted/30 p-2 font-mono text-[10px] outline-none focus-visible:ring-1"
        placeholder={field.nullable ? "(vacío)" : "[]"}
      />
    );
  }
  return (
    <div className="space-y-1">
      <Input
        id={field.path}
        type={field.kind === "number" ? "number" : "text"}
        value={raw}
        onChange={(e) => onChange(e.target.value)}
        className="mt-1"
        placeholder={
          field.kind === "list"
            ? "valor1, valor2, ..."
            : field.nullable
              ? "(vacío)"
              : undefined
        }
      />
      {field.kind === "list" && (
        <p className="text-[10px] text-muted-foreground">
          Separa los elementos con comas.
        </p>
      )}
    </div>
  );
}
