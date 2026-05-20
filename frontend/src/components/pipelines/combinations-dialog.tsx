// Top-level "Generar combinaciones" dialog.
//
// Mental model the engineer is working with:
//   1. Pick a contiguous chain of steps to run (train → simulate → evaluate, in
//      any contiguous subrange). Each chain has a *head* — the first step —
//      whose input has to come from somewhere external (raw files / a saved
//      inspection / a trained model / a stored simulation). Subsequent steps
//      auto-bind to the previous step's output.
//   2. Decide what to vary across the generated jobs. Anything pickable can
//      either be a single shared value (one combo) or a list of values (one
//      combo per value, multiplied with every other axis). The dialog exposes
//      this as one editor per parameter — give it 1 value and you've defined a
//      shared input; give it more and it becomes an axis of variation.
//   3. Optionally add extra override axes (max_epochs, model presets, …) the
//      same way the existing variant dialog does.
//
// The dialog stays a pure renderer: it emits Job[] + an apply mode through
// `onApply`. Splicing into the doc is the page's job.

"use client";

import { useEffect, useMemo, useState } from "react";
import { Layers, Plus, X, Check } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SELECT_CLASS } from "@/lib/ui";
import { cn } from "@/lib/utils";

import {
  AxisValuesEditor,
  type AxisCatalogues,
} from "./axis-value-editor";
import {
  AXIS_LABELS,
  type Axis,
  type AxisField,
  type AxisValue,
  expandGrid,
  gridSize,
  isAxisApplicable,
} from "./expansion";
import {
  EMPTY_CONDITIONAL_CONFIG,
  EMPTY_JOB,
  EMPTY_OVERRIDES,
  type Job,
  type SyntheticDataFileFormat,
} from "./types";

export type ApplyMode = "replace" | "insertAfter";

type StepKey = "train" | "simulate" | "evaluate";
const STEP_ORDER: StepKey[] = ["train", "simulate", "evaluate"];
const STEP_LABEL: Record<StepKey, string> = {
  train: "Entrenar",
  simulate: "Generar",
  evaluate: "Evaluar",
};

// Source of the train head: either raw files or a saved inspection. The
// backend treats them as mutually exclusive on the YAML side, so the picker
// has to pick one or the other.
type TrainSource = "files" | "inspection";

export function CombinationsDialog({
  open,
  jobs,
  catalogues,
  onClose,
  onApply,
}: {
  open: boolean;
  jobs: Job[];
  catalogues: AxisCatalogues;
  onClose: () => void;
  onApply: (input: {
    baseIndex: number;
    generated: Job[];
    mode: ApplyMode;
  }) => void;
}) {
  const [steps, setSteps] = useState<Record<StepKey, boolean>>({
    train: true,
    simulate: true,
    evaluate: true,
  });

  // Train-head source toggle — only meaningful when train is the head step.
  const [trainSource, setTrainSource] = useState<TrainSource>("files");

  // Head-step input values as a multi-value list. 1 value = shared input
  // (single combo); 2+ values = head axis (one combo per value, multiplied
  // with the user-defined override axes below). Stored as AxisValue so we
  // can hand them straight to expandGrid.
  const [headValues, setHeadValues] = useState<AxisValue[]>([]);

  // Shared simulate-step inputs. These are single values rather than axes —
  // the user can already vary them via the override-axis section if they
  // want to (sample_size is in the AxisField vocabulary already).
  const [sampleSize, setSampleSize] = useState<number>(1000);
  const [format, setFormat] = useState<SyntheticDataFileFormat>("csv");

  const [extraAxes, setExtraAxes] = useState<Axis[]>([]);

  // Active-steps form a contiguous range or the chain is invalid. Compute
  // bounds + contiguity once for use across validation, head detection, and
  // axis applicability.
  const { headStep, contiguous, anyActive } = useMemo(() => {
    const indices = STEP_ORDER.map((s, i) => (steps[s] ? i : -1)).filter(
      (i) => i >= 0,
    );
    if (indices.length === 0) {
      return { headStep: null as StepKey | null, contiguous: false, anyActive: false };
    }
    const min = indices[0];
    const max = indices[indices.length - 1];
    const isContig = max - min + 1 === indices.length;
    return {
      headStep: STEP_ORDER[min],
      contiguous: isContig,
      anyActive: true,
    };
  }, [steps]);

  // Reset head-input whenever the head step (or its source flavour) changes —
  // values authored for one head shape don't carry meaning under another.
  useEffect(() => {
    setHeadValues([]);
  }, [headStep, trainSource]);

  // Field that the head input axis maps to. Drives both the value editor's
  // "kind" and the apply-time job mutation.
  const headAxisField: AxisField | null = useMemo(() => {
    if (headStep === "train") {
      return trainSource === "files" ? "train_files" : "train_inspection_id";
    }
    if (headStep === "simulate") return "simulate_model_id";
    if (headStep === "evaluate") return "evaluate_simulation_id";
    return null;
  }, [headStep, trainSource]);

  // Build the synthetic base job from the active-step set + shared simulate
  // inputs. Subsequent steps deliberately leave their bound IDs empty so the
  // executor's auto-bind path takes over (see project_evaluate_real_data_autobind).
  const baseJob: Job = useMemo(
    () => buildBase(steps, { sampleSize, format }),
    [steps, sampleSize, format],
  );

  // Materialise the axes we'll feed to expandGrid: head axis (if it has any
  // values) plus every user-defined override axis.
  const effectiveAxes: Axis[] = useMemo(() => {
    const out: Axis[] = [];
    if (headAxisField && headValues.length > 0) {
      out.push({ field: headAxisField, values: headValues });
    }
    for (const a of extraAxes) out.push(a);
    return out;
  }, [headAxisField, headValues, extraAxes]);

  const totalJobs = gridSize(effectiveAxes);
  const previewNames = useMemo(() => {
    if (effectiveAxes.length === 0) return [];
    return expandGrid(baseJob, effectiveAxes).slice(0, 4).map((j) => j.name);
  }, [baseJob, effectiveAxes]);

  if (!open) return null;

  const toggleStep = (key: StepKey) =>
    setSteps((cur) => ({ ...cur, [key]: !cur[key] }));

  const updateExtraAxis = (idx: number, patch: Partial<Axis>) => {
    setExtraAxes((cur) => cur.map((a, i) => (i === idx ? { ...a, ...patch } : a)));
  };
  const removeExtraAxis = (idx: number) => {
    setExtraAxes((cur) => cur.filter((_, i) => i !== idx));
  };
  const addExtraAxis = () => {
    // Hide head-input fields from the override-axis picker — they're already
    // first-class above and authoring them in two places is just confusing.
    const used = new Set(extraAxes.map((a) => a.field));
    const candidate = (Object.keys(AXIS_LABELS) as AxisField[]).find(
      (f) =>
        !used.has(f)
        && f !== headAxisField
        && !HEAD_AXIS_FIELDS.has(f)
        && isAxisApplicable(f, baseJob),
    );
    if (!candidate) return;
    setExtraAxes((cur) => [...cur, { field: candidate, values: [] }]);
  };

  // The chain is "ready" when contiguous, has at least one step, and the head
  // has at least one input value (either shared or as an axis). expandGrid
  // returns [] when no axis carries values — that's also enforced by the
  // disabled state below to keep the error messaging actionable.
  const headReady = headValues.length > 0;
  const ready = anyActive && contiguous && headReady;

  const apply = () => {
    if (!ready) return;
    const generated = expandGrid(baseJob, effectiveAxes);
    if (generated.length === 0) return;
    onApply({
      baseIndex: jobs.length - 1,
      generated,
      mode: "insertAfter",
    });
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg border border-border bg-card shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <Layers className="h-5 w-5 text-[#00215C]" />
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                Generador de combinaciones
              </div>
              <h3 className="text-lg font-semibold tracking-tight">
                Cadena de pasos × ejes de variación
              </h3>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 overflow-y-auto p-6">
          <div className="space-y-5">
            {/* Step toggles. Contiguity validation surfaces below — the
                chain has to be a single connected run because non-head steps
                consume the previous step's output, not an unrelated artefact
                pulled from another job. */}
            <section className="space-y-2">
              <Label className="text-xs">Pasos en la cadena</Label>
              <div className="flex gap-2">
                {STEP_ORDER.map((key) => {
                  const active = steps[key];
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => toggleStep(key)}
                      className={cn(
                        "flex flex-1 items-center justify-center gap-2 rounded-md border px-3 py-2 text-xs font-semibold transition-colors",
                        active
                          ? "border-[#00215C] bg-[#00215C] text-white"
                          : "border-border bg-background text-muted-foreground hover:bg-accent/40",
                      )}
                    >
                      {active ? (
                        <Check className="h-3.5 w-3.5" />
                      ) : (
                        <div className="h-3.5 w-3.5 rounded-[3px] border border-muted-foreground/50" />
                      )}
                      {STEP_LABEL[key]}
                    </button>
                  );
                })}
              </div>
              {!anyActive && (
                <p className="text-[11px] text-amber-600">
                  Selecciona al menos un paso.
                </p>
              )}
              {anyActive && !contiguous && (
                <p className="text-[11px] text-amber-600">
                  Los pasos deben ser contiguos: cada paso reutiliza el
                  resultado del anterior.
                </p>
              )}
            </section>

            {/* Head-step input. Doubles as both the "shared input" (1 value)
                and the head axis (2+ values) — same editor either way. */}
            {anyActive && contiguous && headStep && (
              <section className="space-y-3 rounded-md border border-border bg-muted/10 p-4">
                <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                  Entrada del primer paso ({STEP_LABEL[headStep]})
                </div>

                {headStep === "train" && (
                  <div className="flex gap-2 text-[11px]">
                    {(["files", "inspection"] as const).map((src) => (
                      <button
                        key={src}
                        type="button"
                        onClick={() => setTrainSource(src)}
                        className={cn(
                          "rounded-md border px-2.5 py-1 font-semibold transition-colors",
                          trainSource === src
                            ? "border-[#00215C] bg-[#00215C] text-white"
                            : "border-border bg-background text-muted-foreground hover:bg-accent/40",
                        )}
                      >
                        {src === "files" ? "Desde archivos" : "Desde inspección"}
                      </button>
                    ))}
                  </div>
                )}

                {headAxisField && (
                  <div className="space-y-1.5">
                    <Label className="text-xs">
                      {headValueHint(headAxisField, headValues.length)}
                    </Label>
                    <AxisValuesEditor
                      field={headAxisField}
                      values={headValues}
                      onChange={setHeadValues}
                      catalogues={catalogues}
                    />
                  </div>
                )}

                {headStep === "evaluate" && (
                  <p className="text-[11px] text-muted-foreground">
                    Los datos reales para evaluar se infieren de la inspección
                    asociada al modelo — no es necesario seleccionarlos.
                  </p>
                )}
              </section>
            )}

            {/* Shared simulate inputs. Always single values; vary them via the
                "Otros ejes" section if you need a sweep. Hidden when simulate
                isn't part of the chain. */}
            {anyActive && contiguous && steps.simulate && (
              <section className="space-y-3 rounded-md border border-border bg-muted/10 p-4">
                <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                  Configuración de generación
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <Label className="text-xs">Tamaño de muestra</Label>
                    <Input
                      type="number"
                      min={1}
                      value={sampleSize}
                      onChange={(e) => setSampleSize(Number(e.target.value || 0))}
                    />
                  </div>
                  <div className="space-y-1">
                    <Label className="text-xs">Formato de salida</Label>
                    <select
                      className={SELECT_CLASS}
                      value={format}
                      onChange={(e) =>
                        setFormat(e.target.value as SyntheticDataFileFormat)
                      }
                    >
                      <option value="csv">csv</option>
                      <option value="parquet">parquet</option>
                    </select>
                  </div>
                </div>
              </section>
            )}

            <section className="space-y-3">
              <div className="flex items-center justify-between">
                <Label className="text-xs">Otros ejes (opcional)</Label>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={addExtraAxis}
                  disabled={!anyActive || !contiguous}
                >
                  <Plus className="mr-1 h-3 w-3" /> Añadir eje
                </Button>
              </div>

              {extraAxes.length === 0 && (
                <div className="rounded border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">
                  Ejes de overrides (p. ej. <code>max_epochs</code> ∈ {"{"}10,
                  20, 30{"}"}). Multiplican con los valores del primer paso.
                </div>
              )}

              <div className="space-y-3">
                {extraAxes.map((axis, idx) => (
                  <AxisRow
                    key={idx}
                    axis={axis}
                    baseJob={baseJob}
                    forbidden={
                      new Set<AxisField>([
                        ...extraAxes
                          .filter((_, i) => i !== idx)
                          .map((a) => a.field),
                        ...(headAxisField ? [headAxisField] : []),
                        ...HEAD_AXIS_FIELDS,
                      ])
                    }
                    catalogues={catalogues}
                    onChange={(patch) => updateExtraAxis(idx, patch)}
                    onRemove={() => removeExtraAxis(idx)}
                  />
                ))}
              </div>
            </section>

            <section className="rounded-md border border-border bg-muted/20 p-4">
              <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                Previsualización
              </div>
              <div className="mt-1 text-sm font-semibold">
                {totalJobs > 0
                  ? `Se generarán ${totalJobs} jobs`
                  : "Aún no hay valores suficientes"}
                {totalJobs > 0 && effectiveAxes.length > 1 && (
                  <span className="ml-2 text-xs font-normal text-muted-foreground">
                    ({effectiveAxes
                      .filter((a) => a.values.length > 0)
                      .map((a) => a.values.length)
                      .join(" × ")}
                    )
                  </span>
                )}
              </div>
              {previewNames.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {previewNames.map((n, i) => (
                    <li
                      key={i}
                      className="truncate font-mono text-[11px] text-muted-foreground"
                    >
                      • {n}
                    </li>
                  ))}
                  {totalJobs > previewNames.length && (
                    <li className="text-[11px] text-muted-foreground">
                      … y {totalJobs - previewNames.length} más
                    </li>
                  )}
                </ul>
              )}
            </section>
          </div>
        </div>

        <footer className="flex justify-end gap-2 border-t border-border bg-muted/20 px-6 py-4">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cancelar
          </Button>
          <Button
            type="button"
            size="sm"
            onClick={apply}
            disabled={!ready || totalJobs === 0}
          >
            <Layers className="mr-1 h-3.5 w-3.5" /> Generar {totalJobs > 0 ? totalJobs : ""}
          </Button>
        </footer>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Set of AxisFields that play the "head input" role for some chain shape.
// Override-axis pickers must hide them all to avoid double-authoring.
const HEAD_AXIS_FIELDS = new Set<AxisField>([
  "train_files",
  "train_inspection_id",
  "simulate_model_id",
  "evaluate_simulation_id",
]);

function headValueHint(field: AxisField, count: number): string {
  const single = AXIS_LABELS[field];
  if (count <= 1) return `${single} (1 valor = compartido en todos los jobs)`;
  return `${single} — ${count} valores · será un eje de variación`;
}

// Build an empty-but-shaped base job from the active-step set. Non-head bound
// IDs (simulate.model_id / evaluate.simulation_id) stay empty: the executor
// auto-binds them from the previous step's output, and the head input is
// applied per-combo by expandGrid.
function buildBase(
  steps: Record<StepKey, boolean>,
  shared: { sampleSize: number; format: SyntheticDataFileFormat },
): Job {
  const job: Job = {
    ...EMPTY_JOB,
    overrides: { ...EMPTY_OVERRIDES },
    name: "combo",
    train: null,
    simulate: null,
    evaluate: null,
  };
  if (steps.train) {
    job.train = { files: [], inspection_id: "" };
  }
  if (steps.simulate) {
    job.simulate = {
      sample_size: shared.sampleSize,
      model_id: "",
      synthetic_data_file_format: shared.format,
      conditional: { ...EMPTY_CONDITIONAL_CONFIG },
    };
  }
  if (steps.evaluate) {
    job.evaluate = {
      simulation_id: "",
      model_id: "",
    };
  }
  return job;
}

function AxisRow({
  axis,
  baseJob,
  forbidden,
  catalogues,
  onChange,
  onRemove,
}: {
  axis: Axis;
  baseJob: Job;
  forbidden: Set<AxisField>;
  catalogues: AxisCatalogues;
  onChange: (patch: Partial<Axis>) => void;
  onRemove: () => void;
}) {
  // Available fields: applicable to the base + not already used and not the
  // head's territory (kept selectable for the row's own current field even if
  // it falls into either bucket, so the dropdown doesn't go empty when the
  // user lands on an edge-case combination).
  const fieldOptions = (Object.keys(AXIS_LABELS) as AxisField[]).filter(
    (f) =>
      isAxisApplicable(f, baseJob)
      && (f === axis.field || !forbidden.has(f)),
  );

  return (
    <div className="space-y-2 rounded-md border border-border bg-background p-3">
      <div className="flex items-center gap-2">
        <select
          className={SELECT_CLASS}
          value={axis.field}
          onChange={(e) =>
            onChange({ field: e.target.value as AxisField, values: [] })
          }
        >
          {fieldOptions.map((f) => (
            <option key={f} value={f}>
              {AXIS_LABELS[f]}
            </option>
          ))}
        </select>
        <button
          type="button"
          aria-label="Quitar eje"
          onClick={onRemove}
          className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-red-600"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <AxisValuesEditor
        field={axis.field}
        values={axis.values}
        onChange={(values) => onChange({ values })}
        catalogues={catalogues}
      />
    </div>
  );
}
