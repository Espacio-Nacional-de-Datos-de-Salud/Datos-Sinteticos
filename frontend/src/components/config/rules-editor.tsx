// Editor for backend/config/rules.yaml with a structured form.
//
// Rules drive preprocessing, so this editor lives on the Inspección page.
// Available tables/columns come from the active inspection's autodetect; if
// none is available the form falls back to free-text inputs.
//
// Two presentations:
//   - <RulesEditor />: side drawer with overlay (legacy modal usage).
//   - <RulesPanel />:  inline Card variant for embedding in a step layout.
// Both share <RulesEditorBody /> for the actual form/yaml UI.

"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import yaml from "js-yaml";
import { Plus, RotateCcw, Save, Settings, Trash2, X } from "lucide-react";
import {
  api,
  type Autodetect,
  type ConfigContent,
  type FilePreview,
} from "@/lib/api";
import { extractDetail } from "@/lib/errors";
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
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { Badge } from "@/components/ui/badge";
import { Tooltip } from "@/components/ui/tooltip";

// "derived" = column-creation rules (date_to_age, numeric_threshold,
// numeric_bucket). "logical" = relationship / business rules (date/numeric
// inequality, semantic consistency, FK consistency). "all" keeps the legacy
// behavior — every rule type is visible/addable in the same panel.
export type RuleMode = "all" | "derived" | "logical";

type DrawerProps = {
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
  mode?: RuleMode;
};

type BodyProps = {
  active: boolean;
  autodetect?: Autodetect | null;
  pendingFilePaths?: string[];
  configId: string;
  onSaved?: () => void;
  mode?: RuleMode;
};

type PanelProps = {
  autodetect?: Autodetect | null;
  pendingFilePaths?: string[];
  configId?: string;
  className?: string;
  defaultOpen?: boolean;
  mode?: RuleMode;
  title?: string;
  description?: string;
};

export type RuleType =
  | "date_inequality"
  | "numeric_inequality"
  | "semantic_ranking_consistency"
  | "semantic_proportional_consistency"
  | "foreign_keys_consistency_rule"
  | "date_to_age"
  | "numeric_threshold"
  | "numeric_bucket";

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
  // date_inequality
  enforce_non_negative?: boolean;
  // Derived-column rule fields (shared)
  drop_origin?: boolean;
  reconstruct_origin?: boolean;
  // date_to_age
  reference_date?: string;
  reference_date_col?: string;
  reference_date_table?: string;
  unit?: "years" | "months" | "days";
  // numeric_threshold
  threshold?: number | null;
  operator?: ">=" | ">" | "<=" | "<";
  true_value?: string | number | boolean | null;
  false_value?: string | number | boolean | null;
  // numeric_bucket
  bins?: number[];
  labels?: string[];
  include_lowest?: boolean;
  right?: boolean;
  // Per-rule generation mode. When true the rule is enforced via rejection
  // sampling (re-draw rows that violate it) rather than the default "forced"
  // application during preprocessing/post-processing.
  rejection_sampling?: boolean;
};

type RulesFile = { rules: Rule[] };

const RULE_TYPE_LABELS: Record<RuleType, string> = {
  date_inequality: "Relación entre fechas",
  numeric_inequality: "Relación entre números",
  semantic_ranking_consistency: "Consistencia semántica (ranking)",
  semantic_proportional_consistency: "Consistencia semántica (proporcional)",
  foreign_keys_consistency_rule: "Consistencia de claves foráneas",
  date_to_age: "Derivar edad o lapso desde fecha",
  numeric_threshold: "Columna derivada: umbral numérico",
  numeric_bucket: "Columna estratificada: buckets numéricos",
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
  date_to_age:
    "Crea una columna derivada con el lapso (en años, meses o días) entre una columna de fecha y una referencia (constante u otra columna). Usa «días» para duraciones cortas como estancias o episodios.",
  numeric_threshold:
    "Crea una columna booleana comparando una columna numérica con un umbral (≥, >, ≤, <).",
  numeric_bucket:
    "Crea una columna categórica estratificando una columna numérica por intervalos (bins). Útil para generalizar el modelo.",
};

const DERIVED_RULE_TYPES: RuleType[] = [
  "date_to_age",
  "numeric_threshold",
  "numeric_bucket",
];

const LOGICAL_RULE_TYPES: RuleType[] = [
  "date_inequality",
  "numeric_inequality",
  "semantic_ranking_consistency",
  "semantic_proportional_consistency",
  "foreign_keys_consistency_rule",
];

function ruleTypesForMode(mode: RuleMode): RuleType[] {
  if (mode === "derived") return DERIVED_RULE_TYPES;
  if (mode === "logical") return LOGICAL_RULE_TYPES;
  return Object.keys(RULE_TYPE_LABELS) as RuleType[];
}

function ruleMatchesMode(rule: Rule, mode: RuleMode): boolean {
  if (mode === "all") return true;
  if (mode === "derived") return DERIVED_RULE_TYPES.includes(rule.type);
  return LOGICAL_RULE_TYPES.includes(rule.type);
}

// Whitelist of fields per rule type — must match the backend dataclass
// constructors in `backend/src/domain/preprocessing/logical_rules.py`. Any
// extra kwarg triggers a TypeError that silently drops the rule
// (`rules_config.extract_rules_and_rejection_config`).
const RULE_TYPE_FIELDS: Record<RuleType, (keyof Rule)[]> = {
  date_inequality: [
    "table_origin",
    "origin_col",
    "table_target",
    "target_col",
    "aux_col",
    "constraint",
    "constraint_operator",
    "enforce_non_negative",
    "rejection_sampling",
  ],
  numeric_inequality: [
    "table_origin",
    "origin_col",
    "table_target",
    "target_col",
    "aux_col",
    "constraint",
    "constraint_operator",
    "rejection_sampling",
  ],
  semantic_ranking_consistency: [
    "table_origin",
    "origin_col",
    "table_target",
    "target_col",
    "rejection_sampling",
  ],
  semantic_proportional_consistency: [
    "table_origin",
    "origin_col",
    "table_target",
    "target_col",
    "rejection_sampling",
  ],
  foreign_keys_consistency_rule: [
    "table_origin",
    "table_target",
    "target_col",
    "source_col",
    "referenced_table",
    "rejection_sampling",
  ],
  date_to_age: [
    "table_origin",
    "table_target",
    "origin_col",
    "aux_col",
    "reference_date",
    "reference_date_col",
    "reference_date_table",
    "unit",
    "enforce_non_negative",
    "drop_origin",
    "reconstruct_origin",
  ],
  numeric_threshold: [
    "table_origin",
    "table_target",
    "origin_col",
    "aux_col",
    "threshold",
    "operator",
    "true_value",
    "false_value",
    "drop_origin",
    "reconstruct_origin",
  ],
  numeric_bucket: [
    "table_origin",
    "table_target",
    "origin_col",
    "aux_col",
    "bins",
    "labels",
    "include_lowest",
    "right",
    "drop_origin",
    "reconstruct_origin",
  ],
};

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
  if (DERIVED_RULE_TYPES.includes(r.type)) {
    const tgt = r.table_target ?? "?";
    const src = r.origin_col ?? "?";
    const dst = r.aux_col ?? "?";
    if (r.type === "date_to_age") {
      const ref = r.reference_date_col ?? r.reference_date ?? "?";
      return `${tgt}.${dst} = age(${src}, ${ref})`;
    }
    if (r.type === "numeric_threshold") {
      return `${tgt}.${dst} = (${src} ${r.operator ?? ">="} ${r.threshold ?? "?"})`;
    }
    if (r.type === "numeric_bucket") {
      const bins = r.bins?.length ? `[${r.bins.join(", ")}]` : "?";
      return `${tgt}.${dst} = bucket(${src}, ${bins})`;
    }
  }
  return `${left} → ${right}`;
}

function RulesEditorBody({
  active,
  autodetect,
  pendingFilePaths,
  configId,
  onSaved,
  mode = "all",
}: BodyProps) {
  const queryClient = useQueryClient();
  // Visible rules (those matching the panel's mode) — these are the ones the
  // user edits. Hidden rules (not matching the mode) are preserved verbatim
  // and merged back in on save so a derived-mode panel never clobbers logical
  // rules in the same file (and vice versa).
  const [rules, setRules] = useState<Rule[]>([]);
  const [hiddenRules, setHiddenRules] = useState<Rule[]>([]);
  const [draftYaml, setDraftYaml] = useState<string>("");
  const [yamlMode, setYamlMode] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  // The add-rule form is shown by default so the user can start defining a
  // rule without an extra click. Saving collapses it back to a rule card.
  const [adding, setAdding] = useState(true);
  const [editingIndex, setEditingIndex] = useState<number | null>(null);

  const configQuery = useQuery({
    queryKey: ["config", configId],
    enabled: active,
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
    enabled: active && (pendingFilePaths?.length ?? 0) > 0,
    queryFn: async () => {
      const { data } = await api.post<FilePreview[]>("/files/preview", {
        paths: pendingFilePaths ?? [],
        sample_rows: 0,
      });
      return data;
    },
  });

  useEffect(() => {
    if (!active || !configQuery.data) return;
    try {
      const parsed = (yaml.load(configQuery.data.content) as RulesFile) ?? {
        rules: [],
      };
      const all = parsed.rules ?? [];
      queueMicrotask(() => {
        setRules(all.filter((r) => ruleMatchesMode(r, mode)));
        setHiddenRules(all.filter((r) => !ruleMatchesMode(r, mode)));
        setDraftYaml(configQuery.data.content);
        setParseError(null);
      });
    } catch (e) {
      queueMicrotask(() => {
        setParseError(e instanceof Error ? e.message : String(e));
      });
    }
  }, [active, configQuery.data, mode]);

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

  // Augment with aux_cols produced by derived-column rules already in the list,
  // so a later rule can target a column that doesn't exist in source data yet
  // (e.g. numeric_threshold on an `edad` aux column produced by date_to_age).
  // The backend sorts dependent rules in PRE, so chaining is supported.
  const columnsByTableWithDerived = useMemo(() => {
    const m: Record<string, string[]> = {};
    for (const [t, cols] of Object.entries(columnsByTable)) {
      m[t] = [...cols];
    }
    for (const r of rules) {
      if (!DERIVED_RULE_TYPES.includes(r.type)) continue;
      if (!r.table_target || !r.aux_col) continue;
      const list = m[r.table_target] ?? (m[r.table_target] = []);
      if (!list.includes(r.aux_col)) list.push(r.aux_col);
    }
    return m;
  }, [columnsByTable, rules]);

  const tableNamesWithDerived = useMemo(
    () => Object.keys(columnsByTableWithDerived).sort(),
    [columnsByTableWithDerived],
  );

  const buildYaml = (rs: Rule[]): string =>
    yaml.dump(
      {
        rules: [...hiddenRules, ...rs].map((r) => {
          // Only emit fields relevant to this rule type. The backend rule
          // dataclasses reject unknown kwargs (TypeError), and
          // `rules_config.extract_rules_and_rejection_config` then skips the
          // rule silently — so leaking e.g. `constraint_operator` into a
          // derived-column rule would make it never apply.
          const allowed = RULE_TYPE_FIELDS[r.type];
          const out: Record<string, unknown> = { type: r.type };
          for (const k of allowed) {
            const v = (r as Record<string, unknown>)[k];
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
      const all = parsed.rules ?? [];
      setRules(all.filter((r) => ruleMatchesMode(r, mode)));
      setHiddenRules(all.filter((r) => !ruleMatchesMode(r, mode)));
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
      onSaved?.();
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

  return (
    <>
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
                  tableNames={tableNamesWithDerived}
                  columnsByTable={columnsByTableWithDerived}
                  mode={mode}
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
                tableNames={tableNamesWithDerived}
                columnsByTable={columnsByTableWithDerived}
                mode={mode}
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
        <Button
          type="button"
          size="sm"
          disabled={saveMutation.isPending || !!parseError}
          onClick={() => saveMutation.mutate()}
        >
          <Save className="mr-2 h-4 w-4" />
          {saveMutation.isPending ? "Guardando…" : "Guardar"}
        </Button>
      </footer>

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

export function RulesEditor({
  open,
  onClose,
  autodetect,
  pendingFilePaths,
  configId = "rules",
  onSaved,
  mode = "all",
}: DrawerProps) {
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
        <RulesEditorBody
          active={open}
          autodetect={autodetect}
          pendingFilePaths={pendingFilePaths}
          configId={configId}
          mode={mode}
          onSaved={() => {
            onSaved?.();
            onClose();
          }}
        />
      </aside>
    </>
  );
}

export function RulesPanel({
  autodetect,
  pendingFilePaths,
  configId = "rules",
  className,
  defaultOpen = false,
  mode = "all",
  title,
  description,
}: PanelProps) {
  const [open, setOpen] = useState(defaultOpen);
  const resolvedTitle =
    title ??
    (mode === "derived"
      ? "Crear columnas derivadas"
      : mode === "logical"
        ? "Reglas lógicas / de negocio"
        : "Reglas de preprocesamiento");
  const resolvedDescription =
    description ??
    (mode === "derived"
      ? "Define columnas nuevas a partir de columnas existentes (edad a partir de fecha, umbral booleano, estratificación por buckets)."
      : mode === "logical"
        ? "Define restricciones entre columnas o entre una columna y un valor (orden de fechas, consistencia semántica, claves foráneas). Para cada regla, elige si se aplica forzada o por muestreo por rechazo."
        : "Definen restricciones que el modelo debe respetar (orden de fechas, consistencia entre categóricas, etc.). Se aplican durante la inspección y la generación.");
  return (
    <Card className={className}>
      <CardHeader className="flex flex-row items-start justify-between gap-4 space-y-0">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Settings className="h-3.5 w-3.5" />
            <span className="font-mono">
              {configId.split("/").pop() || "rules.yaml"}
            </span>
          </div>
          <CardTitle className="text-base">{resolvedTitle}</CardTitle>
          <CardDescription>{resolvedDescription}</CardDescription>
        </div>
        <CollapseToggle
          open={open}
          onToggle={() => setOpen((v) => !v)}
          ariaLabel={open ? "Contraer reglas" : "Expandir reglas"}
        />
      </CardHeader>
      {open && (
        <CardContent className="flex flex-col p-0">
          <RulesEditorBody
            active
            autodetect={autodetect}
            pendingFilePaths={pendingFilePaths}
            configId={configId}
            mode={mode}
          />
        </CardContent>
      )}
    </Card>
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
  const isDerived = DERIVED_RULE_TYPES.includes(rule.type);
  return (
    <div className={"rounded-md border p-3 " + (isDerived ? "bg-blue-50/40 dark:bg-blue-950/20" : "bg-card")}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge
              variant="secondary"
              className={
                "text-[10px] " +
                (isDerived
                  ? "border-blue-400/50 bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300"
                  : "")
              }
            >
              {RULE_TYPE_LABELS[rule.type] ?? rule.type}
            </Badge>
            {LOGICAL_RULE_TYPES.includes(rule.type) && (
              <Badge
                variant="outline"
                className={
                  "text-[10px] " +
                  (rule.rejection_sampling
                    ? "border-amber-500/70 text-amber-700 dark:text-amber-400"
                    : "")
                }
              >
                {rule.rejection_sampling ? "Muestreo por rechazo" : "Forzado"}
              </Badge>
            )}
            {isDerived && rule.aux_col && (
              <span className="text-[11px] text-blue-700 dark:text-blue-400">
                nueva col.: <span className="font-mono">{rule.aux_col}</span>
              </span>
            )}
          </div>
          <p className="mt-1 truncate font-mono text-xs text-muted-foreground">{summarizeRule(rule)}</p>
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
  mode = "all",
  onCancel,
  onSubmit,
}: {
  initial?: Rule;
  tableNames: string[];
  columnsByTable: Record<string, string[]>;
  mode?: RuleMode;
  onCancel: () => void;
  onSubmit: (rule: Rule) => void;
}) {
  const allowedTypes = useMemo(() => ruleTypesForMode(mode), [mode]);
  const [draft, setDraft] = useState<Rule>(
    initial ??
    (mode === "derived"
      ? { type: "numeric_bucket" }
      : { type: "date_inequality", constraint_operator: ">=" }),
  );

  const update = (patch: Partial<Rule>) =>
    setDraft((prev) => ({ ...prev, ...patch }));

  const showInequality =
    draft.type === "date_inequality" || draft.type === "numeric_inequality";
  const showFK = draft.type === "foreign_keys_consistency_rule";
  const showDerived = DERIVED_RULE_TYPES.includes(draft.type);

  const derivedValid =
    !!draft.table_target &&
    !!draft.origin_col &&
    !!draft.aux_col &&
    draft.origin_col !== draft.aux_col &&
    (draft.type !== "date_to_age" ||
      !!draft.reference_date ||
      !!draft.reference_date_col) &&
    (draft.type !== "numeric_threshold" ||
      (draft.threshold !== undefined && draft.threshold !== null)) &&
    (draft.type !== "numeric_bucket" || (draft.bins?.length ?? 0) >= 2);

  const hasConstraint =
    draft.constraint !== undefined &&
    draft.constraint !== null &&
    String(draft.constraint).trim() !== "";
  const valid = showDerived
    ? derivedValid
    : showInequality
      ? !!draft.table_target &&
      !!draft.target_col &&
      ((!!draft.table_origin && !!draft.origin_col) || hasConstraint)
      : !!draft.table_target &&
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
            setDraft({
              type: e.target.value as RuleType,
              constraint_operator: ">=",
            })
          }
          className="mt-1 h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm"
        >
          {allowedTypes.map((t) => (
            <option key={t} value={t}>
              {RULE_TYPE_LABELS[t]}
            </option>
          ))}
        </select>
        <p className="mt-1 text-[11px] text-muted-foreground">
          {RULE_TYPE_HELP[draft.type]}
        </p>
      </div>

      {showDerived ? (
        <DerivedRuleFields
          draft={draft}
          update={update}
          tableNames={tableNames}
          columnsByTable={columnsByTable}
        />
      ) : showInequality ? (
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

          {draft.type === "date_inequality" && (
            <div
              className={
                "col-span-3 " + (draft.rejection_sampling ? "opacity-50" : "")
              }
            >
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4"
                  disabled={!!draft.rejection_sampling}
                  checked={draft.enforce_non_negative !== false}
                  onChange={(e) =>
                    update({ enforce_non_negative: e.target.checked })
                  }
                />
                <span>Forzar duraciones no negativas</span>
              </label>
              <p className="mt-1 text-[11px] text-muted-foreground">
                {draft.rejection_sampling
                  ? "No aplica en muestreo por rechazo: no se reconstruye nada, las filas se resimulan."
                  : "Limita las duraciones a valores ≥ 0. Desactiva para permitir duraciones negativas (p. ej., edades futuras)."}
              </p>
            </div>
          )}
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

      {LOGICAL_RULE_TYPES.includes(draft.type) && (
        <div className="rounded-md border bg-background p-2 text-xs">
          <Label className="text-xs">Modo de aplicación</Label>
          <div className="mt-1 flex flex-col gap-1">
            <label className="flex items-start gap-2">
              <input
                type="radio"
                name="rejection-mode"
                className="mt-0.5"
                checked={!draft.rejection_sampling}
                onChange={() => update({ rejection_sampling: false })}
              />
              <span className="flex flex-1 items-start gap-1.5">
                <span>
                  <span className="font-medium">Forzado</span>
                  <span className="ml-1 text-muted-foreground">
                    — aplicar la regla durante el preprocesado/postprocesado.
                  </span>
                </span>
                <Tooltip
                  side="right"
                  content="Eficiente computacionalmente: la regla se aplica de forma determinista. Riesgo: si los datos reales no cumplen la regla, al forzarla se distorsionan las distribuciones para que se cumpla por construcción — los datos sintéticos dejan de reflejar la realidad."
                />
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input
                type="radio"
                name="rejection-mode"
                className="mt-0.5"
                checked={!!draft.rejection_sampling}
                onChange={() => update({ rejection_sampling: true })}
              />
              <span className="flex flex-1 items-start gap-1.5">
                <span>
                  <span className="font-medium">Muestreo por rechazo</span>
                  <span className="ml-1 text-muted-foreground">
                    — descartar filas que la incumplan y volver a muestrear.
                  </span>
                </span>
                <Tooltip
                  side="right"
                  content="Más seguro: no fuerza la regla, sino que resimula la fila entera hasta que cumpla, de modo que toda la fila queda coherente entre sí. Costoso computacionalmente y, si se alcanza el nº máximo de intentos, puede no llegarse al total de filas solicitado."
                />
              </span>
            </label>
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

function DerivedRuleFields({
  draft,
  update,
  tableNames,
  columnsByTable,
}: {
  draft: Rule;
  update: (patch: Partial<Rule>) => void;
  tableNames: string[];
  columnsByTable: Record<string, string[]>;
}) {
  const targetCols = draft.table_target
    ? (columnsByTable[draft.table_target] ?? [])
    : [];
  const hasSchema = tableNames.length > 0;

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-xs">Tabla objetivo</Label>
          {hasSchema ? (
            <select
              value={draft.table_target ?? ""}
              onChange={(e) =>
                update({
                  table_target: e.target.value,
                  origin_col: undefined,
                  reference_date_col: undefined,
                  reference_date_table: undefined,
                })
              }
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
              value={draft.table_target ?? ""}
              onChange={(e) => update({ table_target: e.target.value })}
              placeholder="nombre de tabla"
              className="mt-1"
            />
          )}
        </div>
        <div>
          <Label className="text-xs">
            {draft.type === "date_to_age" ? (
              <>
                Fecha origen (la más reciente)
                <Tooltip
                  side="top"
                  content="Convención: la fecha origen es la MÁS RECIENTE (admisión, fin de episodio, fecha de la consulta…). El cálculo es origen − referencia, así que la referencia de abajo debe ser la MÁS ANTIGUA (DOB, inicio del episodio…). Si activas «forzar lapso ≥ 0», los negativos se truncan a 0; desactiva para conservar el signo."
                />
              </>
            ) : (
              "Columna objetivo"
            )}
          </Label>
          {hasSchema && targetCols.length > 0 ? (
            <select
              value={draft.origin_col ?? ""}
              onChange={(e) => update({ origin_col: e.target.value })}
              className="mt-1 h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm"
            >
              <option value="">— elegir —</option>
              {targetCols.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </select>
          ) : (
            <Input
              value={draft.origin_col ?? ""}
              onChange={(e) => update({ origin_col: e.target.value })}
              placeholder="nombre de columna"
              className="mt-1"
            />
          )}
        </div>
      </div>

      <div>
        <Label className="text-xs">
          Nombre de la nueva columna <span className="text-destructive">*</span>
        </Label>
        <Input
          value={draft.aux_col ?? ""}
          onChange={(e) => update({ aux_col: e.target.value || undefined })}
          placeholder="p. ej. edad, is_adult, age_group"
          className="mt-1"
        />
        <p className="mt-1 text-[11px] text-muted-foreground">
          Obligatorio. Debe ser distinto del nombre de la columna objetivo.
        </p>
      </div>

      {draft.type === "date_to_age" && (
        <>
          <DateToAgeReferenceFields
            draft={draft}
            update={update}
            tableNames={tableNames}
            columnsByTable={columnsByTable}
          />
          <div>
            <Label className="text-xs">
              Unidad del lapso
              <Tooltip
                side="top"
                content="Granularidad del valor derivado. «Años» es la opción clásica para edad. Usa «Días» o «Meses» para duraciones cortas (estancias, episodios) — de lo contrario un episodio de 5 días redondea a 0 años."
              />
            </Label>
            <select
              value={draft.unit ?? "years"}
              onChange={(e) =>
                update({ unit: e.target.value as "years" | "months" | "days" })
              }
              className="mt-1 h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm"
            >
              <option value="years">Años</option>
              <option value="months">Meses</option>
              <option value="days">Días</option>
            </select>
          </div>
          <div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                className="h-4 w-4"
                checked={draft.enforce_non_negative !== false}
                onChange={(e) =>
                  update({ enforce_non_negative: e.target.checked })
                }
              />
              <span>Forzar lapso no negativo</span>
            </label>
            <p className="mt-1 text-[11px] text-muted-foreground">
              Limita el lapso a valores ≥ 0 (truncando los negativos). Desactiva
              si el origen puede ser posterior a la referencia y quieres
              conservar el signo (p. ej. fechas futuras frente a una referencia
              pasada).
            </p>
          </div>
        </>
      )}

      {draft.type === "numeric_threshold" && (
        <div className="grid grid-cols-[1fr_auto_1fr] items-end gap-2">
          <div>
            <Label className="text-xs">Operador</Label>
            <select
              value={draft.operator ?? ">="}
              onChange={(e) =>
                update({
                  operator: e.target.value as ">=" | ">" | "<=" | "<",
                })
              }
              className="mt-1 h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm"
            >
              <option value=">=">≥</option>
              <option value=">">&gt;</option>
              <option value="<=">≤</option>
              <option value="<">&lt;</option>
            </select>
          </div>
          <div>
            <Label className="text-xs">Umbral</Label>
            <Input
              type="number"
              value={draft.threshold == null ? "" : String(draft.threshold)}
              onChange={(e) =>
                update({
                  threshold: e.target.value === "" ? null : Number(e.target.value),
                })
              }
              className="mt-1"
            />
          </div>
          <div className="col-span-3 grid grid-cols-2 gap-2">
            <div>
              <Label className="text-xs">Valor si verdadero (opcional)</Label>
              <Input
                value={
                  draft.true_value == null ? "" : String(draft.true_value)
                }
                onChange={(e) =>
                  update({ true_value: e.target.value || undefined })
                }
                placeholder="True"
                className="mt-1"
              />
            </div>
            <div>
              <Label className="text-xs">Valor si falso (opcional)</Label>
              <Input
                value={
                  draft.false_value == null ? "" : String(draft.false_value)
                }
                onChange={(e) =>
                  update({ false_value: e.target.value || undefined })
                }
                placeholder="False"
                className="mt-1"
              />
            </div>
          </div>
        </div>
      )}

      {draft.type === "numeric_bucket" && (
        <div className="space-y-2">
          <div>
            <Label className="text-xs">Bordes de bins (coma o espacio)</Label>
            <Input
              value={(draft.bins ?? []).join(", ")}
              onChange={(e) => {
                const parts = e.target.value
                  .split(/[,\s]+/)
                  .map((s) => s.trim())
                  .filter((s) => s.length > 0);
                const nums = parts
                  .map((s) => (s === "inf" || s === "Infinity" ? Infinity : Number(s)))
                  .filter((n) => !Number.isNaN(n));
                update({ bins: nums });
              }}
              placeholder="0, 18, 65, Infinity"
              className="mt-1 font-mono"
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              Se necesitan al menos 2 valores. Usa &quot;Infinity&quot; para
              límites abiertos.
            </p>
          </div>
          <div>
            <Label className="text-xs">Etiquetas (opcional)</Label>
            <Input
              value={(draft.labels ?? []).join(", ")}
              onChange={(e) => {
                const parts = e.target.value
                  .split(",")
                  .map((s) => s.trim())
                  .filter((s) => s.length > 0);
                update({ labels: parts.length ? parts : undefined });
              }}
              placeholder="child, adult, senior"
              className="mt-1"
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              Si se indican, deben ser exactamente {(draft.bins?.length ?? 0) - 1 || "N-1"}{" "}
              etiquetas.
            </p>
          </div>
          <div className="flex gap-4">
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={draft.include_lowest ?? true}
                onChange={(e) =>
                  update({ include_lowest: e.target.checked })
                }
              />
              include_lowest
            </label>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={draft.right ?? false}
                onChange={(e) => update({ right: e.target.checked })}
              />
              right (bins inclusivos por la derecha)
            </label>
          </div>
        </div>
      )}

      <div className="flex gap-4 border-t pt-3">
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={draft.drop_origin ?? false}
            onChange={(e) =>
              update({
                drop_origin: e.target.checked,
                reconstruct_origin: e.target.checked
                  ? draft.reconstruct_origin
                  : false,
              })
            }
          />
          Eliminar columna objetivo
          <Tooltip
            side="top"
            content="Tras crear la nueva columna, descarta la columna objetivo de los datos preprocesados para que el modelo solo aprenda la versión derivada. Activa cuando la derivada resume todo lo útil de la original (p. ej. te basta «is_adult» y no quieres que el modelo aprenda «age») y para evitar redundancia/colinealidad. Desactiva si quieres conservar la columna objetivo en el entrenamiento."
          />
        </label>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={draft.reconstruct_origin ?? false}
            disabled={!draft.drop_origin}
            onChange={(e) =>
              update({ reconstruct_origin: e.target.checked })
            }
          />
          Reconstruir en POST
          <Tooltip
            side="top"
            content="Solo aplica si has marcado «Eliminar columna objetivo». En la fase POST, recompone la columna objetivo a partir de la derivada (cuando es invertible: p. ej. de «edad» se puede reconstruir una fecha de nacimiento aproximada usando la fecha de referencia). Activa si quieres que la columna objetivo aparezca también en los datos sintéticos finales sin que el modelo la haya aprendido directamente. Desactiva si solo necesitas la columna derivada en el output."
          />
        </label>
      </div>
    </div>
  );
}

// Reference-date picker for date_to_age. The user picks ONE of two modes:
//   - Constante: free-text date string (e.g. 2020-01-01)
//   - Columna: tabla + columna; when tabla != table_target the backend
//     joins them via the FK path and the column is read from the joined
//     view in apply_pre.
//
// Switching modes clears the inactive fields so the rule only ever
// carries one source of truth, matching the backend's __post_init__
// validation (`reference_date` XOR `reference_date_col` + optional
// `reference_date_table`).
function DateToAgeReferenceFields({
  draft,
  update,
  tableNames,
  columnsByTable,
}: {
  draft: Rule;
  update: (patch: Partial<Rule>) => void;
  tableNames: string[];
  columnsByTable: Record<string, string[]>;
}) {
  // The mode (constant vs. column) is tracked locally rather than derived from
  // draft truthiness: clearing the inactive side leaves both fields empty, so a
  // derived-only mode would snap back to its default the moment the user
  // toggled. Keep local state in sync when the draft is replaced from outside
  // (loading an existing rule).
  const [mode, setModeState] = useState<"constant" | "column">(
    draft.reference_date_col ? "column" : "constant",
  );
  useEffect(() => {
    if (draft.reference_date_col) setModeState("column");
    else if (draft.reference_date) setModeState("constant");
  }, [draft.reference_date_col, draft.reference_date]);

  const hasSchema = tableNames.length > 0;
  const refTable = draft.reference_date_table || draft.table_target || "";
  const refTableCols = refTable ? (columnsByTable[refTable] ?? []) : [];

  const setMode = (next: "constant" | "column") => {
    setModeState(next);
    if (next === "constant") {
      update({
        reference_date_col: undefined,
        reference_date_table: undefined,
      });
    } else {
      update({ reference_date: undefined });
    }
  };

  return (
    <div className="space-y-2 rounded-md border bg-background p-2">
      <Label className="text-xs">
        Fecha de referencia (la más antigua)
        <Tooltip
          side="top"
          content="La fecha contra la que se resta el origen (DOB para edad, inicio del episodio para duración). Puede ser una fecha fija o una columna. El cálculo es origen − referencia."
        />
      </Label>
      <div className="flex flex-col gap-1 text-xs">
        <label className="flex items-start gap-2">
          <input
            type="radio"
            name="date-to-age-ref"
            className="mt-0.5"
            checked={mode === "constant"}
            onChange={() => setMode("constant")}
          />
          <span>
            <span className="font-medium">Fecha constante</span>
            <span className="ml-1 text-muted-foreground">
              — un valor fijo para todas las filas (p. ej. fecha del estudio).
            </span>
          </span>
        </label>
        <label className="flex items-start gap-2">
          <input
            type="radio"
            name="date-to-age-ref"
            className="mt-0.5"
            checked={mode === "column"}
            onChange={() => setMode("column")}
          />
          <span>
            <span className="font-medium">Columna de referencia</span>
            <span className="ml-1 text-muted-foreground">
              — usar otra columna fecha como referencia por fila (puede estar
              en otra tabla relacionada).
            </span>
          </span>
        </label>
      </div>

      {mode === "constant" ? (
        <div>
          <Input
            value={draft.reference_date ?? ""}
            onChange={(e) =>
              update({ reference_date: e.target.value || undefined })
            }
            placeholder="p. ej. 2020-01-01"
            className="mt-1"
          />
          <p className="mt-1 text-[11px] text-muted-foreground">
            Formato parseable por pandas (ISO 8601 funciona bien).
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2 pt-1">
          <div>
            <Label className="text-xs">Tabla</Label>
            {hasSchema ? (
              <select
                value={refTable}
                onChange={(e) => {
                  const t = e.target.value;
                  update({
                    reference_date_table:
                      t && t !== draft.table_target ? t : undefined,
                    reference_date_col: undefined,
                  });
                }}
                className="mt-1 h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm"
              >
                {tableNames.map((t) => (
                  <option key={t} value={t}>
                    {t}
                    {t === draft.table_target ? " (misma tabla)" : ""}
                  </option>
                ))}
              </select>
            ) : (
              <Input
                value={refTable}
                onChange={(e) =>
                  update({
                    reference_date_table:
                      e.target.value && e.target.value !== draft.table_target
                        ? e.target.value
                        : undefined,
                    reference_date_col: undefined,
                  })
                }
                placeholder="nombre de tabla"
                className="mt-1"
              />
            )}
          </div>
          <div>
            <Label className="text-xs">Columna</Label>
            {hasSchema && refTableCols.length > 0 ? (
              <select
                value={draft.reference_date_col ?? ""}
                onChange={(e) =>
                  update({ reference_date_col: e.target.value || undefined })
                }
                className="mt-1 h-8 w-full rounded-lg border border-input bg-background px-2.5 text-sm"
              >
                <option value="">— elegir —</option>
                {refTableCols.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            ) : (
              <Input
                value={draft.reference_date_col ?? ""}
                onChange={(e) =>
                  update({ reference_date_col: e.target.value || undefined })
                }
                placeholder="nombre de columna"
                className="mt-1"
              />
            )}
          </div>
          {draft.reference_date_table && (
            <p className="col-span-2 text-[11px] text-muted-foreground">
              La columna está en otra tabla; el motor unirá{" "}
              <span className="font-mono">{draft.table_target}</span> con{" "}
              <span className="font-mono">{draft.reference_date_table}</span>{" "}
              usando las claves foráneas detectadas en la carga de datos.
            </p>
          )}
        </div>
      )}
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
