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

"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import yaml from "js-yaml";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Plus,
  Trash2,
  Play,
  Save,
  FileCode,
  Workflow,
  X,
  RotateCcw,
  Settings,
  Eye,
  SlidersHorizontal,
  Layers,
  Copy,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Download,
  FileText,
} from "lucide-react";

import {
  ConditionalGenerationDrawer,
  EMPTY_CONDITIONAL_CONFIG,
  buildConditionalPayload,
  isConditionalConfigActive,
  type ConditionalConfig,
} from "@/components/generation/conditional-config";
import { ConfigDrawer } from "@/components/config/config-drawer";
import { JobProgressPanel } from "@/components/jobs/job-progress";
import { RulesEditor } from "@/components/config/rules-editor";
import {
  EMPTY_JOB,
  EMPTY_OVERRIDES,
  MOSTLY_AI_MODELS,
  type Job,
  type JobOverrides,
  type PipelineDoc,
  type SyntheticDataFileFormat,
} from "@/components/pipelines/types";
import {
  CombinationsDialog,
  type ApplyMode,
} from "@/components/pipelines/combinations-dialog";
import { VariantsDialog } from "@/components/pipelines/variants-dialog";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { useIsDev } from "@/lib/mode";
import {
  api,
  API_BASE_URL,
  deletePipelineConfig,
  getPipelineConfig,
  getPipelineRunConfigs,
  launchPipeline,
  listPipelineConfigs,
  listPipelineRuns,
  savePipelineConfig,
  type ConfigFile,
  type DataFile,
  type EvaluationSummary,
  type InspectionSummary,
  type ModelSummary,
  type PipelineConfigFile,
  type PipelineSummary,
  type SimulationSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";

// ---------------------------------------------------------------------------
// In-memory pipeline model. Structural rather than free-form YAML so the
// builder can render dropdowns; we serialize back to YAML on save. The shapes
// themselves live in `@/components/pipelines/types` so the combinations and
// variants dialogs can speak the same vocabulary.
// ---------------------------------------------------------------------------

const SELECT_CLASS =
  "h-9 w-full rounded-md border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

function emptyDoc(): PipelineDoc {
  return { jobs: [{ ...EMPTY_JOB, name: "job_1" }] };
}

// ---------------------------------------------------------------------------
// YAML <-> structured model. We pass through unknown keys (e.g. `config:`
// overrides) so the builder doesn't lose advanced fields written by hand.
// ---------------------------------------------------------------------------

// Render booleans/numbers from YAML back to the form-friendly string repr.
// Empty string is the canonical "no override" value across the form.
function boolToTri(v: unknown): "" | "true" | "false" {
  if (v === true) return "true";
  if (v === false) return "false";
  return "";
}
function numToStr(v: unknown): string {
  return typeof v === "number" ? String(v) : "";
}

function parseConditionalConfig(raw: unknown): ConditionalConfig {
  if (!raw || typeof raw !== "object") return { ...EMPTY_CONDITIONAL_CONFIG };
  const payload = raw as Record<string, unknown>;
  const seed = payload.seed as Record<string, unknown> | undefined;
  const distribution = payload.distribution as Record<string, unknown> | undefined;

  return {
    table: typeof payload.table === "string" ? payload.table : "",
    seeds: seed
      ? Object.entries(seed).map(([column, value]) => ({ column, value: String(value) }))
      : [],
    distributionField:
      typeof payload.distribution_field === "string" ? payload.distribution_field : "",
    distribution: distribution
      ? Object.entries(distribution).map(([value, weight]) => ({
        value,
        weight: String(weight),
      }))
      : [],
  };
}

function readOverrides(rawCfg: unknown): JobOverrides {
  if (!rawCfg || typeof rawCfg !== "object") return { ...EMPTY_OVERRIDES };
  const cfg = rawCfg as Record<string, unknown>;
  const ma = (cfg.mostly_ai ?? {}) as Record<string, unknown>;
  const ms = (ma.model_settings ?? {}) as Record<string, unknown>;
  const dp = (ms.differential_privacy ?? {}) as Record<string, unknown>;
  const gn = (cfg.general ?? {}) as Record<string, unknown>;
  return {
    rules_config: typeof cfg.rules_config === "string" ? cfg.rules_config : "",
    max_epochs: numToStr(ms.max_epochs),
    batch_size: numToStr(ms.batch_size),
    model: typeof ms.model === "string" ? ms.model : "",
    enable_flexible_generation: boolToTri(ms.enable_flexible_generation),
    enable_model_report: boolToTri(ms.enable_model_report),
    dp_max_epsilon: numToStr(dp.max_epsilon),
    dp_noise_multiplier: numToStr(dp.noise_multiplier),
    enable_data_profiling: boolToTri(gn.enable_data_profiling),
    default_csv_delimiter:
      typeof gn.default_csv_delimiter === "string" ? gn.default_csv_delimiter : "",
  };
}

function parseYamlToDoc(text: string): PipelineDoc {
  const raw = yaml.load(text);
  if (!raw || typeof raw !== "object" || !Array.isArray((raw as { jobs?: unknown }).jobs)) {
    return emptyDoc();
  }
  const rawJobs = (raw as { jobs: Record<string, unknown>[] }).jobs;
  const jobs: Job[] = rawJobs.map((rawJob, i) => {
    const train =
      (rawJob.train as
        | { files?: string[]; inspection_id?: string | null }
        | undefined) ?? undefined;
    const sim = rawJob.simulate as
      | {
        sample_size?: number;
        model_id?: string | null;
        synthetic_data_file_format?: SyntheticDataFileFormat;
        conditional?: unknown;
      }
      | undefined;
    const ev = rawJob.evaluate as
      | { real_data?: string[]; simulation_id?: string | null; model_id?: string | null }
      | undefined;
    return {
      name: typeof rawJob.name === "string" ? rawJob.name : `job_${i + 1}`,
      overrides: readOverrides(rawJob.config),
      train: train
        ? {
          files: train.files ?? [],
          inspection_id: train.inspection_id ?? "",
        }
        : null,
      simulate: sim
        ? {
          sample_size: sim.sample_size ?? 1000,
          model_id: sim.model_id ?? "",
          synthetic_data_file_format: sim.synthetic_data_file_format ?? "csv",
          conditional: parseConditionalConfig(sim.conditional),
        }
        : null,
      evaluate: ev
        ? {
          real_data: ev.real_data ?? [],
          simulation_id: ev.simulation_id ?? "",
          model_id: ev.model_id ?? "",
        }
        : null,
    };
  });
  return { jobs };
}

// Serialise overrides → YAML. Returns an empty object the caller skips entirely
// when no override is set, so the YAML doesn't carry a noisy ``config: {}``.
function emitOverrides(o: JobOverrides): Record<string, unknown> {
  const cfg: Record<string, unknown> = {};
  if (o.rules_config.trim()) cfg.rules_config = o.rules_config.trim();

  const modelSettings: Record<string, unknown> = {};
  if (o.max_epochs.trim()) modelSettings.max_epochs = Number(o.max_epochs);
  if (o.batch_size.trim()) modelSettings.batch_size = Number(o.batch_size);
  if (o.model.trim()) modelSettings.model = o.model.trim();
  if (o.enable_flexible_generation)
    modelSettings.enable_flexible_generation = o.enable_flexible_generation === "true";
  if (o.enable_model_report)
    modelSettings.enable_model_report = o.enable_model_report === "true";

  const dp: Record<string, unknown> = {};
  if (o.dp_max_epsilon.trim()) dp.max_epsilon = Number(o.dp_max_epsilon);
  if (o.dp_noise_multiplier.trim()) dp.noise_multiplier = Number(o.dp_noise_multiplier);
  if (Object.keys(dp).length > 0) modelSettings.differential_privacy = dp;

  if (Object.keys(modelSettings).length > 0) {
    cfg.mostly_ai = { model_settings: modelSettings };
  }

  const general: Record<string, unknown> = {};
  if (o.enable_data_profiling)
    general.enable_data_profiling = o.enable_data_profiling === "true";
  if (o.default_csv_delimiter.trim())
    general.default_csv_delimiter = o.default_csv_delimiter;
  if (Object.keys(general).length > 0) cfg.general = general;

  return cfg;
}

function docToYaml(doc: PipelineDoc): string {
  const out = {
    jobs: doc.jobs.map((j) => {
      // Drop step keys when the section is null and prune empty optional ids
      // so the saved YAML stays readable.
      const job: Record<string, unknown> = { name: j.name };
      const cfg = emitOverrides(j.overrides);
      if (Object.keys(cfg).length > 0) job.config = cfg;
      if (j.train) {
        // Inspection-id and files are mutually exclusive on the backend; emit
        // whichever the user picked, never both, so the YAML stays unambiguous.
        const tr: Record<string, unknown> = {};
        if (j.train.inspection_id) {
          tr.inspection_id = j.train.inspection_id;
        } else {
          tr.files = j.train.files;
        }
        job.train = tr;
      }
      if (j.simulate) {
        const sim: Record<string, unknown> = {
          sample_size: j.simulate.sample_size,
          synthetic_data_file_format: j.simulate.synthetic_data_file_format,
        };
        if (j.simulate.model_id) sim.model_id = j.simulate.model_id;
        const conditional = buildConditionalPayload(j.simulate.conditional);
        if (conditional) sim.conditional = conditional;
        job.simulate = sim;
      }
      if (j.evaluate) {
        const ev: Record<string, unknown> = { real_data: j.evaluate.real_data };
        if (j.evaluate.simulation_id) ev.simulation_id = j.evaluate.simulation_id;
        if (j.evaluate.model_id) ev.model_id = j.evaluate.model_id;
        job.evaluate = ev;
      }
      return job;
    }),
  };
  return yaml.dump(out, { lineWidth: 100, noRefs: true });
}

// ---------------------------------------------------------------------------
// Helpers used by the dropdowns. Kept tiny and inline rather than promoted to
// a generic <MultiSelect/> — the page only needs three flavours.
// ---------------------------------------------------------------------------

function FilesMultiSelect({
  files,
  selected,
  onChange,
  placeholder = "Añade archivos…",
}: {
  files: DataFile[];
  selected: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
}) {
  const remaining = files.filter((f) => !selected.includes(f.path));
  return (
    <div className="space-y-2">
      {selected.length > 0 && (
        <ul className="space-y-1">
          {selected.map((path) => (
            <li
              key={path}
              className="flex items-center justify-between gap-2 rounded-md border border-border bg-muted/30 px-2.5 py-1.5 text-xs"
            >
              <span className="truncate font-mono">{path}</span>
              <button
                type="button"
                aria-label="Quitar archivo"
                className="text-muted-foreground hover:text-foreground"
                onClick={() => onChange(selected.filter((p) => p !== path))}
              >
                <X className="h-3 w-3" />
              </button>
            </li>
          ))}
        </ul>
      )}
      <select
        className={SELECT_CLASS}
        value=""
        onChange={(e) => {
          const next = e.target.value;
          if (next) onChange([...selected, next]);
        }}
      >
        <option value="">{placeholder}</option>
        {remaining.map((f) => (
          <option key={f.path} value={f.path}>
            {f.name}
          </option>
        ))}
      </select>
    </div>
  );
}

function InspectionSelect({
  inspections,
  value,
  onChange,
}: {
  inspections: InspectionSummary[];
  value: string;
  onChange: (next: string) => void;
}) {
  return (
    <select
      className={SELECT_CLASS}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">Selecciona una inspección…</option>
      {inspections.map((i) => (
        <option key={i.inspection_id} value={i.inspection_id}>
          {i.inspection_name || i.inspection_id}
        </option>
      ))}
    </select>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export default function PipelinesPage() {
  const isDev = useIsDev();
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

  const configsQuery = useQuery({
    queryKey: ["pipeline-configs"],
    queryFn: listPipelineConfigs,
    enabled: isDev,
  });

  const runsQuery = useQuery({
    queryKey: ["pipeline-runs"],
    queryFn: listPipelineRuns,
    enabled: isDev,
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
    enabled: isDev,
  });

  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const { data } = await api.get<ModelSummary[]>("/models/");
      return data;
    },
    enabled: isDev,
  });

  const simulationsQuery = useQuery({
    queryKey: ["simulations"],
    queryFn: async () => {
      const { data } = await api.get<SimulationSummary[]>("/simulations/");
      return data;
    },
    enabled: isDev,
  });

  const inspectionsQuery = useQuery({
    queryKey: ["inspections"],
    queryFn: async () => {
      const { data } = await api.get<InspectionSummary[]>("/inspections/");
      return data;
    },
    enabled: isDev,
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
    enabled: isDev,
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
      jobs: [...d.jobs, { ...EMPTY_JOB, name: `job_${d.jobs.length + 1}` }],
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
        : `Se añadieron ${generated.length} jobs.`,
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
      toast.error("El pipeline debe tener al menos un job.");
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

  if (!isDev) {
    return (
      <div className="flex h-full items-center justify-center p-8">
        <div className="max-w-md rounded-md border border-border bg-card p-6 text-center">
          <Workflow className="mx-auto mb-2 h-6 w-6 text-muted-foreground" />
          <h2 className="mb-1 text-base font-bold">Modo desarrollo requerido</h2>
          <p className="text-sm text-muted-foreground">
            Activa el modo <strong>Dev</strong> en la cabecera para diseñar y
            ejecutar pipelines.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full overflow-hidden">
      {/* ---- Left rail: saved configs + past runs ---- */}
      <aside className="flex w-72 shrink-0 flex-col overflow-hidden border-r border-border bg-card">
        <div className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
              Pipelines guardados
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
                {creatingNew || !selectedName ? "Define jobs paso a paso" : selectedName}
              </div>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              type="button"
              onClick={() => setCombinationsOpen(true)}
              title="Generar varios jobs como producto cartesiano de ejes"
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
              <Plus className="mr-2 h-3.5 w-3.5" /> Añadir job
            </Button>
          </div>
        </div>
      </section>

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

// ---------------------------------------------------------------------------

function RunRow({ run, onClick }: { run: PipelineSummary; onClick: () => void }) {
  const color =
    run.status === "completed"
      ? "bg-emerald-500"
      : run.status === "failed"
        ? "bg-red-500"
        : run.status === "in_progress"
          ? "bg-amber-500"
          : run.status === "partial"
            ? "bg-amber-400"
            : "bg-muted-foreground";
  return (
    <li>
      <button
        type="button"
        onClick={onClick}
        className="flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left text-xs transition-colors hover:bg-accent/60"
      >
        <div className="flex items-center gap-2 truncate">
          <span className={cn("inline-block h-1.5 w-1.5 shrink-0 rounded-full", color)} />
          <span className="truncate font-mono">{run.pipeline_id}</span>
        </div>
        <Eye className="h-3 w-3 shrink-0 text-muted-foreground" />
      </button>
    </li>
  );
}

// ---------------------------------------------------------------------------

function JobCard({
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
                <Label className="text-xs">Modelo origen (linaje MLflow)</Label>
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

// ---------------------------------------------------------------------------
// Per-job overrides editor — collapsible. Only the keys explicitly set by the
// user end up in the YAML (deep-merge semantics on the backend); empty fields
// inherit the global defaults from mostly_ai.yaml / general.yaml.
// ---------------------------------------------------------------------------

const TRI_OPTIONS: { value: "" | "true" | "false"; label: string }[] = [
  { value: "", label: "Por defecto" },
  { value: "true", label: "Activado" },
  { value: "false", label: "Desactivado" },
];

function OverridesBlock({
  overrides,
  rulesConfigs,
  overrideCount,
  setOverride,
  onEditRules,
}: {
  overrides: JobOverrides;
  rulesConfigs: ConfigFile[];
  overrideCount: number;
  setOverride: <K extends keyof JobOverrides>(key: K, val: JobOverrides[K]) => void;
  onEditRules: (id: string) => void;
}) {
  const [open, setOpen] = useState(overrideCount > 0);
  return (
    <div className="rounded-md border border-border bg-background">
      <button
        type="button"
        className="flex w-full items-center justify-between px-3 py-2 text-left"
        onClick={() => setOpen((v) => !v)}
      >
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
            Overrides (opcional)
          </span>
          {overrideCount > 0 && (
            <span className="rounded-full bg-[#FFDB00] px-1.5 py-0.5 text-[10px] font-bold text-[#00215C]">
              {overrideCount} {overrideCount === 1 ? "ajuste" : "ajustes"}
            </span>
          )}
        </div>
        <span className="text-xs text-muted-foreground">{open ? "▾" : "▸"}</span>
      </button>

      {open && (
        <div className="space-y-4 border-t border-border p-3">
          {/* Reglas dedicadas — apuntan a un YAML del scope `rules`. Permite
              que el usuario defina constraints específicos para este job sin
              tocar el archivo global. */}
          <div className="space-y-1">
            <div className="flex items-center justify-between gap-2">
              <Label className="text-xs">Configuración de reglas</Label>
              <button
                type="button"
                onClick={() => {
                  const val = overrides.rules_config;
                  const id = val.startsWith("config/") ? val.slice(7) : "rules";
                  onEditRules(id);
                }}
                className="flex items-center gap-1 text-[10px] font-semibold text-muted-foreground transition-colors hover:text-foreground"
              >
                <Settings className="h-3 w-3" />
                {overrides.rules_config ? "Editar selección" : "Editar reglas globales"}
              </button>
            </div>
            <select
              className={SELECT_CLASS}
              value={overrides.rules_config}
              onChange={(e) => setOverride("rules_config", e.target.value)}
            >
              <option value="">Usar reglas globales (rules.yaml)</option>
              {rulesConfigs.map((r) => (
                <option key={r.id} value={`config/${r.id}`}>
                  {r.id}
                </option>
              ))}
            </select>
          </div>

          {/* Mostly AI — model_settings.* */}
          <div className="rounded border border-border/60 p-3">
            <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
              Mostly AI · model_settings
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">Modelo</Label>
                <select
                  className={SELECT_CLASS}
                  value={overrides.model}
                  onChange={(e) => setOverride("model", e.target.value)}
                >
                  <option value="">Por defecto</option>
                  {MOSTLY_AI_MODELS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">max_epochs</Label>
                <Input
                  type="number"
                  min={1}
                  placeholder="por defecto"
                  value={overrides.max_epochs}
                  onChange={(e) => setOverride("max_epochs", e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">batch_size</Label>
                <Input
                  type="number"
                  min={1}
                  placeholder="por defecto"
                  value={overrides.batch_size}
                  onChange={(e) => setOverride("batch_size", e.target.value)}
                />
              </div>
              <div className="space-y-1">
                <Label className="text-xs">enable_flexible_generation</Label>
                <select
                  className={SELECT_CLASS}
                  value={overrides.enable_flexible_generation}
                  onChange={(e) =>
                    setOverride(
                      "enable_flexible_generation",
                      e.target.value as "" | "true" | "false",
                    )
                  }
                >
                  {TRI_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">enable_model_report</Label>
                <select
                  className={SELECT_CLASS}
                  value={overrides.enable_model_report}
                  onChange={(e) =>
                    setOverride(
                      "enable_model_report",
                      e.target.value as "" | "true" | "false",
                    )
                  }
                >
                  {TRI_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {/* Differential privacy — leaving both empty keeps DP off (or
                whatever the global config has). Filling them turns it on. */}
            <div className="mt-3 rounded border border-dashed border-border/60 p-2.5">
              <div className="mb-2 text-[10px] font-bold uppercase tracking-wide text-muted-foreground">
                differential_privacy (opcional)
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div className="space-y-1">
                  <Label className="text-xs">max_epsilon</Label>
                  <Input
                    type="number"
                    step="0.1"
                    min={0}
                    placeholder="—"
                    value={overrides.dp_max_epsilon}
                    onChange={(e) => setOverride("dp_max_epsilon", e.target.value)}
                  />
                </div>
                <div className="space-y-1">
                  <Label className="text-xs">noise_multiplier</Label>
                  <Input
                    type="number"
                    step="0.1"
                    min={0}
                    placeholder="—"
                    value={overrides.dp_noise_multiplier}
                    onChange={(e) => setOverride("dp_noise_multiplier", e.target.value)}
                  />
                </div>
              </div>
            </div>
          </div>

          {/* General — settings.* */}
          <div className="rounded border border-border/60 p-3">
            <div className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">
              General
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label className="text-xs">enable_data_profiling</Label>
                <select
                  className={SELECT_CLASS}
                  value={overrides.enable_data_profiling}
                  onChange={(e) =>
                    setOverride(
                      "enable_data_profiling",
                      e.target.value as "" | "true" | "false",
                    )
                  }
                >
                  {TRI_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-1">
                <Label className="text-xs">default_csv_delimiter</Label>
                <Input
                  placeholder="por defecto (,)"
                  maxLength={3}
                  value={overrides.default_csv_delimiter}
                  onChange={(e) => setOverride("default_csv_delimiter", e.target.value)}
                />
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function StepBlock({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2 rounded-md border border-border bg-background p-3">
      <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
        {title}
      </div>
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pipeline results viewer modal.
// ---------------------------------------------------------------------------

// The pipeline-run timestamp emitted by the backend is the engine's session
// stamp ``YYYYMMDD_HHMMSS`` — not ISO. ``new Date(...)`` returns Invalid Date
// for it, which is why "Iniciado" used to render blank. Parse it explicitly
// and fall back gracefully when the format is unfamiliar.
function formatRunTimestamp(raw: string | undefined | null): string {
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

// Storage keys the wizard pages already read on mount to restore the
// "currently selected" model/simulation/evaluation. We piggy-back on them so
// the "Ir a …" buttons below land the user on the exact artifact this run
// produced — no new query-param plumbing needed.
//   ``ends.pipeline.currentModelId``       → /pipeline/entrenamiento, /pipeline/generacion
//   ``ends.pipeline.currentSimulationId``  → /pipeline/generacion, /pipeline/auditoria
//   ``ends.pipeline.currentEvaluationId``  → /pipeline/auditoria
const RUN_MODEL_STORAGE_KEY = "ends.pipeline.currentModelId";
const RUN_SIMULATION_STORAGE_KEY = "ends.pipeline.currentSimulationId";
const RUN_EVALUATION_STORAGE_KEY = "ends.pipeline.currentEvaluationId";

type RunTab = "summary" | "jobs";

async function copyToClipboard(value: string) {
  try {
    await navigator.clipboard.writeText(value);
    toast.success("Copiado");
  } catch {
    toast.error("No se pudo copiar al portapapeles");
  }
}

function CopyableField({
  label,
  value,
  mono = true,
}: {
  label: string;
  value: string | undefined | null;
  mono?: boolean;
}) {
  if (!value) return null;
  return (
    <div className="space-y-1">
      <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
        {label}
      </div>
      <div className="flex items-center gap-2 rounded-md border border-border bg-muted/30 px-2 py-1.5">
        <span
          className={cn(
            "flex-1 truncate text-[11px] text-foreground",
            mono ? "font-mono" : "",
          )}
          title={value}
        >
          {value}
        </span>
        <button
          type="button"
          onClick={() => void copyToClipboard(value)}
          className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label={`Copiar ${label}`}
          title="Copiar"
        >
          <Copy className="h-3.5 w-3.5" />
        </button>
      </div>
    </div>
  );
}

function ArtifactShell({
  label,
  color,
  children,
  actions,
}: {
  label: string;
  color: string;
  children: React.ReactNode;
  actions: React.ReactNode;
}) {
  return (
    <div className="space-y-2 rounded-md border border-border bg-background p-3">
      <div className="flex items-center justify-between gap-2">
        <Badge variant="secondary" className={cn("text-[9px] capitalize", color)}>
          {label}
        </Badge>
        <div className="flex flex-wrap items-center gap-1.5">{actions}</div>
      </div>
      <div className="space-y-1">{children}</div>
    </div>
  );
}

function ArtifactStat({
  label,
  value,
}: {
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 text-[11px]">
      <span className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground">
        {label}
      </span>
      <span className="truncate text-right font-medium">{value}</span>
    </div>
  );
}

function ModelArtifactCard({
  modelId,
  onOpen,
}: {
  modelId: string;
  onOpen: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["model", modelId],
    queryFn: async () => {
      const { data } = await api.get<ModelSummary>(`/models/${modelId}`);
      return data;
    },
  });

  const reportUrl =
    data?.qa_report_filename
      ? `${API_BASE_URL}/models/${modelId}/reports/${data.qa_report_filename}`
      : null;
  const generatorUrl = `${API_BASE_URL}/models/${modelId}/download/generator`;

  return (
    <ArtifactShell
      label="Modelo"
      color="text-blue-600"
      actions={
        <>
          {reportUrl && (
            <a
              href={reportUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent"
            >
              <FileText className="h-3.5 w-3.5" /> QA report
            </a>
          )}
          <a
            href={generatorUrl}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent"
          >
            <Download className="h-3.5 w-3.5" /> Generator
          </a>
          <Button type="button" size="sm" variant="outline" onClick={onOpen}>
            <ExternalLink className="mr-1 h-3.5 w-3.5" />
            Detalles
          </Button>
        </>
      }
    >
      {isLoading && (
        <span className="text-[11px] text-muted-foreground">Cargando…</span>
      )}
      {error && (
        <span className="text-[11px] text-red-600">No se pudo cargar el modelo.</span>
      )}
      {data && (
        <>
          <ArtifactStat
            label="Accuracy"
            value={
              data.accuracy != null
                ? `${(data.accuracy * 100).toFixed(2)}%`
                : "—"
            }
          />
          <ArtifactStat
            label="Filas entrenadas"
            value={
              data.train_size != null ? data.train_size.toLocaleString() : "—"
            }
          />
          <ArtifactStat label="Tablas" value={data.tables || "—"} />
          {data.model_name && (
            <ArtifactStat label="Nombre" value={data.model_name} />
          )}
        </>
      )}
    </ArtifactShell>
  );
}

function SimulationArtifactCard({
  simulationId,
  onOpen,
}: {
  simulationId: string;
  onOpen: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["simulation", simulationId],
    queryFn: async () => {
      const { data } = await api.get<SimulationSummary>(
        `/simulations/${simulationId}`,
      );
      return data;
    },
  });

  const datasetUrl = `${API_BASE_URL}/simulations/${simulationId}/download/synthetic-dataset`;

  return (
    <ArtifactShell
      label="Simulación"
      color="text-emerald-600"
      actions={
        <>
          <a
            href={datasetUrl}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent"
          >
            <Download className="h-3.5 w-3.5" /> Dataset sintético
          </a>
          <Button type="button" size="sm" variant="outline" onClick={onOpen}>
            <ExternalLink className="mr-1 h-3.5 w-3.5" />
            Detalles
          </Button>
        </>
      }
    >
      {isLoading && (
        <span className="text-[11px] text-muted-foreground">Cargando…</span>
      )}
      {error && (
        <span className="text-[11px] text-red-600">
          No se pudo cargar la simulación.
        </span>
      )}
      {data && (
        <>
          <ArtifactStat
            label="Filas generadas"
            value={
              data.sample_size != null ? data.sample_size.toLocaleString() : "—"
            }
          />
          <ArtifactStat label="Tablas" value={data.tables || "—"} />
          {data.model_accuracy != null && (
            <ArtifactStat
              label="Accuracy del modelo"
              value={`${(data.model_accuracy * 100).toFixed(2)}%`}
            />
          )}
          {data.simulation_name && (
            <ArtifactStat label="Nombre" value={data.simulation_name} />
          )}
        </>
      )}
    </ArtifactShell>
  );
}

function EvaluationArtifactCard({
  evaluationId,
  onOpen,
}: {
  evaluationId: string;
  onOpen: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["evaluation", evaluationId],
    queryFn: async () => {
      const { data } = await api.get<EvaluationSummary>(
        `/evaluations/${evaluationId}`,
      );
      return data;
    },
  });

  const downloadUrl = `${API_BASE_URL}/evaluations/${evaluationId}/download`;

  return (
    <ArtifactShell
      label="Evaluación"
      color="text-purple-600"
      actions={
        <>
          <a
            href={downloadUrl}
            className="inline-flex items-center gap-1 rounded-md border border-border bg-background px-2 py-1 text-[11px] font-medium hover:bg-accent"
          >
            <Download className="h-3.5 w-3.5" /> Reporte (zip)
          </a>
          <Button type="button" size="sm" variant="outline" onClick={onOpen}>
            <ExternalLink className="mr-1 h-3.5 w-3.5" />
            Auditoría
          </Button>
        </>
      }
    >
      {isLoading && (
        <span className="text-[11px] text-muted-foreground">Cargando…</span>
      )}
      {error && (
        <span className="text-[11px] text-red-600">
          No se pudo cargar la evaluación.
        </span>
      )}
      {data && (
        <>
          <ArtifactStat label="Estado" value={data.status} />
          {data.metrics_evaluated && data.metrics_evaluated.length > 0 && (
            <ArtifactStat
              label="Métricas"
              value={data.metrics_evaluated.join(", ")}
            />
          )}
          {data.evaluation_name && (
            <ArtifactStat label="Nombre" value={data.evaluation_name} />
          )}
        </>
      )}
    </ArtifactShell>
  );
}

function RunTabButton({
  id,
  label,
  badge,
  active,
  onSelect,
}: {
  id: RunTab;
  label: string;
  badge?: number;
  active: RunTab;
  onSelect: (id: RunTab) => void;
}) {
  const isActive = active === id;
  return (
    <button
      type="button"
      onClick={() => onSelect(id)}
      className={cn(
        "relative -mb-px border-b-2 px-3 py-2 text-xs font-medium transition-colors",
        isActive
          ? "border-primary text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground",
      )}
    >
      <span>{label}</span>
      {badge !== undefined && (
        <span
          className={cn(
            "ml-1.5 rounded px-1.5 py-0.5 text-[9px] font-semibold",
            isActive ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground",
          )}
        >
          {badge}
        </span>
      )}
    </button>
  );
}

function PipelineRunDialog({ run, onClose }: { run: PipelineSummary; onClose: () => void }) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<RunTab>("summary");
  const [expanded, setExpanded] = useState<Record<number, boolean>>({});
  const [configsOpen, setConfigsOpen] = useState(false);

  const cancelRun = useMutation({
    mutationFn: async (id: string) => {
      const { data } = await api.post(`/pipelines/${id}/cancel`);
      return data;
    },
    onSuccess: () => {
      toast.success("Cancelación solicitada");
      queryClient.invalidateQueries({ queryKey: ["pipeline-runs"] });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "Error desconocido";
      toast.error(`No se pudo cancelar: ${msg}`);
    },
  });
  const isRunning = run.status === "in_progress";

  const counts = useMemo(() => {
    let completed = 0;
    let failed = 0;
    let other = 0;
    for (const j of run.jobs) {
      if (j.status === "completed") completed += 1;
      else if (j.status === "failed") failed += 1;
      else other += 1;
    }
    return { completed, failed, other };
  }, [run.jobs]);

  const goToModel = (id: string) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(RUN_MODEL_STORAGE_KEY, id);
    }
    onClose();
    router.push("/pipeline/entrenamiento");
  };

  const goToSimulation = (id: string) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(RUN_SIMULATION_STORAGE_KEY, id);
    }
    onClose();
    router.push("/pipeline/generacion");
  };

  const goToEvaluation = (id: string) => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(RUN_EVALUATION_STORAGE_KEY, id);
    }
    onClose();
    router.push("/pipeline/auditoria");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg border border-border bg-card shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div className="flex items-center gap-3">
            <div
              className={cn(
                "h-2 w-2 rounded-full",
                run.status === "completed" ? "bg-emerald-500" : "bg-amber-500",
              )}
            />
            <h3 className="text-lg font-semibold tracking-tight">{run.pipeline_id}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="border-b border-border px-4">
          <div className="flex gap-1">
            <RunTabButton id="summary" label="Resumen" active={tab} onSelect={setTab} />
            <RunTabButton
              id="jobs"
              label="Jobs"
              badge={run.jobs.length}
              active={tab}
              onSelect={setTab}
            />
          </div>
        </div>

        <div className="flex-1 overflow-y-auto p-6">
          {tab === "summary" && (
            <div className="grid gap-5">
              {isRunning && (
                <div className="rounded-md border border-border bg-muted/20 p-4">
                  <JobProgressPanel
                    status={run.status}
                    progress={run.progress}
                    timestamp={run.timestamp}
                  />
                  <div className="mt-3">
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={cancelRun.isPending}
                      onClick={() => cancelRun.mutate(run.pipeline_id)}
                    >
                      Cancelar
                    </Button>
                  </div>
                </div>
              )}
              <div className="grid grid-cols-2 gap-4 rounded-md border border-border bg-muted/30 p-4">
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                    Estado
                  </div>
                  <div className="text-sm font-medium capitalize">{run.status}</div>
                </div>
                <div>
                  <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                    Iniciado
                  </div>
                  <div className="text-sm font-medium">{formatRunTimestamp(run.timestamp)}</div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                <div className="rounded-md border border-border bg-background p-3 text-center">
                  <div className="text-2xl font-bold text-emerald-600">{counts.completed}</div>
                  <div className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground">
                    Completados
                  </div>
                </div>
                <div className="rounded-md border border-border bg-background p-3 text-center">
                  <div className="text-2xl font-bold text-red-600">{counts.failed}</div>
                  <div className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground">
                    Fallidos
                  </div>
                </div>
                <div className="rounded-md border border-border bg-background p-3 text-center">
                  <div className="text-2xl font-bold text-amber-600">{counts.other}</div>
                  <div className="text-[10px] uppercase tracking-[0.06em] text-muted-foreground">
                    Otros
                  </div>
                </div>
              </div>

              <div className="space-y-1">
                <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                  Configuración lanzada
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setConfigsOpen(true)}
                >
                  <Eye className="mr-1 h-3.5 w-3.5" />
                  Ver configuración
                </Button>
              </div>

              <p className="text-[11px] leading-relaxed text-muted-foreground">
                Abre la pestaña <strong>Jobs</strong> para revisar el detalle por job, o{" "}
                <strong>Artefactos</strong> para acceder rápido a los modelos y simulaciones
                producidos.
              </p>
            </div>
          )}

          {tab === "jobs" && (
            <div className="space-y-2">
              {run.jobs.length === 0 && (
                <div className="rounded-md border border-dashed border-border px-3 py-4 text-center text-[11px] text-muted-foreground">
                  Esta ejecución no registró jobs (probablemente falló antes de completar
                  el primer paso).
                </div>
              )}
              {run.jobs.map((job, i) => {
                const jobStatus = job.status ?? "unknown";
                const statusColor =
                  jobStatus === "completed"
                    ? "text-emerald-600"
                    : jobStatus === "failed"
                      ? "text-red-600"
                      : "text-amber-600";
                const isOpen = !!expanded[i];
                const hasArtifacts = !!(
                  job.model_id || job.simulation_id || job.evaluation_id
                );
                const previewBits = [
                  job.model_id ? `model: ${job.model_id}` : null,
                  job.simulation_id ? `sim: ${job.simulation_id}` : null,
                  job.evaluation_id ? `eval: ${job.evaluation_id}` : null,
                ].filter(Boolean) as string[];
                return (
                  <div key={i} className="rounded-md border border-border bg-background">
                    <button
                      type="button"
                      onClick={() => setExpanded((s) => ({ ...s, [i]: !s[i] }))}
                      className="flex w-full items-center gap-2 px-3 py-2 text-left hover:bg-muted/40"
                      aria-expanded={isOpen}
                    >
                      {isOpen ? (
                        <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
                      ) : (
                        <ChevronRight className="h-3.5 w-3.5 text-muted-foreground" />
                      )}
                      <span className="text-xs font-bold">
                        {job.job_name ?? `job_${i + 1}`}
                      </span>
                      <Badge
                        variant="secondary"
                        className={cn("ml-1 text-[9px] capitalize", statusColor)}
                      >
                        {jobStatus}
                      </Badge>
                      {!isOpen && hasArtifacts && (
                        <span className="ml-2 truncate font-mono text-[10px] text-muted-foreground">
                          {previewBits.join("  ·  ")}
                        </span>
                      )}
                      {!isOpen && !hasArtifacts && (
                        <span className="ml-2 text-[10px] italic text-muted-foreground">
                          sin artefactos
                        </span>
                      )}
                    </button>
                    {isOpen && (
                      <div className="space-y-2 border-t border-border bg-muted/20 p-3">
                        {!hasArtifacts && (
                          <div className="text-[11px] text-muted-foreground">
                            Este job no produjo artefactos (estado: {jobStatus}).
                          </div>
                        )}
                        {job.model_id && (
                          <ModelArtifactCard
                            modelId={job.model_id}
                            onOpen={() => goToModel(job.model_id!)}
                          />
                        )}
                        {job.simulation_id && (
                          <SimulationArtifactCard
                            simulationId={job.simulation_id}
                            onOpen={() => goToSimulation(job.simulation_id!)}
                          />
                        )}
                        {job.evaluation_id && (
                          <EvaluationArtifactCard
                            evaluationId={job.evaluation_id}
                            onOpen={() => goToEvaluation(job.evaluation_id!)}
                          />
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {configsOpen && (
            <PipelineConfigSnapshotDialog
              pipelineId={run.pipeline_id}
              onClose={() => setConfigsOpen(false)}
            />
          )}
        </div>

        <footer className="flex justify-end border-t border-border bg-muted/20 px-6 py-4">
          <Button type="button" onClick={onClose} size="sm">
            Cerrar
          </Button>
        </footer>
      </div>
    </div>
  );
}

function PipelineYamlDialog({
  open,
  name,
  yamlText,
  canSave,
  onClose,
  onCopy,
  onSaveRaw,
}: {
  open: boolean;
  name: string;
  yamlText: string;
  canSave: boolean;
  onClose: () => void;
  onCopy: () => void;
  onSaveRaw: (raw: string) => Promise<void> | void;
}) {
  // Local editable buffer. Initialised from ``yamlText`` and re-synced when
  // the dialog reopens so the user always sees the latest serialised view as
  // a starting point. Edits stay local until the user clicks "Guardar".
  const [draft, setDraft] = useState(yamlText);
  useEffect(() => {
    if (open) setDraft(yamlText);
  }, [open, yamlText]);

  if (!open) return null;

  const dirty = draft !== yamlText;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-4xl flex-col rounded-lg border border-border bg-card shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
              YAML editable
            </div>
            <h3 className="text-lg font-semibold tracking-tight">{name}.yaml</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 overflow-auto p-6">
          <textarea
            spellCheck={false}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            className="h-[60vh] w-full resize-none rounded-md border border-border bg-muted/20 p-4 font-mono text-xs leading-5 outline-none focus:border-ring"
          />
          <p className="mt-2 text-[11px] text-muted-foreground">
            Edita libremente el YAML aquí. El backend valida la sintaxis y la presencia
            de un campo <code>jobs</code> al guardar. Tras guardar, el editor visual se
            recarga; cualquier campo desconocido al builder se conservará en disco
            pero no se mostrará en los formularios.
          </p>
        </div>

        <footer className="flex justify-end gap-2 border-t border-border bg-muted/20 px-6 py-4">
          <Button type="button" variant="outline" size="sm" onClick={onCopy}>
            Copiar YAML
          </Button>
          <Button
            type="button"
            size="sm"
            disabled={!canSave || !dirty}
            title={!canSave ? "Guarda primero el pipeline desde el formulario" : undefined}
            onClick={() => void onSaveRaw(draft)}
          >
            <Save className="mr-1 h-3.5 w-3.5" /> Guardar YAML
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Cerrar
          </Button>
        </footer>
      </div>
    </div>
  );
}

// Reads the snapshots that ``PipelineTracker`` archives next to each run and
// renders a readable summary — the user shouldn't need to open files on the
// server to know what configuration ran.
function PipelineConfigSnapshotDialog({
  pipelineId,
  onClose,
}: {
  pipelineId: string;
  onClose: () => void;
}) {
  const { data, isLoading, error } = useQuery({
    queryKey: ["pipeline-run-configs", pipelineId],
    queryFn: () => getPipelineRunConfigs(pipelineId),
  });

  const jobs = useMemo(() => {
    const raw = (data?.pipeline_config as { jobs?: unknown } | null)?.jobs;
    return Array.isArray(raw) ? (raw as Record<string, unknown>[]) : [];
  }, [data]);

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4 backdrop-blur-sm">
      <div className="flex max-h-[90vh] w-full max-w-3xl flex-col rounded-lg border border-border bg-card shadow-2xl">
        <header className="flex items-center justify-between border-b border-border px-6 py-4">
          <div>
            <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
              Configuración del run
            </div>
            <h3 className="text-base font-semibold tracking-tight">{pipelineId}</h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded-md p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="h-5 w-5" />
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-auto p-6">
          {isLoading && (
            <p className="text-[11px] text-muted-foreground">Cargando configuración…</p>
          )}
          {error && (
            <p className="text-[11px] text-red-600">
              No se pudo leer la configuración congelada para este run.
            </p>
          )}
          {data && (
            <>
              {data.config_path && (
                <div className="rounded-md border border-border bg-muted/30 px-3 py-2">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-muted-foreground">
                    YAML lanzado
                  </div>
                  <div
                    className="truncate font-mono text-[11px]"
                    title={data.config_path}
                  >
                    {data.config_path}
                  </div>
                </div>
              )}

              {jobs.length > 0 && (
                <section className="space-y-2">
                  <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                    Jobs ({jobs.length})
                  </div>
                  <div className="space-y-1">
                    {jobs.map((job, i) => {
                      const name = (job.name as string) ?? `job_${i + 1}`;
                      const steps = [
                        job.train ? "train" : null,
                        job.simulate ? "simulate" : null,
                        job.evaluate ? "evaluate" : null,
                      ].filter(Boolean) as string[];
                      return (
                        <div
                          key={i}
                          className="flex items-center justify-between rounded-md border border-border bg-background px-3 py-1.5"
                        >
                          <span className="font-mono text-[11px]">{name}</span>
                          <span className="text-[10px] text-muted-foreground">
                            {steps.length > 0 ? steps.join(" · ") : "—"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                </section>
              )}

              {data.general_config && (
                <section className="space-y-2">
                  <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                    Constantes generales
                  </div>
                  <div className="rounded-md border border-border bg-muted/30 p-3">
                    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
                      {Object.entries(data.general_config).map(([k, v]) => (
                        <FragmentEntry key={k} k={k} v={v} />
                      ))}
                    </dl>
                  </div>
                </section>
              )}

              {data.pipeline_config_yaml && (
                <section className="space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="text-[10px] font-bold uppercase tracking-[0.08em] text-muted-foreground">
                      pipeline_config.yaml
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        void copyToClipboard(data.pipeline_config_yaml ?? "")
                      }
                      className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                      title="Copiar YAML"
                    >
                      <Copy className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  <pre className="max-h-[40vh] overflow-auto rounded-md border border-border bg-muted/30 p-3 font-mono text-[11px] leading-5">
                    {data.pipeline_config_yaml}
                  </pre>
                </section>
              )}

              {!data.pipeline_config_yaml && !data.general_config && (
                <p className="text-[11px] text-muted-foreground">
                  Esta ejecución no incluye snapshots de configuración (run anterior al
                  registro de <code>configs</code> en el pipeline_card).
                </p>
              )}
            </>
          )}
        </div>

        <footer className="flex justify-end border-t border-border bg-muted/20 px-6 py-4">
          <Button type="button" size="sm" onClick={onClose}>
            Cerrar
          </Button>
        </footer>
      </div>
    </div>
  );
}

function FragmentEntry({ k, v }: { k: string; v: unknown }) {
  const display =
    v === null || v === undefined
      ? "—"
      : typeof v === "object"
        ? JSON.stringify(v)
        : String(v);
  return (
    <>
      <dt className="font-mono text-muted-foreground">{k}</dt>
      <dd className="truncate font-mono" title={display}>
        {display}
      </dd>
    </>
  );
}
