// Read-only summary of the current rules.yaml. Shown on steps that consume a
// preprocessed dataset (training / generation / audit) so the user can see
// which rules apply but cannot modify them here — edits live in Inspección,
// since changing rules requires re-preprocessing the data.

"use client";

import { useQuery } from "@tanstack/react-query";
import yaml from "js-yaml";
import axios from "axios";
import { Info, Lock, LockOpen } from "lucide-react";
import { api, type Autodetect, type ComplianceReport, type ConfigContent } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { getBrc, getBrcRulesSnapshot, type BRCSummary } from "@/lib/brc";

type Props = {
  inspectionId?: string | null;
  brcId?: string | null;
  title?: string;
  forceLiveRules?: boolean;
};

type Rule = {
  type: string;
  table_origin?: string;
  origin_col?: string;
  table_target?: string;
  target_col?: string;
  constraint?: unknown;
  constraint_operator?: string;
  source_col?: string;
  aux_col?: string;
  reference_date?: string;
  reference_date_col?: string;
  threshold?: number | null;
  operator?: string;
  bins?: number[];
  rejection_sampling?: boolean;
  enforce_non_negative?: boolean;
  unit?: string;
  canonical_col?: string;
  part_cols?: Record<string, string>;
};

type RulesFile = { rules?: Rule[] };

const TYPE_LABELS: Record<string, string> = {
  date_inequality: "Relación entre fechas",
  numeric_inequality: "Relación entre números",
  semantic_ranking_consistency: "Consistencia semántica (flexible)",
  semantic_proportional_consistency: "Consistencia semántica (fijo)",
  foreign_keys_consistency_rule: "Consistencia de claves foráneas",
  date_to_age: "Derivar edad o lapso desde fecha",
  numeric_threshold: "Columna derivada: umbral numérico",
  numeric_bucket: "Columna estratificada: intervalos numéricos",
  date_composition: "Componer fecha desde columnas año/mes/día",
  // Synthetic pseudo-type used to render post-BRC column drops alongside the
  // real rules — picked up by the same blue "derived/deletion" treatment.
  column_drop: "Eliminar columna",
};

const DERIVED_TYPES = new Set([
  "date_to_age",
  "numeric_threshold",
  "numeric_bucket",
  "column_drop",
]);
const LOGICAL_TYPES = new Set([
  "date_inequality",
  "numeric_inequality",
  "semantic_ranking_consistency",
  "semantic_proportional_consistency",
  "foreign_keys_consistency_rule",
  "date_composition",
]);
// Subset of logical types that carry the forced/rejection-sampling toggle.
// date_composition is always deterministic, so we don't render that badge for it.
const REJECTION_SAMPLING_TYPES = new Set([
  "date_inequality",
  "numeric_inequality",
  "semantic_ranking_consistency",
  "semantic_proportional_consistency",
  "foreign_keys_consistency_rule",
]);

function summarize(r: Rule): string {
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
  if (r.type === "date_to_age") {
    const tgt = r.table_target ?? "?";
    const src = r.origin_col ?? "?";
    const dst = r.aux_col ?? "?";
    const ref = r.reference_date_col ?? r.reference_date ?? "?";
    return `${tgt}.${dst} = lapso(${src} − ${ref})`;
  }
  if (r.type === "numeric_threshold") {
    const tgt = r.table_target ?? "?";
    const src = r.origin_col ?? "?";
    const dst = r.aux_col ?? "?";
    return `${tgt}.${dst} = (${src} ${r.operator ?? ">="} ${r.threshold ?? "?"})`;
  }
  if (r.type === "numeric_bucket") {
    const tgt = r.table_target ?? "?";
    const src = r.origin_col ?? "?";
    const dst = r.aux_col ?? "?";
    const bins = r.bins?.length ? `[${r.bins.join(", ")}]` : "?";
    return `${tgt}.${dst} = bucket(${src}, ${bins})`;
  }
  if (r.type === "date_composition") {
    const parts = Object.values(r.part_cols ?? {}).filter(Boolean);
    const partsLabel = parts.length ? `[${parts.join(", ")}]` : "?";
    return `${r.table_target ?? "?"}.${partsLabel} ← decompose(${r.canonical_col ?? "?"})`;
  }
  if (r.type === "column_drop") {
    return `${r.table_target ?? "?"}.${r.target_col ?? "?"} → ∅`;
  }
  return `${left} → ${right}`;
}

export function RulesBanner({
  inspectionId,
  brcId,
  title,
  forceLiveRules = false,
}: Props = {}) {
  type Source = "snapshot" | "live" | "brc";
  const query = useQuery({
    queryKey: [
      "rules-banner",
      brcId ?? null,
      forceLiveRules ? null : inspectionId ?? null,
    ],
    queryFn: async (): Promise<{ yaml: string; source: Source }> => {
      if (brcId) {
        const yamlText = await getBrcRulesSnapshot(brcId);
        return { yaml: yamlText, source: "brc" };
      }
      if (inspectionId && !forceLiveRules) {
        try {
          const { data } = await api.get<string>(
            `/inspections/${encodeURIComponent(inspectionId)}/rules`,
            { transformResponse: (r) => r as string },
          );
          return { yaml: data, source: "snapshot" };
        } catch (err) {
          // Fall through to live rules.yaml on 404 (snapshot missing for
          // older runs); rethrow other errors.
          if (
            !axios.isAxiosError(err) ||
            err.response?.status !== 404
          ) {
            throw err;
          }
        }
      }
      const { data } = await api.get<ConfigContent>("/configs/rules");
      return { yaml: data.content, source: "live" };
    },
  });

  const rules: Rule[] = (() => {
    if (!query.data) return [];
    try {
      const parsed = (yaml.load(query.data.yaml) as RulesFile) ?? {};
      return parsed.rules ?? [];
    } catch {
      return [];
    }
  })();
  const source = query.data?.source;

  const brcSummaryQuery = useQuery({
    queryKey: ["brc", brcId ?? null],
    enabled: !!brcId,
    queryFn: async () => getBrc(brcId!),
    // Keep polling while the run is in progress. The summary's
    // ``excluded_columns`` / ``new_columns`` are only written when the run
    // finalizes, so a one-shot fetch made right after launch (when the page
    // optimistically selects the new, still-running run) would cache an empty
    // summary and never refresh — making the dropped columns disappear from
    // "Resumen de cambios aplicados" until a manual reload.
    refetchInterval: (q) => {
      const data = q.state.data as BRCSummary | undefined;
      return data && data.status !== "in_progress" ? false : 2000;
    },
  });
  const inspectionAutodetectQuery = useQuery({
    queryKey: ["autodetect", inspectionId ?? null],
    enabled: !brcId && !!inspectionId,
    queryFn: async () => {
      const { data } = await api.get<Autodetect>(
        `/inspections/${encodeURIComponent(inspectionId!)}/autodetect`,
      );
      return data;
    },
  });
  const complianceQuery = useQuery({
    queryKey: ["rules-compliance", inspectionId ?? null, query.data?.yaml ?? null],
    enabled: source === "live" && !!inspectionId,
    queryFn: async () => {
      const { data } = await api.get<ComplianceReport>(
        `/inspections/${encodeURIComponent(inspectionId!)}/rules/compliance`,
        { params: { sample_size: 10000 } },
      );
      return data;
    },
    retry: false,
  });
  // Map rule_index -> compliance row for O(1) lookup per banner entry.
  const complianceByIndex = new Map(
    (complianceQuery.data?.rows ?? []).map((r) => [r.rule_index, r]),
  );

  // In BRC mode the summary already carries the union of all dropped columns.
  // In live (Reglas de negocio) mode, show what *this* run will drop: the
  // Carga de Datos exclusions plus the Reglas-de-negocio exclusions.
  const exclusionsData: Record<string, string[]> = brcId
    ? brcSummaryQuery.data?.excluded_columns ?? {}
    : (() => {
      const merged: Record<string, string[]> = {};
      for (const source of [
        inspectionAutodetectQuery.data?.excluded_columns ?? {},
        inspectionAutodetectQuery.data?.rules_excluded_columns ?? {},
      ]) {
        for (const [table, cols] of Object.entries(source)) {
          merged[table] = [...new Set([...(merged[table] ?? []), ...cols])];
        }
      }
      return merged;
    })();
  const dropRules: Rule[] = Object.entries(exclusionsData).flatMap(([table, cols]) =>
    cols.map(
      (col): Rule => ({
        type: "column_drop",
        table_target: table,
        target_col: col,
      }),
    ),
  );
  // Each entry keeps its original compliance index (only the parsed `rules`
  // carry a compliance row; drop rules don't). We then reorder so derived/
  // column rules come first, matching the order they're configured on the page
  // (columnas derivadas → reglas lógicas), without breaking the compliance
  // lookup, which is keyed by the original index.
  type Entry = { rule: Rule; complianceIndex: number | null };
  const ruleEntries: Entry[] = rules.map((rule, i) => ({ rule, complianceIndex: i }));
  const dropEntries: Entry[] = dropRules.map((rule) => ({ rule, complianceIndex: null }));
  const allEntries: Entry[] = [...ruleEntries, ...dropEntries];
  // Stable sort: derived/column types first, logical types after.
  const orderedEntries = allEntries
    .map((e, idx) => ({ e, idx }))
    .sort((a, b) => {
      const da = DERIVED_TYPES.has(a.e.rule.type) ? 0 : 1;
      const db = DERIVED_TYPES.has(b.e.rule.type) ? 0 : 1;
      return da !== db ? da - db : a.idx - b.idx;
    })
    .map(({ e }) => e);
  const allRules: Rule[] = orderedEntries.map((e) => e.rule);

  return (
    <div className="rounded-md border bg-muted/30 p-3 text-sm">
      <div className="flex items-start gap-2">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {title ?? "Reglas de preprocesamiento"}
            {allRules.length > 0 && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                ({allRules.length})
              </span>
            )}
            {forceLiveRules && (
              <Badge
                variant="outline"
                className="ml-2 align-middle text-[10px] border-emerald-500/60 text-emerald-700 dark:text-emerald-400"
              >
                en vivo · próxima ejecución
              </Badge>
            )}
            {source === "brc" && (
              <Badge
                variant="outline"
                className="ml-2 align-middle text-[10px] border-muted-foreground/40 text-muted-foreground"
              >
                snapshot BRC
              </Badge>
            )}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {source === "brc"
              ? "Reglas aplicadas (PRE) en esta ejecución BRC. El entrenamiento reutilizará este dataset preprocesado."
              : source === "snapshot"
                ? "Reglas aplicadas al preprocesar este dataset. Para modificarlas, vuelve a Reglas de negocio y reprocesa."
                : "Reglas actualmente configuradas."}
          </p>
          {source === "live" && !inspectionId && allRules.length > 0 && (
            <p className="mt-1 text-[10px] text-muted-foreground">
              Selecciona una carga de datos para ver el cumplimiento en datos reales.
            </p>
          )}
          {query.isLoading && (
            <p className="mt-2 text-xs text-muted-foreground">Cargando…</p>
          )}
          {!query.isLoading && allRules.length === 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              No hay reglas definidas.
            </p>
          )}
          {allRules.length > 0 && (
            <>
              <ul className="mt-2 space-y-1.5">
                {orderedEntries.map(({ rule: r, complianceIndex }, i) => {
                  const compliance =
                    complianceIndex != null
                      ? complianceByIndex.get(complianceIndex)
                      : undefined;
                  return (
                    <li key={i} className="flex flex-wrap items-center gap-2">
                      <Badge
                        variant="secondary"
                        className={
                          "text-[10px] " +
                          (DERIVED_TYPES.has(r.type)
                            ? "border-blue-400/50 bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300"
                            : "")
                        }
                      >
                        {TYPE_LABELS[r.type] ?? r.type}
                      </Badge>
                      {REJECTION_SAMPLING_TYPES.has(r.type) && (
                        <Badge
                          variant="outline"
                          className={
                            "text-[10px] " +
                            (r.rejection_sampling
                              ? "border-amber-500/70 text-amber-700 dark:text-amber-400"
                              : "border-muted-foreground/30 text-muted-foreground")
                          }
                        >
                          {r.rejection_sampling ? "Muestreo por rechazo" : "Determinista"}
                        </Badge>
                      )}
                      {(r.type === "date_inequality" || r.type === "date_to_age") && !r.rejection_sampling && (
                        r.enforce_non_negative !== false ? (
                          <Badge
                            variant="outline"
                            className="inline-flex items-center gap-1 text-[10px] border-sky-500/60 text-sky-700 dark:text-sky-400"
                          >
                            <Lock className="h-2.5 w-2.5" />
                            {r.type === "date_to_age" ? "Lapso ≥ 0" : "Duración ≥ 0"}
                          </Badge>
                        ) : (
                          <Badge
                            variant="outline"
                            className="inline-flex items-center gap-1 text-[10px] border-muted-foreground/30 text-muted-foreground"
                          >
                            <LockOpen className="h-2.5 w-2.5" />
                            {r.type === "date_to_age" ? "Lapso libre" : "Duración libre"}
                          </Badge>
                        )
                      )}
                      {r.type === "date_inequality" && (
                        <Badge
                          variant="outline"
                          className="text-[10px] border-muted-foreground/30 text-muted-foreground"
                        >
                          {r.unit === "months" ? "Meses" : r.unit === "years" ? "Años" : "Días"}
                        </Badge>
                      )}
                      <span className="font-mono text-xs text-muted-foreground">{summarize(r)}</span>
                      {compliance && !compliance.skipped && compliance.pct_compliant != null && (
                        <span
                          className="ml-auto inline-flex items-center gap-2 tabular-nums text-[10px]"
                          title={
                            `Sobre ${compliance.checked.toLocaleString()} filas totales:\n` +
                            `· ${compliance.pct_compliant}% cumplen (no nulas y dentro de la regla)\n` +
                            (compliance.pct_null != null
                              ? `· ${compliance.pct_null}% nulas (${(compliance.null_rows ?? 0).toLocaleString()} sin valor)\n`
                              : "") +
                            (compliance.pct_nonnull_noncompliant != null
                              ? `· ${compliance.pct_nonnull_noncompliant}% no cumplen (no nulas) ` +
                              `(${(compliance.nonnull_failing ?? 0).toLocaleString()} filas)`
                              : "")
                          }
                        >
                          <span
                            className={
                              compliance.pct_compliant === 100
                                ? "text-emerald-600 dark:text-emerald-400"
                                : compliance.pct_compliant >= 90
                                  ? "text-amber-600 dark:text-amber-400"
                                  : "text-red-600 dark:text-red-400"
                            }
                          >
                            {compliance.pct_compliant}% cumplen
                          </span>
                          {compliance.pct_null != null && compliance.pct_null > 0 && (
                            <span className="text-muted-foreground">{compliance.pct_null}% nulas</span>
                          )}
                          {compliance.pct_nonnull_noncompliant != null &&
                            compliance.pct_nonnull_noncompliant > 0 && (
                              <span className="text-muted-foreground">
                                {compliance.pct_nonnull_noncompliant}% no cumplen
                              </span>
                            )}
                        </span>
                      )}
                      {complianceQuery.isLoading && LOGICAL_TYPES.has(r.type) && complianceIndex != null && (
                        <span className="ml-auto text-[10px] text-muted-foreground animate-pulse">evaluando…</span>
                      )}
                    </li>
                  );
                })}
              </ul>
              <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
                <span className="font-medium">Leyenda:</span>
                <span className="inline-flex items-center gap-1">
                  <Badge
                    variant="secondary"
                    className="text-[10px] border-blue-400/50 bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300"
                  >
                    tipo
                  </Badge>
                  columnas derivadas (creación/eliminación)
                </span>
                <span className="inline-flex items-center gap-1">
                  <Badge variant="secondary" className="text-[10px]">
                    tipo
                  </Badge>
                  reglas lógicas
                </span>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
