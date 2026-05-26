// Centralised error-message extractor.
//
// Pulls the most useful human-readable string out of an unknown error.
// Order of preference for axios errors:
//   1. response.data.detail              (FastAPI's standard error shape)
//   2. response.data.detail.message      (when detail is a structured object)
//   3. err.message                       (axios' own message)
// Falls back to Error.message, then a generic spanish string.

import axios from "axios";

export function extractDetail(err: unknown): string {
  if (axios.isAxiosError(err)) {
    const detail = (err.response?.data as { detail?: unknown } | undefined)
      ?.detail;
    if (typeof detail === "string") return detail;
    if (detail && typeof detail === "object" && "message" in detail) {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string") return message;
    }
    return err.message;
  }
  if (err instanceof Error) return err.message;
  return "Error desconocido";
}

export type DeleteConflict = {
  /** Human-readable explanation from the API. */
  message: string;
  /** IDs of the downstream artifacts blocking the delete. */
  linkedIds: string[];
};

// Detects the 409 a delete endpoint returns when the artifact still has
// downstream jobs. Returns null for any other error so callers can fall back
// to a plain toast.
export function extractDeleteConflict(err: unknown): DeleteConflict | null {
  if (!axios.isAxiosError(err) || err.response?.status !== 409) return null;
  const detail = (err.response?.data as { detail?: unknown } | undefined)?.detail;
  if (!detail || typeof detail !== "object") return null;

  const rawMessage = (detail as { message?: unknown }).message;
  const message =
    typeof rawMessage === "string"
      ? rawMessage
      : "El elemento tiene dependencias asociadas.";

  const linkedIds: string[] = [];
  for (const [key, value] of Object.entries(detail)) {
    if (key.startsWith("linked_") && Array.isArray(value)) {
      linkedIds.push(...value.map(String));
    }
  }
  return { message, linkedIds };
}
