"use client";

import { useQuery } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  AlertTriangle,
  CheckCircle2,
  Pin,
} from "lucide-react";
import { useState, useMemo } from "react";
import { api, type RejectionSamplingReport } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Tooltip } from "@/components/ui/tooltip";
import { AdvancedBadge } from "@/components/ui/advanced-section";
import { cn } from "@/lib/utils";
import yaml from "js-yaml";
import { getBrcRulesSnapshot } from "@/lib/brc";

type Props = { simulationId: string };

const CLASS_TO_YAML_TYPE: Record<string, string> = {
  DateInequalityRule: "date_inequality",
  NumericInequalityRule: "numeric_inequality",
  SemanticRankingConsistencyRule: "semantic_ranking_consistency",
  SemanticProportionalConsistencyRule: "semantic_proportional_consistency",
  ForeignKeysConsistencyRule: "foreign_keys_consistency_rule",
};

type BrcRule = {
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
};

function summarizeRule(r: BrcRule): string {
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

// Same human labels the sanity card / rules banner use, so a rejection rule
// reads identically here and there.
const RULE_TYPE_LABELS: Record<string, string> = {
  DateInequalityRule: "Relación entre fechas",
  NumericInequalityRule: "Relación entre números",
  SemanticRankingConsistencyRule: "Consistencia semántica (flexible)",
  SemanticProportionalConsistencyRule: "Consistencia semántica (fijo)",
  ForeignKeysConsistencyRule: "Consistencia de claves foráneas",
};

function pct(part: number, whole: number): string {
  if (whole <= 0) return "—";
  return `${((part / whole) * 100).toFixed(1)}%`;
}

export function RejectionSamplingCard({ simulationId }: Props) {
  const [open, setOpen] = useState(false);
  const [attemptsOpen, setAttemptsOpen] = useState(false);
  const query = useQuery<RejectionSamplingReport>({
    queryKey: ["simulations", simulationId, "rejection-report"],
    queryFn: async () => {
      const { data } = await api.get<RejectionSamplingReport>(
        `/simulations/${encodeURIComponent(simulationId)}/rejection-report`,
      );
      return data;
    },
    retry: false,
  });

  const simulationQuery = useQuery({
    queryKey: ["simulations", simulationId],
    queryFn: async () => {
      const { data } = await api.get<{ model_id: string }>(`/simulations/${encodeURIComponent(simulationId)}`);
      return data;
    },
    retry: false,
  });

  const modelId = simulationQuery.data?.model_id;
  const modelQuery = useQuery({
    queryKey: ["models", modelId],
    enabled: !!modelId,
    queryFn: async () => {
      const { data } = await api.get<{ brc_id: string }>(`/models/${encodeURIComponent(modelId!)}`);
      return data;
    },
    retry: false,
  });

  const brcId = modelQuery.data?.brc_id;
  const brcRulesQuery = useQuery({
    queryKey: ["brc-rules-snapshot", brcId],
    enabled: !!brcId,
    queryFn: async () => {
      const yamlText = await getBrcRulesSnapshot(brcId!);
      try {
        const parsed = (yaml.load(yamlText) as { rules?: any[] }) ?? {};
        return parsed.rules ?? [];
      } catch {
        return [];
      }
    },
  });

  // No report → rejection sampling did not run for this simulation. Render
  // nothing so the section only appears when it has something to say.
  if (query.isError || (query.isSuccess && !query.data)) return null;
  if (!query.data) return null;

  const report = query.data;
  const tables = Object.entries(report.tables);
  const partial = report.partial_results;
  // Row objetivo per table. ``all_targets`` carries the proportional goal for
  // *every* table (real-data ratios at the requested scale). No objetivo is
  // guaranteed — the run drives the fixed table towards its goal and the rest
  // cascade, but a restrictive rule can leave even the fixed one short (→
  // parcial). Fall back to the older subject/child maps for reports written
  // before ``all_targets`` existed.
  const targetFor = (name: string): number | undefined =>
    report.all_targets?.[name] ??
    report.subject_targets?.[name] ??
    report.child_targets?.[name];
  // Table the run targets (master in modo estándar, the fijada child in objetivo
  // fijo) — marked with a pin. Its size is the one being driven, not a guarantee.
  const fixedTables = new Set(
    report.fixed_tables ?? (report.target_table ? [report.target_table] : []),
  );
  const hasChildTargets =
    report.child_targets != null && Object.keys(report.child_targets).length > 0;
  // Fixed-target mode: the user fixed one (child) table's compliant row count
  // and the mother table floated — the inverse of the default best-subset mode.
  const isFixedTarget = report.selection === "fixed_target";

  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setOpen((o) => !o)}
            aria-expanded={open}
            className="flex flex-1 items-center gap-2 text-left"
          >
            {open ? (
              <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" />
            ) : (
              <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" />
            )}
            <CardTitle className="text-base">Muestreo por rechazo</CardTitle>
            <Badge
              variant="outline"
              className="border-muted-foreground/40 text-muted-foreground"
            >
              {report.attempts}/{report.max_attempts} intentos
            </Badge>
            {partial ? (
              <Badge
                variant="outline"
                className="border-amber-500/60 text-amber-700 dark:text-amber-400"
              >
                <AlertTriangle className="mr-1 h-3 w-3" />
                resultado parcial
              </Badge>
            ) : (
              <Badge
                variant="outline"
                className="border-emerald-500/60 text-emerald-700 dark:text-emerald-400"
              >
                <CheckCircle2 className="mr-1 h-3 w-3" />
                completo
              </Badge>
            )}
          </button>
          <AdvancedBadge tooltip="Métricas avanzadas del muestreo por rechazo: filas generadas, aceptadas, rechazadas y reintentos." />
        </div>
        {open && (
          <CardDescription>
            {isFixedTarget
              ? `Se fijó el número de filas de ${report.target_table ?? "la tabla objetivo"}: la tabla maestra se sobresimuló de forma adaptativa (hasta ${report.max_attempts} intentos) hasta alcanzar el objetivo${report.rules.length > 0 ? ", contando solo filas que cumplen las reglas de rechazo" : ""}; el resto de tablas quedó con el tamaño resultante.`
              : `Las reglas marcadas como «muestreo por rechazo» no reescriben los datos: se generan filas de más y se descartan las que incumplen la regla, repitiendo hasta ${report.max_attempts} veces.`}
          </CardDescription>
        )}
      </CardHeader>

      {/* Collapsed: surface the partial-result warning so it's visible without
          expanding. */}
      {!open && partial && (
        <CardContent className="pt-0">
          <p className="text-[11px] text-amber-700 dark:text-amber-400">
            {isFixedTarget
              ? `Se alcanzó el máximo de intentos sin llegar a las filas objetivo de ${report.target_table ?? "la tabla fijada"}.`
              : hasChildTargets
                ? "Se alcanzó el máximo de intentos sin llegar al objetivo de filas que cumplen en alguna tabla hija."
                : "Se alcanzó el máximo de intentos antes de completar el tamaño solicitado."}
          </p>
        </CardContent>
      )}

      {open && (
        <CardContent className="space-y-3">
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-muted-foreground">
            <span>
              Intentos usados:{" "}
              <span className="font-medium text-foreground">
                {report.attempts}
              </span>{" "}
              / {report.max_attempts}
            </span>
            <span className="inline-flex items-center gap-1">
              Sobre-generación:{" "}
              <span className="font-medium text-foreground">
                ×{report.overgenerate_factor}
              </span>
              <Tooltip content="El factor de sobre-generación (ej: ×2.0) se aplica en cada intento para ampliar la cohorte generada y cumplir con las proporciones objetivo de las tablas hijas." />
            </span>
            {report.sample_size != null && (
              <span>
                Tamaño solicitado:{" "}
                <span className="font-medium text-foreground">
                  {report.sample_size.toLocaleString()}
                </span>
              </span>
            )}
            {isFixedTarget && report.target_table && report.target_rows != null && (
              <span>
                Objetivo fijado:{" "}
                <span className="font-medium text-foreground">
                  {report.target_table} · {report.target_rows.toLocaleString()} filas
                </span>
              </span>
            )}
          </div>

          {report.rules.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                Reglas
              </span>
              {report.rules.map((ruleName, i) => {
                const yamlType = CLASS_TO_YAML_TYPE[ruleName];
                const matchingRules = (brcRulesQuery.data ?? []).filter(
                  (r) => r.type === yamlType && r.rejection_sampling
                );
                if (matchingRules.length > 0) {
                  return matchingRules.map((mr, idx) => (
                    <Badge key={`${ruleName}-${idx}`} variant="secondary" className="text-[10px] flex items-center gap-1.5">
                      <span>{RULE_TYPE_LABELS[ruleName] ?? ruleName}</span>
                      <span className="font-mono text-[9px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded border border-muted-foreground/10">
                        {summarizeRule(mr)}
                      </span>
                    </Badge>
                  ));
                }
                return (
                  <Badge key={i} variant="secondary" className="text-[10px]">
                    {RULE_TYPE_LABELS[ruleName] ?? ruleName}
                  </Badge>
                );
              })}
            </div>
          )}

          {tables.length > 0 && (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="border-b text-left text-muted-foreground">
                      <th className="py-1 pr-3 font-medium">Tabla</th>
                      <th className="py-1 pr-3 text-right font-medium">
                        Generadas
                      </th>
                      <th className="py-1 pr-3 text-right font-medium">
                        <span className="inline-flex items-center gap-1">
                          Objetivo
                          <Tooltip content="Filas objetivo de cada tabla, a escala de los datos reales. La tabla fijada (📌) es la que el muestreo intenta alcanzar; las demás cascadean a partir de ella. Ningún objetivo está garantizado: si la regla es muy restrictiva, ni la fijada se alcanza y el resultado sale «parcial» — entonces conviene resimular subiendo los intentos o el factor de sobre-generación." />
                        </span>
                      </th>
                      <th className="py-1 pr-3 text-right font-medium">
                        <span className="inline-flex items-center gap-1">
                          Rechazadas
                          <Tooltip content="Filas descartadas por incumplir la regla. Es la señal de cumplimiento: no incluye las sobrantes." />
                        </span>
                      </th>
                      <th className="py-1 pr-3 text-right font-medium">
                        <span className="inline-flex items-center gap-1">
                          Sobrantes
                          <Tooltip content="Filas que cumplían la regla pero se descartaron por exceder el tamaño solicitado en la tabla fijada (sobre-generación)." />
                        </span>
                      </th>
                      <th className="py-1 text-right font-medium">Aceptadas</th>
                    </tr>
                  </thead>
                  <tbody>
                    {tables.map(([name, t]) => (
                      <tr key={name} className="border-b last:border-0">
                        <td className="py-1 pr-3 font-mono">
                          <span className="inline-flex items-center gap-1">
                            {name}
                            {fixedTables.has(name) && (
                              <Tooltip content="Tabla con número de filas fijado.">
                                <Pin className="h-4 w-4 shrink-0 fill-red-500 text-red-600 dark:fill-red-500 dark:text-red-400" />
                              </Tooltip>
                            )}
                          </span>
                        </td>
                        <td className="py-1 pr-3 text-right tabular-nums">
                          {t.generated.toLocaleString()}
                        </td>
                        <td
                          className={
                            "py-1 pr-3 text-right tabular-nums " +
                            (targetFor(name) != null && t.accepted < targetFor(name)!
                              ? "text-amber-700 dark:text-amber-400"
                              : "text-muted-foreground")
                          }
                        >
                          {targetFor(name) != null ? targetFor(name)!.toLocaleString() : "—"}
                        </td>
                        <td className="py-1 pr-3 text-right tabular-nums text-amber-700 dark:text-amber-400">
                          {t.rejected.toLocaleString()} ({pct(t.rejected, t.rejected + t.accepted)})
                        </td>
                        <td className="py-1 pr-3 text-right tabular-nums text-muted-foreground">
                          {(t.trimmed ?? 0).toLocaleString()}
                        </td>
                        <td
                          className="py-1 text-right tabular-nums text-emerald-700 dark:text-emerald-400"
                          title={
                            targetFor(name) != null
                              ? `${t.accepted.toLocaleString()} de ${targetFor(name)!.toLocaleString()} objetivo`
                              : undefined
                          }
                        >
                          {t.accepted.toLocaleString()}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {report.attempt_history && report.attempt_history.length > 0 && (
            <div className="mt-4 space-y-2 border-t pt-3">
              <button
                type="button"
                onClick={() => setAttemptsOpen((v) => !v)}
                aria-expanded={attemptsOpen}
                className="flex w-full items-center gap-1 text-left text-xs font-semibold text-foreground"
              >
                {attemptsOpen ? (
                  <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                )}
                Detalle por intento
              </button>
              {attemptsOpen && (
                <>
                  <p className="text-[10px] text-muted-foreground">
                    Métricas detalladas de generación, aceptación y descarte registradas en cada reintento.
                  </p>
                  <div className="space-y-2">
                    {report.attempt_history.map((att) => (
                      <div
                        key={att.attempt}
                        className={cn(
                          "rounded-md border p-2 text-[10px]",
                          att.is_best ? "border-emerald-500/30 bg-emerald-500/5" : "bg-muted/20"
                        )}
                      >
                        <div className="flex items-center justify-between mb-1.5 font-medium">
                          <span>
                            Intento {att.attempt}{" "}
                            <span className="text-muted-foreground font-normal">
                              (Multiplicador: ×{att.multiplier.toFixed(1)})
                            </span>
                          </span>
                        </div>
                        <table className="w-full text-left text-muted-foreground">
                          <thead>
                            <tr className="border-b text-[9px]">
                              <th className="py-0.5 pr-2">Tabla</th>
                              <th className="py-0.5 pr-2 text-right">Generadas</th>
                              <th className="py-0.5 pr-2 text-right">Rechazadas</th>
                              <th className="py-0.5 text-right">Aceptadas</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(att.tables).map(([tableName, stats]) => (
                              <tr key={tableName} className="border-b border-muted/20 last:border-0">
                                <td className="py-0.5 pr-2 font-mono text-[9px] text-foreground">
                                  <span className="inline-flex items-center gap-1">
                                    {tableName}
                                    {fixedTables.has(tableName) && (
                                      <Tooltip content="Tabla con número de filas fijado.">
                                        <Pin className="h-4 w-4 shrink-0 fill-red-500 text-red-600 dark:fill-red-500 dark:text-red-400" />
                                      </Tooltip>
                                    )}
                                  </span>
                                </td>
                                <td className="py-0.5 pr-2 text-right tabular-nums">{stats.generated.toLocaleString()}</td>
                                <td className="py-0.5 pr-2 text-right tabular-nums text-amber-700 dark:text-amber-400">{stats.rejected.toLocaleString()}</td>
                                <td className="py-0.5 text-right tabular-nums text-emerald-700 dark:text-emerald-400">{stats.accepted.toLocaleString()}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          )}

          {partial && (
            <div className="flex items-start gap-1.5 text-[11px] text-amber-700 dark:text-amber-400">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span>
                {isFixedTarget
                  ? `Se agotaron los intentos sin alcanzar las filas objetivo de ${report.target_table ?? "la tabla fijada"}. Sube «intentos», o relaja la regla, para que la sobresimulación de la maestra pueda cerrar la brecha.`
                  : hasChildTargets
                    ? "Se agotaron los intentos sin alcanzar el objetivo de filas que cumplen en alguna tabla hija (columna «Objetivo»). La tabla maestra sí mantiene su tamaño exacto. Sube «intentos» o el factor de sobre-generación, o relaja la regla, para acercarte al objetivo."
                    : "Se alcanzó el máximo de intentos antes de completar el tamaño solicitado para alguna tabla. Sube «intentos» o el factor de sobre-generación, o relaja la regla."}
              </span>
              <Tooltip content="El muestreo por rechazo descarta filas que incumplen la regla y vuelve a generar, manteniendo la tabla maestra en su tamaño exacto y quedándose con las filas maestras que aportan más filas hijas que cumplen. Si la regla es muy restrictiva, el objetivo proporcional de las hijas puede no alcanzarse dentro del máximo de intentos." side="left" />
            </div>
          )}
        </CardContent>
      )}
    </Card>
  );
}
