// Client for the rule library (presets) backend API.
//
// A rule preset is a user-saved snapshot of rules.yaml kept for reuse,
// independent of any BRC run. The Reglas de negocio page saves the current
// rule set here and lets the user load any preset back into the live editor.
// See backend/src/sessions/rule_presets.py.

import { api } from "./api";

export type RulePresetSummary = {
  preset_id: string;
  preset_name: string;
  timestamp: string;
  timestamp_ms: number | null;
  rules_count: number;
  // Column deletions (rules_excluded_columns) bundled with the rule set.
  excluded_columns: Record<string, string[]>;
};

const BASE = "/rule-presets";

export async function listRulePresets(): Promise<RulePresetSummary[]> {
  const { data } = await api.get<RulePresetSummary[]>(`${BASE}/`);
  return data;
}

export async function saveRulePreset(
  content: string,
  name?: string | null,
  excludedColumns?: Record<string, string[]>,
): Promise<RulePresetSummary> {
  const { data } = await api.post<RulePresetSummary>(`${BASE}/`, {
    content,
    ...(name ? { name } : {}),
    ...(excludedColumns ? { excluded_columns: excludedColumns } : {}),
  });
  return data;
}

export async function getRulePresetRules(presetId: string): Promise<string> {
  const { data } = await api.get<string>(`${BASE}/${presetId}/rules`, {
    transformResponse: (raw) => raw,
  });
  return data;
}

export async function renameRulePreset(
  presetId: string,
  name: string,
): Promise<RulePresetSummary> {
  const { data } = await api.patch<RulePresetSummary>(`${BASE}/${presetId}/name`, {
    name,
  });
  return data;
}

export async function deleteRulePreset(presetId: string): Promise<void> {
  await api.delete(`${BASE}/${presetId}`);
}
