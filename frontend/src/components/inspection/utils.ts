// Shared helpers for the inspection page widgets. Lifted out of the page file
// so each card can live in its own module without dragging private helpers
// along.

import type { Autodetect } from "@/lib/api";

// Same shape we feed every editor card: a useQuery slice narrowed to the
// fields the editor actually reads. Keeps the prop type honest without
// importing TanStack types into every module.
export type AutodetectQuery = {
  data: Autodetect | undefined;
  isLoading: boolean;
  isError: boolean;
};

export function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
}

// Color-code the MostlyAI encoding labels so related types are visually
// grouped. Purely presentational — kept here, not in api.ts.
export function typeBadgeClass(type: string): string {
  if (type.includes("NUMERIC")) return "bg-blue-100 text-blue-800 border-blue-200";
  if (type.includes("CATEGORICAL")) return "bg-amber-100 text-amber-800 border-amber-200";
  if (type.includes("DATETIME")) return "bg-violet-100 text-violet-800 border-violet-200";
  if (type.includes("CHARACTER")) return "bg-emerald-100 text-emerald-800 border-emerald-200";
  return "bg-muted text-muted-foreground";
}

// Local SELECT_CLASS — the one in lib/ui.ts targets full-width inputs; the
// autodetect editor uses tighter mono-styled selects inside table cells.
export const SELECT_CLASS =
  "rounded-md border bg-background px-2 py-1 font-mono text-xs focus:outline-none focus:ring-1 focus:ring-ring";
