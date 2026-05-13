// YAML <-> structured PipelineDoc round-trip used by the pipelines designer.
// Pure functions: no React, no network, no toast. The page imports these to
// load a saved YAML into the form, and to serialise the form back on save.
// The combinations / variants dialogs reuse `docToYaml` for previews.
//
// Unknown keys are preserved on the way in (rawJob → Job) but only fields the
// builder actually models survive the round-trip. Empty overrides, empty
// arrays, and `null` step blocks are pruned so the saved YAML stays readable
// instead of carrying noisy `config: {}` / `evaluate: null` stubs.

import yaml from "js-yaml";

import {
  EMPTY_CONDITIONAL_CONFIG,
  buildConditionalPayload,
  type ConditionalConfig,
} from "@/components/generation/conditional-config";
import {
  EMPTY_JOB,
  EMPTY_OVERRIDES,
  type Job,
  type JobOverrides,
  type PipelineDoc,
  type SyntheticDataFileFormat,
} from "@/components/pipelines/types";

export function emptyDoc(): PipelineDoc {
  return { jobs: [{ ...EMPTY_JOB, name: "job_1" }] };
}

// Render booleans/numbers from YAML back to the form-friendly string repr.
// Empty string is the canonical "no override" value across the form.
function boolToTri(v: unknown): "" | "true" | "false" {
  if (v === true) return "true";
  if (v === false) return "false";
  return "";
}
function numToStr(v: unknown): string {
  return typeof v === "number" ? String(v) : "";
}

export function parseConditionalConfig(raw: unknown): ConditionalConfig {
  if (!raw || typeof raw !== "object") return { ...EMPTY_CONDITIONAL_CONFIG };
  const payload = raw as Record<string, unknown>;
  const seed = payload.seed as Record<string, unknown> | undefined;
  const distribution = payload.distribution as Record<string, unknown> | undefined;

  return {
    table: typeof payload.table === "string" ? payload.table : "",
    seeds: seed
      ? Object.entries(seed).map(([column, value]) => ({ column, value: String(value) }))
      : [],
    distributionField:
      typeof payload.distribution_field === "string" ? payload.distribution_field : "",
    distribution: distribution
      ? Object.entries(distribution).map(([value, weight]) => ({
        value,
        weight: String(weight),
      }))
      : [],
  };
}

export function readOverrides(rawCfg: unknown): JobOverrides {
  if (!rawCfg || typeof rawCfg !== "object") return { ...EMPTY_OVERRIDES };
  const cfg = rawCfg as Record<string, unknown>;
  const ma = (cfg.mostly_ai ?? {}) as Record<string, unknown>;
  const ms = (ma.model_settings ?? {}) as Record<string, unknown>;
  const dp = (ms.differential_privacy ?? {}) as Record<string, unknown>;
  const gn = (cfg.general ?? {}) as Record<string, unknown>;
  return {
    rules_config: typeof cfg.rules_config === "string" ? cfg.rules_config : "",
    max_epochs: numToStr(ms.max_epochs),
    batch_size: numToStr(ms.batch_size),
    model: typeof ms.model === "string" ? ms.model : "",
    enable_flexible_generation: boolToTri(ms.enable_flexible_generation),
    enable_model_report: boolToTri(ms.enable_model_report),
    dp_max_epsilon: numToStr(dp.max_epsilon),
    dp_noise_multiplier: numToStr(dp.noise_multiplier),
    enable_data_profiling: boolToTri(gn.enable_data_profiling),
    default_csv_delimiter:
      typeof gn.default_csv_delimiter === "string" ? gn.default_csv_delimiter : "",
  };
}

export function parseYamlToDoc(text: string): PipelineDoc {
  const raw = yaml.load(text);
  if (!raw || typeof raw !== "object" || !Array.isArray((raw as { jobs?: unknown }).jobs)) {
    return emptyDoc();
  }
  const rawJobs = (raw as { jobs: Record<string, unknown>[] }).jobs;
  const jobs: Job[] = rawJobs.map((rawJob, i) => {
    const train =
      (rawJob.train as
        | { files?: string[]; inspection_id?: string | null }
        | undefined) ?? undefined;
    const sim = rawJob.simulate as
      | {
        sample_size?: number;
        model_id?: string | null;
        synthetic_data_file_format?: SyntheticDataFileFormat;
        conditional?: unknown;
      }
      | undefined;
    const ev = rawJob.evaluate as
      | { real_data?: string[]; simulation_id?: string | null; model_id?: string | null }
      | undefined;
    return {
      name: typeof rawJob.name === "string" ? rawJob.name : `job_${i + 1}`,
      overrides: readOverrides(rawJob.config),
      train: train
        ? {
          files: train.files ?? [],
          inspection_id: train.inspection_id ?? "",
        }
        : null,
      simulate: sim
        ? {
          sample_size: sim.sample_size ?? 1000,
          model_id: sim.model_id ?? "",
          synthetic_data_file_format: sim.synthetic_data_file_format ?? "csv",
          conditional: parseConditionalConfig(sim.conditional),
        }
        : null,
      evaluate: ev
        ? {
          real_data: ev.real_data ?? [],
          simulation_id: ev.simulation_id ?? "",
          model_id: ev.model_id ?? "",
        }
        : null,
    };
  });
  return { jobs };
}

// Serialise overrides → YAML. Returns an empty object the caller skips entirely
// when no override is set, so the YAML doesn't carry a noisy ``config: {}``.
export function emitOverrides(o: JobOverrides): Record<string, unknown> {
  const cfg: Record<string, unknown> = {};
  if (o.rules_config.trim()) cfg.rules_config = o.rules_config.trim();

  const modelSettings: Record<string, unknown> = {};
  if (o.max_epochs.trim()) modelSettings.max_epochs = Number(o.max_epochs);
  if (o.batch_size.trim()) modelSettings.batch_size = Number(o.batch_size);
  if (o.model.trim()) modelSettings.model = o.model.trim();
  if (o.enable_flexible_generation)
    modelSettings.enable_flexible_generation = o.enable_flexible_generation === "true";
  if (o.enable_model_report)
    modelSettings.enable_model_report = o.enable_model_report === "true";

  const dp: Record<string, unknown> = {};
  if (o.dp_max_epsilon.trim()) dp.max_epsilon = Number(o.dp_max_epsilon);
  if (o.dp_noise_multiplier.trim()) dp.noise_multiplier = Number(o.dp_noise_multiplier);
  if (Object.keys(dp).length > 0) modelSettings.differential_privacy = dp;

  if (Object.keys(modelSettings).length > 0) {
    cfg.mostly_ai = { model_settings: modelSettings };
  }

  const general: Record<string, unknown> = {};
  if (o.enable_data_profiling)
    general.enable_data_profiling = o.enable_data_profiling === "true";
  if (o.default_csv_delimiter.trim())
    general.default_csv_delimiter = o.default_csv_delimiter;
  if (Object.keys(general).length > 0) cfg.general = general;

  return cfg;
}

export function docToYaml(doc: PipelineDoc): string {
  const out = {
    jobs: doc.jobs.map((j) => {
      // Drop step keys when the section is null and prune empty optional ids
      // so the saved YAML stays readable.
      const job: Record<string, unknown> = { name: j.name };
      const cfg = emitOverrides(j.overrides);
      if (Object.keys(cfg).length > 0) job.config = cfg;
      if (j.train) {
        // Inspection-id and files are mutually exclusive on the backend; emit
        // whichever the user picked, never both, so the YAML stays unambiguous.
        const tr: Record<string, unknown> = {};
        if (j.train.inspection_id) {
          tr.inspection_id = j.train.inspection_id;
        } else {
          tr.files = j.train.files;
        }
        job.train = tr;
      }
      if (j.simulate) {
        const sim: Record<string, unknown> = {
          sample_size: j.simulate.sample_size,
          synthetic_data_file_format: j.simulate.synthetic_data_file_format,
        };
        if (j.simulate.model_id) sim.model_id = j.simulate.model_id;
        const conditional = buildConditionalPayload(j.simulate.conditional);
        if (conditional) sim.conditional = conditional;
        job.simulate = sim;
      }
      if (j.evaluate) {
        const ev: Record<string, unknown> = { real_data: j.evaluate.real_data };
        if (j.evaluate.simulation_id) ev.simulation_id = j.evaluate.simulation_id;
        if (j.evaluate.model_id) ev.model_id = j.evaluate.model_id;
        job.evaluate = ev;
      }
      return job;
    }),
  };
  return yaml.dump(out, { lineWidth: 100, noRefs: true });
}
