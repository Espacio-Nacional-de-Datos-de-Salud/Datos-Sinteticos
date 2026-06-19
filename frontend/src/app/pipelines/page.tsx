// Dev-mode pipelines workbench.
//
// Two columns:
//   • Left: list of saved pipeline YAML configs + a "New" button. Each entry
//     can be selected (loads it into the editor) or deleted.
//   • Right: visual job designer for the selected config. Each job is a card
//     with dropdown-driven step toggles (train / simulate / evaluate) — no
//     YAML typing required. The same area also lists past pipeline runs so
//     the engineer can re-launch with one click.
//
// All authoring happens against the backend's `/pipelines/configs` endpoints;
// "Run" hands the saved YAML's absolute path to `POST /pipelines/`. This is a
// thin wrapper over the same flow the CLI uses, which is why we don't try to
// hide config_path semantics behind a synthetic name.
//
// Cards, dialogs, and the YAML round-trip live under @/components/pipelines.
// This file owns page-level state (selection, draft name, dialog flags) and
// the data-layer queries/mutations against the backend.

"use client";

import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Plus,
  Trash2,
  Play,
  Save,
  FileCode,
  Workflow,
  RotateCcw,
  Layers,
  BookOpen,
} from "lucide-react";

import { RulesEditor } from "@/components/config/rules-editor";
import { PipelinesInstructionsPanel } from "@/components/pipelines/instructions-content";
import {
  CombinationsDialog,
  type ApplyMode,
} from "@/components/pipelines/combinations-dialog";
import { JobCard } from "@/components/pipelines/job-card";
import { RunRow } from "@/components/pipelines/run-row";
import {
  EMPTY_JOB,
  type Job,
  type PipelineDoc,
} from "@/components/pipelines/types";
import { VariantsDialog } from "@/components/pipelines/variants-dialog";
import { docToYaml, emptyDoc, parseYamlToDoc } from "@/components/pipelines/yaml";
import { PipelineRunDialog } from "@/components/pipelines/run-dialog/pipeline-run-dialog";
import { PipelineYamlDialog } from "@/components/pipelines/yaml-dialog";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  api,
  deletePipelineConfig,
  getPipelineConfig,
  launchPipeline,
  listPipelineConfigs,
  listPipelineRuns,
  savePipelineConfig,
  type Autodetect,
  type ConfigFile,
  type DataFile,
  type InspectionSummary,
  type ModelSummary,
  type PipelineConfigFile,
  type SimulationSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { AdvancedBadge } from "@/components/ui/advanced-section";

export default function PipelinesPage() {
  const queryClient = useQueryClient();
  const [selectedName, setSelectedName] = useState<string | null>(null);
  const [doc, setDoc] = useState<PipelineDoc>(emptyDoc);
  const [draftName, setDraftName] = useState<string>("");
  const [creatingNew, setCreatingNew] = useState<boolean>(false);
  const [confirmDeleteName, setConfirmDeleteName] = useState<string | null>(null);
  const [editingRulesConfig, setEditingRulesConfig] = useState<string | null>(null);
  // Track the selected run by id so the dialog re-renders against the live
  // entry from ``runsQuery`` (which polls every 5s). Keeping a stale snapshot
  // would freeze status/progress while a run is still in flight.
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [yamlPreviewOpen, setYamlPreviewOpen] = useState(false);
  // Combinations dialog operates on the whole doc; variants targets one job by
  // index (null = closed). Both flow back through `applyExpansion` below.
  const [combinationsOpen, setCombinationsOpen] = useState(false);
  const [variantsTarget, setVariantsTarget] = useState<number | null>(null);
  const [instructionsOpen, setInstructionsOpen] = useState(false);

  const configsQuery = useQuery({
    queryKey: ["pipeline-configs"],
    queryFn: listPipelineConfigs,
    enabled: true,
  });

  const runsQuery = useQuery({
    queryKey: ["pipeline-runs"],
    queryFn: listPipelineRuns,
    enabled: true,
    refetchInterval: 5000,
  });

  const selectedRun =
    selectedRunId != null
      ? (runsQuery.data ?? []).find((r) => r.pipeline_id === selectedRunId) ?? null
      : null;

  const filesQuery = useQuery({
    queryKey: ["files-all"],
    queryFn: async () => {
      const { data } = await api.get<DataFile[]>("/files/");
      return data;
    },
    enabled: true,
  });

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const { data } = await api.get<ModelSummary[]>("/models/");
      return data;
    },
    enabled: true,
  });

  const simulationsQuery = useQuery({
    queryKey: ["simulations"],
    queryFn: async () => {
      const { data } = await api.get<SimulationSummary[]>("/simulations/");
      return data;
    },
    enabled: true,
  });

  const inspectionsQuery = useQuery({
    queryKey: ["inspections"],
    queryFn: async () => {
      const { data } = await api.get<InspectionSummary[]>("/inspections/");
      return data;
    },
    enabled: true,
  });

  // Per-job overrides may point at a custom rules YAML — list them so we can
  // offer a dropdown instead of forcing the user to type a path.
  const rulesQuery = useQuery({
    queryKey: ["configs", "rules"],
    queryFn: async () => {
      const { data } = await api.get<ConfigFile[]>("/configs/", {
        params: { scope: "rules" },
      });
      return data;
    },
    enabled: true,
  });

  // To give the rules editor the same table/column autocompletion it has on
  // the BRC page, derive context from the pipeline doc: union of all training
  // file paths (drive `/files/preview`-based table discovery) and the
  // autodetect of the first job that resumes from an existing inspection.
  const rulesPendingFilePaths = useMemo(() => {
    const all = doc.jobs.flatMap((j) => j.train?.files ?? []);
    return Array.from(new Set(all));
  }, [doc]);

  const rulesInspectionId = useMemo(() => {
    for (const j of doc.jobs) {
      if (j.train?.inspection_id) return j.train.inspection_id;
    }
    return null;
  }, [doc]);

  const rulesAutodetectQuery = useQuery({
    queryKey: ["autodetect", rulesInspectionId],
    enabled: !!rulesInspectionId && !!editingRulesConfig,
    queryFn: async () => {
      const { data } = await api.get<Autodetect>(
        `/inspections/${rulesInspectionId}/autodetect`,
      );
      return data;
    },
  });

  const completedModels = useMemo(
    () => (modelsQuery.data ?? []).filter((m) => m.status === "completed"),
    [modelsQuery.data],
  );
  const completedSimulations = useMemo(
    () => (simulationsQuery.data ?? []).filter((s) => s.status === "completed"),
    [simulationsQuery.data],
  );
  const completedInspections = useMemo(
    () => (inspectionsQuery.data ?? []).filter((i) => i.status === "completed"),
    [inspectionsQuery.data],
  );

  // Load YAML when selecting an existing config.
  useEffect(() => {
    if (!selectedName) return;
    let cancelled = false;
    getPipelineConfig(selectedName)
      .then((cfg) => {
        if (!cancelled) {
          setDoc(parseYamlToDoc(cfg.content));
          setDraftName(selectedName);
          setCreatingNew(false);
        }
      })
      .catch(() => toast.error(`No se pudo abrir '${selectedName}'.`));
    return () => {
      cancelled = true;
    };
  }, [selectedName]);

  const saveMutation = useMutation({
    mutationFn: async (input: { name: string; doc: PipelineDoc }) =>
      savePipelineConfig(input.name, docToYaml(input.doc)),
    onSuccess: (saved) => {
      toast.success(`Pipeline '${saved.name}' guardado.`);
      queryClient.invalidateQueries({ queryKey: ["pipeline-configs"] });
      setSelectedName(saved.name);
      setCreatingNew(false);
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "desconocido";
      toast.error(`Error al guardar: ${msg}`);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: deletePipelineConfig,
    onSuccess: (_data, name) => {
      toast.success(`Pipeline '${name}' eliminado.`);
      queryClient.invalidateQueries({ queryKey: ["pipeline-configs"] });
      if (selectedName === name) {
        setSelectedName(null);
        setDoc(emptyDoc());
        setDraftName("");
      }
    },
  });

  const launchMutation = useMutation({
    mutationFn: async (cfg: PipelineConfigFile) => launchPipeline(cfg.path),
    onSuccess: (ack) => {
      toast.success(`Pipeline lanzado: ${ack.pipeline_id}`);
      queryClient.invalidateQueries({ queryKey: ["pipeline-runs"] });
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : "desconocido";
      toast.error(`Error al lanzar: ${msg}`);
    },
  });

  // ---- Mutators on the in-memory doc ----

  const updateJob = (idx: number, patch: Partial<Job>) => {
    setDoc((d) => ({
      jobs: d.jobs.map((j, i) => (i === idx ? { ...j, ...patch } : j)),
    }));
  };
  const removeJob = (idx: number) => {
    setDoc((d) => ({ jobs: d.jobs.filter((_, i) => i !== idx) }));
  };
  const addJob = () => {
    setDoc((d) => ({
      jobs: [...d.jobs, { ...EMPTY_JOB, name: `trabajo_${d.jobs.length + 1}` }],
    }));
  };

  // Splice generated jobs into the doc. `replace` swaps out the base job in
  // place; `insertAfter` keeps the base and inserts the new jobs immediately
  // after it. `baseIndex < 0` (blank-template combinations) appends at the
  // end. Always closes both dialogs when done so the user lands back on the
  // refreshed list.
  const applyExpansion = ({
    baseIndex,
    generated,
    mode,
  }: {
    baseIndex: number;
    generated: Job[];
    mode: ApplyMode;
  }) => {
    setDoc((d) => {
      const jobs = [...d.jobs];
      if (baseIndex < 0 || baseIndex >= jobs.length) {
        jobs.push(...generated);
      } else if (mode === "replace") {
        jobs.splice(baseIndex, 1, ...generated);
      } else {
        jobs.splice(baseIndex + 1, 0, ...generated);
      }
      return { jobs };
    });
    setCombinationsOpen(false);
    setVariantsTarget(null);
    toast.success(
      generated.length === 1
        ? "Variante añadida."
        : `Se añadieron ${generated.length} trabajos.`,
    );
  };

  const configs = configsQuery.data ?? [];
  const runs = runsQuery.data ?? [];

  const startNew = () => {
    setSelectedName(null);
    setCreatingNew(true);
    setDoc(emptyDoc());
    setDraftName("");
  };

  const onSave = () => {
    const name = draftName.trim();
    if (!name) {
      toast.error("Indica un nombre para el pipeline.");
      return;
    }
    if (!/^[A-Za-z0-9_-]+$/.test(name)) {
      toast.error("Solo letras, números, guiones y guiones bajos.");
      return;
    }
    if (doc.jobs.length === 0) {
      toast.error("El pipeline debe tener al menos un trabajo.");
      return;
    }
    saveMutation.mutate({ name, doc });
  };

  const yamlText = useMemo(() => docToYaml(doc), [doc]);

  const copyYamlToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(yamlText);
      toast.success("YAML copiado al portapapeles.");
    } catch {
      toast.error("No se pudo copiar el YAML.");
    }
  };

  return (
    <div className="flex h-full overflow-hidden">
      {/* ---- Left rail: saved configs + past runs ---- */}
      <aside className="flex w-72 shrink-0 flex-col overflow-hidden border-r border-border bg-card">
        <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
          <div>
            <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
              Pipelines guardados
              <AdvancedBadge tooltip="Sección avanzada: editor de pipelines reutilizables. Diseña flujos de trabajo para que se puedan ejecutar de manera automatizada." />
            </div>
            <div className="text-sm font-semibold">{configs.length} configuraciones</div>
          </div>
          <Button size="sm" type="button" onClick={startNew}>
            <Plus className="mr-1 h-3.5 w-3.5" /> Nuevo
          </Button>
        </div>
        <ul className="flex-1 overflow-y-auto p-2">
          {configs.length === 0 && (
            <li className="px-2 py-4 text-xs text-muted-foreground">
              {configsQuery.isLoading ? "Cargando…" : "Aún no hay pipelines."}
            </li>
          )}
          {configs.map((cfg) => (
            <li key={cfg.name}>
              <div
                className={cn(
                  "group flex items-center justify-between gap-1 rounded px-2 py-1.5 text-sm transition-colors",
                  selectedName === cfg.name
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-accent/60",
                )}
              >
                <button
                  type="button"
                  onClick={() => setSelectedName(cfg.name)}
                  className="flex flex-1 items-center gap-2 truncate text-left"
                >
                  <FileCode className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="truncate">{cfg.name}</span>
                </button>
                <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100">
                  <button
                    type="button"
                    aria-label="Lanzar pipeline"
                    title="Lanzar pipeline"
                    onClick={() => launchMutation.mutate(cfg)}
                    className="text-muted-foreground hover:text-emerald-600"
                  >
                    <Play className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    aria-label="Eliminar pipeline"
                    title="Eliminar pipeline"
                    onClick={() => setConfirmDeleteName(cfg.name)}
                    className="text-muted-foreground hover:text-red-600"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            </li>
          ))}
        </ul>

        {/* ---- Past runs ---- */}
        <div className="border-t border-border px-4 py-3">
          <div className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
            Ejecuciones recientes
          </div>
          {runs.length === 0 ? (
            <div className="text-xs text-muted-foreground">Sin ejecuciones.</div>
          ) : (
            <ul className="space-y-1">
              {runs.slice(0, 10).map((r) => (
                <RunRow key={r.pipeline_id} run={r} onClick={() => setSelectedRunId(r.pipeline_id)} />
              ))}
            </ul>
          )}
        </div>
      </aside>

      {/* ---- Main editor ---- */}
      <section className="flex flex-1 flex-col overflow-hidden">
        <div className="flex items-center justify-between gap-3 border-b border-border bg-background px-6 py-3">
          <div className="flex items-center gap-3">
            <Workflow className="h-4 w-4 text-muted-foreground" />
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                {creatingNew ? "Nuevo pipeline" : selectedName ? "Editando" : "Diseñador"}
              </div>
              <div className="text-sm font-semibold">
                {creatingNew || !selectedName ? "Define trabajos paso a paso" : selectedName}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {!instructionsOpen && (
              <button
                type="button"
                onClick={() => setInstructionsOpen(true)}
                aria-label="Abrir manual de instrucciones"
                className="mr-1 flex items-center gap-2 rounded-lg bg-[#FFDB00] px-3 py-2 text-sm font-bold text-[#00215C] shadow-md transition-colors hover:bg-[#f0cf00]"
              >
                <BookOpen className="h-4 w-4" />
                Manual
              </button>
            )}
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setCombinationsOpen(true)}
              title="Generar varios trabajos como producto cartesiano de ejes"
            >
              <Layers className="mr-1 h-3.5 w-3.5" /> Combinaciones
            </Button>
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setYamlPreviewOpen(true)}
            >
              <FileCode className="mr-1 h-3.5 w-3.5" /> Ver YAML
            </Button>
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => {
                if (selectedName) {
                  // Reload from server to discard local edits.
                  getPipelineConfig(selectedName).then((cfg) =>
                    setDoc(parseYamlToDoc(cfg.content)),
                  );
                } else {
                  setDoc(emptyDoc());
                }
              }}
              title="Descartar cambios locales"
            >
              <RotateCcw className="mr-1 h-3.5 w-3.5" /> Restablecer
            </Button>
            <Button
              size="sm"
              type="button"
              onClick={onSave}
              disabled={saveMutation.isPending}
            >
              <Save className="mr-1 h-3.5 w-3.5" />
              {saveMutation.isPending ? "Guardando…" : "Guardar"}
            </Button>
            <Button
              size="sm"
              type="button"
              variant="default"
              className="bg-emerald-600 text-white hover:bg-emerald-700"
              disabled={!selectedName || launchMutation.isPending}
              onClick={() => {
                const cfg = configs.find((c) => c.name === selectedName);
                if (cfg) launchMutation.mutate(cfg);
              }}
              title={!selectedName ? "Guarda primero el pipeline" : "Lanzar pipeline"}
            >
              <Play className="mr-1 h-3.5 w-3.5" />
              {launchMutation.isPending ? "Lanzando…" : "Lanzar"}
            </Button>
          </div>
        </div>

        <div className="border-b border-border bg-muted/20 px-6 pt-5 pb-1">
          <div className="mx-auto max-w-4xl">
            {/* Pipeline-name banner. Always editable; on save the name becomes
                the YAML filename. Placed prominently above the job list so it
                can't be missed before clicking Guardar. */}
            <div className="rounded-md border border-border bg-card p-4 shadow-sm">
              <Label htmlFor="pipeline-name" className="text-xs">
                Nombre del pipeline (se usa como nombre del archivo YAML)
              </Label>
              <Input
                id="pipeline-name"
                placeholder="mi_pipeline"
                value={draftName}
                onChange={(e) => setDraftName(e.target.value)}
                className="mt-1 h-10 text-base"
              />
              <p className="mt-1 text-[11px] text-muted-foreground">
                Solo letras, números, guiones (<code>-</code>) y guiones bajos
                (<code>_</code>). Guardar con un nombre distinto crea una copia.
              </p>
            </div>
          </div>
        </div>

        <div className="flex-1 overflow-y-auto bg-muted/20 px-6 py-5">
          <div className="mx-auto max-w-4xl space-y-4">
            {doc.jobs.map((job, idx) => (
              <JobCard
                key={idx}
                index={idx}
                job={job}
                files={filesQuery.data ?? []}
                models={completedModels}
                simulations={completedSimulations}
                inspections={completedInspections}
                rulesConfigs={rulesQuery.data ?? []}
                onChange={(patch) => updateJob(idx, patch)}
                onRemove={() => removeJob(idx)}
                onEditRules={(id) => setEditingRulesConfig(id)}
                onExpand={() => setVariantsTarget(idx)}
              />
            ))}
            <Button type="button" variant="outline" onClick={addJob} className="w-full">
              <Plus className="mr-2 h-3.5 w-3.5" /> Añadir trabajo
            </Button>
          </div>
        </div>
      </section>

      {instructionsOpen && (
        <PipelinesInstructionsPanel onClose={() => setInstructionsOpen(false)} />
      )}

      <ConfirmDialog
        open={!!confirmDeleteName}
        title="¿Eliminar pipeline?"
        description={`El archivo '${confirmDeleteName}.yaml' se eliminará. Las ejecuciones pasadas no se ven afectadas.`}
        confirmLabel="Eliminar"
        onConfirm={() => {
          if (confirmDeleteName) deleteMutation.mutate(confirmDeleteName);
          setConfirmDeleteName(null);
        }}
        onCancel={() => setConfirmDeleteName(null)}
      />

      <RulesEditor
        open={!!editingRulesConfig}
        configId={editingRulesConfig || "rules"}
        autodetect={rulesAutodetectQuery.data ?? null}
        pendingFilePaths={rulesPendingFilePaths}
        onClose={() => setEditingRulesConfig(null)}
        onSaved={() => queryClient.invalidateQueries({ queryKey: ["configs", "rules"] })}
      />

      <PipelineYamlDialog
        open={yamlPreviewOpen}
        name={draftName.trim() || selectedName || "pipeline"}
        yamlText={yamlText}
        canSave={!!selectedName}
        onClose={() => setYamlPreviewOpen(false)}
        onCopy={copyYamlToClipboard}
        onSaveRaw={async (raw) => {
          const name = (draftName.trim() || selectedName || "").trim();
          if (!name) {
            toast.error("Indica un nombre para el pipeline antes de guardar el YAML.");
            return;
          }
          try {
            // Round-trip the freshly typed YAML through the backend (which
            // validates it and writes it to disk verbatim) and then reload
            // it into the structured editor so both views stay in sync.
            const saved = await savePipelineConfig(name, raw);
            toast.success(`Pipeline '${saved.name}' guardado.`);
            setDoc(parseYamlToDoc(saved.content));
            setSelectedName(saved.name);
            setCreatingNew(false);
            queryClient.invalidateQueries({ queryKey: ["pipeline-configs"] });
            setYamlPreviewOpen(false);
          } catch (err) {
            const msg = err instanceof Error ? err.message : "desconocido";
            toast.error(`Error al guardar YAML: ${msg}`);
          }
        }}
      />

      {selectedRun && (
        <PipelineRunDialog run={selectedRun} onClose={() => setSelectedRunId(null)} />
      )}

      <CombinationsDialog
        open={combinationsOpen}
        jobs={doc.jobs}
        catalogues={{
          files: filesQuery.data ?? [],
          models: modelsQuery.data ?? [],
          rulesConfigs: rulesQuery.data ?? [],
          inspections: inspectionsQuery.data ?? [],
          simulations: simulationsQuery.data ?? [],
        }}
        onClose={() => setCombinationsOpen(false)}
        onApply={applyExpansion}
      />

      <VariantsDialog
        open={variantsTarget !== null}
        baseJob={variantsTarget !== null ? doc.jobs[variantsTarget] ?? null : null}
        baseIndex={variantsTarget ?? 0}
        catalogues={{
          files: filesQuery.data ?? [],
          models: modelsQuery.data ?? [],
          rulesConfigs: rulesQuery.data ?? [],
          inspections: inspectionsQuery.data ?? [],
          simulations: simulationsQuery.data ?? [],
        }}
        onClose={() => setVariantsTarget(null)}
        onApply={applyExpansion}
      />
    </div>
  );
}
