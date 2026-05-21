// Entrenamiento — step 4 of the pipeline wizard.
//
// Launches a training run from a completed inspection. The user picks which
// inspection to train from; the mostly_ai and rules configs are edited via
// the "Configurar" drawer (which writes to mostly_ai.yaml / rules.yaml that
// the backend reads by default).
//
// Multiple trainings can be launched back-to-back; each completed model
// shows up in the catalog table at the bottom and becomes selectable in
// the Generación step.
//
// All shared lifecycle wiring (queries / mutations / confirm dialogs /
// history table) lives under @/components/pipeline-step. This file owns
// only the kind-specific bits: the form, the per-row metadata, the
// downloadable artefacts, and the Spanish copy.

"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { FileText, Play, Sparkles, Trash2, XCircle } from "lucide-react";

import { ConfigPanel } from "@/components/config/config-drawer";
import { EditableName } from "@/components/jobs/editable-name";
import { ActiveJobCard } from "@/components/pipeline-step/active-job-card";
import { HistoryCard, type HistoryColumn } from "@/components/pipeline-step/history-card";
import { useArtifactLifecycle } from "@/components/pipeline-step/use-artifact-lifecycle";
import { useUpstreamSelection } from "@/components/pipeline-step/use-upstream-selection";
import { WizardConfirmDialogs } from "@/components/pipeline-step/wizard-confirm-dialogs";
import { RulesBanner } from "@/components/config/rules-banner";
import { WizardShell } from "@/components/layout/wizard-shell";
import { WorkflowGroup } from "@/components/layout/workflow-group";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip } from "@/components/ui/tooltip";
import {
  api,
  API_BASE_URL,
  type InspectionSummary,
  type ModelSummary,
} from "@/lib/api";
import { statusBadgeVariant, translateStatus } from "@/lib/job-status";
import { STORAGE_KEYS } from "@/lib/storage-keys";
import { cn } from "@/lib/utils";

type StartInput = { inspection_id: string };

const ENTRENAMIENTO_OUTLINE = [
  { id: "preparacion", label: "Preparación", level: 1 },
  { id: "reglas-preprocesamiento", label: "Reglas de preprocesamiento", level: 2 },
  { id: "nuevo-entrenamiento", label: "Nuevo entrenamiento", level: 2 },
  { id: "configuracion-modelo", label: "Configuración del modelo", level: 2 },
  { id: "ejecutar-entrenamiento", label: "Ejecutar entrenamiento", level: 2 },
  { id: "resultados", label: "Resultados", level: 1 },
  { id: "entrenamiento-actual", label: "Entrenamiento actual", level: 2 },
  { id: "historial", label: "Historial", level: 1 },
  { id: "modelos-entrenados", label: "Modelos entrenados", level: 2 },
] as const;

export default function EntrenamientoPage() {
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
  const [confirmCleanup, setConfirmCleanup] = useState(false);
  const [confirmPurge, setConfirmPurge] = useState(false);

  const lc = useArtifactLifecycle<ModelSummary, StartInput>({
    apiPath: "/models",
    listKey: "models",
    itemKey: "model",
    storageKey: STORAGE_KEYS.model,
    idField: "model_id",
    buildStartBody: (input) => ({ inspection_id: input.inspection_id }),
    labels: {
      startedToast: (id) => `Entrenamiento iniciado: ${id}`,
      startErrorPrefix: "No se pudo iniciar el entrenamiento",
      cancelErrorPrefix: "No se pudo cancelar",
      deletedToast: (id) => `Modelo eliminado: ${id}`,
      deleteErrorPrefix: "No se pudo eliminar",
      cleanupOkToast: (n) => `${n} modelo(s) limpiado(s)`,
      cleanupNoopToast: "Nada que limpiar",
      cleanupErrorPrefix: "Error en limpieza",
      purgeOkToast: (n) => `${n} modelo(s) eliminado(s)`,
      purgeErrorPrefix: "Error al purgar",
    },
  });

  const inspectionsQuery = useQuery({
    queryKey: ["inspections"],
    queryFn: async () => {
      const { data } = await api.get<InspectionSummary[]>("/inspections/");
      return data;
    },
  });
  const completedInspections = (inspectionsQuery.data ?? []).filter(
    (i) => i.status === "completed",
  );

  const { selectedId: selectedInspectionId, setSelectedId: setSelectedInspectionId } =
    useUpstreamSelection(completedInspections, "inspection_id", STORAGE_KEYS.inspection);

  const openReport = (model: ModelSummary) => {
    if (!model.qa_report_filename) {
      toast.info("No hay informes de calidad disponibles para este modelo.");
      return;
    }
    const url = `${API_BASE_URL}/models/${model.model_id}/reports/${model.qa_report_filename}`;
    window.open(url, "_blank");
  };

  const columns: HistoryColumn<ModelSummary>[] = [
    {
      key: "name",
      header: "Nombre",
      width: "24%",
      render: (m) => (
        <div className="space-y-0.5">
          <p
            className="truncate font-mono text-[10px] text-muted-foreground"
            title={m.model_id}
          >
            {m.model_id}
          </p>
          <EditableName
            name={m.model_name || m.model_id}
            existingNames={lc.list.map((x) => x.model_name || x.model_id)}
            onSave={(name) => lc.rename(m.model_id, name)}
          />
        </div>
      ),
    },
    {
      key: "status",
      header: "Estado",
      width: "11%",
      render: (m) => (
        <Badge
          variant={statusBadgeVariant(m.status)}
          className={cn(m.status === "completed" && "!bg-blue-500/20 !text-blue-400")}
        >
          {translateStatus(m.status)}
        </Badge>
      ),
    },
    {
      key: "tables",
      header: "Tablas",
      width: "26%",
      render: (m) => (
        <span className="block truncate font-mono text-xs" title={m.tables || ""}>
          {m.tables || "—"}
        </span>
      ),
    },
    {
      key: "rows",
      header: "Filas",
      width: "13%",
      align: "right",
      render: (m) => (
        <span className="tabular-nums">
          {m.train_size != null ? m.train_size.toLocaleString() : "—"}
        </span>
      ),
    },
    {
      key: "accuracy",
      header: "Precisión",
      width: "13%",
      align: "right",
      render: (m) => (
        <span className="tabular-nums">
          {m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : "—"}
        </span>
      ),
    },
  ];

  return (
    <WizardShell currentSlug="entrenamiento" canAdvance={lc.hasCompleted} outline={ENTRENAMIENTO_OUTLINE}>
      <div className="mx-auto max-w-5xl space-y-6">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Entrenamiento</h1>
          <p className="text-sm text-muted-foreground">
            Lanza un entrenamiento a partir de una inspección completada.
            Puedes encadenar varios entrenamientos; cada uno aparecerá en el
            catálogo de abajo y estará disponible en el paso de{" "}
            <b>Generación</b>.
          </p>
        </div>

        <WorkflowGroup id="preparacion" label="Preparación" defaultOpen className="scroll-mt-24">
          <div id="reglas-preprocesamiento" className="scroll-mt-24">
            <RulesBanner inspectionId={selectedInspectionId || null} />
          </div>

          <div id="nuevo-entrenamiento" className="scroll-mt-24">
            <Card>
              <CardContent className="flex flex-col gap-3 p-4 md:flex-row md:items-end">
              <div className="hidden h-10 w-10 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary md:flex">
                <Sparkles className="h-5 w-5" />
              </div>
              <div className="min-w-0 flex-1 space-y-1">
                <div className="flex items-center gap-2">
                  <Label htmlFor="inspection-select">Nuevo entrenamiento</Label>
                  <Tooltip content="Selecciona la inspección completada sobre la que quieres entrenar el modelo. El modelo aprenderá los patrones de los datos y las reglas de preprocesamiento que definas." />
                </div>
                {inspectionsQuery.isLoading ? (
                  <Skeleton className="h-9 w-full" />
                ) : completedInspections.length === 0 ? (
                  <p className="text-sm text-destructive">
                    No hay inspecciones completadas. Vuelve al paso{" "}
                    <b>Inspección</b>.
                  </p>
                ) : (
                  <select
                    id="inspection-select"
                    value={selectedInspectionId}
                    onChange={(e) => setSelectedInspectionId(e.target.value)}
                    className="w-full rounded-md border bg-background px-3 py-2 font-mono text-xs"
                  >
                    {completedInspections.map((i) => {
                      const tableSummary = Object.keys(i.tables ?? {}).join(", ");
                      return (
                        <option key={i.inspection_id} value={i.inspection_id}>
                          {i.inspection_name || i.inspection_id}
                          {tableSummary ? ` · ${tableSummary}` : ""}
                        </option>
                      );
                    })}
                  </select>
                )}
              </div>
            </CardContent>
            </Card>
          </div>

          <div id="configuracion-modelo" className="scroll-mt-24">
              <ConfigPanel configId="mostly_ai" />
          </div>

          <div id="ejecutar-entrenamiento" className="scroll-mt-24">
            <Card>
              <CardContent className="flex flex-col gap-2 p-4 md:flex-row md:items-center">
                <div className="flex-1 flex items-start gap-2">
                  <p className="text-sm text-muted-foreground pt-0.5">
                    Configura los parámetros del modelo y haz clic en ejecutar.
                  </p>
                  <Tooltip content="El entrenamiento creará un modelo de machine learning basado en los datos de la inspección seleccionada. Este modelo aprendera patrones y sera usado para generar datos sintéticos en el siguiente paso." side="left" />
                </div>
                <Button
                  type="button"
                  disabled={!selectedInspectionId || lc.isStarting || lc.isRunning}
                  onClick={() => lc.start({ inspection_id: selectedInspectionId })}
                >
                  <Play className="mr-2 h-4 w-4" />
                  {lc.isStarting
                    ? "Iniciando…"
                    : lc.isRunning
                      ? "Entrenamiento en curso…"
                      : "Iniciar entrenamiento"}
                </Button>
              </CardContent>
            </Card>
          </div>
        </WorkflowGroup>

        <WorkflowGroup id="resultados" label="Resultados" className="scroll-mt-24">
          <div id="entrenamiento-actual" className="scroll-mt-24">
            <ActiveJobCard
            id={lc.activeId}
            title="Entrenamiento actual"
            description="Estado del último entrenamiento iniciado desde esta sesión."
            isLoading={lc.activeQuery.isLoading}
            isError={lc.activeQuery.isError}
            errorMessage="No se pudo cargar el estado del modelo."
            active={lc.active}
            activeName={lc.active?.model_name || lc.active?.model_id}
            existingNames={lc.list.map((x) => x.model_name || x.model_id)}
            onRename={
              lc.active
                ? (name) => lc.rename(lc.active!.model_id, name)
                : undefined
            }
            metadata={
              lc.active && (
                <div className="flex flex-wrap items-center gap-x-6 gap-y-1 text-xs text-muted-foreground">
                  {lc.active.tables && (
                    <span>
                      Tablas:{" "}
                      <span className="font-mono">{lc.active.tables}</span>
                    </span>
                  )}
                  {lc.active.train_size != null && (
                    <span className="tabular-nums">
                      Filas: {lc.active.train_size.toLocaleString()}
                    </span>
                  )}
                  {lc.active.accuracy != null && (
                    <span className="tabular-nums">
                      Precisión: {(lc.active.accuracy * 100).toFixed(2)}%
                    </span>
                  )}
                </div>
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
                    Cancelar entrenamiento
                  </Button>
                )}
                {lc.active?.status === "completed" && (
                  <Button
                    type="button"
                    size="sm"
                    variant="outline"
                    onClick={() => lc.active && openReport(lc.active)}
                  >
                    <FileText className="mr-2 h-4 w-4" />
                    Ver informe de calidad
                  </Button>
                )}
              </>
            }
            />
          </div>
        </WorkflowGroup>

        <WorkflowGroup id="historial" label="Historial" className="scroll-mt-24">
          <div id="modelos-entrenados" className="scroll-mt-24">
            <HistoryCard
            title="Modelos entrenados"
            description="Catálogo completo de modelos disponibles en el servidor. Haz click para cargar un modelo pasado y ver su estado."
            items={lc.list}
            isLoading={lc.listQuery.isLoading}
            isError={lc.listQuery.isError}
            errorMessage="No se pudo cargar el catálogo de modelos."
            emptyMessage="Todavía no hay modelos entrenados."
            columns={columns}
            actionsWidth="13%"
            collapseLabel="modelos entrenados"
            onCleanup={() => setConfirmCleanup(true)}
            onPurge={() => setConfirmPurge(true)}
            isCleaning={lc.isCleaning}
            isPurging={lc.isPurging}
            activeId={lc.activeId}
            getRowId={(m) => m.model_id}
            onSelect={(id) => lc.setActiveId(id)}
            actionsCell={(m) => (
              <>
                {m.status === "completed" && (
                  <button
                    type="button"
                    aria-label="Ver informe"
                    onClick={() => openReport(m)}
                    className="rounded p-1 text-muted-foreground hover:bg-primary/10 hover:text-primary"
                  >
                    <FileText className="h-3.5 w-3.5" />
                  </button>
                )}
                {m.status === "in_progress" ? (
                  <button
                    type="button"
                    aria-label="Cancelar modelo"
                    disabled={lc.isCancelling}
                    onClick={() => lc.cancel(m.model_id)}
                    className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                  >
                    <XCircle className="h-3.5 w-3.5" />
                  </button>
                ) : (
                  <button
                    type="button"
                    aria-label="Eliminar modelo"
                    disabled={lc.isDeleting}
                    onClick={() => setConfirmDeleteId(m.model_id)}
                    className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive disabled:opacity-40"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                )}
              </>
            )}
            />
          </div>
        </WorkflowGroup>
      </div>

      <WizardConfirmDialogs
        texts={{
          delete: {
            title: "¿Eliminar modelo?",
            description:
              "Se borrarán permanentemente la carpeta del modelo y todos sus artefactos. Esta acción no se puede deshacer.",
          },
          cleanup: {
            title: "¿Limpiar modelos?",
            description:
              "Se borrarán permanentemente las carpetas vacías y las ejecuciones huérfanas. Esta acción no se puede deshacer.",
          },
          purge: {
            title: "¿Purgar todos los modelos?",
            description:
              "Se eliminarán TODOS los modelos, incluidos los completados correctamente. Esta acción no se puede deshacer.",
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
