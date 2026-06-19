// Client for the business-rules-configurations (BRC) backend API.
//
// A BRC run is a snapshot of the rules YAML applied (PRE phase) on top of
// an upload's preprocessed parquet. Each run lives in its own folder so
// the user can keep a history of attempts per upload and the original
// upload parquet is never mutated. See backend/src/sessions/business_rules_configurations.py.
//
// Types are hand-typed here rather than pulled from api-types.ts so the
// generated OpenAPI types can be refreshed independently — once the
// OpenAPI snapshot is regenerated, replace these with `Schemas["BRCSummary"]`
// etc. and drop this file.

import { api, type FilePreview, type JobProgress } from "./api";

export type BRCStatus =
  | "in_progress"
  | "completed"
  | "failed"
  | "cancelled"
  | string;

// Advisory raised while loading or applying a rule during the BRC run
// (e.g. a date-only constraint against a datetime column, or a rule that
// was skipped because its YAML entry is invalid).
export type BRCRuleWarning = {
  rule?: string | null;
  table?: string | null;
  column?: string | null;
  constraint?: string | null;
  message: string;
};

export type BRCSummary = {
  brc_id: string;
  brc_name: string;
  inspection_id: string;
  status: BRCStatus;
  timestamp: string;
  timestamp_ms: number | null;
  tables: Record<string, number>;
  new_columns: Record<string, string[]>;
  excluded_columns: Record<string, string[]>;
  // Reglas-de-negocio column deletions for this run, kept separate from the
  // `excluded_columns` union so they can be reloaded as a rule set.
  rules_excluded_columns?: Record<string, string[]>;
  rules_count: number;
  warnings?: BRCRuleWarning[];
  progress: JobProgress | null;
  duration_seconds: number | null;
  started_at_ms: number | null;
  error_message?: string | null;
};

export type BRCCreateRequest = {
  inspection_id: string;
  name?: string | null;
  rules_config_path?: string | null;
  enable_profiling?: boolean;
};

export type BRCJob = { brc_id: string };

export type BRCProfilingReport = { table: string; filename: string };
export type BRCProfilingReports = {
  brc_id: string;
  reports: BRCProfilingReport[];
};

// Visible rule count = logical/derived rules + post-BRC column drops. Used
// everywhere a BRC summary is shown so the count matches the rows in the
// rules banner (which renders both as entries).
export function totalRuleCount(brc: Pick<BRCSummary, "rules_count" | "excluded_columns">): number {
  const dropped = Object.values(brc.excluded_columns ?? {}).reduce(
    (n, cs) => n + cs.length,
    0,
  );
  return (brc.rules_count ?? 0) + dropped;
}

const BASE = "/business-rules-configurations";

export async function listBrcs(inspectionId?: string): Promise<BRCSummary[]> {
  const { data } = await api.get<BRCSummary[]>(`${BASE}/`, {
    params: inspectionId ? { inspection_id: inspectionId } : undefined,
  });
  return data;
}

export async function getBrc(brcId: string): Promise<BRCSummary> {
  const { data } = await api.get<BRCSummary>(`${BASE}/${brcId}`);
  return data;
}

export async function createBrc(request: BRCCreateRequest): Promise<BRCJob> {
  const { data } = await api.post<BRCJob>(`${BASE}/`, request);
  return data;
}

export async function renameBrc(
  brcId: string,
  name: string,
): Promise<BRCSummary> {
  const { data } = await api.patch<BRCSummary>(`${BASE}/${brcId}/name`, {
    name,
  });
  return data;
}

export async function deleteBrc(brcId: string): Promise<void> {
  await api.delete(`${BASE}/${brcId}`);
}

export async function getBrcRulesSnapshot(brcId: string): Promise<string> {
  const { data } = await api.get<string>(`${BASE}/${brcId}/rules-snapshot`, {
    transformResponse: (raw) => raw,
  });
  return data;
}

export async function getBrcNewColumns(
  brcId: string,
): Promise<Record<string, string[]>> {
  const { data } = await api.get<Record<string, string[]>>(
    `${BASE}/${brcId}/new-columns`,
  );
  return data;
}

export async function getBrcPreview(
  brcId: string,
  params: {
    sample_rows?: number;
    offset?: number;
    only_new_columns?: boolean;
    include_total?: boolean;
  } = {},
): Promise<FilePreview[]> {
  const { data } = await api.get<FilePreview[]>(`${BASE}/${brcId}/preview`, {
    params,
  });
  return data;
}

export async function getBrcProfiling(
  brcId: string,
): Promise<BRCProfilingReports> {
  const { data } = await api.get<BRCProfilingReports>(
    `${BASE}/${brcId}/profiling`,
  );
  return data;
}

export function brcProfilingReportUrl(brcId: string, table: string): string {
  return `${api.defaults.baseURL ?? ""}${BASE}/${brcId}/profiling/${encodeURIComponent(table)}`;
}

export function brcDownloadFolderUrl(brcId: string): string {
  return `${api.defaults.baseURL ?? ""}${BASE}/${brcId}/download`;
}

export function brcDownloadDatasetUrl(brcId: string): string {
  return `${api.defaults.baseURL ?? ""}${BASE}/${brcId}/download/dataset`;
}

export function brcDownloadProfilingUrl(brcId: string): string {
  return `${api.defaults.baseURL ?? ""}${BASE}/${brcId}/download/profiling`;
}
