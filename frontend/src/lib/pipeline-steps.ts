// Single source of truth for the pipeline wizard steps.
//
// Sidebar, top breadcrumb, and bottom Anterior/Siguiente nav all read from
// this list. Adding or reordering a step is a one-line change here — the
// three places that consume it derive their behaviour from the shared
// order.

export type PipelineStep = {
  /** URL segment under /pipeline/ */
  slug: string;
  /** Display label shown in navigation */
  label: string;
  /** True if the step has a real implementation; false means stub/coming soon */
  implemented: boolean;
};

export const PIPELINE_STEPS: PipelineStep[] = [
  { slug: "inspeccion", label: "Carga de Datos", implemented: true },
  { slug: "configuracion", label: "Reglas de negocio", implemented: true },
  { slug: "entrenamiento", label: "Entrenamiento", implemented: true },
  { slug: "generacion", label: "Generación", implemented: true },
  { slug: "auditoria", label: "Auditoría", implemented: true },
];

export function stepHref(step: PipelineStep): string {
  return `/pipeline/${step.slug}`;
}

export function findStepBySlug(slug: string): PipelineStep | undefined {
  return PIPELINE_STEPS.find((s) => s.slug === slug);
}

export function findStepIndex(slug: string): number {
  return PIPELINE_STEPS.findIndex((s) => s.slug === slug);
}
