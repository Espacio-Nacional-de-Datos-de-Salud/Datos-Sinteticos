"use client";

import { useQuery } from "@tanstack/react-query";
import {
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Clock,
  ChevronDown,
  ChevronRight,
} from "lucide-react";
import { useState } from "react";
import { api, type SanityReport, type SanityReportRow } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { AdvancedBadge } from "@/components/ui/advanced-section";
import { Tooltip } from "@/components/ui/tooltip";

type Props = { simulationId: string };

// Matches TYPE_LABELS in rules-banner.tsx exactly.
const RULE_TYPE_LABELS: Record<string, string> = {
  DateInequalityRule: "Relación entre fechas",
  NumericInequalityRule: "Relación entre números",
  SemanticRankingConsistencyRule: "Consistencia semántica (flexible)",
  SemanticProportionalConsistencyRule: "Consistencia semántica (fijo)",
  ForeignKeysConsistencyRule: "Consistencia de claves foráneas",
  DateToAgeRule: "Derivar edad o lapso desde fecha",
  NumericThresholdRule: "Columna derivada: umbral numérico",
  NumericBucketRule: "Columna estratificada: intervalos numéricos",
  DateCompositionRule: "Componer fecha desde columnas año/mes/día",
};

const GENERAL_CHECK_LABELS: Record<string, string> = {
  referential_integrity: "Integridad referencial",
  contextual_fk_consistency: "Consistencia FK contextual",
};

// Derived rule class names — same set as DERIVED_TYPES in rules-banner (by class name).
const DERIVED_CHECKS = new Set([
  "DateToAgeRule",
  "NumericThresholdRule",
  "NumericBucketRule",
  "DateCompositionRule",
]);

function checkTooltip(row: SanityReportRow): string {
  const tbl = row.table ?? "?";
  const src = row.origin_col ?? "?";
  const dst = row.aux_col ?? "?";
  const tgt = row.target_col ?? "?";

  if (row.type === "general") {
    if (row.check === "referential_integrity")
      return `Verifica que todas las claves foráneas de '${tbl}' apuntan a un registro existente en la tabla padre. Filas huérfanas = FK apunta a un ID que no existe en el padre.`;
    if (row.check === "contextual_fk_consistency")
      return `Verifica coherencia contextual de FK: dentro de cada grupo de contexto (episodio, visita…), la clave foránea es consistente entre todas las filas relacionadas.`;
    return `Comprobación estructural sobre '${tbl}'.`;
  }

  switch (row.check) {
    case "DateInequalityRule": {
      const op = row.constraint_operator ?? ">=";
      const bound = row.origin_col
        ? `la columna ${[row.table_origin, row.origin_col].filter(Boolean).join(".")}`
        : `la constante ${row.constraint ?? "?"}`;
      return `Verifica que '${tgt}' ${op} ${bound} en cada fila del dataset sintético. Filas que incumplen esta relación temporal se registran como errores.`;
    }
    case "NumericInequalityRule": {
      const op = row.constraint_operator ?? ">=";
      const bound = row.origin_col
        ? `la columna ${[row.table_origin, row.origin_col].filter(Boolean).join(".")}`
        : `la constante ${row.constraint ?? "?"}`;
      return `Verifica que '${tgt}' ${op} ${bound} en cada fila. Filas que incumplen la relación numérica se registran como errores.`;
    }
    case "DateToAgeRule": {
      const ref = row.reference_date_col ?? row.reference_date ?? "?";
      return `Verifica que la columna derivada '${dst}' coincide exactamente con el recálculo determinista de la diferencia entre '${src}' y '${ref}'. Esta comprobación es automática para toda regla de derivación: si el valor reconstruido en POST no cuadra con el original, lo detecta aquí.`;
    }
    case "NumericThresholdRule":
      return `Verifica que la columna derivada '${dst}' coincide con el valor que se obtendría aplicando el umbral sobre '${src}'. Detecta casos en que el POST no reconstruyó correctamente la columna derivada.`;
    case "NumericBucketRule":
      return `Verifica que el intervalo asignado en '${dst}' coincide con el que se obtendría de '${src}' con los bordes definidos. Detecta inconsistencias entre el valor continuo y su tramo de intervalo.`;
    case "ForeignKeysConsistencyRule": {
      const parent = [row.table_origin, row.source_col].filter(Boolean).join(".");
      return `Verifica que '${tgt}' en '${tbl}' coincide con el valor copiado de la tabla padre ('${parent}'). Detecta filas donde la FK reconstruida no coincide con el origen.`;
    }
    case "DateCompositionRule": {
      const canon = row.canonical_col ?? "?";
      return `Verifica que las columnas de componentes (año/mes/día) coinciden con los valores que se obtendrían descomponiendo '${canon}'. Detecta desajustes entre la fecha completa y sus partes.`;
    }
    case "SemanticRankingConsistencyRule":
    case "SemanticProportionalConsistencyRule":
      return `Verifica que las combinaciones de categorías generadas para '${tgt}' dentro de cada grupo ('${src}') ya existían en los datos de entrenamiento. Combinaciones nuevas son errores semánticos.`;
    default:
      return `Comprobación de la regla ${row.check} sobre '${tbl}'.`;
  }
}

function ruleLabel(row: SanityReportRow): string {
  const left = [row.table_origin, row.origin_col].filter(Boolean).join(".");
  const right = [row.table, row.target_col].filter(Boolean).join(".");

  if (row.check === "DateInequalityRule" || row.check === "NumericInequalityRule") {
    const op = row.constraint_operator ?? ">=";
    const bound = row.origin_col ? left : (row.constraint ?? "?");
    return `${right} ${op} ${bound}`;
  }
  if (row.check === "ForeignKeysConsistencyRule")
    return `${right} ← ${row.table_origin ?? "?"}.${row.source_col ?? row.target_col ?? "?"}`;
  if (row.check === "DateToAgeRule") {
    const ref = row.reference_date_col ?? row.reference_date ?? "?";
    return `${row.table}.${row.aux_col ?? "?"} = lapso(${row.origin_col ?? "?"} − ${ref})`;
  }
  if (row.check === "NumericThresholdRule")
    return `${row.table}.${row.aux_col ?? "?"} = (${row.origin_col ?? "?"} ${row.operator ?? ">="} ${row.threshold ?? "?"})`;
  if (row.check === "NumericBucketRule") {
    let bins = "?";
    try { bins = `[${(JSON.parse(row.bins ?? "[]") as number[]).join(", ")}]`; } catch { /* raw */ }
    return `${row.table}.${row.aux_col ?? "?"} = bucket(${row.origin_col ?? "?"}, ${bins})`;
  }
  if (row.check === "DateCompositionRule") {
    let parts: string[] = [];
    try { parts = Object.values(JSON.parse(row.part_cols ?? "{}") as Record<string, string>); } catch { /* raw */ }
    return `${row.table}.[${parts.join(", ") || "?"}] ← decompose(${row.canonical_col ?? "?"})`;
  }
  if (left && right) return `${left} → ${right}`;
  return row.rule ?? row.check;
}

function StatusIcon({ status }: { status: string }) {
  if (status === "PASS") return <CheckCircle2 className="h-3.5 w-3.5 shrink-0 text-emerald-500" />;
  if (status === "FAIL") return <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-500" />;
  return <XCircle className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />;
}

function StatusBadge({ row }: { row: SanityReportRow }) {
  if (row.status === "PASS")
    return (
      <span className="tabular-nums text-emerald-700 dark:text-emerald-400">
        ✓ {row.total_rows > 0 ? `${row.total_rows.toLocaleString()} filas` : "OK"}
      </span>
    );
  if (row.status === "FAIL") {
    const pct = row.total_rows > 0
      ? ((row.failed_rows / row.total_rows) * 100).toFixed(1)
      : "?";
    return (
      <span className="tabular-nums text-amber-700 dark:text-amber-400">
        {row.failed_rows.toLocaleString()} / {row.total_rows.toLocaleString()} violaciones ({pct}% incumplimiento)
      </span>
    );
  }
  return <span className="text-muted-foreground">Omitido</span>;
}

function CheckRow({ row }: { row: SanityReportRow }) {
  const typeLabel = row.type === "rule"
    ? (RULE_TYPE_LABELS[row.check] ?? row.check)
    : (GENERAL_CHECK_LABELS[row.check] ?? row.check);
  const label = row.type === "rule" ? ruleLabel(row) : (row.rule ?? row.check);
  const isDerived = DERIVED_CHECKS.has(row.check);

  return (
    <li className="flex flex-wrap items-start gap-x-2 gap-y-1 py-1.5 text-xs">
      <StatusIcon status={row.status} />
      <Badge
        variant="secondary"
        className={
          "text-[10px] " +
          (isDerived
            ? "border-blue-400/50 bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300"
            : "")
        }
      >
        {typeLabel}
      </Badge>
      <span className="font-mono text-muted-foreground">{label}</span>
      <span className="ml-auto shrink-0 pl-4">
        <StatusBadge row={row} />
      </span>
      <Tooltip content={checkTooltip(row)} side="left" />
      {row.details != null && row.details !== "" && row.status !== "PASS" && (
        <p className="w-full pl-5 text-[10px] text-muted-foreground">{row.details}</p>
      )}
    </li>
  );
}

export function SanityReportCard({ simulationId }: Props) {
  // Collapsed by default, like the rest of the desplegables in the UI. When
  // collapsed we still surface any failing checks so the user notices them
  // without having to expand the card.
  const [open, setOpen] = useState(false);
  const query = useQuery<SanityReport>({
    queryKey: ["simulations", simulationId, "sanity-report"],
    queryFn: async () => {
      const { data } = await api.get<SanityReport>(
        `/simulations/${encodeURIComponent(simulationId)}/sanity-report`,
      );
      return data;
    },
    retry: false,
  });

  const ruleRows = (query.data?.rows ?? []).filter((r) => r.type === "rule");
  const generalRows = (query.data?.rows ?? []).filter((r) => r.type === "general");
  const failedRows = (query.data?.rows ?? []).filter((r) => r.status === "FAIL");

  const summary = query.data
    ? {
        passed: query.data.rows.filter((r) => r.status === "PASS").length,
        failed: query.data.rows.filter((r) => r.status === "FAIL").length,
        total: query.data.rows.length,
      }
    : null;

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
          <CardTitle className="text-base">Informe de sanidad</CardTitle>
          {summary && (
            <Badge
              variant="outline"
              className={
                summary.failed > 0
                  ? "border-amber-500/60 text-amber-700 dark:text-amber-400"
                  : "border-emerald-500/60 text-emerald-700 dark:text-emerald-400"
              }
            >
              {summary.passed}/{summary.total} OK
            </Badge>
          )}
          {!open && summary && summary.failed > 0 && (
            <Badge
              variant="outline"
              className="border-amber-500/60 text-amber-700 dark:text-amber-400"
            >
              {summary.failed} con incidencias
            </Badge>
          )}
        </button>
          <AdvancedBadge tooltip="Validación avanzada: comprueba que el dataset sintético cumple las restricciones y reglas definidas." />
        </div>
        {open && (
          <CardDescription>
            Validaciones ejecutadas sobre el dataset sintético al finalizar la generación.
          </CardDescription>
        )}
      </CardHeader>

      {/* Collapsed: surface only the failing checks so a problem is visible
          without expanding. Expanded: the full report below. */}
      {!open && failedRows.length > 0 && (
        <CardContent className="pt-0">
          <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-amber-700 dark:text-amber-400">
            Incidencias detectadas
          </p>
          <ul className="divide-y">
            {failedRows.map((row, i) => <CheckRow key={i} row={row} />)}
          </ul>
        </CardContent>
      )}

      {open && (
      <CardContent>
        {query.isLoading && <p className="text-xs text-muted-foreground">Cargando…</p>}
        {query.isError && (
          <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <Clock className="h-3.5 w-3.5 shrink-0" />
            Esta ejecución no tiene informe de sanidad guardado.
          </div>
        )}
        {query.data && query.data.rows.length === 0 && (
          <p className="text-xs text-muted-foreground">No se ejecutaron validaciones.</p>
        )}
        {ruleRows.length > 0 && (
          <div className="mb-3">
            <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Reglas de negocio
            </p>
            <ul className="divide-y">
              {ruleRows.map((row, i) => <CheckRow key={i} row={row} />)}
            </ul>
          </div>
        )}
        {generalRows.length > 0 && (
          <div>
            <p className="mb-1 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
              Comprobaciones generales
            </p>
            <ul className="divide-y">
              {generalRows.map((row, i) => <CheckRow key={i} row={row} />)}
            </ul>
          </div>
        )}
        {query.data && query.data.rows.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-muted-foreground">
            <span className="font-medium">Leyenda:</span>
            <span className="inline-flex items-center gap-1">
              <Badge variant="secondary" className="text-[10px] border-blue-400/50 bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">tipo</Badge>
              columnas derivadas
            </span>
            <span className="inline-flex items-center gap-1">
              <Badge variant="secondary" className="text-[10px]">tipo</Badge>
              reglas lógicas / comprobaciones generales
            </span>
          </div>
        )}
      </CardContent>
      )}
    </Card>
  );
}
