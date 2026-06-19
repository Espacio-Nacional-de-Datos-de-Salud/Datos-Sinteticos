// Axios client for talking to the FastAPI backend.
//
// All Pydantic-derived response shapes come from `./api-types.ts`, which is
// auto-generated from the backend's OpenAPI document by `openapi-typescript`.
// Refresh it after backend schema changes:
//
//     cd frontend && npm run generate:api      # backend running on :8000
//
// We re-export those generated shapes under the original friendly names so
// the rest of the app keeps importing `DataFile`, `InspectionSummary`, etc.
// from "@/lib/api" — no churn at the call sites.
//
// Frontend-only helpers (axios client, ENCODING_TYPES enum, async wrappers,
// and a couple of overlay types where the backend's response_model is too
// loose for what the UI actually needs) live below the type re-exports.

import axios from "axios";
import type { components } from "./api-types";

type Schemas = components["schemas"];

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

export const API_BASE_URL = baseURL;

// ---- Types from the backend OpenAPI schema ---------------------------------

export type DataFile = Schemas["DataFile"];
export type FilePreview = Schemas["FilePreview"];
export type JobProgress = Schemas["JobProgress"];

// `error_message` is written by the backend on failed cards (see
// card_io.mark_card_failed) and surfaced on the status pill. The intersection
// keeps it typed until the OpenAPI snapshot is regenerated, after which the
// generated field is identical and the overlay becomes a harmless no-op.
type WithErrorMessage = { error_message?: string | null };

export type InspectionSummary = Schemas["InspectionSummary"] & WithErrorMessage;
export type InspectionJob = Schemas["InspectionJob"];
export type ForeignKey = Schemas["ForeignKey"];
export type Autodetect = Schemas["Autodetect"];
export type ColumnWarning = Schemas["ColumnWarning"];

export type ProfilingReport = Schemas["ProfilingReport"];
export type ProfilingReports = Schemas["ProfilingReports"];

export type ModelSummary = Schemas["ModelSummary"] & WithErrorMessage;
export type ModelTrainingConfig = Schemas["ModelTrainingConfig"];
export type TrainingJob = Schemas["TrainingJob"];

export type SimulationSummary = Schemas["SimulationSummary"] & WithErrorMessage;
export type SimulationRelationship = Schemas["SimulationRelationship"];
export type SimulationJob = Schemas["SimulationJob"];
export type ComplianceRow = {
  rule_index: number;
  rule_type: string;
  table: string;
  origin_col?: string | null;
  target_col?: string | null;
  source_col?: string | null;
  checked: number;
  failing: number;
  pct_compliant?: number | null;
  null_rows?: number;
  pct_null?: number | null;
  nonnull_failing?: number;
  pct_nonnull_noncompliant?: number | null;
  skipped: boolean;
  skip_reason?: string | null;
};
export type ComplianceReport = {
  inspection_id: string;
  sample_size: number;
  rows: ComplianceRow[];
};

export type SanityReportRow = {
  type: "rule" | "general";
  check: string;
  rule: string;
  table: string;
  status: "PASS" | "FAIL" | "SKIPPED";
  failed_rows: number;
  total_rows: number;
  details?: string | null;
  table_origin?: string | null;
  origin_col?: string | null;
  target_col?: string | null;
  source_col?: string | null;
  aux_col?: string | null;
  canonical_col?: string | null;
  part_cols?: string | null;
  constraint?: string | null;
  constraint_operator?: string | null;
  threshold?: number | null;
  operator?: string | null;
  bins?: string | null;
  reference_date?: string | null;
  reference_date_col?: string | null;
};
export type SanityReport = {
  simulation_id: string;
  rows: SanityReportRow[];
};

export type RejectionSamplingTableStats = {
  generated: number;
  accepted: number;
  rejected: number;
  trimmed: number;
};
export type RejectionSamplingAttemptTableStats = {
  generated: number;
  accepted: number;
  rejected: number;
  trimmed: number;
};
export type RejectionSamplingAttempt = {
  attempt: number;
  multiplier: number;
  tables: Record<string, RejectionSamplingAttemptTableStats>;
  score: number;
  is_best: boolean;
  subject_draw?: Record<string, number> | null;
};
export type RejectionSamplingReport = {
  simulation_id: string;
  enabled: boolean;
  max_attempts: number;
  overgenerate_factor: number;
  attempts: number;
  sample_size?: number | null;
  partial_results: boolean;
  selection?: string | null;
  rules: string[];
  tables: Record<string, RejectionSamplingTableStats>;
  subject_targets?: Record<string, number>;
  child_targets?: Record<string, number>;
  all_targets?: Record<string, number>;
  fixed_tables?: string[];
  target_table?: string | null;
  target_rows?: number | null;
  attempt_history?: RejectionSamplingAttempt[];
};

export type EvaluationSummary = Schemas["EvaluationSummary"] & WithErrorMessage;
export type EvaluationJob = Schemas["EvaluationJob"];

export type TimeProfilingReport = Schemas["TimeProfilingReport"];
export type TimeProfilingPhase = Schemas["TimeProfilingPhase"];

export type ConfigScope = Schemas["ConfigScope"];
export type ConfigFile = Schemas["ConfigFile"];
export type ConfigContent = Schemas["ConfigContent"];
export type ConfigBulkResult = Schemas["ConfigBulkResult"];

export type PipelineConfigFile = Schemas["PipelineConfigFile"];
export type PipelineConfigContent = Schemas["PipelineConfigContent"];
export type PipelineConfigSnapshot = Schemas["PipelineConfigSnapshot"];

// ---- Frontend-only types and overlays --------------------------------------

// The encoding-type enum is consumed both as a value list (for a <select>)
// and as a type. The backend doesn't expose it as an enum schema, so the
// canonical list lives here; keep it in sync with the mostly_ai SDK.
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

// Spanish display labels for the MostlyAI encoding types. The enum values
// above are sent to the backend unchanged; these are only for the UI.
export const ENCODING_TYPE_LABELS: Record<string, string> = {
  AUTO: "Automático",
  TABULAR_CATEGORICAL: "Categórica",
  TABULAR_NUMERIC_AUTO: "Numérica (automática)",
  TABULAR_NUMERIC_DISCRETE: "Numérica discreta",
  TABULAR_NUMERIC_BINNED: "Numérica agrupada",
  TABULAR_NUMERIC_DIGIT: "Numérica por dígitos",
  TABULAR_CHARACTER: "Texto corto",
  TABULAR_DATETIME: "Fecha y hora",
  TABULAR_DATETIME_RELATIVE: "Fecha y hora relativa",
  TABULAR_LAT_LONG: "Latitud / longitud",
  LANGUAGE_TEXT: "Texto libre",
  LANGUAGE_CATEGORICAL: "Categórica (lenguaje)",
  LANGUAGE_NUMERIC: "Numérica (lenguaje)",
  LANGUAGE_DATETIME: "Fecha y hora (lenguaje)",
};

// Spanish description of each encoding type, for help/manual content.
export const ENCODING_TYPE_DESCRIPTIONS: Record<string, string> = {
  AUTO: "El sistema detecta el tipo de dato y elige automáticamente una codificación tabular (categórica, numérica o de fecha). Es el valor de partida de cada columna; los tipos de lenguaje y el resto se fijan a mano.",
  TABULAR_CATEGORICAL: "Conjunto cerrado de valores discretos (p. ej. servicio, sexo). El modelo respeta las categorías existentes.",
  TABULAR_NUMERIC_AUTO: "Fuerza que la columna sea un número tabular; el sistema solo elige entre las codificaciones numéricas (discreta, agrupada o por dígitos). A diferencia de «Automático», no reconsidera si en realidad es categoría o texto.",
  TABULAR_NUMERIC_DISCRETE: "Valores numéricos con un número limitado de valores distintos (p. ej. número de hijos).",
  TABULAR_NUMERIC_BINNED: "Valores numéricos agrupados en intervalos; suaviza distribuciones muy dispersas.",
  TABULAR_NUMERIC_DIGIT: "Modela el número dígito a dígito; útil para identificadores numéricos con formato fijo.",
  TABULAR_CHARACTER: "Texto corto con estructura fija, como códigos o matrículas.",
  TABULAR_DATETIME: "Marcas temporales absolutas; se preservan rangos y estacionalidad.",
  TABULAR_DATETIME_RELATIVE: "Solo para tablas enlazadas (secuencias): modela cada fecha como la diferencia respecto a la fecha anterior de la misma secuencia, no como una fecha absoluta.",
  TABULAR_LAT_LONG: "Pares de coordenadas geográficas (latitud y longitud).",
  LANGUAGE_TEXT: "Texto libre sin estructura fija, como observaciones o comentarios clínicos.",
  LANGUAGE_CATEGORICAL: "Categórica modelada con el motor de lenguaje, para categorías de texto complejas.",
  LANGUAGE_NUMERIC: "Valores numéricos modelados con el motor de lenguaje.",
  LANGUAGE_DATETIME: "Fechas modeladas con el motor de lenguaje.",
};

// UI-only: which editor mode the config drawer should render. Not part of
// the backend response (the backend infers format from the file extension).
export type ConfigEditorFormat = "yaml" | "json" | "python" | "toml";

// Per-table list of column names. Backend returns a free-form
// ``Dict[str, List[str]]`` so it's not in the schema as a named type.
export type SimulationColumns = Record<string, string[]>;
export type ModelColumns = Record<string, string[]>;

// /pipelines/ launch ack: backend returns the ``PipelineJob`` schema, which
// already has the right shape (`{pipeline_id, status}`). Keep the alias so
// existing call sites that import `PipelineLaunchAck` keep compiling.
export type PipelineLaunchAck = Schemas["PipelineJob"];

// /pipelines/ catalog rows. The backend's response_model leaves ``jobs`` and
// ``progress`` as untyped dicts (each pipeline run can hold any number of
// arbitrary job records), but the frontend reads typed fields off them. Keep
// a strict overlay here so call sites stay typed; the backend writes these
// fields, openapi-typescript just doesn't see them.
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

export type PipelineSummary = Omit<
  Schemas["PipelineSummary"],
  "jobs" | "progress"
> & {
  // Snapshots that ``PipelineTracker`` writes alongside the run (see
  // pipeline_card.json: ``configs.pipeline_config`` / ``configs.general_config``).
  // Older runs may omit it entirely.
  configs?: {
    pipeline_config?: string;
    general_config?: string;
  };
  jobs: PipelineJobRecord[];
  progress: JobProgress | null;
};

// ---- Purge ----
// Destructive operations that delete every folder in a resource (including
// completed runs). The global purge also resets configs from templates.
//
// Per-resource purges all return the same ``CleanupResult`` shape on the
// backend (see backend/src/api/schemas/{inspections,models,...}). They're
// distinct schemas in OpenAPI only because Pydantic qualifies same-named
// classes by module — pick one to alias.

export type PurgeResult =
  Schemas["backend__src__api__schemas__inspections__CleanupResult"];
export type PurgeAllResult = Schemas["PurgeAllResult"];

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

// One known problem that would make a training run fail (GET /models/training-preflight).
export type TrainingPreflightIssue = {
  id: string;
  title: string;
  guidance: string;
  tables: string[];
};

export async function getTrainingPreflight(
  inspectionId: string,
): Promise<TrainingPreflightIssue[]> {
  const { data } = await api.get<TrainingPreflightIssue[]>("/models/training-preflight", {
    params: { inspection_id: inspectionId },
  });
  return data;
}

export async function getSimulationColumns(simulationId: string): Promise<SimulationColumns> {
  const { data } = await api.get<SimulationColumns>(`/simulations/${simulationId}/columns`);
  return data;
}

export async function getModelColumns(modelId: string): Promise<ModelColumns> {
  const { data } = await api.get<ModelColumns>(`/models/${modelId}/columns`);
  return data;
}

export type ColumnKind = "numeric" | "datetime" | "categorical";
export type ModelColumnTypes = Record<string, Record<string, ColumnKind>>;

export async function getModelColumnTypes(
  modelId: string,
): Promise<ModelColumnTypes> {
  const { data } = await api.get<ModelColumnTypes>(
    `/models/${modelId}/columns/types`,
  );
  return data;
}

export async function getModelTrainingConfig(
  modelId: string,
): Promise<ModelTrainingConfig> {
  const { data } = await api.get<ModelTrainingConfig>(`/models/${modelId}/config`);
  return data;
}

export async function getModelKeyColumns(modelId: string): Promise<string[]> {
  const { data } = await api.get<string[]>(`/models/${modelId}/key-columns`);
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

export interface KillBgResult {
  killed_pids: number[];
  cancelled_simulations: string[];
}

export async function killBgProcesses(): Promise<KillBgResult> {
  const { data } = await api.post<KillBgResult>("/admin/kill-bg");
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

export async function getConfigSchemas(): Promise<Record<string, unknown>> {
  const { data } = await api.get<Record<string, unknown>>("/configs/schemas");
  return data;
}
