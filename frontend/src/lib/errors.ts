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
