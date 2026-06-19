import { clsx, type ClassValue } from "clsx"
import { twMerge } from "tailwind-merge"

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs))
}

// Formats the YYYYMMDD_HHMMSS local timestamp the backend stamps on jobs into a
// readable Spanish long-form date, e.g. "21 may 2026, 14:30".
export function formatJobDate(ts: string | undefined | null): string {
  if (!ts) return "—"
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/.exec(ts)
  if (!m) return "—"
  const [, y, mo, d, h, mi, s] = m
  const date = new Date(+y, +mo - 1, +d, +h, +mi, +s)
  if (Number.isNaN(date.getTime())) return "—"
  return date.toLocaleString("es-ES", {
    day: "numeric",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  })
}

// Formats an elapsed time in seconds as compact "Hh Mm Ss" / "Mm Ss" / "Ns".
// Used in history tables and the time-profiling breakdown panel. Returns "—"
// for null/undefined/non-positive values so callers don't have to guard.
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null || !Number.isFinite(seconds) || seconds < 0) return "—"
  if (seconds < 1) return `${(seconds * 1000).toFixed(0)} ms`
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = seconds - h * 3600 - m * 60
  if (h > 0) return `${h}h ${m}m ${Math.round(s)}s`
  if (m > 0) return `${m}m ${Math.round(s)}s`
  return `${Math.round(s)}s`
}
