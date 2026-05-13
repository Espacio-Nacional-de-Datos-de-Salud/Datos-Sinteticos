"use client";

// One job in the pipeline designer. The header carries job_N + name input
// and per-job actions (expand-as-variants, remove); the body shows the three
// step toggles (train / simulate / evaluate) plus the collapsible overrides
// editor. All edits stream up via `onChange(patch)` — JobCard is a pure view.

import { useState } from "react";
import { Copy, SlidersHorizontal, Settings, Trash2 } from "lucide-react";

import {
  ConditionalGenerationDrawer,
  EMPTY_CONDITIONAL_CONFIG,
  isConditionalConfigActive,
} from "@/components/generation/conditional-config";
import { ConfigDrawer } from "@/components/config/config-drawer";
import { FilesMultiSelect, InspectionSelect } from "@/components/pipelines/form-widgets";
import { OverridesBlock } from "@/components/pipelines/overrides-block";
import { StepBlock } from "@/components/pipelines/step-block";
import type {
  Job,
  JobOverrides,
  SyntheticDataFileFormat,
} from "@/components/pipelines/types";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type {
  ConfigFile,
  DataFile,
  InspectionSummary,
  ModelSummary,
  SimulationSummary,
} from "@/lib/api";
import { SELECT_CLASS } from "@/lib/ui";
import { cn } from "@/lib/utils";

export function JobCard({
  index,
  job,
  files,
  models,
  simulations,
  inspections,
  rulesConfigs,
  onChange,
  onRemove,
  onEditRules,
  onExpand,
}: {
  index: number;
  job: Job;
  files: DataFile[];
  models: ModelSummary[];
  simulations: SimulationSummary[];
  inspections: InspectionSummary[];
  rulesConfigs: ConfigFile[];
  onChange: (patch: Partial<Job>) => void;
  onRemove: () => void;
  onEditRules: (id: string) => void;
  onExpand: () => void;
}) {
  const [conditionalOpen, setConditionalOpen] = useState(false);
  const [evaluationConfigOpen, setEvaluationConfigOpen] = useState(false);
  const setOverride = <K extends keyof JobOverrides>(key: K, val: JobOverrides[K]) => {
    onChange({ overrides: { ...job.overrides, [key]: val } });
  };
  const overrideCount = Object.values(job.overrides).filter((v) => v !== "").length;
  const toggleStep = (key: "train" | "simulate" | "evaluate") => {
    if (key === "train") {
      onChange({
        train: job.train ? null : { files: [], inspection_id: "" },
      });
    } else if (key === "simulate") {
      onChange({
        simulate: job.simulate
          ? null
          : {
            sample_size: 1000,
            model_id: "",
            synthetic_data_file_format: "csv",
            conditional: { ...EMPTY_CONDITIONAL_CONFIG },
          },
      });
    } else {
      onChange({
        evaluate: job.evaluate
          ? null
          : { real_data: [], simulation_id: "", model_id: "" },
      });
    }
  };

  return (
    <div className="overflow-hidden rounded-md border border-border bg-card">
      <header className="flex items-center justify-between gap-3 border-b border-border bg-[#00215C] px-4 py-2.5 text-white">
        <div className="flex items-center gap-2.5">
          <span className="rounded bg-white/15 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide">
            Job {index + 1}
          </span>
          <Input
            value={job.name}
            onChange={(e) => onChange({ name: e.target.value })}
            className="h-7 w-56 border-white/30 bg-white/10 text-white placeholder:text-white/50 focus-visible:border-white"
            placeholder="nombre_del_job"
          />
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            aria-label="Expandir job en variantes"
            title="Expandir en variantes"
            onClick={onExpand}
            className="rounded p-1 text-white/70 hover:bg-white/10 hover:text-white"
          >
            <Copy className="h-3.5 w-3.5" />
          </button>
          <button
            type="button"
            aria-label="Eliminar job"
            onClick={onRemove}
            className="rounded p-1 text-white/70 hover:bg-white/10 hover:text-white"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      </header>

      <div className="space-y-3 p-4">
        {/* Step toggles — three buttons that mirror what /ENDS users actually
            think about: do I want to train, simulate, evaluate? */}
        <div className="flex gap-2">
          {(["train", "simulate", "evaluate"] as const).map((key) => {
            const active = !!job[key];
            return (
              <button
                key={key}
                type="button"
                onClick={() => toggleStep(key)}
                className={cn(
                  "flex-1 rounded-md border px-3 py-2 text-xs font-semibold transition-colors",
                  active
                    ? "border-[#00215C] bg-[#00215C] text-white"
                    : "border-border bg-background text-muted-foreground hover:bg-accent/40",
                )}
              >
                {key === "train" ? "Entrenar" : key === "simulate" ? "Generar" : "Evaluar"}
              </button>
            );
          })}
        </div>

        {job.train && (
          <StepBlock title="Entrenamiento">
            {/* Train can resume from a previously produced inspection (handy
                if the user manually edited relationships / encoding types on
                that inspection) or train from raw files. The two are mutually
                exclusive — switching modes resets the other side. */}
            <div className="flex gap-2 text-[11px]">
              {(["files", "inspection"] as const).map((src) => {
                const active = src === "inspection"
                  ? !!job.train!.inspection_id
                  : !job.train!.inspection_id;
                return (
                  <button
                    key={src}
                    type="button"
                    onClick={() =>
                      onChange({
                        train:
                          src === "inspection"
                            ? { files: [], inspection_id: job.train!.inspection_id || "" }
                            : { files: job.train!.files, inspection_id: "" },
                      })
                    }
                    className={cn(
                      "rounded-md border px-2.5 py-1 font-semibold transition-colors",
                      active
                        ? "border-[#00215C] bg-[#00215C] text-white"
                        : "border-border bg-background text-muted-foreground hover:bg-accent/40",
                    )}
                  >
                    {src === "files" ? "Desde archivos" : "Desde inspección"}
                  </button>
                );
              })}
            </div>
            {!job.train.inspection_id ? (
              <>
                <Label className="text-xs">Archivos de entrada</Label>
                <FilesMultiSelect
                  files={files}
                  selected={job.train.files}
                  onChange={(next) =>
                    onChange({ train: { files: next, inspection_id: "" } })
                  }
                />
              </>
            ) : (
              <>
                <Label className="text-xs">Inspección</Label>
                <InspectionSelect
                  inspections={inspections}
                  value={job.train.inspection_id}
                  onChange={(v) =>
                    onChange({ train: { files: [], inspection_id: v } })
                  }
                />
              </>
            )}
          </StepBlock>
        )}

        {job.simulate && (
          <StepBlock title="Generación">
            <div className="flex items-center justify-between gap-3 rounded-md border border-dashed border-border/70 bg-muted/20 px-3 py-2">
              <div>
                <p className="text-xs font-medium">Generación condicionada</p>
                <p className="text-[11px] text-muted-foreground">
                  Misma superficie que en Generación para definir seeds y distribuciones.
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setConditionalOpen(true)}
                className="h-8 shrink-0"
              >
                <SlidersHorizontal className="mr-1.5 h-3.5 w-3.5" />
                Configurar
                {isConditionalConfigActive(job.simulate.conditional) && (
                  <Badge variant="secondary" className="ml-2">
                    activa
                  </Badge>
                )}
              </Button>
            </div>

            <ConditionalGenerationDrawer
              open={conditionalOpen}
              modelId={job.simulate.model_id}
              pendingFilePaths={job.train?.files ?? []}
              config={job.simulate.conditional}
              onChange={(conditional) =>
                onChange({ simulate: { ...job.simulate!, conditional } })
              }
              onClose={() => setConditionalOpen(false)}
            />

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Tamaño de muestra</Label>
                <Input
                  type="number"
                  min={1}
                  value={job.simulate.sample_size}
                  onChange={(e) =>
                    onChange({
                      simulate: {
                        ...job.simulate!,
                        sample_size: Number(e.target.value || 0),
                      },
                    })
                  }
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">
                  Modelo (opcional — reanudar desde un modelo existente)
                </Label>
                <select
                  className={SELECT_CLASS}
                  value={job.simulate.model_id}
                  onChange={(e) =>
                    onChange({
                      simulate: { ...job.simulate!, model_id: e.target.value },
                    })
                  }
                >
                  <option value="">Usar modelo entrenado en este job</option>
                  {models.map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.model_name || m.model_id}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Formato de salida</Label>
                <select
                  className={SELECT_CLASS}
                  value={job.simulate.synthetic_data_file_format}
                  onChange={(e) =>
                    onChange({
                      simulate: {
                        ...job.simulate!,
                        synthetic_data_file_format: e.target.value as SyntheticDataFileFormat,
                      },
                    })
                  }
                >
                  <option value="csv">CSV</option>
                  <option value="parquet">Parquet</option>
                </select>
              </div>
            </div>
          </StepBlock>
        )}

        {job.evaluate && (
          <StepBlock title="Evaluación">
            <div className="flex items-center justify-between gap-3 rounded-md border border-dashed border-border/70 bg-muted/20 px-3 py-2">
              <div>
                <p className="text-xs font-medium">Métricas y parámetros</p>
                <p className="text-[11px] text-muted-foreground">
                  Esta sección usa la misma configuración editable que la página de Auditoría.
                </p>
              </div>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setEvaluationConfigOpen(true)}
                className="h-8 shrink-0"
              >
                <Settings className="mr-1.5 h-3.5 w-3.5" />
                Configurar métricas
              </Button>
            </div>

            <ConfigDrawer
              configId="evaluation"
              open={evaluationConfigOpen}
              onClose={() => setEvaluationConfigOpen(false)}
            />

            <Label className="text-xs">Datos reales (referencia)</Label>
            <FilesMultiSelect
              files={files}
              selected={job.evaluate.real_data}
              onChange={(next) =>
                onChange({ evaluate: { ...job.evaluate!, real_data: next } })
              }
            />
            <div className="grid grid-cols-2 gap-3 pt-2">
              <div className="space-y-1">
                <Label className="text-xs">
                  Simulación a re-evaluar (opcional)
                </Label>
                <select
                  className={SELECT_CLASS}
                  value={job.evaluate.simulation_id}
                  onChange={(e) =>
                    onChange({
                      evaluate: { ...job.evaluate!, simulation_id: e.target.value },
                    })
                  }
                >
                  <option value="">Usar simulación de este job</option>
                  {simulations.map((s) => (
                    <option key={s.simulation_id} value={s.simulation_id}>
                      {s.simulation_name || s.simulation_id}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">Modelo origen (linaje)</Label>
                <select
                  className={SELECT_CLASS}
                  value={job.evaluate.model_id}
                  onChange={(e) =>
                    onChange({
                      evaluate: { ...job.evaluate!, model_id: e.target.value },
                    })
                  }
                >
                  <option value="">—</option>
                  {models.map((m) => (
                    <option key={m.model_id} value={m.model_id}>
                      {m.model_name || m.model_id}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </StepBlock>
        )}

        {!job.train && !job.simulate && !job.evaluate && (
          <p className="rounded border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
            Selecciona al menos un paso (Entrenar / Generar / Evaluar).
          </p>
        )}

        <OverridesBlock
          overrides={job.overrides}
          rulesConfigs={rulesConfigs}
          overrideCount={overrideCount}
          setOverride={setOverride}
          onEditRules={onEditRules}
        />
      </div>
    </div>
  );
}
