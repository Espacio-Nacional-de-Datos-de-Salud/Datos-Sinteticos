// localStorage keys used to remember the user's "current" pipeline artifact
// across page reloads and across the four pipeline pages.
//
// Keep all keys grouped here so it's obvious which pages read/write which
// values — and so renaming a key is a one-line change instead of a grep.
//
// Cross-page flow:
//   currentInspectionId   → /pipeline/inspeccion writes; /pipeline/entrenamiento reads
//   currentModelId        → /pipeline/entrenamiento writes; /pipeline/generacion reads
//   currentSimulationId   → /pipeline/generacion writes;  /pipeline/auditoria reads
//   currentEvaluationId   → /pipeline/auditoria writes
//
// /pipelines (the orchestrated runs page) writes all three of the trailing
// keys when the user opens a finished run, so navigating to a step page
// pre-selects the matching artifact.

export const STORAGE_KEYS = {
  inspection: "ends.pipeline.currentInspectionId",
  model: "ends.pipeline.currentModelId",
  simulation: "ends.pipeline.currentSimulationId",
  evaluation: "ends.pipeline.currentEvaluationId",
} as const;

export type StorageKey = (typeof STORAGE_KEYS)[keyof typeof STORAGE_KEYS];
