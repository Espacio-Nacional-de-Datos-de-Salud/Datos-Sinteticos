// Home dashboard. Shows one panel per pipeline step with a preview of the
// latest sessions, plus a global "Purge all" button that wipes every catalog
// (inspections, models, simulations, evaluations) and resets configs.

"use client";

import Link from "next/link";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { Folder, Brain, Sparkles, ShieldCheck, ArrowRight } from "lucide-react";
import {
  api,
  purgeAll,
  type EvaluationSummary,
  type InspectionSummary,
  type ModelSummary,
  type SimulationSummary,
} from "@/lib/api";

type Panel = {
  href: string;
  title: string;
  description: string;
  stage: string;
  queryKey: string;
  endpoint: string;
  idField: string;
  nameField: string;
  Icon: React.ComponentType<{ className?: string }>;
};

const PANELS: Panel[] = [
  {
    href: "/pipeline/inspeccion",
    title: "Inspección",
    description: "Detección de claves, tipos y profiling de los datos crudos.",
    stage: "Etapa 1",
    queryKey: "inspections",
    endpoint: "/inspections/",
    idField: "inspection_id",
    nameField: "inspection_name",
    Icon: Folder,
  },
  {
    href: "/pipeline/entrenamiento",
    title: "Entrenamiento",
    description: "Entrenamiento del generador a partir de una inspección.",
    stage: "Etapa 2",
    queryKey: "models",
    endpoint: "/models/",
    idField: "model_id",
    nameField: "model_name",
    Icon: Brain,
  },
  {
    href: "/pipeline/generacion",
    title: "Generación",
    description: "Síntesis de datos a partir de un modelo entrenado.",
    stage: "Etapa 3",
    queryKey: "simulations",
    endpoint: "/simulations/",
    idField: "simulation_id",
    nameField: "simulation_name",
    Icon: Sparkles,
  },
  {
    href: "/pipeline/auditoria",
    title: "Auditoría",
    description: "Evaluación de calidad y privacidad de los datos sintéticos.",
    stage: "Etapa 4",
    queryKey: "evaluations",
    endpoint: "/evaluations/",
    idField: "evaluation_id",
    nameField: "evaluation_name",
    Icon: ShieldCheck,
  },
];

type AnySummary = InspectionSummary | ModelSummary | SimulationSummary | EvaluationSummary;

function StatusDot({ status }: { status?: string }) {
  const color =
    status === "completed"
      ? "bg-emerald-500"
      : status === "failed"
        ? "bg-red-500"
        : status === "in_progress"
          ? "bg-amber-500"
          : "bg-muted-foreground";
  return <span className={`inline-block h-1.5 w-1.5 rounded-full ${color}`} />;
}

function PanelCard({ panel }: { panel: Panel }) {
  const query = useQuery({
    queryKey: [panel.queryKey],
    queryFn: async () => {
      const { data } = await api.get<AnySummary[]>(panel.endpoint);
      return data;
    },
  });

  const items = query.data ?? [];
  const sorted = [...items].sort((a, b) => (b.timestamp ?? "").localeCompare(a.timestamp ?? ""));
  const preview = sorted.slice(0, 3);
  const Icon = panel.Icon;

  return (
    <div className="flex flex-col overflow-hidden rounded border border-border bg-card text-card-foreground transition-all hover:border-[#9cb9e5] hover:shadow-[0_4px_16px_rgba(0,0,0,0.18)]">
      <div className="flex items-center gap-3 border-b-[3px] border-[#FFDB00] bg-[#00215C] px-[18px] py-4">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded bg-white/10">
          <Icon className="h-4 w-4 text-[#FFDB00]" />
        </div>
        <div>
          <div className="text-[10px] font-bold uppercase tracking-[0.06em] text-white/55">
            {panel.stage}
          </div>
          <div className="text-[14px] font-bold leading-tight text-white">{panel.title}</div>
        </div>
      </div>

      <div className="flex flex-1 flex-col gap-2.5 p-[18px]">
        <p className="text-[13px] leading-[1.55] text-card-foreground/85">{panel.description}</p>

        <div className="text-xs text-muted-foreground">
          {query.isLoading
            ? "Cargando…"
            : query.isError
              ? "No se pudo cargar el catálogo."
              : `${items.length} ${items.length === 1 ? "sesión" : "sesiones"}`}
        </div>

        {preview.length > 0 && (
          <ul className="space-y-1 text-xs">
            {preview.map((item) => {
              const rec = item as unknown as Record<string, string | null | undefined>;
              const id = rec[panel.idField] ?? "";
              const displayName = rec[panel.nameField] || id;
              return (
                <li key={id} className="flex items-center gap-2">
                  <StatusDot status={item.status} />
                  <span className="truncate font-mono text-card-foreground">{displayName}</span>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="border-t border-border p-3">
        <Link
          href={panel.href}
          className="flex w-full items-center justify-center gap-2 rounded bg-[#00215C] py-[9px] text-[13px] font-semibold text-white transition-colors hover:bg-[#04214d] dark:bg-[#FFDB00] dark:text-[#00215C] dark:hover:bg-[#ffe54d]"
        >
          Abrir <ArrowRight className="h-3 w-3" />
        </Link>
      </div>
    </div>
  );
}

export default function Home() {
  const queryClient = useQueryClient();
  const [confirmOpen, setConfirmOpen] = useState(false);

  const purgeMutation = useMutation({
    mutationFn: purgeAll,
    onSuccess: (data) => {
      const total =
        data.inspections.length +
        data.models.length +
        data.simulations.length +
        data.evaluations.length;
      toast.success(
        `Purgado: ${total} ${total === 1 ? "sesión eliminada" : "sesiones eliminadas"}. Configs reiniciados.`,
      );
      queryClient.invalidateQueries();
    },
    onError: (err) => {
      toast.error(`Error al purgar: ${err instanceof Error ? err.message : "desconocido"}`);
    },
  });

  return (
    <div className="h-full overflow-y-auto">
      {/* Welcome banner — navy with yellow underline, mirrors portal-ends. */}
      <div className="relative overflow-hidden border-b-4 border-[#FFDB00] bg-[#00215C] px-8 py-[22px]">
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-[0.08em] text-white/50">
          Bienvenido/a
        </p>
        <h1 className="mb-1.5 text-[21px] font-bold text-white">Datos Sintéticos — ENDS</h1>
        <div className="flex items-center gap-2.5">
          <span className="inline-block whitespace-nowrap rounded border border-white/25 bg-white/15 px-2 py-0.5 text-[11px] font-bold tracking-wide text-white">
            Área privada ENDS
          </span>
          <span className="text-xs text-white/45">
            Herramienta de generación de datos sintéticos tabulares
          </span>
        </div>
        <span className="pointer-events-none absolute right-0 top-0 bottom-0 w-[260px] bg-gradient-to-r from-transparent to-white/[0.04]" />
      </div>

      <div className="px-8 py-7">
        <div className="mb-6 flex items-start justify-between gap-6">
          <div>
            <div className="flex items-center gap-2.5">
              <div className="flex h-8 w-8 items-center justify-center rounded bg-accent text-accent-foreground">
                <Folder className="h-3.5 w-3.5" />
              </div>
              <span className="text-[19px] font-bold text-foreground">Pipeline</span>
            </div>
            <p className="ml-[42px] mt-1 text-[13px] text-muted-foreground">
              Cuatro etapas: inspección, entrenamiento, generación y auditoría.
            </p>
          </div>
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={purgeMutation.isPending}
            onClick={() => setConfirmOpen(true)}
          >
            <Trash2 className="mr-2 h-3.5 w-3.5" />
            {purgeMutation.isPending ? "Limpiando…" : "Limpiar toda la sesión"}
          </Button>
        </div>

        <div className="grid max-w-[1100px] gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {PANELS.map((panel) => (
            <PanelCard key={panel.href} panel={panel} />
          ))}
        </div>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        title="¿Limpiar toda la sesión?"
        description="Esto elimina TODAS las inspecciones, modelos, generaciones y evaluaciones (incluidas las completadas correctamente) y reinicia los archivos de configuración. Esta acción no se puede deshacer."
        confirmLabel="Limpiar todo"
        onConfirm={() => {
          setConfirmOpen(false);
          purgeMutation.mutate();
        }}
        onCancel={() => setConfirmOpen(false)}
      />
    </div>
  );
}
