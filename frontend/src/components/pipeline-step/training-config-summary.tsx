"use client";

// Read-only, friendly summary of a Mostly AI training configuration.
//
// It is schema-driven: it only shows parameters that exist as fields in the
// "Configuración del modelo" form (GET /configs/schemas), so the summary always
// matches what the user can actually see and edit above — internal keys like
// `enable_model_report` or the generator metadata are never shown, and new
// form fields appear automatically. Differential-privacy fields are included
// (and grouped) only when the run actually enabled that block.
//
// Two sources feed it:
//   • <TrainingConfigSummary modelId> reads the FROZEN config a past/active
//     model was trained with (GET /models/{id}/config).
//   • <CurrentConfigSummary> reads the CURRENT live config the next run will
//     use (GET /configs/mostly_ai), so the user can review it before launching.

import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import yaml from "js-yaml";

import { api, getModelTrainingConfig, type ConfigContent } from "@/lib/api";
import {
  useConfigSchemas,
  type ConfigSchema,
  type FieldSchema,
} from "@/components/config/schemas";
import { Skeleton } from "@/components/ui/skeleton";

type AnyRecord = Record<string, unknown>;

const DP_PATH = "model_settings.differential_privacy";

function getByPath(obj: AnyRecord, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, key) => {
    if (acc && typeof acc === "object" && !Array.isArray(acc)) {
      return (acc as AnyRecord)[key];
    }
    return undefined;
  }, obj);
}

// Friendly display for a single field's value, using the field's own metadata:
// booleans → Sí/No, select values → their human label, empty → "Sin límite".
function formatFieldValue(field: FieldSchema, value: unknown): string {
  if (value === null || value === undefined || value === "") {
    // Most numeric model limits treat "empty" as "no limit".
    return field.kind === "number" ? "Sin límite" : "—";
  }
  if (typeof value === "boolean") return value ? "Activada" : "Desactivada";
  if (field.kind === "select" && field.options) {
    const match = field.options.find((o) => o.value === value);
    if (match) return match.label;
  }
  if (Array.isArray(value)) return value.length ? value.join(", ") : "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

type SummaryRow = { label: string; value: string };
type SummarySection = { title: string; rows: SummaryRow[] };

// Walk the schema groups in order and collect a row for every leaf field that
// the config actually carries — skipping the per-table JSON blob and the DP
// block (handled separately so it can be grouped and conditionally hidden).
function buildSections(
  schema: ConfigSchema | undefined,
  config: AnyRecord,
): SummarySection[] {
  if (!schema) return [];

  const sections: SummarySection[] = [];
  for (const group of schema.groups) {
    const isDpGroup = group.fields.some((f) => f.path.startsWith(`${DP_PATH}.`));
    // Differential privacy only matters when the run enabled it.
    if (isDpGroup) {
      const dpEnabled =
        getByPath(config, DP_PATH) !== undefined &&
        getByPath(config, DP_PATH) !== null;
      if (!dpEnabled) continue;
    }

    const rows: SummaryRow[] = [];
    for (const field of group.fields) {
      // Skip free-form JSON fields (e.g. per-table overrides) — too detailed
      // for a glanceable summary.
      if (field.kind === "json") continue;
      const value = getByPath(config, field.path);
      // For non-DP fields, omit keys absent from the config entirely; for DP
      // (already known enabled) show every field so the protection is explicit.
      if (value === undefined && !isDpGroup) continue;
      rows.push({ label: field.label, value: formatFieldValue(field, value) });
    }
    if (rows.length > 0) {
      sections.push({ title: group.title, rows });
    }
  }
  return sections;
}

function SummaryBody({ sections }: { sections: SummarySection[] }) {
  return (
    <div className="space-y-3">
      {sections.map((section) => (
        <div key={section.title} className="space-y-1.5">
          <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
            {section.title}
          </p>
          <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
            {section.rows.map((row) => (
              <div
                key={row.label}
                className="flex items-baseline justify-between gap-3 border-b border-border/40 pb-1"
              >
                <dt className="text-xs text-muted-foreground">{row.label}</dt>
                <dd
                  className="truncate text-xs font-medium text-foreground"
                  title={row.value}
                >
                  {row.value}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      ))}
    </div>
  );
}

function SummaryShell({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-3 rounded-lg border bg-card p-4">
      <p className="text-sm font-semibold text-foreground">{title}</p>
      {children}
    </div>
  );
}

/** Frozen configuration a specific model was trained with. */
export function TrainingConfigSummary({ modelId }: { modelId: string }) {
  const query = useQuery({
    queryKey: ["model-config", modelId],
    queryFn: () => getModelTrainingConfig(modelId),
  });
  const { schemas } = useConfigSchemas();

  const sections = useMemo(
    () =>
      buildSections(schemas.mostly_ai, (query.data?.config ?? {}) as AnyRecord),
    [schemas.mostly_ai, query.data],
  );

  if (query.isLoading) return <Skeleton className="h-24 w-full rounded-lg" />;
  if (query.isError) {
    return (
      <SummaryShell title="Resumen configuración del entrenamiento">
        <p className="text-xs text-muted-foreground">
          No se pudo cargar la configuración del entrenamiento.
        </p>
      </SummaryShell>
    );
  }
  if (sections.length === 0) {
    return (
      <SummaryShell title="Resumen configuración del entrenamiento">
        <p className="text-xs text-muted-foreground">
          No se registró la configuración de este entrenamiento.
        </p>
      </SummaryShell>
    );
  }

  return (
    <SummaryShell title="Resumen configuración del entrenamiento">
      <SummaryBody sections={sections} />
    </SummaryShell>
  );
}

/** Current live configuration the next training run will use. */
export function CurrentConfigSummary() {
  const query = useQuery({
    queryKey: ["config", "mostly_ai"],
    queryFn: async () => {
      const { data } = await api.get<ConfigContent>("/configs/mostly_ai");
      return data;
    },
  });
  const { schemas } = useConfigSchemas();

  const sections = useMemo(() => {
    if (!query.data) return [];
    let parsed: AnyRecord = {};
    try {
      parsed = (yaml.load(query.data.content) as AnyRecord) ?? {};
    } catch {
      parsed = {};
    }
    return buildSections(schemas.mostly_ai, parsed);
  }, [schemas.mostly_ai, query.data]);

  if (query.isLoading) return <Skeleton className="h-24 w-full rounded-lg" />;
  if (query.isError || sections.length === 0) {
    return (
      <SummaryShell title="Resumen configuración que se usará">
        <p className="text-xs text-muted-foreground">
          No se pudo cargar la configuración actual del modelo.
        </p>
      </SummaryShell>
    );
  }

  return (
    <SummaryShell title="Resumen configuración que se usará">
      <p className="text-xs text-muted-foreground">
        Estos son los parámetros guardados que se aplicarán al iniciar el
        entrenamiento. Edítalos arriba en «Configuración del modelo».
      </p>
      <SummaryBody sections={sections} />
    </SummaryShell>
  );
}
