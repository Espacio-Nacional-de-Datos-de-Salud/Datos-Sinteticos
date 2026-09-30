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

import { useEffect, useId, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import yaml from "js-yaml";
import {
  AlertTriangle,
  Plus,
  RotateCcw,
  Save,
  Settings,
  Trash2,
  X,
} from "lucide-react";
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
import { NativeSelect } from "@/components/ui/native-select";
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
  | "numeric_bucket"
  | "date_composition";

const DATE_PART_NAMES = ["year", "month", "day", "hour", "minute", "second"] as const;
type DatePart = (typeof DATE_PART_NAMES)[number];
const DATE_PART_LABELS: Record<DatePart, string> = {
  year: "Año",
  month: "Mes",
  day: "Día",
  hour: "Hora",
  minute: "Minuto",
  second: "Segundo",
};

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
  // date_composition
  canonical_col?: string;
  part_cols?: Partial<Record<DatePart, string>>;
  // Per-rule generation mode. When true the rule is enforced via rejection
  // sampling (re-draw rows that violate it) rather than the default "forced"
  // application during preprocessing/post-processing.
  rejection_sampling?: boolean;
};

type RejectionSamplingSettings = {
  max_attempts?: number;
  overgenerate_factor?: number;
};

type RulesFile = { rules: Rule[]; rejection_sampling?: RejectionSamplingSettings };

// Defaults mirror the backend (_resolve_rejection_sampling_config).
const DEFAULT_REJECTION_SAMPLING: Required<RejectionSamplingSettings> = {
  max_attempts: 5,
  overgenerate_factor: 2,
};

const RULE_TYPE_LABELS: Record<RuleType, string> = {
  date_inequality: "Relación entre fechas",
  numeric_inequality: "Relación entre números",
  semantic_ranking_consistency: "Consistencia semántica (flexible)",
  semantic_proportional_consistency: "Consistencia semántica (fijo)",
  foreign_keys_consistency_rule: "Consistencia de claves foráneas",
  date_to_age: "Derivar edad o lapso desde fecha",
  numeric_threshold: "Columna derivada: umbral numérico",
  numeric_bucket: "Columna estratificada: intervalos numéricos",
  date_composition: "Componer fecha desde columnas año/mes/día",
};

const RULE_TYPE_HELP: Record<RuleType, string> = {
  date_inequality:
    "Garantiza que una fecha objetivo cumpla un orden (≥ o ≤) respecto a una fecha origen o una constante.",
  numeric_inequality:
    "Garantiza que un valor numérico objetivo cumpla un orden (≥ o ≤) respecto a un origen o constante.",
  semantic_ranking_consistency:
    "Restringe qué combinaciones (origen, objetivo) son válidas en un categórico; el modelo aprende libremente las proporciones.",
  semantic_proportional_consistency:
    "Como la flexible, pero además fuerza las proporciones reales de cada categoría.",
  foreign_keys_consistency_rule:
    "Reconstruye una FK redundante copiando el valor desde la tabla padre marcada como contexto.",
  date_to_age:
    "Crea una columna derivada con el lapso (en años, meses o días) entre una columna de fecha y una referencia (constante u otra columna). Usa «días» para duraciones cortas como estancias o episodios.",
  numeric_threshold:
    "Crea una columna booleana comparando una columna numérica con un umbral (≥, >, ≤, <).",
  numeric_bucket:
    "Crea una columna categórica estratificando una columna numérica por intervalos. Útil para generalizar el modelo.",
  date_composition:
    "Tratar columnas año/mes/día como derivadas de una fecha canónica: se eliminan en el entreno y se reconstruyen tras la generación para evitar incoherencias.",
};

const DERIVED_RULE_TYPES: RuleType[] = [
  "date_to_age",
  "numeric_threshold",
  "numeric_bucket",
];

// Rules that live in the "Reglas lógicas / de negocio" panel. date_composition
// fits here because it doesn't create new columns nor destroy semantic info —
// it just declares a deterministic relationship between a canonical date and
// its split parts (year/month/day…), conceptually a business rule.
const LOGICAL_RULE_TYPES: RuleType[] = [
  "date_inequality",
  "numeric_inequality",
  "semantic_ranking_consistency",
  "semantic_proportional_consistency",
  "date_composition",
];

// Subset of logical rules that support the forced/rejection-sampling toggle.
// date_composition is always deterministic (drop in PRE, re-derive in POST),
// so it's excluded from this UI control.
const REJECTION_SAMPLING_RULE_TYPES: RuleType[] = [
  "date_inequality",
  "numeric_inequality",
  "semantic_ranking_consistency",
  "semantic_proportional_consistency",
];

// Count of date_composition candidate warnings emitted during inspection that
// don't yet have a corresponding rule registered. Used to surface a warning
// badge on the rules panel header so the user notices the suggestions
// without having to expand the panel first (same pattern as types-card).
export function countDateCompositionSuggestions(
  autodetect: Autodetect | null | undefined,
  registered: { type: string; table_target?: string; canonical_col?: string }[],
): number {
  if (!autodetect?.warnings?.length) return 0;
  const seen = new Set<string>();
  for (const w of autodetect.warnings) {
    if (w.kind !== "date_composition_candidate") continue;
    const d = (w.details ?? {}) as { canonical_col?: string };
    if (!d.canonical_col) continue;
    const key = `${w.table}::${d.canonical_col}`;
    if (seen.has(key)) continue;
    const covered = registered.some(
      (r) =>
        r.type === "date_composition" &&
        r.table_target === w.table &&
        r.canonical_col === d.canonical_col,
    );
    if (!covered) seen.add(key);
  }
  return seen.size;
}

function ruleTypesForMode(mode: RuleMode): RuleType[] {
  if (mode === "derived") return DERIVED_RULE_TYPES;
  if (mode === "logical") return LOGICAL_RULE_TYPES;
  return (Object.keys(RULE_TYPE_LABELS) as RuleType[]).filter(
    (t) => t !== "foreign_keys_consistency_rule",
  );
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
    "unit",
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
  date_composition: ["table_target", "canonical_col", "part_cols"],
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
    if (r.type === "date_composition") {
      const parts = Object.values(r.part_cols ?? {}).filter(Boolean);
      const partsLabel = parts.length ? `[${parts.join(", ")}]` : "?";
      return `${tgt}.${partsLabel} ← decompose(${r.canonical_col ?? "?"})`;
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
  // Top-level rejection-sampling settings (global, not per-rule). Preserved
  // across saves and editable below; null until the config loads.
  const [rejection, setRejection] = useState<RejectionSamplingSettings | null>(null);
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
        setRejection(parsed.rejection_sampling ?? null);
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

  // Inspection-time warnings of kind "date_composition_candidate" become
  // one-click suggestions in the derived/all rules panels. They surface
  // canonical↔parts groupings that the detector found in the data but the
  // user has not registered yet. Hidden once a matching rule exists.
  const suggestions = useMemo(() => {
    if (mode === "derived") return [];
    type Suggestion = {
      table: string;
      canonical_col: string;
      part_cols: Partial<Record<DatePart, string>>;
      confidence?: number;
    };
    const seen = new Map<string, Suggestion>();
    for (const w of autodetect?.warnings ?? []) {
      if (w.kind !== "date_composition_candidate") continue;
      const d = (w.details ?? {}) as {
        canonical_col?: string;
        part_cols?: Record<string, string>;
        confidence?: number;
      };
      if (!d.canonical_col || !d.part_cols) continue;
      const key = `${w.table}::${d.canonical_col}`;
      if (seen.has(key)) continue;
      const parts: Partial<Record<DatePart, string>> = {};
      for (const [k, v] of Object.entries(d.part_cols)) {
        if ((DATE_PART_NAMES as readonly string[]).includes(k) && v) {
          parts[k as DatePart] = v;
        }
      }
      seen.set(key, {
        table: w.table,
        canonical_col: d.canonical_col,
        part_cols: parts,
        confidence: d.confidence,
      });
    }
    // Drop suggestions already covered by an existing rule (same canonical col).
    return [...seen.values()].filter(
      (s) =>
        !rules.some(
          (r) =>
            r.type === "date_composition" &&
            r.table_target === s.table &&
            r.canonical_col === s.canonical_col,
        ),
    );
  }, [autodetect, rules, mode]);

  const acceptSuggestion = (s: {
    table: string;
    canonical_col: string;
    part_cols: Partial<Record<DatePart, string>>;
  }) => {
    setRules((prev) => [
      ...prev,
      {
        type: "date_composition",
        table_target: s.table,
        canonical_col: s.canonical_col,
        part_cols: s.part_cols,
      },
    ]);
  };

  const buildYaml = (rs: Rule[]): string =>
    yaml.dump(
      {
        // Preserve the global rejection-sampling block. Without this, saving
        // rules from the form would silently wipe max_attempts/overgenerate.
        ...(rejection ? { rejection_sampling: rejection } : {}),
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
      setRejection(parsed.rejection_sampling ?? null);
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
      queryClient.invalidateQueries({ queryKey: ["rules-banner"] });
      queryClient.invalidateQueries({ queryKey: ["rules-compliance"] });
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
      queryClient.invalidateQueries({ queryKey: ["rules-banner"] });
      queryClient.invalidateQueries({ queryKey: ["rules-compliance"] });
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
        {configQuery.data && !yamlMode && suggestions.length > 0 && (
          <div className="mb-3 rounded-md border border-amber-300/60 bg-amber-50/60 p-3 dark:border-amber-700/40 dark:bg-amber-950/20">
            <p className="text-xs font-medium text-amber-900 dark:text-amber-200">
              Sugerencias detectadas durante la inspección
            </p>
            <p className="mt-0.5 text-[11px] text-amber-800/80 dark:text-amber-300/80">
              Estas columnas año/mes/día parecen derivar de una fecha canónica.
              Añade la regla para que se eliminen del entreno y se reconstruyan
              tras la generación; déjalo así si la divergencia es intencionada.
            </p>
            <ul className="mt-2 space-y-1.5">
              {suggestions.map((s, i) => {
                const parts = Object.values(s.part_cols).filter(Boolean);
                return (
                  <li
                    key={`${s.table}-${s.canonical_col}-${i}`}
                    className="flex flex-wrap items-center justify-between gap-2 rounded border border-amber-200/70 bg-background/60 p-2 dark:border-amber-800/40"
                  >
                    <div className="min-w-0 flex-1">
                      <span className="font-mono text-xs">
                        {s.table}.{s.canonical_col}
                      </span>
                      <span className="ml-2 text-[11px] text-muted-foreground">
                        ← {parts.join(", ")}
                        {typeof s.confidence === "number" && (
                          <span className="ml-1">
                            ({Math.round(s.confidence * 100)}% coincidencia)
                          </span>
                        )}
                      </span>
                    </div>
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      onClick={() => acceptSuggestion(s)}
                    >
                      <Plus className="mr-1 h-3.5 w-3.5" />
                      Añadir regla
                    </Button>
                  </li>
                );
              })}
            </ul>
          </div>
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
                  autodetect={autodetect}
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
                autodetect={autodetect}
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

  // Fetch the live rules so we can show a suggestion-count badge on the
  // collapsed header — same queryKey as RulesEditorBody so the panel and
  // body share a single network request.
  const headerConfigQuery = useQuery({
    queryKey: ["config", configId],
    queryFn: async () => {
      const { data } = await api.get<ConfigContent>(
        `/configs/${encodeURIComponent(configId)}`,
      );
      return data;
    },
  });
  const registeredRules: Rule[] = useMemo(() => {
    if (!headerConfigQuery.data) return [];
    try {
      const parsed = (yaml.load(headerConfigQuery.data.content) as RulesFile) ?? {
        rules: [],
      };
      return parsed.rules ?? [];
    } catch {
      return [];
    }
  }, [headerConfigQuery.data]);
  const suggestionCount =
    mode === "derived"
      ? 0
      : countDateCompositionSuggestions(autodetect, registeredRules);

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
      ? "Define columnas nuevas a partir de columnas existentes (edad a partir de fecha, umbral booleano, estratificación por intervalos)."
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
          <div className="flex flex-wrap items-center gap-2">
            <CardTitle className="text-base">{resolvedTitle}</CardTitle>
            {suggestionCount > 0 && (
              <Tooltip
                side="top"
                content={
                  suggestionCount === 1
                    ? "La inspección detectó 1 sugerencia de regla. Abre el panel para revisarla."
                    : `La inspección detectó ${suggestionCount} sugerencias de regla. Abre el panel para revisarlas.`
                }
              >
                <span className="inline-flex items-center gap-1 rounded-full border border-amber-500/70 bg-amber-50 px-2 py-0.5 text-[11px] font-medium text-amber-700 dark:bg-amber-950/30 dark:text-amber-400">
                  <AlertTriangle className="h-3 w-3" />
                  {suggestionCount}{" "}
                  {suggestionCount === 1 ? "sugerencia" : "sugerencias"}
                </span>
              </Tooltip>
            )}
          </div>
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
            {REJECTION_SAMPLING_RULE_TYPES.includes(rule.type) && (
              <Badge
                variant="outline"
                className={
                  "text-[10px] " +
                  (rule.rejection_sampling
                    ? "border-amber-500/70 text-amber-700 dark:text-amber-400"
                    : "")
                }
              >
                {rule.rejection_sampling ? "Muestreo por rechazo" : "Determinista"}
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
  autodetect,
  mode = "all",
  onCancel,
  onSubmit,
}: {
  initial?: Rule;
  tableNames: string[];
  columnsByTable: Record<string, string[]>;
  autodetect?: Autodetect | null;
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

  // Unique per-instance radio group name. A hardcoded name made every mounted
  // RuleForm share one document-wide radio group, so the browser unchecked the
  // controlled radios and both options rendered blank.
  const rejectionModeName = useId();

  const showInequality =
    draft.type === "date_inequality" || draft.type === "numeric_inequality";
  const showFK = draft.type === "foreign_keys_consistency_rule";
  const showDateComposition = draft.type === "date_composition";
  const isSemantic =
    draft.type === "semantic_ranking_consistency" ||
    draft.type === "semantic_proportional_consistency";
  const showDerived =
    DERIVED_RULE_TYPES.includes(draft.type) && !showDateComposition;

  // Collapse both semantic subtypes into a single top-level entry in the main
  // dropdown. semantic_ranking_consistency acts as the group representative.
  const dropdownTypes = allowedTypes.filter(
    (t) => t !== "semantic_proportional_consistency",
  );
  const dropdownValue = isSemantic ? "semantic_ranking_consistency" : draft.type;

  const dateCompositionParts = Object.entries(draft.part_cols ?? {}).filter(
    ([, v]) => !!v,
  );
  const dateCompositionValid =
    !!draft.table_target &&
    !!draft.canonical_col &&
    dateCompositionParts.length > 0 &&
    dateCompositionParts.every(([, v]) => v !== draft.canonical_col);

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
  const valid = showDateComposition
    ? dateCompositionValid
    : showDerived
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
        <NativeSelect
          value={dropdownValue}
          onValueChange={(v) =>
            setDraft({
              type: v as RuleType,
              constraint_operator: ">=",
            })
          }
          className="mt-1 h-8 rounded-lg"
        >
          {dropdownTypes.map((t) => (
            <option key={t} value={t}>
              {t === "semantic_ranking_consistency"
                ? "Consistencia semántica"
                : RULE_TYPE_LABELS[t]}
            </option>
          ))}
        </NativeSelect>
        {!isSemantic && (
          <p className="mt-1 text-[11px] text-muted-foreground">
            {RULE_TYPE_HELP[draft.type]}
          </p>
        )}
      </div>

      {isSemantic && (
        <div className="rounded-md border bg-background p-2 text-xs">
          <Label className="text-xs">Subtipo</Label>
          <div className="mt-1 flex flex-col gap-1">
            <label className="flex items-start gap-2">
              <input
                type="radio"
                name="semantic-subtype"
                className="mt-0.5"
                checked={draft.type === "semantic_proportional_consistency"}
                onChange={() => update({ type: "semantic_proportional_consistency" })}
              />
              <span className="flex flex-1 items-start gap-1.5">
                <span>
                  <span className="font-medium">Fijo</span>
                  <span className="ml-1 text-muted-foreground">
                    — fuerza las proporciones del dato real.
                  </span>
                </span>
                <Tooltip
                  side="right"
                  content="Las proporciones sintéticas quedan ancladas a las reales: el modelo reproduce la frecuencia con que aparece cada categoría en los datos originales."
                />
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input
                type="radio"
                name="semantic-subtype"
                className="mt-0.5"
                checked={draft.type === "semantic_ranking_consistency"}
                onChange={() => update({ type: "semantic_ranking_consistency" })}
              />
              <span className="flex flex-1 items-start gap-1.5">
                <span>
                  <span className="font-medium">Flexible</span>
                  <span className="ml-1 text-muted-foreground">
                    — el modelo ajusta las proporciones libremente.
                  </span>
                </span>
                <Tooltip
                  side="right"
                  content="Solo se garantiza que las combinaciones sean semánticamente válidas (p. ej. diagnóstico secundario coherente con el primario); las proporciones las aprende y simula el modelo a su criterio."
                />
              </span>
            </label>
          </div>
        </div>
      )}

      {showDateComposition ? (
        <DateCompositionFields
          draft={draft}
          update={update}
          tableNames={tableNames}
          columnsByTable={columnsByTable}
        />
      ) : showDerived ? (
        <DerivedRuleFields
          draft={draft}
          update={update}
          tableNames={tableNames}
          columnsByTable={columnsByTable}
          autodetect={autodetect}
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
              <NativeSelect
                aria-label="Operador"
                value={draft.constraint_operator ?? ">="}
                onValueChange={(v) =>
                  update({
                    constraint_operator: v as ">=" | "<=",
                  })
                }
                className="mt-1 h-8 w-16 rounded-lg text-lg font-semibold"
              >
                <option value=">=">≥</option>
                <option value="<=">≤</option>
              </NativeSelect>
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
            <>
              <div className="col-span-3">
                <Label className="text-xs">
                  Unidad de la duración
                  <Tooltip
                    side="top"
                    content="Granularidad del valor auxiliar que el modelo aprende. «Días» es lo habitual para estancias y episodios cortos. Usa «Meses» o «Años» si la diferencia suele ser larga — de lo contrario un episodio de 5 días redondea a 0 meses o años."
                  />
                </Label>
                <NativeSelect
                  value={draft.unit ?? "days"}
                  onValueChange={(v) =>
                    update({ unit: v as "years" | "months" | "days" })
                  }
                  className="mt-1 h-8 rounded-lg"
                >
                  <option value="days">Días</option>
                  <option value="months">Meses</option>
                  <option value="years">Años</option>
                </NativeSelect>
              </div>
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
            </>
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

      {REJECTION_SAMPLING_RULE_TYPES.includes(draft.type) && (
        <div className="rounded-md border bg-background p-2 text-xs">
          <Label className="text-xs">Modo de aplicación</Label>
          <div className="mt-1 flex flex-col gap-1">
            <label className="flex items-start gap-2">
              <input
                type="radio"
                name={rejectionModeName}
                className="mt-0.5"
                checked={!draft.rejection_sampling}
                onChange={() => update({ rejection_sampling: false })}
              />
              <span className="flex flex-1 items-start gap-1.5">
                <span>
                  <span className="font-medium">Determinista</span>
                  <span className="ml-1 text-muted-foreground">
                    — reconstrucción automática vía columnas auxiliares (PRE/POST).
                  </span>
                </span>
                <Tooltip
                  side="right"
                  content="El modelo aprende sobre una columna auxiliar continua; durante POST se reconstruye la columna original de forma determinista. Eficiente, pero si los datos reales no cumplen la regla las distribuciones se ajustan por construcción."
                />
              </span>
            </label>
            <label className="flex items-start gap-2">
              <input
                type="radio"
                name={rejectionModeName}
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

// Encoding-type sets used to filter "Columna objetivo" by rule type.
// date_to_age needs a date/datetime origin; numeric_threshold and
// numeric_bucket need a numeric origin.
const DATE_ENCODING_TYPES = new Set([
  "TABULAR_DATETIME",
  "TABULAR_DATETIME_RELATIVE",
  "LANGUAGE_DATETIME",
]);
const NUMERIC_ENCODING_TYPES = new Set([
  "TABULAR_NUMERIC_AUTO",
  "TABULAR_NUMERIC_DISCRETE",
  "TABULAR_NUMERIC_BINNED",
  "TABULAR_NUMERIC_DIGIT",
]);

function DerivedRuleFields({
  draft,
  update,
  tableNames,
  columnsByTable,
  autodetect,
}: {
  draft: Rule;
  update: (patch: Partial<Rule>) => void;
  tableNames: string[];
  columnsByTable: Record<string, string[]>;
  autodetect?: Autodetect | null;
}) {
  const allCols = draft.table_target
    ? (columnsByTable[draft.table_target] ?? [])
    : [];

  // Filter the column list by encoding type when autodetect is available.
  // Falls back to the full list if no encoding info exists for this table.
  const targetCols = (() => {
    const encTypes =
      autodetect?.encoding_types?.[draft.table_target ?? ""] ?? {};
    const hasEnc = Object.keys(encTypes).length > 0;
    if (!hasEnc) return allCols;
    const allowed =
      draft.type === "date_to_age"
        ? DATE_ENCODING_TYPES
        : draft.type === "numeric_threshold" || draft.type === "numeric_bucket"
          ? NUMERIC_ENCODING_TYPES
          : null;
    if (!allowed) return allCols;
    return allCols.filter((c) => encTypes[c] === undefined || allowed.has(encTypes[c]));
  })();

  const hasSchema = tableNames.length > 0;

  const [binsStr, setBinsStr] = useState(() => (draft.bins ?? []).join(", "));
  const [labelsStr, setLabelsStr] = useState(() => (draft.labels ?? []).join(", "));

  // Helper function to prevent unnecessary parent updates
  const areArraysEqual = (a: any[] | undefined, b: any[] | undefined) => {
    if (!a && !b) return true;
    if (!a || !b) return false;
    if (a.length !== b.length) return false;
    return a.every((val, idx) => val === b[idx]);
  };

  // 2. Sync local state if external draft changes (e.g., switching rules)
  useEffect(() => {
    setBinsStr((draft.bins ?? []).join(", "));
  }, [draft.bins]);

  useEffect(() => {
    setLabelsStr((draft.labels ?? []).join(", "));
  }, [draft.labels]);

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-xs">Tabla objetivo</Label>
          {hasSchema ? (
            <NativeSelect
              value={draft.table_target ?? ""}
              onValueChange={(v) =>
                update({
                  table_target: v,
                  origin_col: undefined,
                  reference_date_col: undefined,
                  reference_date_table: undefined,
                })
              }
              className="mt-1 h-8 rounded-lg"
            >
              <option value="">— elegir —</option>
              {tableNames.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </NativeSelect>
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
            <NativeSelect
              value={draft.origin_col ?? ""}
              onValueChange={(v) => update({ origin_col: v })}
              className="mt-1 h-8 rounded-lg"
            >
              <option value="">— elegir —</option>
              {targetCols.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </NativeSelect>
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
            <NativeSelect
              value={draft.unit ?? "years"}
              onValueChange={(v) =>
                update({ unit: v as "years" | "months" | "days" })
              }
              className="mt-1 h-8 rounded-lg"
            >
              <option value="years">Años</option>
              <option value="months">Meses</option>
              <option value="days">Días</option>
            </NativeSelect>
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
            <NativeSelect
              value={draft.operator ?? ">="}
              onValueChange={(v) =>
                update({
                  operator: v as ">=" | ">" | "<=" | "<",
                })
              }
              className="mt-1 h-8 rounded-lg"
            >
              <option value=">=">≥</option>
              <option value=">">&gt;</option>
              <option value="<=">≤</option>
              <option value="<">&lt;</option>
            </NativeSelect>
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
                placeholder="Verdadero"
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
                placeholder="Falso"
                className="mt-1"
              />
            </div>
          </div>
        </div>
      )}

      {draft.type === "numeric_bucket" && (
        <div className="space-y-2">
          <div>
            <Label className="text-xs">Bordes de intervalo (coma o espacio)</Label>
            <Input
              value={binsStr}
              onChange={(e) => {
                const val = e.target.value;
                setBinsStr(val);

                const parts = val
                  .split(/[,\s]+/)
                  .map((s) => s.trim())
                  .filter((s) => s.length > 0);
                const nums = parts
                  .map((s) => (s === "inf" || s === "Infinity" ? Infinity : Number(s)))
                  .filter((n) => !Number.isNaN(n));

                
                if (!areArraysEqual(nums, draft.bins)) {
                  update({ bins: nums });
                }
              }}
              placeholder="0, 18, 65, inf"
              className="mt-1 font-mono"
            />
            <p className="mt-1 text-[11px] text-muted-foreground">
              Se necesitan al menos 2 valores. Usa <code>inf</code> para
              límites abiertos.
            </p>
          </div>
          <div>
            <Label className="text-xs">Etiquetas (opcional)</Label>
            <Input
              value={labelsStr}
              onChange={(e) => {
                const val = e.target.value;
                setLabelsStr(val);
                const parts = val
                  .split(",")
                  .map((s) => s.trim())
                  .filter((s) => s.length > 0);
                if (!areArraysEqual(parts, draft.labels ?? [])) {
                  update({ labels: parts.length ? parts : undefined });
                }
              }}
              placeholder="menor, adulto, mayor"
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
              Incluir borde inferior
            </label>
            <label className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={draft.right ?? false}
                onChange={(e) => update({ right: e.target.checked })}
              />
              Cerrado por la derecha
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

// Form fields for date_composition: pick the canonical datetime column and
// map each part (year/month/day/...) to the split column it should
// reconstruct. At least one part must be set; the rest are optional.
function DateCompositionFields({
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
  const hasSchema = tableNames.length > 0;
  const targetCols = draft.table_target
    ? columnsByTable[draft.table_target] ?? []
    : [];
  const setPart = (part: DatePart, col: string) => {
    const next = { ...(draft.part_cols ?? {}) } as Partial<Record<DatePart, string>>;
    if (col) next[part] = col;
    else delete next[part];
    update({ part_cols: next });
  };
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label className="text-xs">Tabla</Label>
          {hasSchema ? (
            <NativeSelect
              value={draft.table_target ?? ""}
              onValueChange={(v) =>
                update({
                  table_target: v,
                  canonical_col: undefined,
                  part_cols: undefined,
                })
              }
              className="mt-1 h-8 rounded-lg"
            >
              <option value="">— elegir —</option>
              {tableNames.map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </NativeSelect>
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
            Fecha canónica
            <Tooltip
              side="top"
              content="Columna con la fecha (o fecha-hora) completa. Las columnas de partes (año/mes/día...) se eliminan del entreno y se reconstruyen tras la generación desde esta columna."
            />
          </Label>
          {hasSchema && targetCols.length > 0 ? (
            <NativeSelect
              value={draft.canonical_col ?? ""}
              onValueChange={(v) =>
                update({ canonical_col: v || undefined })
              }
              className="mt-1 h-8 rounded-lg"
            >
              <option value="">— elegir —</option>
              {targetCols.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </NativeSelect>
          ) : (
            <Input
              value={draft.canonical_col ?? ""}
              onChange={(e) =>
                update({ canonical_col: e.target.value || undefined })
              }
              placeholder="nombre de columna"
              className="mt-1"
            />
          )}
        </div>
      </div>

      <div>
        <Label className="text-xs">
          Columnas componente (al menos una)
          <Tooltip
            side="top"
            content="Para cada parte que aparezca como columna separada en tus datos, indica la columna correspondiente. Se eliminarán en preprocesado y se rederivarán deterministamente desde la fecha canónica al final."
          />
        </Label>
        <div className="mt-1 grid grid-cols-1 gap-2">
          {DATE_PART_NAMES.map((part) => {
            const value = draft.part_cols?.[part] ?? "";
            return (
              <div key={part}>
                <Label className="text-[11px] text-muted-foreground">
                  {DATE_PART_LABELS[part]}
                </Label>
                {hasSchema && targetCols.length > 0 ? (
                  <NativeSelect
                    value={value}
                    onValueChange={(v) => setPart(part, v)}
                    className="mt-1 h-8 rounded-lg"
                  >
                    <option value="">— ninguna —</option>
                    {targetCols
                      .filter((c) => c !== draft.canonical_col)
                      .map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                  </NativeSelect>
                ) : (
                  <Input
                    value={value}
                    onChange={(e) => setPart(part, e.target.value)}
                    placeholder="nombre de columna"
                    className="mt-1"
                  />
                )}
              </div>
            );
          })}
        </div>
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
              <NativeSelect
                value={refTable}
                onValueChange={(t) => {
                  update({
                    reference_date_table:
                      t && t !== draft.table_target ? t : undefined,
                    reference_date_col: undefined,
                  });
                }}
                className="mt-1 h-8 rounded-lg"
              >
                {tableNames.map((t) => (
                  <option key={t} value={t}>
                    {t}
                    {t === draft.table_target ? " (misma tabla)" : ""}
                  </option>
                ))}
              </NativeSelect>
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
              <NativeSelect
                value={draft.reference_date_col ?? ""}
                onValueChange={(v) =>
                  update({ reference_date_col: v || undefined })
                }
                className="mt-1 h-8 rounded-lg"
              >
                <option value="">— elegir —</option>
                {refTableCols.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </NativeSelect>
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
          <NativeSelect
            value={table ?? ""}
            onValueChange={onChangeTable}
            className="mt-1 h-8 rounded-lg"
          >
            <option value="">— elegir —</option>
            {tableNames.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </NativeSelect>
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
            <NativeSelect
              value={column ?? ""}
              onValueChange={onChangeColumn}
              className="mt-1 h-8 rounded-lg"
            >
              <option value="">— elegir —</option>
              {cols.map((c) => (
                <option key={c} value={c}>
                  {c}
                </option>
              ))}
            </NativeSelect>
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
