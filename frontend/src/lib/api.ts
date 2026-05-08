// Axios client for talking to the FastAPI backend.
//
// Why axios instead of the built-in `fetch`?
//   - Automatic JSON parsing (one less line per call).
//   - Easier interceptors for logging / error handling.
//   - Consistent error shape across browsers.
//
// Every feature module imports `api` from here. Centralising means one place
// to add auth headers, retries, or base-URL changes later.

import axios from "axios";

// Default to a same-origin "/api" path that the Next.js dev server rewrites
// to the backend (see next.config.ts). Same-origin avoids CORS entirely and
// removes the need for the browser to reach the backend port directly — which
// matters when the frontend is served on a forwarded port (e.g. localhost:3001
// instead of 3000) or behind a proxy like SageMaker Studio.
const baseURL = process.env.NEXT_PUBLIC_API_URL ?? "/api";

export const api = axios.create({
  baseURL,
  headers: { "Content-Type": "application/json" },
});

// ---- Types ----
// These mirror the Pydantic schemas in backend/src/api/schemas/.
// TODO(step 2 of README section 7): auto-generate these with
// `openapi-typescript` so they can never drift from the backend.

export type DataFile = {
  path: string;
  name: string;
  size_bytes: number;
  extension: string;
};

export type FilePreview = {
  path: string;
  table: string;
  columns: string[];
  rows: string[][];
};

export type JobProgress = {
  step: number;
  total: number;
  label: string;
};

export type InspectionSummary = {
  inspection_id: string;
  inspection_name: string;
  status: "in_progress" | "completed" | "failed" | string;
  timestamp: string;
  tables: Record<string, number>;
  file_paths: string[];
  progress: JobProgress | null;
};

export type InspectionJob = {
  inspection_id: string;
  status: string;
};

export type ForeignKey = {
  parent: string;
  child: string;
  fk_column: string;
  pk_column: string;
  is_context: boolean;
  direct?: boolean;
};

export const ENCODING_TYPES = [
  "AUTO",
  "TABULAR_CATEGORICAL",
  "TABULAR_NUMERIC_AUTO",
  "TABULAR_NUMERIC_DISCRETE",
  "TABULAR_NUMERIC_BINNED",
  "TABULAR_NUMERIC_DIGIT",
  "TABULAR_CHARACTER",
  "TABULAR_DATETIME",
  "TABULAR_DATETIME_RELATIVE",
  "TABULAR_LAT_LONG",
  "LANGUAGE_TEXT",
  "LANGUAGE_CATEGORICAL",
  "LANGUAGE_NUMERIC",
  "LANGUAGE_DATETIME",
] as const;
export type EncodingType = (typeof ENCODING_TYPES)[number];

export type Autodetect = {
  relationships: {
    pks: Record<string, string>;
    fks: ForeignKey[];
  };
  encoding_types: Record<string, Record<string, string>>;
};

export type ProfilingReport = {
  table: string;
  filename: string;
};

export type ProfilingReports = {
  inspection_id: string;
  reports: ProfilingReport[];
};

export type ModelSummary = {
  model_id: string;
  model_name?: string | null;
  status: string;
  timestamp: string;
  tables: string;
  train_size: number | null;
  training_table_sizes: Record<string, number>;
  accuracy: number | null;
  qa_report_filename: string | null;
  progress: JobProgress | null;
};

export type TrainingJob = {
  model_id: string;
  status: string;
};

export type SimulationSummary = {
  simulation_id: string;
  simulation_name?: string | null;
  status: string;
  timestamp: string;
  model_id: string | null;
  sample_size: number | null;
  tables: string;
  training_table_sizes: Record<string, number>;
  model_accuracy: number | null;
  progress: JobProgress | null;
};

export type SimulationJob = {
  simulation_id: string;
  status: string;
};

export type EvaluationSummary = {
  evaluation_id: string;
  evaluation_name?: string | null;
  status: string;
  timestamp: string;
  simulation_id: string | null;
  model_id: string | null;
  pipeline_id: string | null;
  job_name: string | null;
  metrics_evaluated: string[] | null;
  progress: JobProgress | null;
};

export type EvaluationJob = {
  evaluation_id: string;
  status: string;
};

export type ConfigScope = "all" | "pipeline" | "evaluation" | "rules";

export type ConfigFile = {
  id: string;
  path: string;
  name: string;
  size_bytes: number;
  scope: ConfigScope;
  exists: boolean;
};

export type ConfigEditorFormat = "yaml" | "json" | "python" | "toml";

export type ConfigContent = {
  id: string;
  scope: ConfigScope;
  exists: boolean;
  example_path: string;
  path: string;
  content: string;
  example_content: string;
  format: ConfigEditorFormat;
};

export type ConfigBulkResult = {
  created: string[];
  skipped: string[];
  removed: string[];
};

export const API_BASE_URL = baseURL;

// ---- Purge ----
// Destructive operations that delete every folder in a resource (including
// completed runs). The global purge also resets configs from templates.

export type PurgeResult = { deleted_ids: string[] };

export type PurgeAllResult = {
  inspections: string[];
  models: string[];
  simulations: string[];
  evaluations: string[];
  configs_removed: string[];
  configs_created: string[];
};

export async function purgeInspections(): Promise<PurgeResult> {
  const { data } = await api.delete<PurgeResult>("/inspections/purge");
  return data;
}

export async function purgeModels(): Promise<PurgeResult> {
  const { data } = await api.delete<PurgeResult>("/models/purge");
  return data;
}

export async function purgeSimulations(): Promise<PurgeResult> {
  const { data } = await api.delete<PurgeResult>("/simulations/purge");
  return data;
}

export async function purgeEvaluations(): Promise<PurgeResult> {
  const { data } = await api.delete<PurgeResult>("/evaluations/purge");
  return data;
}

export type SimulationColumns = Record<string, string[]>;

export async function getSimulationColumns(simulationId: string): Promise<SimulationColumns> {
  const { data } = await api.get<SimulationColumns>(`/simulations/${simulationId}/columns`);
  return data;
}

export type ModelColumns = Record<string, string[]>;

export async function getModelColumns(modelId: string): Promise<ModelColumns> {
  const { data } = await api.get<ModelColumns>(`/models/${modelId}/columns`);
  return data;
}

export async function getModelColumnValues(
  modelId: string,
  table: string,
  column: string,
  limit = 200,
): Promise<string[]> {
  const { data } = await api.get<string[]>(
    `/models/${modelId}/columns/${encodeURIComponent(column)}/values`,
    { params: { table, limit } },
  );
  return data;
}

export async function purgeAll(): Promise<PurgeAllResult> {
  const { data } = await api.delete<PurgeAllResult>("/admin/purge-all");
  return data;
}

// ---- Upload Storage ----

export type UploadStats = {
  used_bytes: number;
  limit_bytes: number;
};

export async function getUploadStats(): Promise<UploadStats> {
  const { data } = await api.get<UploadStats>("/files/uploads/stats");
  return data;
}

// ---- Pipelines ----
// Dev-mode authoring + run-launching for the pipeline YAML files. The
// readonly catalog of past runs is fetched separately via /pipelines/.

export type PipelineJobRecord = {
  job_name?: string;
  status?: string;
  model_id?: string;
  model_output_dir?: string;
  simulation_id?: string;
  simulation_output_dir?: string;
  evaluation_id?: string;
  evaluation_output_dir?: string;
};

export type PipelineSummary = {
  pipeline_id: string;
  status: string;
  timestamp: string;
  config_path: string;
  // Snapshots that ``PipelineTracker`` writes alongside the run (see
  // pipeline_card.json: ``configs.pipeline_config`` / ``configs.general_config``).
  // Older runs may omit it entirely.
  configs?: {
    pipeline_config?: string;
    general_config?: string;
  };
  jobs: PipelineJobRecord[];
  // Coarse "Job X of N" progress while in_progress. Null when the run is
  // terminal or the card was written by an older backend.
  progress: JobProgress | null;
};

export type PipelineConfigFile = {
  name: string;
  filename: string;
  path: string;
  size_bytes: number;
};

export type PipelineConfigContent = PipelineConfigFile & { content: string };

export type PipelineLaunchAck = {
  pipeline_id: string;
  status: string;
};

export async function listPipelineConfigs(): Promise<PipelineConfigFile[]> {
  const { data } = await api.get<PipelineConfigFile[]>("/pipelines/configs");
  return data;
}

export async function getPipelineConfig(name: string): Promise<PipelineConfigContent> {
  const { data } = await api.get<PipelineConfigContent>(`/pipelines/configs/${name}`);
  return data;
}

export async function savePipelineConfig(
  name: string,
  content: string,
): Promise<PipelineConfigContent> {
  const { data } = await api.put<PipelineConfigContent>(`/pipelines/configs/${name}`, {
    content,
  });
  return data;
}

export async function deletePipelineConfig(name: string): Promise<void> {
  await api.delete(`/pipelines/configs/${name}`);
}

export type PipelineConfigSnapshot = {
  pipeline_id: string;
  config_path: string;
  pipeline_config_yaml: string | null;
  pipeline_config: Record<string, unknown> | null;
  general_config: Record<string, unknown> | null;
};

export async function getPipelineRunConfigs(
  pipelineId: string,
): Promise<PipelineConfigSnapshot> {
  const { data } = await api.get<PipelineConfigSnapshot>(
    `/pipelines/${pipelineId}/configs`,
  );
  return data;
}

export async function listPipelineRuns(): Promise<PipelineSummary[]> {
  const { data } = await api.get<PipelineSummary[]>("/pipelines/");
  return data;
}

export async function launchPipeline(configPath: string): Promise<PipelineLaunchAck> {
  const { data } = await api.post<PipelineLaunchAck>("/pipelines/", {
    config_path: configPath,
  });
  return data;
}
