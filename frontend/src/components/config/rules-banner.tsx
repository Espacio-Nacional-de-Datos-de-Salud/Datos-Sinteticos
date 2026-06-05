// Read-only summary of the current rules.yaml. Shown on steps that consume a
// preprocessed dataset (training / generation / audit) so the user can see
// which rules apply but cannot modify them here — edits live in Inspección,
// since changing rules requires re-preprocessing the data.

"use client";

import { useQuery } from "@tanstack/react-query";
import yaml from "js-yaml";
import axios from "axios";
import { Info } from "lucide-react";
import { api, type ConfigContent } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { getBrcRulesSnapshot } from "@/lib/brc";

type Props = {
  // When provided, fetch the rules snapshot frozen at this inspection's run
  // time. Falls back to the live ``rules.yaml`` if the snapshot is absent
  // (older inspections) or no inspection id is supplied.
  inspectionId?: string | null;
  // When provided, takes precedence over inspectionId and fetches the rules
  // snapshot frozen at the time this BRC run was executed — exactly the rules
  // that were PRE-applied to the parquet the trainer will read.
  brcId?: string | null;
  // Title shown on the banner. Defaults to "Reglas de preprocesamiento";
  // callers training from a BRC pass "Reglas de negocio" since at that point
  // the rules are already materialised and act as business invariants.
  title?: string;
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
  // derived-column fields
  aux_col?: string;
  reference_date?: string;
  reference_date_col?: string;
  threshold?: number | null;
  operator?: string;
  bins?: number[];
};

type RulesFile = { rules?: Rule[] };

const TYPE_LABELS: Record<string, string> = {
  date_inequality: "Relación entre fechas",
  numeric_inequality: "Relación entre números",
  semantic_ranking_consistency: "Consistencia semántica (ranking)",
  semantic_proportional_consistency: "Consistencia semántica (proporcional)",
  foreign_keys_consistency_rule: "Consistencia de claves foráneas",
  date_to_age: "Derivar edad o lapso desde fecha",
  numeric_threshold: "Columna derivada: umbral numérico",
  numeric_bucket: "Columna estratificada: buckets numéricos",
};

const DERIVED_TYPES = new Set(["date_to_age", "numeric_threshold", "numeric_bucket"]);

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
  return `${left} → ${right}`;
}

export function RulesBanner({ inspectionId, brcId, title }: Props = {}) {
  type Source = "snapshot" | "live" | "brc";
  const query = useQuery({
    queryKey: ["rules-banner", brcId ?? null, inspectionId ?? null],
    queryFn: async (): Promise<{ yaml: string; source: Source }> => {
      if (brcId) {
        const yamlText = await getBrcRulesSnapshot(brcId);
        return { yaml: yamlText, source: "brc" };
      }
      if (inspectionId) {
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

  return (
    <div className="rounded-md border bg-muted/30 p-3 text-sm">
      <div className="flex items-start gap-2">
        <Info className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1">
          <p className="font-medium">
            {title ?? "Reglas de preprocesamiento"}
            {rules.length > 0 && (
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                ({rules.length})
              </span>
            )}
          </p>
          <p className="mt-0.5 text-xs text-muted-foreground">
            {source === "brc"
              ? "Reglas aplicadas (PRE) en esta ejecución BRC. El entrenamiento reutilizará este dataset preprocesado."
              : source === "snapshot"
                ? "Reglas aplicadas al preprocesar este dataset. Para modificarlas, vuelve a Reglas de negocio y reprocesa."
                : "Reglas actualmente configuradas (rules.yaml). Para modificarlas, ve a Reglas de negocio y reprocesa."}
          </p>
          {query.isLoading && (
            <p className="mt-2 text-xs text-muted-foreground">Cargando…</p>
          )}
          {!query.isLoading && rules.length === 0 && (
            <p className="mt-2 text-xs text-muted-foreground">
              No hay reglas definidas.
            </p>
          )}
          {rules.length > 0 && (
            <ul className="mt-2 space-y-1.5">
              {rules.map((r, i) => (
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
                  <span className="font-mono text-xs text-muted-foreground">{summarize(r)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
