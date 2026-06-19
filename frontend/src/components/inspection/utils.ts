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
  if (type.includes("NUMERIC")) return "bg-blue-50/50 text-blue-900 border-blue-100/60";
  if (type.includes("CATEGORICAL")) return "bg-amber-50/50 text-amber-900 border-amber-100/60";
  if (type.includes("DATETIME")) return "bg-violet-50/50 text-violet-900 border-violet-100/60";
  if (type.includes("CHARACTER")) return "bg-emerald-50/50 text-emerald-900 border-emerald-100/60";
  return "bg-muted text-muted-foreground";
}
