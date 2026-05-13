// Pure helpers for the two pipeline-expansion modes:
//
//   • `expandGrid`     — cartesian product of N axes against a base job. Used
//                        by the top-level "Generar combinaciones" dialog when
//                        the engineer wants to systematically benchmark a job
//                        across hyperparameter / dataset combinations.
//   • `expandVariants` — sparse list of patches against a base job. Used by
//                        the per-job "Expandir" dialog when sweeps are
//                        hand-picked rather than full-product (e.g. take a
//                        simulate-only job and run it with three different
//                        sample sizes + one DP-on variant).
//
// Both modes converge on the same axis vocabulary (`AxisField`) so the value
// editors can be reused. `evaluate.real_data` is intentionally absent — it's
// derived from the model's training inspection data, not a meaningful sweep
// axis.

import type { Job } from "./types";

// ---------------------------------------------------------------------------
// Axis vocabulary
// ---------------------------------------------------------------------------

export type AxisField =
  | "rules_config"
  | "max_epochs"
  | "batch_size"
  | "model"
  | "enable_flexible_generation"
  | "enable_model_report"
  | "dp_max_epsilon"
  | "dp_noise_multiplier"
  | "enable_data_profiling"
  | "default_csv_delimiter"
  | "train_files" //   Job.train.files       — one axis value = one file group
  | "train_inspection_id" // Job.train.inspection_id (resume-from-inspection)
  | "sample_size" //   Job.simulate.sample_size
  | "simulate_model_id" // Job.simulate.model_id (resume-from)
  | "evaluate_simulation_id"; // Job.evaluate.simulation_id (eval-only chains)

// Each axis value carries the human label used to build the job name and the
// raw payload that gets written into the Job. Most fields use string raw, but
// `train_files` uses `string[]` so a single axis value can represent a group
// of files (e.g. "ventas" → [a.csv, b.csv]).
export type AxisValue = {
  label: string;
  raw: string | string[];
};

export type Axis = {
  field: AxisField;
  values: AxisValue[];
};

// Variant mode: each variant is a sparse map of (field → raw). Missing fields
// inherit unchanged from the base job.
export type Variant = {
  label: string;
  patch: Partial<Record<AxisField, string | string[]>>;
};

// Override-style fields apply to JobOverrides. Step-bound fields require their
// step to be enabled on the base job — `axisRequiresStep` lets the dialogs
// hide axes that wouldn't apply.
const OVERRIDE_FIELDS = new Set<AxisField>([
  "rules_config",
  "max_epochs",
  "batch_size",
  "model",
  "enable_flexible_generation",
  "enable_model_report",
  "dp_max_epsilon",
  "dp_noise_multiplier",
  "enable_data_profiling",
  "default_csv_delimiter",
]);

export function isOverrideField(f: AxisField): boolean {
  return OVERRIDE_FIELDS.has(f);
}

export function axisRequiresStep(
  f: AxisField,
): "train" | "simulate" | "evaluate" | null {
  if (f === "train_files" || f === "train_inspection_id") return "train";
  if (f === "sample_size" || f === "simulate_model_id") return "simulate";
  if (f === "evaluate_simulation_id") return "evaluate";
  return null;
}

export function isAxisApplicable(field: AxisField, base: Job): boolean {
  const step = axisRequiresStep(field);
  if (step === "train") return base.train !== null;
  if (step === "simulate") return base.simulate !== null;
  if (step === "evaluate") return base.evaluate !== null;
  return true;
}

// ---------------------------------------------------------------------------
// Application
// ---------------------------------------------------------------------------

// Mutates the input — callers should pass a deep-enough clone.
function applyAxisValue(job: Job, field: AxisField, raw: string | string[]): void {
  if (isOverrideField(field) && typeof raw === "string") {
    // Cast is safe because OVERRIDE_FIELDS is a subset of JobOverrides keys
    // and every override field accepts strings ("" | enum-string | numeric
    // string). Tri-bool fields receive "true" / "false" which match their
    // declared union.
    (job.overrides as Record<string, unknown>)[field] = raw;
    return;
  }
  if (field === "train_files" && job.train) {
    // Switching to a files-based train clears any inspection-id source the
    // base might have carried — the two are mutually exclusive on the
    // backend.
    job.train = { files: Array.isArray(raw) ? raw : [raw], inspection_id: "" };
    return;
  }
  if (field === "train_inspection_id" && job.train && typeof raw === "string") {
    job.train = { ...job.train, files: [], inspection_id: raw };
    return;
  }
  if (field === "sample_size" && job.simulate && typeof raw === "string") {
    job.simulate = { ...job.simulate, sample_size: Number(raw) || 0 };
    return;
  }
  if (field === "simulate_model_id" && job.simulate && typeof raw === "string") {
    job.simulate = { ...job.simulate, model_id: raw };
    return;
  }
  if (
    field === "evaluate_simulation_id"
    && job.evaluate
    && typeof raw === "string"
  ) {
    job.evaluate = { ...job.evaluate, simulation_id: raw };
  }
}

// JSON round-trip is enough — the Job tree is JSON-safe (no Dates, functions,
// or Maps). Cheap and avoids a structural-clone polyfill in older browsers.
function deepCloneJob(job: Job): Job {
  return JSON.parse(JSON.stringify(job)) as Job;
}

// ---------------------------------------------------------------------------
// Naming
// ---------------------------------------------------------------------------

// Job names need to remain `[A-Za-z0-9_-]+` (the page validates this on save).
// Slug aggressively, fall back to "v" when a label slugs to nothing so we
// always emit a non-empty segment.
function slug(s: string): string {
  const out = s
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
  return out || "v";
}

// After slug truncation two distinct labels can collide ("config/pipelines/rules-A"
// and "config/pipelines/rules-B" both flatten to the same 32-char prefix), which
// would produce duplicate Job names — the backend rejects those and React warns.
// Walk the list once and disambiguate any repeats with `__2`, `__3`, …
function dedupeJobNames(jobs: Job[]): Job[] {
  const seen = new Map<string, number>();
  return jobs.map((j) => {
    const count = seen.get(j.name) ?? 0;
    seen.set(j.name, count + 1);
    return count === 0 ? j : { ...j, name: `${j.name}__${count + 1}` };
  });
}

function formatExpandedName(
  base: string,
  combo: { field: AxisField; value: AxisValue }[],
): string {
  const tail = combo.map((c) => `${c.field}-${slug(c.value.label)}`).join("__");
  return tail ? `${base}__${tail}` : base;
}

// ---------------------------------------------------------------------------
// Public expanders
// ---------------------------------------------------------------------------

// Cartesian product of axis values, applied to a clone of `base` per combo.
// Axes with zero values are skipped (rather than collapsing the product to
// zero) so half-finished editor state still produces something sensible to
// preview.
export function expandGrid(base: Job, axes: Axis[]): Job[] {
  const usable = axes.filter((a) => a.values.length > 0);
  if (usable.length === 0) return [];

  let combos: { field: AxisField; value: AxisValue }[][] = [[]];
  for (const axis of usable) {
    const next: typeof combos = [];
    for (const combo of combos) {
      for (const v of axis.values) {
        next.push([...combo, { field: axis.field, value: v }]);
      }
    }
    combos = next;
  }

  const expanded = combos.map((combo) => {
    const clone = deepCloneJob(base);
    for (const { field, value } of combo) applyAxisValue(clone, field, value.raw);
    clone.name = formatExpandedName(base.name, combo);
    return clone;
  });
  return dedupeJobNames(expanded);
}

export function expandVariants(base: Job, variants: Variant[]): Job[] {
  const expanded = variants.map((v) => {
    const clone = deepCloneJob(base);
    for (const [field, raw] of Object.entries(v.patch) as [
      AxisField,
      string | string[],
    ][]) {
      applyAxisValue(clone, field, raw);
    }
    clone.name = `${base.name}__${slug(v.label)}`;
    return clone;
  });
  return dedupeJobNames(expanded);
}

// Count how many jobs `expandGrid` would produce — used by the dialog to show
// a live "Se generarán N jobs" preview without materialising the products.
export function gridSize(axes: Axis[]): number {
  const usable = axes.filter((a) => a.values.length > 0);
  if (usable.length === 0) return 0;
  return usable.reduce((acc, a) => acc * a.values.length, 1);
}

// ---------------------------------------------------------------------------
// Display metadata
// ---------------------------------------------------------------------------

export const AXIS_LABELS: Record<AxisField, string> = {
  rules_config: "Reglas (rules_config)",
  max_epochs: "max_epochs",
  batch_size: "batch_size",
  model: "Modelo (model)",
  enable_flexible_generation: "enable_flexible_generation",
  enable_model_report: "enable_model_report",
  dp_max_epsilon: "DP · max_epsilon",
  dp_noise_multiplier: "DP · noise_multiplier",
  enable_data_profiling: "enable_data_profiling",
  default_csv_delimiter: "default_csv_delimiter",
  train_files: "Archivos de entrenamiento",
  train_inspection_id: "Inspección de entrenamiento",
  sample_size: "sample_size (generación)",
  simulate_model_id: "Modelo origen (generación)",
  evaluate_simulation_id: "Simulación a evaluar",
};

// Editor kind drives which input the value pickers render.
export type AxisFieldKind =
  | "numeric"
  | "text"
  | "tri"
  | "model"
  | "rules"
  | "modelId"
  | "inspectionId"
  | "simulationId"
  | "filesGroup";

export const AXIS_FIELD_KIND: Record<AxisField, AxisFieldKind> = {
  rules_config: "rules",
  max_epochs: "numeric",
  batch_size: "numeric",
  model: "model",
  enable_flexible_generation: "tri",
  enable_model_report: "tri",
  dp_max_epsilon: "numeric",
  dp_noise_multiplier: "numeric",
  enable_data_profiling: "tri",
  default_csv_delimiter: "text",
  train_files: "filesGroup",
  train_inspection_id: "inspectionId",
  sample_size: "numeric",
  simulate_model_id: "modelId",
  evaluate_simulation_id: "simulationId",
};
