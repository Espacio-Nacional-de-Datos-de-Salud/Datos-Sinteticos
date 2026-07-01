// Per-config field metadata. Drives <ConfigDrawer> form rendering.
//
// SOURCE OF TRUTH: backend/src/config/field_schemas.py
// These types map 1-to-1 to the Python dataclasses in that module.
// Schemas are fetched at runtime via GET /configs/schemas so the frontend
// never needs to be updated when fields are added or renamed in the backend.
//
// Use the `useConfigSchemas()` hook in React components instead of importing
// the (now removed) CONFIG_SCHEMAS constant directly.

import { useQuery } from "@tanstack/react-query";
import { getConfigSchemas } from "@/lib/api";

export type FieldKind = "boolean" | "number" | "text" | "select" | "list" | "json" | "checklist";

export type SelectOption = {
  value: string;
  label: string;
  // Optional per-option YAML path override (checklist only). Lets one checklist
  // mix options stored under different config keys; when absent the option uses
  // its FieldSchema's `path`. Mirrors FieldOption.path in field_schemas.py.
  path?: string | null;
};

export type FieldSchema = {
  // Dotted path inside the parsed YAML, e.g. "settings.default_csv_delimiter".
  path: string;
  label: string;
  help?: string;
  kind: FieldKind;
  // Used only when kind === "select".
  options?: SelectOption[];
  // When set, options are populated dynamically from the current context (e.g. simulation).
  dynamicOptions?: "tables" | "columns";
  // When true, an empty string in the form maps to YAML null.
  nullable?: boolean;
  // Minimum allowed value; only meaningful for kind === "number". Inputs below
  // this are clamped up to it.
  min?: number | null;
  // Model settings that can be overridden for a single table via
  // model_settings.per_table.<table>; drives the guided per-table UI.
  perTable?: boolean;
  // Optional sub-heading within a group. Consecutive fields sharing the same
  // subgroup render under one heading, mirroring the manual's organisation.
  subgroup?: string;
};

// Optional on/off toggle for an entire group. When off, the whole `path`
// (typically a nested object key in the YAML) is removed from the draft;
// when on, it is inserted with `defaults`. Lets us model conditional blocks
// like `model_settings.differential_privacy` that should be absent unless
// explicitly enabled.
export type GroupToggle = {
  path: string;
  label: string;
  help?: string;
  defaults: Record<string, unknown>;
};

export type FieldGroup = {
  title: string;
  description?: string;
  fields: FieldSchema[];
  toggle?: GroupToggle;
};

export type ConfigSchema = {
  title: string;
  description: string;
  groups: FieldGroup[];
};


/**
 * Fetch all config field schemas from the backend.
 * Replaces the former CONFIG_SCHEMAS constant — the backend is now
 * the single source of truth (backend/src/config/field_schemas.py).
 */
export function useConfigSchemas(): {
  schemas: Record<string, ConfigSchema>;
  isLoading: boolean;
} {
  const query = useQuery({
    queryKey: ["config-schemas"],
    queryFn: getConfigSchemas,
    staleTime: Infinity, // schemas change only on deploy
  });
  return {
    schemas: (query.data as Record<string, ConfigSchema>) ?? {},
    isLoading: query.isLoading,
  };
}
