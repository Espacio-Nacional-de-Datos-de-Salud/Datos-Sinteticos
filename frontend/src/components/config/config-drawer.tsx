// Editor for one config file (e.g. backend/config/general.yaml).
//
// Schema-driven: known configs (see ./schemas.ts) get a friendly form with
// labels/help. An "Editar como YAML" toggle exposes the raw text for advanced
// users or fields not covered by the schema. Per-field reset reverts a single
// key to its example value; "Restaurar todo" deletes the real file (the
// backend recreates it from the *.example template).
//
// Two presentations:
//   - <ConfigDrawer />: side drawer with overlay (legacy modal usage).
//   - <ConfigPanel />:  inline Card variant for embedding in a step layout.
// Both share <ConfigEditor /> for the actual form/yaml UI.

"use client";

import { Fragment, useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import yaml from "js-yaml";
import { CheckCircle2, CircleDot, FileCode2, ListTree, Lock, Plus, RotateCcw, Save, Settings, Trash2, X } from "lucide-react";
import { api, getSimulationColumns, type ConfigContent, type SimulationColumns } from "@/lib/api";
import { extractDetail } from "@/lib/errors";
import { cn } from "@/lib/utils";
import {
  useConfigSchemas,
  type ConfigSchema,
  type FieldSchema,
} from "@/components/config/schemas";
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
import { NativeSelect } from "@/components/ui/native-select";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import { AdvancedSection, AdvancedBadge } from "@/components/ui/advanced-section";
import { ModeSelector, type ModeType } from "@/components/config/mode-selector";
import { type BatchSpeed } from "@/lib/batch-size";

type DrawerProps = {
  configId: string;
  contextId?: string; // Optional simulation ID to fetch table/column metadata
  tableNames?: string[]; // Known table names when there is no simulation context
  open: boolean;
  onClose: () => void;
};

type EditorProps = {
  configId: string;
  contextId?: string;
  tableNames?: string[];
  active: boolean; // gate queries (e.g. drawer open, panel mounted)
  onSaved?: () => void;
  onEdit?: () => void;
  activeGroup?: string;
  onGroupChange?: (group: string) => void;
  /** Field paths fixed by the active preset (locked + greyed in the form). */
  lockedPaths?: Set<string>;
};

type PanelProps = {
  configId: string;
  contextId?: string;
  tableNames?: string[];
  className?: string;
  defaultOpen?: boolean;
  /** Called after a successful save (e.g. to refresh config-dependent queries). */
  onSaved?: () => void;
  activeGroup?: string;
  onGroupChange?: (group: string) => void;
  /** Row count of the selected upstream dataset (largest table). When set, the
      preset auto-sizes the training batch to it, and a hint is shown. */
  presetRowCount?: number;
};

type AnyRecord = Record<string, unknown>;

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

function normalizeQiSubsets(value: unknown): Record<string, string[]> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .map(([name, columns]) => [
        name,
        Array.isArray(columns) ? columns.map(String).filter(Boolean) : [],
      ])
      .filter(([name]) => String(name).trim() !== ""),
  );
}

// Guided statistical-utility tests editor (metrics.utility_tests.tests).
const UTILITY_TESTS_PATH = "metrics.utility_tests.tests";

type UtilitySpec = {
  metric?: string;
  table?: string;
  column?: string;
  filter?: string;
  percentile?: number;
  formula?: string;
  numerator?: UtilitySpec;
  denominator?: UtilitySpec;
};
type UtilityTest = UtilitySpec & {
  name?: string;
  weight?: number;
};

// Metrics that operate on a single column. count/proportion work on filtered
// row counts and need no column; rate/ratio compose two nested sub-specs.
const UTILITY_COLUMN_METRICS = new Set([
  "mean",
  "median",
  "sum",
  "std",
  "min",
  "max",
  "nunique",
  "percentile",
]);
const UTILITY_SUBSPEC_METRIC_OPTIONS: { value: string; label: string }[] = [
  { value: "count", label: "Conteo (count)" },
  { value: "proportion", label: "Proporción (proportion)" },
  { value: "mean", label: "Media (mean)" },
  { value: "median", label: "Mediana (median)" },
  { value: "sum", label: "Suma (sum)" },
  { value: "std", label: "Desv. estándar (std)" },
  { value: "min", label: "Mínimo (min)" },
  { value: "max", label: "Máximo (max)" },
  { value: "nunique", label: "Valores únicos (nunique)" },
  { value: "percentile", label: "Percentil (percentile)" },
];
// Predefined metrics shown in the dropdown. The custom-formula path is chosen
// via the Predefinida/Personalizada mode buttons, not from this list.
const UTILITY_METRIC_OPTIONS: { value: string; label: string }[] = [
  ...UTILITY_SUBSPEC_METRIC_OPTIONS,
  { value: "rate", label: "Tasa (rate = num / den)" },
  { value: "ratio", label: "Razón (ratio = num / den)" },
];

function normalizeUtilityTests(value: unknown): UtilityTest[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (v): v is UtilityTest => !!v && typeof v === "object" && !Array.isArray(v),
  );
}

// Guided per-table overrides editor (model_settings.per_table).
const PER_TABLE_PATH = "model_settings.per_table";
const MODEL_SETTINGS_PREFIX = "model_settings.";
const DP_PATH = "model_settings.differential_privacy";
const DP_KEY = "differential_privacy";

function normalizePerTableOverrides(value: unknown): Record<string, AnyRecord> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return {};
  const result: Record<string, AnyRecord> = {};
  for (const [table, overrides] of Object.entries(value as AnyRecord)) {
    if (overrides && typeof overrides === "object" && !Array.isArray(overrides)) {
      result[table] = overrides as AnyRecord;
    }
  }
  return result;
}

function describeFieldValue(value: unknown, field: FieldSchema): string {
  if (value === null || value === undefined || value === "") return "automático";
  if (field.kind === "boolean") return value ? "activado" : "desactivado";
  if (field.kind === "select") {
    const opt = field.options?.find((o) => o.value === String(value));
    if (opt) return opt.label;
  }
  return String(value);
}

function makeUniqueGroupName(base: string, existing: Iterable<string>): string {
  const used = new Set(existing);
  const cleanBase = base.trim() || "grupo";
  if (!used.has(cleanBase)) return cleanBase;
  let i = 2;
  while (used.has(`${cleanBase}_${i}`)) i += 1;
  return `${cleanBase}_${i}`;
}

function ConfigEditor({ configId, contextId, tableNames, active, onSaved, onEdit, activeGroup, onGroupChange, lockedPaths }: EditorProps) {
  const queryClient = useQueryClient();
  const { schemas } = useConfigSchemas();
  const schema: ConfigSchema | undefined = schemas[configId];
  const [yamlMode, setYamlMode] = useState(false);
  const [draftYaml, setDraftYaml] = useState<string>("");
  const [draftObj, setDraftObj] = useState<AnyRecord>({});
  const [exampleObj, setExampleObj] = useState<AnyRecord>({});
  const [confirmReset, setConfirmReset] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  const configQuery = useQuery({
    queryKey: ["config", configId],
    enabled: active,
    staleTime: 0,
    gcTime: 0,
    refetchOnMount: true,
    queryFn: async () => {
      const { data } = await api.get<ConfigContent>(
        `/configs/${encodeURIComponent(configId)}`,
      );
      return data;
    },
  });

  const columnsQuery = useQuery({
    queryKey: ["simulation-columns", contextId],
    enabled: active && !!contextId,
    queryFn: () => getSimulationColumns(contextId!),
  });

  useEffect(() => {
    if (!active) return;
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
  }, [active, configQuery.data]);

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
      onSaved?.();
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
    onEdit?.();
    setDraftObj((prev) => setByPath(prev, field.path, inputToFieldValue(raw, field)));
  };

  const onResetField = (field: FieldSchema) => {
    const defaultValue = getByPath(exampleObj, field.path);
    if (field.kind === "checklist" && field.options && field.options.length > 0) {
      const ownOptions = new Set(field.options.map((o) => o.value));
      const current = getByPath(exampleObj, field.path);
      const defaultOwn = Array.isArray(current)
        ? current.filter((v) => ownOptions.has(String(v)))
        : [];
      setDraftObj((prev) => {
        const existing = getByPath(prev, field.path);
        const others = Array.isArray(existing)
          ? existing.filter((v) => !ownOptions.has(String(v)))
          : [];
        return setByPath(prev, field.path, [...others, ...defaultOwn]);
      });
      return;
    }
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

  return (
    <>
      <div className="flex items-center justify-between border-b px-4 py-2 text-xs">
        <Button
          type="button"
          size="sm"
          variant="outline"
          onClick={yamlMode ? switchToFormMode : switchToYamlMode}
        >
          {yamlMode ? (
            <>
              <ListTree className="mr-2 h-4 w-4" />
              Volver al formulario
            </>
          ) : (
            <>
              <FileCode2 className="mr-2 h-4 w-4" />
              Editar como YAML
            </>
          )}
        </Button>
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
            onChange={(e) => { onEdit?.(); setDraftYaml(e.target.value); }}
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
            tableNames={tableNames}
            activeGroup={activeGroup}
            onGroupChange={onGroupChange}
            lockedPaths={lockedPaths}
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
        {/* Saved-state indicator. The config is persisted server-side at all
            times (changing a mode saves immediately); only pending manual field
            edits are "unsaved". Make that explicit so a greyed-out "Guardar"
            doesn't read as "nothing is saved". */}
        <span
          className={cn(
            "flex items-center gap-1.5 text-xs font-medium",
            dirty
              ? "text-amber-600 dark:text-amber-400"
              : "text-emerald-600 dark:text-emerald-400",
          )}
          aria-live="polite"
        >
          {dirty ? (
            <>
              <CircleDot className="h-3.5 w-3.5" />
              Cambios sin guardar
            </>
          ) : (
            <>
              <CheckCircle2 className="h-3.5 w-3.5" />
              Configuración guardada
            </>
          )}
        </span>
        <Button
          type="button"
          size="sm"
          disabled={!dirty || saveMutation.isPending || !!parseError}
          onClick={() => saveMutation.mutate()}
        >
          <Save className="mr-2 h-4 w-4" />
          {saveMutation.isPending ? "Guardando…" : "Guardar"}
        </Button>
      </footer>

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

export function ConfigDrawer({ configId, contextId, tableNames, open, onClose }: DrawerProps) {
  const { schemas } = useConfigSchemas();
  const schema: ConfigSchema | undefined = schemas[configId];
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
        <ConfigEditor
          configId={configId}
          contextId={contextId}
          tableNames={tableNames}
          active={open}
          onSaved={onClose}
        />
      </aside>
    </>
  );
}

export function ConfigPanel({
  configId,
  contextId,
  tableNames,
  className,
  defaultOpen = false,
  onSaved,
  activeGroup,
  onGroupChange,
  presetRowCount,
}: PanelProps) {
  const { schemas } = useConfigSchemas();
  const schema: ConfigSchema | undefined = schemas[configId];
  const [open, setOpen] = useState(defaultOpen);
  // "free" (Libre) is the default: normal/custom configuration with every field
  // editable. Selecting another preset locks the fields that preset fixes.
  const [selectedMode, setSelectedMode] = useState<ModeType>("free");
  // Training speed drives the (auto-sized, locked) batch size, independently of
  // the privacy mode. Defaults to the balanced curve.
  const [selectedSpeed, setSelectedSpeed] = useState<BatchSpeed>("balanced");
  const [refreshKey, setRefreshKey] = useState(0);

  const isMostlyAi = configId === "mostly_ai";

  // Load the presets so we can lock exactly the fields the active (non-"free")
  // preset fixes. "Libre" leaves everything editable.
  const presetsQuery = useQuery({
    queryKey: ["config", "mode_presets"],
    enabled: isMostlyAi,
    queryFn: async () => {
      const { data } = await api.get<{ content: string }>("/configs/mode_presets");
      const parsed = yaml.load(data.content) as
        | { modes?: Record<string, { config?: AnyRecord }> }
        | null;
      return parsed?.modes ?? {};
    },
  });

  const lockedPaths = useMemo(() => {
    if (!isMostlyAi || !selectedMode || selectedMode === "free") return undefined;
    const cfg = presetsQuery.data?.[selectedMode]?.config;
    if (!cfg) return undefined;
    // A preset LOCKS the choices that define its privacy/utility tradeoff (model
    // size, flexible-generation flag, differential privacy) plus the batch size,
    // which is derived automatically from the dataset size rather than chosen by
    // the user. Everything else the preset sets (epochs, time/sample caps…) is a
    // sensible starting value the user is free to tune. "Libre" leaves
    // everything editable.
    const isPlainObject = (v: unknown): v is AnyRecord =>
      !!v && typeof v === "object" && !Array.isArray(v);
    const ms = (cfg as AnyRecord).model_settings;
    if (!isPlainObject(ms)) return undefined;
    const paths = new Set<string>();
    if (ms.model != null) paths.add("model_settings.model");
    // Batch size is auto-sized to the selected data, so the user shouldn't edit
    // it under a preset; lock it whenever the preset declares it.
    if ("batch_size" in ms) paths.add("model_settings.batch_size");
    // The flexible-generation flag is dictated by the mode (off for Privacidad,
    // on for Equilibrado/Utilidad); lock it whenever the preset declares it,
    // including when ``false`` (which a null-check would skip).
    if ("enable_flexible_generation" in ms) {
      paths.add("model_settings.enable_flexible_generation");
    }
    // The DP toggle is dictated by the mode too: Privacidad turns it on (an
    // object), the others off (null). Lock the toggle (and its sub-fields, via
    // prefix match) whenever the preset declares the key — even when null.
    if (DP_KEY in ms) paths.add(DP_PATH);
    return paths;
  }, [isMostlyAi, selectedMode, presetsQuery.data]);

  return (
    <Card className={className}>
      <CardHeader className="space-y-0">
        <div className="flex flex-row items-start justify-between gap-4">
          <div className="min-w-0 flex-1">
            {!isMostlyAi && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <Settings className="h-3.5 w-3.5" />
                <span className="font-mono">{configId}.yaml</span>
              </div>
            )}
            <CardTitle className="flex items-center gap-2 text-base">
              {isMostlyAi && <Settings className="h-4 w-4 shrink-0 text-muted-foreground" />}
              {schema?.title ?? `Configuración: ${configId}`}
            </CardTitle>
            {schema?.description && (
              <CardDescription>{schema.description}</CardDescription>
            )}
          </div>
          <CollapseToggle
            open={open}
            onToggle={() => setOpen((v) => !v)}
            ariaLabel={open ? "Contraer configuración" : "Expandir configuración"}
          />
        </div>
        {isMostlyAi && open && (
          <div className="pt-3 border-t mt-3">
            <p className="text-xs text-muted-foreground mb-2">Modos de configuración:</p>
            <ModeSelector
              selectedMode={selectedMode}
              onModeSelected={setSelectedMode}
              presetRowCount={presetRowCount}
              selectedSpeed={selectedSpeed}
              onSpeedSelected={setSelectedSpeed}
              onApplyMode={() => {
                setRefreshKey((k) => k + 1);
                onSaved?.();
              }}
            />
          </div>
        )}
      </CardHeader>
      {open && (
        <CardContent className="flex flex-col p-0">
          <ConfigEditor
            key={refreshKey}
            configId={configId}
            contextId={contextId}
            tableNames={tableNames}
            active
            onEdit={() => setSelectedMode("free")}
            onSaved={onSaved}
            activeGroup={activeGroup}
            onGroupChange={onGroupChange}
            lockedPaths={lockedPaths}
          />
        </CardContent>
      )}
    </Card>
  );
}

const AXIS_GROUP_COLORS: Record<string, string> = {
  Privacidad: "#9a3412",
  Fidelidad: "#166534",
  Utilidad: "#6b21a8",
};

function SchemaForm({
  schema,
  draft,
  onChange,
  onResetField,
  onToggleGroup,
  exampleObj,
  simulationColumns,
  tableNames,
  activeGroup,
  onGroupChange,
  lockedPaths,
}: {
  schema: ConfigSchema;
  draft: AnyRecord;
  onChange: (field: FieldSchema, raw: string) => void;
  onResetField: (field: FieldSchema) => void;
  onToggleGroup: (path: string, defaults: AnyRecord, on: boolean) => void;
  exampleObj: AnyRecord;
  simulationColumns?: SimulationColumns;
  tableNames?: string[];
  activeGroup?: string;
  onGroupChange?: (group: string) => void;
  /** Field paths fixed by the active preset — rendered locked + greyed.
      A path matches a field directly or any of its descendants (e.g. the DP
      group toggle is locked when "model_settings.differential_privacy" is set). */
  lockedPaths?: Set<string>;
}) {
  const isLocked = (path: string) => {
    if (!lockedPaths || lockedPaths.size === 0) return false;
    if (lockedPaths.has(path)) return true;
    // A locked parent path (e.g. the DP block) also locks its sub-fields.
    for (const p of lockedPaths) {
      if (path === p || path.startsWith(p + ".")) return true;
    }
    return false;
  };
  const axisGroups = schema.groups.filter((g) => g.title in AXIS_GROUP_COLORS);
  const otherGroups = schema.groups.filter((g) => !(g.title in AXIS_GROUP_COLORS));
  const hasAxisTabs = axisGroups.length > 0 && !!activeGroup;
  const activeAxisGroup = hasAxisTabs
    ? (axisGroups.find((g) => g.title === activeGroup) ?? axisGroups[0])
    : null;

  function renderGroupFields(group: (typeof schema.groups)[number]) {
        const toggle = group.toggle;
        const groupOn = toggle
          ? getByPath(draft, toggle.path) != null
          : true;
        // Per-table overrides is an advanced personalisation — render it as a
        // distinct "advanced" callout (icon + tinted box) instead of a plain
        // group, so it reads as a separate, optional section.
        const isAdvanced = group.fields.some((f) => f.path === PER_TABLE_PATH);
        if (isAdvanced) {
          return (
            <AdvancedSection
              key={group.title}
              title={group.title}
              tooltip={group.description || "Opcional · ajuste avanzado"}
            >
              {group.description && (
                <p className="-mt-1 text-xs text-muted-foreground">{group.description}</p>
              )}
              {group.fields.map((field) => (
                <FieldControl
                  key={field.path}
                  field={field}
                  value={getByPath(draft, field.path)}
                  onChange={(raw) => onChange(field, raw)}
                  simulationColumns={simulationColumns}
                  draft={draft}
                  knownTables={tableNames}
                />
              ))}
            </AdvancedSection>
          );
        }
        return (
          <section key={group.title} className="space-y-3">
            {!hasAxisTabs && (
              <div>
                <h3 className="text-sm font-semibold">{group.title}</h3>
                {group.description && (
                  <p className="text-xs text-muted-foreground">{group.description}</p>
                )}
              </div>
            )}
            <div className="space-y-3 rounded-md border p-3">
              {toggle && (
                <label className={"flex items-center gap-2 text-sm " + (isLocked(toggle.path) ? "opacity-60" : "")}>
                  <input
                    type="checkbox"
                    className="h-4 w-4"
                    checked={groupOn}
                    disabled={isLocked(toggle.path)}
                    onChange={(e) =>
                      onToggleGroup(toggle.path, toggle.defaults, e.target.checked)
                    }
                  />
                  <span>{toggle.label}</span>
                  {isLocked(toggle.path) && (
                    <Lock className="h-3 w-3 text-muted-foreground" />
                  )}
                </label>
              )}
              {toggle?.help && groupOn && (
                <p className="-mt-1 text-[11px] text-muted-foreground">
                  {toggle.help}
                </p>
              )}
              {groupOn && group.fields.map((field, fieldIdx) => {
                const prevSubgroup =
                  fieldIdx > 0 ? group.fields[fieldIdx - 1].subgroup : undefined;
                const showSubgroupHeading =
                  !!field.subgroup && field.subgroup !== prevSubgroup;
                const value = getByPath(draft, field.path);
                const defaultValue = getByPath(exampleObj, field.path);
                // For checklist fields with a static option list, isModified
                // must be scoped to the field's own options — otherwise two
                // checklists sharing a path (e.g. Privacy/Fidelity halves of
                // metrics.default.custom) both light up whenever either side
                // changes.
                const isModified = (() => {
                  if (
                    field.kind === "checklist" &&
                    field.options &&
                    field.options.length > 0
                  ) {
                    const own = new Set(field.options.map((o) => o.value));
                    const pickOwn = (v: unknown) =>
                      Array.isArray(v)
                        ? v.filter((x) => own.has(String(x))).map(String).sort()
                        : [];
                    return (
                      JSON.stringify(pickOwn(value)) !==
                      JSON.stringify(pickOwn(defaultValue))
                    );
                  }
                  return JSON.stringify(value) !== JSON.stringify(defaultValue);
                })();
                const locked = isLocked(field.path);
                return (
                  <Fragment key={field.path}>
                  {showSubgroupHeading && (
                    <h4 className="mt-1 border-b pb-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground first:mt-0">
                      {field.subgroup}
                    </h4>
                  )}
                  <div className="grid grid-cols-[1fr_auto] gap-2">
                    <fieldset disabled={locked} className={locked ? "min-w-0 opacity-60" : "min-w-0"}>
                      {field.kind === "boolean" ? (
                        // Render boolean fields as a single inline checkbox with
                        // the field label — same style as metric checklists,
                        // instead of a label header + "Activado/Desactivado".
                        <div className="flex items-center gap-1">
                          <label className="flex items-center gap-2 text-xs">
                            <input
                              id={field.path}
                              type="checkbox"
                              className="h-4 w-4"
                              checked={value === true || value === "true"}
                              onChange={(e) =>
                                onChange(field, e.target.checked ? "true" : "false")
                              }
                            />
                            <span>{field.label}</span>
                          </label>
                          {field.help && <Tooltip content={field.help} side="top" />}
                          {locked && (
                            <Tooltip
                              content="Fijado por el preset seleccionado. Cambia a «Libre» para editarlo."
                              side="top"
                            >
                              <Lock className="h-3 w-3 text-muted-foreground" />
                            </Tooltip>
                          )}
                        </div>
                      ) : (
                        <>
                          <div className="flex items-center gap-1">
                            <Label htmlFor={field.path} className="text-xs">
                              {field.label}
                            </Label>
                            {field.help && (
                              <Tooltip content={field.help} side="top" />
                            )}
                            {locked && (
                              <Tooltip
                                content="Fijado por el preset seleccionado. Cambia a «Libre» para editarlo."
                                side="top"
                              >
                                <Lock className="h-3 w-3 text-muted-foreground" />
                              </Tooltip>
                            )}
                          </div>
                          <FieldControl
                            field={field}
                            value={value}
                            onChange={(raw) => onChange(field, raw)}
                            simulationColumns={simulationColumns}
                            draft={draft}
                            knownTables={tableNames}
                          />
                        </>
                      )}
                    </fieldset>
                    <button
                      type="button"
                      aria-label="Restablecer al valor por defecto"
                      title="Restablecer al valor por defecto"
                      disabled={!isModified || locked}
                      onClick={() => onResetField(field)}
                      className="mt-5 self-start rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-30"
                    >
                      <RotateCcw className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  </Fragment>
                );
              })}
            </div>
          </section>
        );
  }

  return (
    <div className="space-y-6">
      {/* Always-visible non-axis groups (e.g. Ajustes generales) */}
      {otherGroups.map((g) => renderGroupFields(g))}

      {/* Tabbed axis groups when sync is active */}
      {hasAxisTabs && activeAxisGroup ? (
        <div className="space-y-2">
          {/* Tab strip */}
          <div className="flex gap-1 overflow-x-auto pb-0.5">
            {axisGroups.map((grp) => {
              const color = AXIS_GROUP_COLORS[grp.title] ?? "#5f83be";
              const selected = grp.title === activeAxisGroup.title;
              return (
                <button
                  key={grp.title}
                  type="button"
                  onClick={() => onGroupChange?.(grp.title)}
                  className="flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-wide transition-colors"
                  style={
                    selected
                      ? { background: `${color}18`, color, boxShadow: `0 0 0 1.5px ${color}55` }
                      : { color: "#7a8fab" }
                  }
                >
                  <span
                    className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                    style={{ background: selected ? color : "#c0cad9" }}
                  />
                  {grp.title}
                </button>
              );
            })}
          </div>
          {/* Active axis group fields */}
          {renderGroupFields(activeAxisGroup)}
        </div>
      ) : (
        /* Non-tabbed fallback: show all axis groups stacked */
        axisGroups.map((g) => renderGroupFields(g))
      )}
    </div>
  );
}

function FieldControl({
  field,
  value,
  onChange,
  simulationColumns,
  draft,
  knownTables,
}: {
  field: FieldSchema;
  value: unknown;
  onChange: (raw: string) => void;
  simulationColumns?: SimulationColumns;
  draft?: AnyRecord;
  knownTables?: string[];
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

  if (field.path === PER_TABLE_PATH) {
    return (
      <PerTableOverridesBuilder
        value={value}
        onChange={(next) => {
          const keys = Object.keys(next);
          onChange(keys.length > 0 ? JSON.stringify(next) : "");
        }}
        availableTables={
          knownTables && knownTables.length > 0
            ? knownTables
            : Object.keys(simulationColumns ?? {})
        }
        globalDraft={draft ?? {}}
      />
    );
  }

  if (field.path === "metrics.quasi_identifier_subsets") {
    return (
      <QiSubsetsBuilder
        value={value}
        onChange={(next) => {
          const keys = Object.keys(next);
          onChange(keys.length > 0 ? JSON.stringify(next) : "");
        }}
        simulationColumns={simulationColumns}
      />
    );
  }

  if (field.path === UTILITY_TESTS_PATH) {
    return (
      <UtilityTestsBuilder
        value={value}
        onChange={(next) => onChange(next.length > 0 ? JSON.stringify(next) : "")}
        simulationColumns={simulationColumns}
        knownTables={knownTables}
      />
    );
  }

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
          <NativeSelect
            value={activeTable}
            onValueChange={setSelectedTable}
            className="h-8 rounded-lg"
          >
            {tableNames.map((table) => (
              <option key={table} value={table}>
                {table}
              </option>
            ))}
          </NativeSelect>
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
          <NativeSelect
            value={activeTable}
            onValueChange={(v) => {
              setSelectedTable(v);
              onChange("");
            }}
            className="h-8 rounded-lg"
          >
            {tableNames.map((table) => (
              <option key={table} value={table}>
                {table}
              </option>
            ))}
          </NativeSelect>
        )}
        <NativeSelect
          id={field.path}
          value={options.some((opt) => opt.value === raw) ? raw : ""}
          onValueChange={onChange}
          className="h-8 rounded-lg"
        >
          <option value="">Seleccionar...</option>
          {options.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </NativeSelect>
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
  const minValue =
    field.kind === "number" && field.min != null ? field.min : undefined;
  return (
    <div className="space-y-1">
      <Input
        id={field.path}
        type={field.kind === "number" ? "number" : "text"}
        value={raw}
        min={minValue}
        onChange={(e) => onChange(e.target.value)}
        // Clamp on blur (not per-keystroke, which would break typing e.g. "10").
        onBlur={(e) => {
          if (minValue === undefined) return;
          const n = Number(e.target.value);
          if (Number.isFinite(n) && n < minValue) onChange(String(minValue));
        }}
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

function QiSubsetsBuilder({
  value,
  onChange,
  simulationColumns,
}: {
  value: unknown;
  onChange: (next: Record<string, string[]>) => void;
  simulationColumns?: SimulationColumns;
}) {
  const subsets = useMemo(() => normalizeQiSubsets(value), [value]);
  const entries = Object.entries(subsets);
  const tableNames = useMemo(
    () => Object.keys(simulationColumns ?? {}),
    [simulationColumns],
  );
  const [selectedTable, setSelectedTable] = useState("");
  const [nameDrafts, setNameDrafts] = useState<Record<string, string>>({});
  const activeTable =
    selectedTable && tableNames.includes(selectedTable)
      ? selectedTable
      : tableNames[0] ?? "";
  const availableColumns = activeTable && simulationColumns
    ? simulationColumns[activeTable] ?? []
    : [];
  const currentColumns = useMemo(
    () => Array.from(new Set(entries.flatMap(([, columns]) => columns))).sort(),
    [entries],
  );
  const columnOptions = availableColumns.length > 0 ? availableColumns : currentColumns;

  const updateGroupColumns = (name: string, columns: string[]) => {
    onChange({ ...subsets, [name]: columns });
  };

  const addGroup = () => {
    const name = makeUniqueGroupName(`grupo_${entries.length + 1}`, Object.keys(subsets));
    onChange({ ...subsets, [name]: [] });
  };

  const removeGroup = (name: string) => {
    const next = { ...subsets };
    delete next[name];
    onChange(next);
  };

  const commitGroupName = (oldName: string) => {
    const draft = nameDrafts[oldName];
    const cleanName = makeUniqueGroupName(
      (draft ?? oldName).trim(),
      Object.keys(subsets).filter((name) => name !== oldName),
    );
    setNameDrafts((prev) => {
      const next = { ...prev };
      delete next[oldName];
      return next;
    });
    if (cleanName === oldName) return;
    const next: Record<string, string[]> = {};
    for (const [name, columns] of Object.entries(subsets)) {
      next[name === oldName ? cleanName : name] = columns;
    }
    onChange(next);
  };

  return (
    <div className="mt-2 space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        {tableNames.length > 0 && (
          <NativeSelect
            value={activeTable}
            onValueChange={setSelectedTable}
            className="h-8 w-auto min-w-0 flex-1 rounded-lg"
          >
            {tableNames.map((table) => (
              <option key={table} value={table}>
                {table}
              </option>
            ))}
          </NativeSelect>
        )}
        <Button type="button" size="sm" variant="outline" onClick={addGroup}>
          <Plus className="h-3.5 w-3.5" />
          Añadir grupo
        </Button>
      </div>

      {entries.length === 0 && (
        <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
          Sin grupos definidos.
        </div>
      )}

      <div className="space-y-2">
        {entries.map(([name, columns]) => {
          const remainingColumns = columnOptions.filter(
            (column) => !columns.includes(column),
          );
          return (
            <div key={name} className="rounded-md border bg-muted/20 p-3">
              <div className="flex items-center gap-2">
                <Input
                  value={nameDrafts[name] ?? name}
                  onChange={(e) =>
                    setNameDrafts((prev) => ({ ...prev, [name]: e.target.value }))
                  }
                  onBlur={() => commitGroupName(name)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      commitGroupName(name);
                    }
                  }}
                  className="h-8 min-w-0 flex-1"
                  aria-label="Nombre del grupo"
                />
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  onClick={() => removeGroup(name)}
                  aria-label="Eliminar grupo"
                  title="Eliminar grupo"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>

              <div className="mt-3 flex flex-wrap gap-1.5">
                {columns.map((column) => (
                  <button
                    key={column}
                    type="button"
                    onClick={() =>
                      updateGroupColumns(
                        name,
                        columns.filter((value) => value !== column),
                      )
                    }
                    className="inline-flex h-6 max-w-full items-center gap-1 rounded-full border bg-background px-2 text-xs text-foreground hover:bg-muted"
                    title="Quitar columna"
                  >
                    <span className="truncate">{column}</span>
                    <X className="h-3 w-3 shrink-0" />
                  </button>
                ))}
                {columns.length === 0 && (
                  <span className="text-xs text-muted-foreground">Sin columnas</span>
                )}
              </div>

              <NativeSelect
                value=""
                disabled={remainingColumns.length === 0}
                onValueChange={(column) => {
                  if (!column) return;
                  updateGroupColumns(name, [...columns, column]);
                }}
                className="mt-3 h-8 rounded-lg"
              >
                <option value="">Añadir columna...</option>
                {remainingColumns.map((column) => (
                  <option key={column} value={column}>
                    {column}
                  </option>
                ))}
              </NativeSelect>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// Renders the data fields (table, column, filter, percentile) for one metric
// spec. Reused for a direct test body and for rate/ratio numerator/denominator.
function UtilitySpecBody({
  spec,
  onChange,
  tableNames,
  simulationColumns,
}: {
  spec: UtilitySpec;
  onChange: (patch: Partial<UtilitySpec>) => void;
  tableNames: string[];
  simulationColumns?: SimulationColumns;
}) {
  const needsColumn = spec.metric ? UTILITY_COLUMN_METRICS.has(spec.metric) : false;
  const isPercentile = spec.metric === "percentile";
  const isFormula = spec.metric === "custom_formula";
  // count/proportion only compare row counts, so without a filter they reduce to
  // "total rows" / "always 1" and the comparison is meaningless: the filter is
  // what defines the subset being measured. For every other metric it's an
  // optional way to restrict the statistic to a subgroup.
  const filterDefinesMetric = spec.metric === "count" || spec.metric === "proportion";
  const columnOptions =
    spec.table && simulationColumns ? simulationColumns[spec.table] ?? [] : [];

  return (
    <div className="space-y-2">
      <label className="block text-[11px] text-muted-foreground">
        Tabla
        <NativeSelect
          value={spec.table ?? ""}
          onValueChange={(table) => onChange({ table })}
          className="mt-1 h-8 rounded-lg"
        >
          <option value="">Selecciona tabla…</option>
          {tableNames.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
          {/* Keep a value set from YAML even if its table isn't in the catalog. */}
          {spec.table && !tableNames.includes(spec.table) && (
            <option value={spec.table}>{spec.table}</option>
          )}
        </NativeSelect>
      </label>

      {needsColumn && (
        <label className="block text-[11px] text-muted-foreground">
          Columna
          {columnOptions.length > 0 ? (
            <NativeSelect
              value={spec.column ?? ""}
              onValueChange={(column) => onChange({ column })}
              className="mt-1 h-8 rounded-lg"
            >
              <option value="">Selecciona columna…</option>
              {columnOptions.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
              {spec.column && !columnOptions.includes(spec.column) && (
                <option value={spec.column}>{spec.column}</option>
              )}
            </NativeSelect>
          ) : (
            <Input
              value={spec.column ?? ""}
              onChange={(e) => onChange({ column: e.target.value })}
              placeholder="nombre_columna"
              className="mt-1 h-8"
            />
          )}
        </label>
      )}

      {isPercentile && (
        <label className="block text-[11px] text-muted-foreground">
          Percentil (0–1)
          <Input
            type="number"
            step="0.05"
            min={0}
            max={1}
            value={spec.percentile ?? ""}
            onChange={(e) =>
              onChange({
                percentile: e.target.value === "" ? undefined : Number(e.target.value),
              })
            }
            placeholder="0.5"
            className="mt-1 h-8"
          />
        </label>
      )}

      {isFormula && (
        <label className="block text-[11px] text-muted-foreground">
          Fórmula personalizada
          <Input
            value={spec.formula ?? ""}
            onChange={(e) => onChange({ formula: e.target.value || undefined })}
            placeholder="df['charges'].sum() / df['age'].mean()"
            className="mt-1 h-8 font-mono"
          />
          <span className="mt-1 block text-[10px] text-muted-foreground">
            Expresión sobre <code>df</code> (el dataframe filtrado), con{" "}
            <code>np</code> y <code>pd</code>. Combina una o varias columnas.
          </span>
        </label>
      )}

      <label className="block text-[11px] text-muted-foreground">
        {filterDefinesMetric ? (
          <>
            Filtro{" "}
            <span className="text-destructive" aria-hidden="true">*</span>
            <span className="sr-only">(obligatorio)</span> —{" "}
            <span className="font-medium text-foreground">condición que define qué filas se cuentan</span>
          </>
        ) : (
          "Filtro (opcional)"
        )}
        <Input
          value={spec.filter ?? ""}
          onChange={(e) => onChange({ filter: e.target.value || undefined })}
          placeholder='p. ej. EXPIRE_FLAG == 1'
          className="mt-1 h-8 font-mono"
        />
        <span className="mt-1 block text-[10px] text-muted-foreground">
          Expresión sobre las columnas de la tabla (operadores{" "}
          <code>== != &gt; &gt;= &lt;</code>, <code>and</code>/<code>or</code>), p. ej.{" "}
          <code>age &gt;= 65</code> o{" "}
          <code>gender == &quot;F&quot; and charges &gt; 1000</code>.
          {filterDefinesMetric ? (
            <>
              {" "}Sin filtro, esta métrica mide el total de filas de la tabla y la
              comparación no aporta información: define una condición.
            </>
          ) : (
            <> Déjalo vacío para toda la tabla, o úsalo para comparar la métrica
              sobre un subgrupo (p. ej. solo fumadores).</>
          )}
        </span>
      </label>
    </div>
  );
}

function UtilityTestsBuilder({
  value,
  onChange,
  simulationColumns,
  knownTables,
}: {
  value: unknown;
  onChange: (next: UtilityTest[]) => void;
  simulationColumns?: SimulationColumns;
  knownTables?: string[];
}) {
  const tests = useMemo(() => normalizeUtilityTests(value), [value]);
  const tableNames = useMemo(() => {
    const fromCols = Object.keys(simulationColumns ?? {});
    if (fromCols.length > 0) return fromCols;
    return knownTables ?? [];
  }, [simulationColumns, knownTables]);

  const updateTest = (idx: number, patch: Partial<UtilityTest>) => {
    onChange(tests.map((t, i) => (i === idx ? { ...t, ...patch } : t)));
  };
  const updateNested = (
    idx: number,
    key: "numerator" | "denominator",
    patch: Partial<UtilitySpec>,
  ) => {
    onChange(
      tests.map((t, i) =>
        i === idx ? { ...t, [key]: { ...(t[key] ?? {}), ...patch } } : t,
      ),
    );
  };
  const addTest = () => {
    onChange([
      ...tests,
      { name: `prueba_${tests.length + 1}`, metric: "mean", table: tableNames[0] ?? "" },
    ]);
  };
  const removeTest = (idx: number) => {
    onChange(tests.filter((_, i) => i !== idx));
  };

  const onMetricChange = (idx: number, metric: string) => {
    const isComposite = metric === "rate" || metric === "ratio";
    const test = tests[idx];
    const patch: Partial<UtilityTest> = { metric };
    if (isComposite) {
      patch.numerator = test.numerator ?? { metric: "count", table: test.table ?? "" };
      patch.denominator = test.denominator ?? { metric: "count", table: test.table ?? "" };
    }
    updateTest(idx, patch);
  };

  // Predefinida = pick an operation from the dropdown; Personalizada = write a
  // formula (metric is then "custom_formula").
  const setMode = (idx: number, mode: "predefined" | "custom") => {
    if (mode === "custom") {
      updateTest(idx, { metric: "custom_formula", numerator: undefined, denominator: undefined });
    } else {
      updateTest(idx, { metric: "mean", formula: undefined });
    }
  };

  return (
    <div className="mt-2 space-y-3">
      <Button type="button" size="sm" variant="outline" onClick={addTest}>
        <Plus className="h-3.5 w-3.5" />
        Añadir agregación
      </Button>

      {tests.length === 0 && (
        <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
          Sin agregaciones definidas.
        </div>
      )}

      <div className="space-y-3">
        {tests.map((test, idx) => {
          const isComposite = test.metric === "rate" || test.metric === "ratio";
          const isCustom = test.metric === "custom_formula";
          return (
            <div key={idx} className="space-y-2 rounded-md border bg-muted/20 p-3">
              <div className="flex items-center gap-2">
                <Input
                  value={test.name ?? ""}
                  onChange={(e) => updateTest(idx, { name: e.target.value })}
                  placeholder="nombre de la prueba"
                  className="h-8 min-w-0 flex-1"
                  aria-label="Nombre de la agregación"
                />
                <Button
                  type="button"
                  size="icon-sm"
                  variant="ghost"
                  onClick={() => removeTest(idx)}
                  aria-label="Eliminar agregación"
                  title="Eliminar agregación"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>

              <div className="flex gap-1">
                <Button
                  type="button"
                  size="sm"
                  variant={isCustom ? "outline" : "default"}
                  className="h-7 flex-1 text-xs"
                  onClick={() => setMode(idx, "predefined")}
                >
                  Predefinida
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant={isCustom ? "default" : "outline"}
                  className="h-7 flex-1 gap-1.5 text-xs"
                  onClick={() => setMode(idx, "custom")}
                >
                  Personalizada
                  <AdvancedBadge tooltip="Modo avanzado: define una fórmula propia sobre una o varias columnas." />
                </Button>
              </div>

              {!isCustom && (
                <label className="block text-[11px] text-muted-foreground">
                  Métrica
                  <NativeSelect
                    value={test.metric ?? ""}
                    onValueChange={(metric) => onMetricChange(idx, metric)}
                    className="mt-1 h-8 rounded-lg"
                  >
                    <option value="">Selecciona métrica…</option>
                    {UTILITY_METRIC_OPTIONS.map((o) => (
                      <option key={o.value} value={o.value}>
                        {o.label}
                      </option>
                    ))}
                  </NativeSelect>
                </label>
              )}

              {isComposite ? (
                <div className="space-y-2">
                  {(["numerator", "denominator"] as const).map((key) => {
                    const sub = test[key] ?? {};
                    return (
                      <div key={key} className="rounded-md border bg-background/60 p-2">
                        <p className="mb-1 text-[11px] font-semibold text-muted-foreground">
                          {key === "numerator" ? "Numerador" : "Denominador"}
                        </p>
                        <label className="block text-[11px] text-muted-foreground">
                          Métrica
                          <NativeSelect
                            value={sub.metric ?? ""}
                            onValueChange={(metric) => updateNested(idx, key, { metric })}
                            className="mt-1 h-8 rounded-lg"
                          >
                            <option value="">Selecciona métrica…</option>
                            {UTILITY_SUBSPEC_METRIC_OPTIONS.map((o) => (
                              <option key={o.value} value={o.value}>
                                {o.label}
                              </option>
                            ))}
                          </NativeSelect>
                        </label>
                        <div className="mt-2">
                          <UtilitySpecBody
                            spec={sub}
                            onChange={(patch) => updateNested(idx, key, patch)}
                            tableNames={tableNames}
                            simulationColumns={simulationColumns}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <UtilitySpecBody
                  spec={test}
                  onChange={(patch) => updateTest(idx, patch)}
                  tableNames={tableNames}
                  simulationColumns={simulationColumns}
                />
              )}

              <label className="block text-[11px] text-muted-foreground">
                Peso (opcional)
                <Input
                  type="number"
                  step="0.5"
                  min={0}
                  value={test.weight ?? ""}
                  onChange={(e) =>
                    updateTest(idx, {
                      weight: e.target.value === "" ? undefined : Number(e.target.value),
                    })
                  }
                  placeholder="1.0"
                  className="mt-1 h-8"
                />
              </label>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function PerTableOverridesBuilder({
  value,
  onChange,
  availableTables,
  globalDraft,
}: {
  value: unknown;
  onChange: (next: Record<string, AnyRecord>) => void;
  availableTables: string[];
  globalDraft: AnyRecord;
}) {
  const { schemas } = useConfigSchemas();
  const mostlySchema = schemas["mostly_ai"];
  const overridableFields = useMemo(
    () => mostlySchema?.groups.flatMap((g) => g.fields.filter((f) => f.perTable)) ?? [],
    [mostlySchema],
  );
  const dpGroup = useMemo(
    () => mostlySchema?.groups.find((g) => g.toggle?.path === DP_PATH),
    [mostlySchema],
  );
  const overrides = useMemo(() => normalizePerTableOverrides(value), [value]);
  const tables = Object.keys(overrides);
  const remainingTables = availableTables.filter((t) => !tables.includes(t));
  const [tableDraft, setTableDraft] = useState("");

  const setTableOverrides = (table: string, next: AnyRecord | undefined) => {
    const result = { ...overrides };
    if (next === undefined) delete result[table];
    else result[table] = next;
    onChange(result);
  };

  const setSetting = (table: string, key: string, settingValue: unknown) => {
    const current = { ...(overrides[table] ?? {}) };
    if (settingValue === undefined) delete current[key];
    else current[key] = settingValue;
    setTableOverrides(table, current);
  };

  const addTable = (name: string) => {
    const clean = name.trim();
    if (!clean || clean in overrides) return;
    setTableOverrides(clean, {});
    setTableDraft("");
  };

  return (
    <div className="mt-2 space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row">
        {availableTables.length > 0 ? (
          <NativeSelect
            value={tableDraft}
            onValueChange={setTableDraft}
            disabled={remainingTables.length === 0}
            className="h-8 w-auto min-w-0 flex-1 rounded-lg"
          >
            <option value="">
              {remainingTables.length === 0
                ? "Todas las tablas configuradas"
                : "Elegir tabla..."}
            </option>
            {remainingTables.map((table) => (
              <option key={table} value={table}>
                {table}
              </option>
            ))}
          </NativeSelect>
        ) : (
          <Input
            value={tableDraft}
            onChange={(e) => setTableDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                addTable(tableDraft);
              }
            }}
            placeholder="Nombre de la tabla"
            className="h-8 min-w-0 flex-1"
            aria-label="Nombre de la tabla"
          />
        )}
        <Button
          type="button"
          size="sm"
          variant="outline"
          disabled={!tableDraft.trim()}
          onClick={() => addTable(tableDraft)}
        >
          <Plus className="h-3.5 w-3.5" />
          Añadir tabla
        </Button>
      </div>

      {tables.length === 0 && (
        <div className="rounded-md border border-dashed p-3 text-xs text-muted-foreground">
          Sin ajustes por tabla. Todas las tablas usan la configuración global.
        </div>
      )}

      <div className="space-y-2">
        {tables.map((table) => (
          <div key={table} className="rounded-md border bg-muted/20 p-3">
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-mono text-xs font-semibold">{table}</span>
              <Button
                type="button"
                size="icon-sm"
                variant="ghost"
                onClick={() => setTableOverrides(table, undefined)}
                aria-label={`Quitar ajustes de ${table}`}
                title="Quitar todos los ajustes de esta tabla"
              >
                <Trash2 className="h-3.5 w-3.5" />
              </Button>
            </div>

            <div className="mt-2 space-y-2">
              {overridableFields.map((field) => (
                <PerTableSettingRow
                  key={field.path}
                  table={table}
                  field={field}
                  overrides={overrides[table] ?? {}}
                  globalDraft={globalDraft}
                  onSet={(key, v) => setSetting(table, key, v)}
                />
              ))}
              {dpGroup?.toggle && (
                <PerTableDpRow
                  table={table}
                  overrides={overrides[table] ?? {}}
                  globalDraft={globalDraft}
                  dpFields={dpGroup.fields}
                  dpDefaults={dpGroup.toggle.defaults}
                  onSet={(v) => setSetting(table, DP_KEY, v)}
                />
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// One overridable setting inside a per-table card: a "Personalizar" toggle
// that, when off, shows the inherited global value and, when on, renders the
// same control used by the global form.
function PerTableSettingRow({
  table,
  field,
  overrides,
  globalDraft,
  onSet,
}: {
  table: string;
  field: FieldSchema;
  overrides: AnyRecord;
  globalDraft: AnyRecord;
  onSet: (key: string, value: unknown) => void;
}) {
  const key = field.path.slice(MODEL_SETTINGS_PREFIX.length);
  const overridden = Object.prototype.hasOwnProperty.call(overrides, key);
  const globalValue = getByPath(globalDraft, field.path);

  return (
    <div className="rounded border bg-background/60 p-2">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1">
          <span className="truncate text-xs">{field.label}</span>
          {field.help && <Tooltip content={field.help} side="top" />}
        </div>
        <label className="flex shrink-0 items-center gap-1.5 text-[11px] text-muted-foreground">
          <input
            type="checkbox"
            className="h-3.5 w-3.5"
            checked={overridden}
            onChange={(e) =>
              onSet(
                key,
                e.target.checked
                  ? (globalValue ?? (field.kind === "boolean" ? false : null))
                  : undefined,
              )
            }
          />
          Personalizar
        </label>
      </div>
      {overridden ? (
        <FieldControl
          field={{ ...field, path: `${PER_TABLE_PATH}.${table}.${key}`, help: "" }}
          value={overrides[key]}
          onChange={(raw) => onSet(key, inputToFieldValue(raw, field))}
        />
      ) : (
        <p className="mt-1 text-[11px] text-muted-foreground">
          Hereda el valor global: {describeFieldValue(globalValue, field)}
        </p>
      )}
    </div>
  );
}

// Differential privacy is a block, not a scalar: per table it can inherit the
// global config, be disabled outright (null), or use its own parameters.
function PerTableDpRow({
  table,
  overrides,
  globalDraft,
  dpFields,
  dpDefaults,
  onSet,
}: {
  table: string;
  overrides: AnyRecord;
  globalDraft: AnyRecord;
  dpFields: FieldSchema[];
  dpDefaults: AnyRecord;
  onSet: (value: unknown) => void;
}) {
  const globalDpOn = getByPath(globalDraft, DP_PATH) != null;
  const hasOverride = Object.prototype.hasOwnProperty.call(overrides, DP_KEY);
  const dpValue = overrides[DP_KEY];
  const state = !hasOverride ? "inherit" : dpValue == null ? "off" : "custom";
  const dpConfig =
    state === "custom" && dpValue && typeof dpValue === "object"
      ? (dpValue as AnyRecord)
      : {};

  return (
    <div className="rounded border bg-background/60 p-2">
      <div className="flex items-center gap-1">
        <span className="text-xs">Privacidad diferencial</span>
        <Tooltip
          content="El motor no soporta privacidad diferencial en más de 2 tablas relacionadas mediante claves de contexto. Desactívala aquí para las tablas más profundas."
          side="top"
        />
      </div>
      <NativeSelect
        value={state}
        onValueChange={(next) => {
          if (next === "inherit") onSet(undefined);
          else if (next === "off") onSet(null);
          else onSet({ ...dpDefaults });
        }}
        className="mt-1 h-8 rounded-lg"
      >
        <option value="inherit">
          Heredar configuración global ({globalDpOn ? "activada" : "desactivada"})
        </option>
        <option value="off">Desactivada en esta tabla</option>
        <option value="custom">Personalizada para esta tabla</option>
      </NativeSelect>
      {state === "custom" && (
        <div className="mt-2 space-y-2 border-l-2 pl-2">
          {dpFields.map((field) => {
            const subKey = field.path.slice(DP_PATH.length + 1);
            return (
              <div key={field.path}>
                <div className="flex items-center gap-1">
                  <Label
                    htmlFor={`${PER_TABLE_PATH}.${table}.${DP_KEY}.${subKey}`}
                    className="text-xs"
                  >
                    {field.label}
                  </Label>
                  {field.help && <Tooltip content={field.help} side="top" />}
                </div>
                <FieldControl
                  field={{
                    ...field,
                    path: `${PER_TABLE_PATH}.${table}.${DP_KEY}.${subKey}`,
                    help: "",
                  }}
                  value={dpConfig[subKey]}
                  onChange={(raw) =>
                    onSet({ ...dpConfig, [subKey]: inputToFieldValue(raw, field) })
                  }
                />
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
