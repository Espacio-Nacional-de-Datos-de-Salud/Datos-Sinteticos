// Shared structural model for the pipelines workbench. Lives outside `page.tsx`
// so the combinations / variants dialogs can reference the same shapes the
// editor builds without reaching back into a Next.js route module.
//
// The YAML <-> structured conversion still lives in the page (it's bound to
// the editor's parse/serialize flow); only the *types* and the canonical
// `EMPTY_*` seeds are shared from here.

import {
  EMPTY_CONDITIONAL_CONFIG,
  type ConditionalConfig,
} from "@/components/generation/conditional-config";

export type SyntheticDataFileFormat = "csv" | "parquet";

// Train step has two mutually-exclusive input modes: raw files (preprocess on
// the fly) or resume from a previously produced inspection. We model them on
// the same record because the YAML allows both keys to coexist (with
// inspection_id taking precedence) — collapsing to a discriminated union here
// would force unnecessary re-shapes when the user toggles between modes.
export type TrainStep = { files: string[]; inspection_id: string };

export type SimulateStep = {
  sample_size: number;
  model_id: string;
  synthetic_data_file_format: SyntheticDataFileFormat;
  conditional: ConditionalConfig;
};

export type EvaluateStep = {
  real_data: string[];
  simulation_id: string;
  model_id: string;
};

// Per-job overrides — every field is optional. Empty string is the canonical
// "no override" value; on serialise we only emit keys the user actually set,
// so the saved YAML keeps the deep-merge semantics that load_pipeline_config
// expects.
export type JobOverrides = {
  rules_config: string;
  // mostly_ai.model_settings.*
  max_epochs: string; // string-typed to allow empty = "no override"
  batch_size: string;
  model: string;
  enable_flexible_generation: "" | "true" | "false";
  enable_model_report: "" | "true" | "false";
  // mostly_ai.model_settings.differential_privacy.*
  dp_max_epsilon: string;
  dp_noise_multiplier: string;
  // general.*
  enable_data_profiling: "" | "true" | "false";
  default_csv_delimiter: string;
};

export type Job = {
  name: string;
  overrides: JobOverrides;
  train: TrainStep | null;
  simulate: SimulateStep | null;
  evaluate: EvaluateStep | null;
};

export type PipelineDoc = { jobs: Job[] };

export const EMPTY_OVERRIDES: JobOverrides = {
  rules_config: "",
  max_epochs: "",
  batch_size: "",
  model: "",
  enable_flexible_generation: "",
  enable_model_report: "",
  dp_max_epsilon: "",
  dp_noise_multiplier: "",
  enable_data_profiling: "",
  default_csv_delimiter: "",
};

export const EMPTY_JOB: Job = {
  name: "new_job",
  overrides: { ...EMPTY_OVERRIDES },
  train: null,
  simulate: null,
  evaluate: null,
};

// Re-exported so callers building a fresh SimulateStep don't need to reach
// into the generation drawer module directly.
export { EMPTY_CONDITIONAL_CONFIG };

// Curated subset of Mostly AI model presets — matches the values the engine
// accepts. Kept intentionally short so dropdowns stay scannable.
export const MOSTLY_AI_MODELS = [
  "MOSTLY_AI/Small",
  "MOSTLY_AI/Medium",
  "MOSTLY_AI/Large",
] as const;
export type MostlyAiModel = (typeof MOSTLY_AI_MODELS)[number];
