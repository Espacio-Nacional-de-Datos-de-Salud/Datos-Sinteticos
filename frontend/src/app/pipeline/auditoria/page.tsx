// Auditoría — step 6 (final) of the pipeline wizard.
//
// Runs the evaluation suite on a completed simulation. The only input the
// user picks is the simulation_id; the backend resolves the underlying
// model and runs the metrics configured in evaluation.yaml.
//
// Shared lifecycle wiring lives under @/components/pipeline-step. This file
// owns the simulation/model name lookups, the metrics chip list, and the
// download-results button.

"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { FileText, Play, ShieldCheck, Trash2, XCircle } from "lucide-react";

import { ConfigPanel } from "@/components/config/config-drawer";
import { EditableName } from "@/components/jobs/editable-name";
import { ActiveJobCard } from "@/components/pipeline-step/active-job-card";
import { TimeProfilingPanel } from "@/components/pipeline-step/time-profiling-panel";
import { DownloadMenu } from "@/components/pipeline-step/download-menu";
import { HistoryCard, type HistoryColumn } from "@/components/pipeline-step/history-card";
import { useArtifactLifecycle } from "@/components/pipeline-step/use-artifact-lifecycle";
import { useUpstreamSelection } from "@/components/pipeline-step/use-upstream-selection";
import { WizardConfirmDialogs } from "@/components/pipeline-step/wizard-confirm-dialogs";
import { RulesBanner } from "@/components/config/rules-banner";
import { EvaluationReportSection } from "@/components/pipelines/evaluation-report-section";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { NamePromptDialog } from "@/components/ui/name-prompt-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  api,
  API_BASE_URL,
  type EvaluationSummary,
  type ModelSummary,
  type SimulationSummary,
} from "@/lib/api";
import { statusBadgeVariant, translateStatus } from "@/lib/job-status";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { cn } from "@/lib/utils";

type StartInput = { simulation_id: string };

const AUDITORIA_OUTLINE = [
  { id: "preparacion", label: "Preparación", level: 1 },
  { id: "reglas-preprocesamiento", label: "Reglas de preprocesamiento", level: 2 },
  { id: "nueva-evaluacion", label: "Nueva evaluación", level: 2 },
  { id: "configuracion-avanzada", label: "Configuración avanzada", level: 2 },
  { id: "ejecutar-evaluacion", label: "Ejecutar evaluación", level: 2 },
  { id: "resultados", label: "Resultados", level: 1 },
  { id: "evaluacion-actual", label: "Evaluación actual", level: 2 },
  { id: "reporte", label: "Reporte", level: 1 },
  { id: "reporte-evaluacion", label: "Detalle del reporte", level: 2 },
  { id: "historial", label: "Historial", level: 1 },
  { id: "evaluaciones", label: "Evaluaciones", level: 2 },
] as const;

export default function AuditoriaPage() {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);
  const [startDialogOpen, setStartDialogOpen] = useState(false);

  const lc = useArtifactLifecycle<EvaluationSummary, StartInput>({
    apiPath: "/evaluations",
    listKey: "evaluations",
    itemKey: "evaluation",
    storageKey: STORAGE_KEYS.evaluation,
    idField: "evaluation_id",
    buildStartBody: (input) => ({ simulation_id: input.simulation_id }),
    labels: {
      startedToast: (id) => `Evaluación iniciada: ${id}`,
      startErrorPrefix: "No se pudo iniciar la evaluación",
      cancelErrorPrefix: "No se pudo cancelar",
      deletedToast: (id) => `Evaluación eliminada: ${id}`,
      deleteErrorPrefix: "No se pudo eliminar",
      cleanupOkToast: (n) => `${n} evaluación(es) limpiada(s)`,
      cleanupNoopToast: "Nada que limpiar",
      cleanupErrorPrefix: "Error en limpieza",
      purgeOkToast: (n) => `${n} evaluación(es) eliminada(s)`,
      purgeErrorPrefix: "Error al purgar",
    },
  });

  const simulationsQuery = useQuery({
    queryKey: ["simulations"],
    queryFn: async () => {
      const { data } = await api.get<SimulationSummary[]>("/simulations/");
      return data;
    },
  });
  const completedSims = (simulationsQuery.data ?? []).filter(
    (s) => s.status === "completed",
  );
  const { selectedId: selectedSimId, setSelectedId: setSelectedSimId } =
    useUpstreamSelection(completedSims, "simulation_id", STORAGE_KEYS.simulation);

  // Models are referenced indirectly (each evaluation knows which simulation
  // it ran on, and that simulation knows the model id), so we fetch the model
  // catalog purely to map ids → functional names.
  const modelsQuery = useQuery({
    queryKey: ["models"],
    queryFn: async () => {
      const { data } = await api.get<ModelSummary[]>("/models/");
      return data;
    },
  });

  const labelForSimId = useMemo(() => {
    const map = new Map<string, string>();
    for (const s of simulationsQuery.data ?? []) {
      map.set(s.simulation_id, s.simulation_name || s.simulation_id);
    }
    return (id: string | null | undefined) => (id ? map.get(id) ?? id : "—");
  }, [simulationsQuery.data]);

  const labelForModelId = useMemo(() => {
    const map = new Map<string, string>();
    for (const m of modelsQuery.data ?? []) {
      map.set(m.model_id, m.model_name || m.model_id);
    }
    return (id: string | null | undefined) => (id ? map.get(id) ?? id : "—");
  }, [modelsQuery.data]);

  const columns: HistoryColumn<EvaluationSummary>[] = [
    {
      key: "name",
      header: "Nombre",
      width: "20%",
      render: (e) => (
        <div className="space-y-0.5">
          <p
            className="truncate font-mono text-[10px] text-muted-foreground"
            title={e.evaluation_id}
          >
            {e.evaluation_id}
          </p>
          <EditableName
            name={e.evaluation_name || e.evaluation_id}
            existingNames={lc.list.map((x) => x.evaluation_name || x.evaluation_id)}
            onSave={(name) => lc.rename(e.evaluation_id, name)}
          />
        </div>
      ),
    },
    {
      key: "status",
      header: "Estado",
      width: "11%",
      render: (e) => (
        <Badge
          variant={statusBadgeVariant(e.status)}
          className={cn(e.status === "completed" && "!bg-blue-500/20 !text-blue-400")}
        >
          {translateStatus(e.status)}
        </Badge>
      ),
    },
    {
      key: "sim",
      header: "Generación",
      width: "18%",
      render: (e) => (
        <span className="block truncate font-mono text-xs" title={e.simulation_id ?? ""}>
          {labelForSimId(e.simulation_id)}
        </span>
      ),
    },
    {
      key: "model",
      header: "Modelo",
      width: "18%",
      render: (e) => (
        <span className="block truncate font-mono text-xs" title={e.model_id ?? ""}>
          {labelForModelId(e.model_id)}
        </span>
      ),
    },
    {
      key: "metrics",
      header: "Métricas",
      width: "22%",
      render: (e) => (
        <span
          className="block truncate text-xs"
          title={e.metrics_evaluated?.join(", ") ?? ""}
        >
          {e.metrics_evaluated?.length ? e.metrics_evaluated.join(", ") : "—"}
        </span>
      ),
    },
  ];

  return (
    <WizardShell currentSlug="auditoria" canAdvance={false} outline={AUDITORIA_OUTLINE}>
      <div className="space-y-6">
        <div className="sticky top-0 z-20 -mx-8 -mt-6 border-b bg-background/95 px-8 py-4 backdrop-blur supports-[backdrop-filter]:bg-background/80">
          <h1 className="text-2xl font-semibold tracking-tight">Auditoría</h1>
          <p className="text-sm text-muted-foreground">
            Evalúa la utilidad y privacidad del dataset sintético según las
            métricas configuradas en{" "}
            <code className="rounded bg-muted px-1 py-0.5 font-mono text-xs">
              evaluation.yaml
            </code>
            .
          </p>
          {lc.activeId && lc.active && (
            <div className="mt-3 flex items-center gap-2 text-sm">
              <span className="text-muted-foreground">Nombre:</span>
              <EditableName
                name={lc.active.evaluation_name || lc.active.evaluation_id}
                existingNames={lc.list.map((x) => x.evaluation_name || x.evaluation_id)}
                onSave={(name) => lc.rename(lc.active!.evaluation_id, name)}
                size="sm"
              />
            </div>
          )}
        </div>

        <WorkflowGroup id="preparacion" label="Preparación" defaultOpen className="scroll-mt-24">
          <div id="reglas-preprocesamiento" className="scroll-mt-24">
            <RulesBanner />
          </div>

          <div id="nueva-evaluacion" className="scroll-mt-24">
            <Card>
              <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-end">
                <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
                  <ShieldCheck className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1 space-y-1">
                  <Label htmlFor="sim-select">Nueva evaluación</Label>
                  {simulationsQuery.isLoading ? (
                    <Skeleton className="h-9 w-full" />
                  ) : completedSims.length === 0 ? (
                    <p className="text-sm text-destructive">
                      No hay generaciones completadas. Vuelve al paso{" "}
                      <b>Generación</b>.
                    </p>
                  ) : (
                    <select
                      id="sim-select"
                      value={selectedSimId}
                      onChange={(e) => setSelectedSimId(e.target.value)}
                      className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs"
                    >
                      {completedSims.map((s) => (
                        <option key={s.simulation_id} value={s.simulation_id}>
                          {s.simulation_name || s.simulation_id}
                          {s.sample_size != null
                            ? ` · ${s.sample_size.toLocaleString()} filas`
                            : ""}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          <div id="configuracion-avanzada" className="scroll-mt-24">
            <ConfigPanel configId="evaluation" contextId={selectedSimId} />
          </div>

          <div id="ejecutar-evaluacion" className="scroll-mt-24">
            <Card>
              <CardContent className="flex flex-col gap-2 p-4 md:flex-row md:items-center">
                <p className="flex-1 text-sm text-muted-foreground">
                  Configura los parámetros de evaluación y haz clic en ejecutar.
                </p>
                <Button
                  type="button"
                  disabled={!selectedSimId || lc.isStarting || lc.isRunning}
                  onClick={() => setStartDialogOpen(true)}
                >
                  <Play className="mr-2 h-4 w-4" />
                  {lc.isStarting
                    ? "Iniciando…"
                    : lc.isRunning
                      ? "Evaluación en curso…"
                      : "Iniciar evaluación"}
                </Button>
              </CardContent>
            </Card>
          </div>
        </WorkflowGroup>

        <WorkflowGroup id="resultados" label="Resultados" className="scroll-mt-24">
          <div id="evaluacion-actual" className="scroll-mt-24">
            <ActiveJobCard
              id={lc.activeId}
              title="Evaluación actual"
              description="Estado de la última evaluación iniciada."
              isLoading={lc.activeQuery.isLoading}
              isError={lc.activeQuery.isError}
              errorMessage="No se pudo cargar el estado de la evaluación."
              active={lc.active}
              metadata={
                lc.active && (
                  <>
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted-foreground">
                      {lc.active.simulation_id && (
                        <span>
                          Generación:{" "}
                          <span className="font-mono" title={lc.active.simulation_id}>
                            {labelForSimId(lc.active.simulation_id)}
                          </span>
                        </span>
                      )}
                      {lc.active.model_id && (
                        <span>
                          Modelo:{" "}
                          <span className="font-mono" title={lc.active.model_id}>
                            {labelForModelId(lc.active.model_id)}
                          </span>
                        </span>
                      )}
                    </div>
                    {lc.active.metrics_evaluated &&
                      lc.active.metrics_evaluated.length > 0 && (
                        <div>
                          <p className="mb-1 text-xs text-muted-foreground">Métricas:</p>
                          <div className="flex flex-wrap gap-1">
                            {lc.active.metrics_evaluated.map((m) => (
                              <Badge key={m} variant="secondary">
                                {m}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      )}
                    {lc.active.status === "completed" && lc.activeId && (
                      <TimeProfilingPanel kind="evaluations" id={lc.activeId} />
                    )}
                  </>
                )
              }
              actions={
                <>
                  {lc.isRunning && (
                    <Button
                      type="button"
                      size="sm"
                      variant="outline"
                      disabled={lc.isCancelling}
                      onClick={() => lc.activeId && lc.cancel(lc.activeId)}
                    >
                      Cancelar
                    </Button>
                  )}
                </>
              }
            />
          </div>
        </WorkflowGroup>

        {lc.active?.status === "completed" && lc.activeId && (
          <WorkflowGroup id="reporte" label="Reporte" className="scroll-mt-24">
            <div id="reporte-evaluacion" className="scroll-mt-24">
              <EvaluationReportSection evaluationId={lc.activeId} />
            </div>
          </WorkflowGroup>
        )}

        <WorkflowGroup id="historial" label="Historial" className="scroll-mt-24">
          <div id="evaluaciones" className="scroll-mt-24">
            <HistoryCard
              title="Evaluaciones"
              description="Catálogo completo de evaluaciones en el servidor. Haz click para cargar una evaluación pasada y ver su informe."
              items={lc.list}
              isLoading={lc.listQuery.isLoading}
              isError={lc.listQuery.isError}
              errorMessage="No se pudo cargar el catálogo de evaluaciones."
              emptyMessage="Todavía no hay evaluaciones."
              columns={columns}
              actionsWidth="11%"
              onCleanup={() => setConfirmCleanup(true)}
              onPurge={() => setConfirmPurge(true)}
              isCleaning={lc.isCleaning}
              isPurging={lc.isPurging}
              activeId={lc.activeId}
              getRowId={(e) => e.evaluation_id}
              getTimestamp={(e) => e.timestamp}
              getDuration={(e) => e.duration_seconds}
              onSelect={(id) => lc.setActiveId(id)}
              actionsCell={(e) =>
                e.status === "in_progress" ? (
                  <button
                    type="button"
                    aria-label="Cancelar evaluación"
                    disabled={lc.isCancelling}
                    onClick={() => lc.cancel(e.evaluation_id)}
                    className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                  >
                    <XCircle className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <>
                    {e.status === "completed" && (
                      <a
                        href={`${API_BASE_URL}/evaluations/${e.evaluation_id}/report`}
                        target="_blank"
                        rel="noopener noreferrer"
                        aria-label="Ver reporte en nueva pestaña"
                        className="rounded p-1 text-muted-foreground hover:bg-primary/10 hover:text-primary"
                      >
                        <FileText className="h-3.5 w-3.5" />
                      </a>
                    )}
                    {e.status === "completed" && (
                      <DownloadMenu
                        ariaLabel="Descargar evaluación"
                        options={[
                          {
                            label: "Informe HTML",
                            href: `/evaluations/${e.evaluation_id}/download/report`,
                          },
                          {
                            label: "Carpeta completa",
                            href: `/evaluations/${e.evaluation_id}/download`,
                          },
                        ]}
                      />
                    )}
                    <button
                      type="button"
                      aria-label="Eliminar evaluación"
                      disabled={lc.isDeleting}
                      onClick={() => setConfirmDeleteId(e.evaluation_id)}
                      className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </>
                )
              }
            />
          </div>
        </WorkflowGroup>
      </div>

      <NamePromptDialog
        open={startDialogOpen}
        title="Iniciar evaluación"
        description="Asigna un nombre funcional a esta evaluación para identificarla más fácilmente. Puedes dejarlo en blanco y editarlo después."
        confirmLabel="Iniciar evaluación"
        onConfirm={(name) => {
          lc.start({ simulation_id: selectedSimId }, name || undefined);
          setStartDialogOpen(false);
        }}
        onCancel={() => setStartDialogOpen(false)}
      />

      <WizardConfirmDialogs
        texts={{
          delete: {
            title: "¿Eliminar evaluación?",
            description:
              "Se borrarán permanentemente la carpeta de la evaluación y todos sus resultados. Esta acción no se puede deshacer.",
          },
          cleanup: {
            title: "¿Limpiar evaluaciones?",
            description:
              "Se borrarán permanentemente las carpetas vacías y las ejecuciones huérfanas. Esta acción no se puede deshacer.",
          },
          purge: {
            title: "¿Purgar todas las evaluaciones?",
            description:
              "Se eliminarán TODAS las evaluaciones, incluidas las completadas correctamente. Esta acción no se puede deshacer.",
          },
        }}
        confirmDeleteId={confirmDeleteId}
        setConfirmDeleteId={setConfirmDeleteId}
        onDelete={lc.remove}
        confirmCleanup={confirmCleanup}
        setConfirmCleanup={setConfirmCleanup}
        onCleanup={lc.cleanup}
        confirmPurge={confirmPurge}
        setConfirmPurge={setConfirmPurge}
        onPurge={lc.purge}
      />
    </WizardShell>
  );
}
