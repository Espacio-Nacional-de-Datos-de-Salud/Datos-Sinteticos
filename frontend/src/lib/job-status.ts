// Maps a backend job status string to a shadcn <Badge> variant.
// Used by every pipeline page (inspeccion, entrenamiento, generacion,
// auditoria) and the JobProgress component.

export type BadgeVariant = "default" | "secondary" | "outline" | "destructive";

export function statusBadgeVariant(status: string): BadgeVariant {
  if (status === "completed") return "default";
  if (status === "in_progress") return "secondary";
  if (status === "failed" || status === "cancelled") return "destructive";
  return "outline";
}
