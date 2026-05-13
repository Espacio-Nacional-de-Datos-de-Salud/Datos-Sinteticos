// Tiny helpers shared across the run dialog and its artifact cards.

import { toast } from "sonner";

// The pipeline-run timestamp emitted by the backend is the engine's session
// stamp ``YYYYMMDD_HHMMSS`` — not ISO. ``new Date(...)`` returns Invalid Date
// for it, which is why "Iniciado" used to render blank. Parse it explicitly
// and fall back gracefully when the format is unfamiliar.
export function formatRunTimestamp(raw: string | undefined | null): string {
  if (!raw) return "—";
  const m = /^(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})$/.exec(raw);
  if (m) {
    const [, y, mo, d, h, mi, s] = m;
    const date = new Date(Number(y), Number(mo) - 1, Number(d), Number(h), Number(mi), Number(s));
    if (!Number.isNaN(date.getTime())) return date.toLocaleString();
  }
  const fallback = new Date(raw);
  return Number.isNaN(fallback.getTime()) ? raw : fallback.toLocaleString();
}

export async function copyToClipboard(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    toast.success("Copiado");
  } catch {
    toast.error("No se pudo copiar al portapapeles");
  }
}
