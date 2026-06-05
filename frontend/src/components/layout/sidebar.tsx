"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQueries } from "@tanstack/react-query";
import {
  BarChart3,
  Brain,
  Folder,
  Home,
  LayoutDashboard,
  LoaderCircle,
  Settings,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";
import { api, type EvaluationSummary, type InspectionSummary, type ModelSummary, type SimulationSummary } from "@/lib/api";
import { PIPELINE_STEPS, stepHref } from "@/lib/pipeline-steps";
import { useIsDev } from "@/lib/mode";
import { cn } from "@/lib/utils";

const STEP_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  inspeccion: Folder,
  profiling: BarChart3,
  configuracion: Settings,
  entrenamiento: Brain,
  generacion: Sparkles,
  auditoria: ShieldCheck,
};

export function Sidebar() {
  const pathname = usePathname();
  const activeIndex = PIPELINE_STEPS.findIndex((s) => pathname?.startsWith(stepHref(s)));
  const isLanding = pathname === "/" || pathname === "";
  const isPanel = pathname?.startsWith("/panel") ?? false;
  const isPipelinesPage = pathname?.startsWith("/pipelines") ?? false;
  const isDev = useIsDev();

  const [inspectionsQuery, modelsQuery, simulationsQuery, evaluationsQuery] = useQueries({
    queries: [
      {
        queryKey: ["sidebar", "inspections"],
        queryFn: async () => {
          const { data } = await api.get<InspectionSummary[]>("/inspections/");
          return data;
        },
        refetchInterval: 5000,
      },
      {
        queryKey: ["sidebar", "models"],
        queryFn: async () => {
          const { data } = await api.get<ModelSummary[]>("/models/");
          return data;
        },
        refetchInterval: 5000,
      },
      {
        queryKey: ["sidebar", "simulations"],
        queryFn: async () => {
          const { data } = await api.get<SimulationSummary[]>("/simulations/");
          return data;
        },
        refetchInterval: 5000,
      },
      {
        queryKey: ["sidebar", "evaluations"],
        queryFn: async () => {
          const { data } = await api.get<EvaluationSummary[]>("/evaluations/");
          return data;
        },
        refetchInterval: 5000,
      },
    ],
  });

  const runningBySlug = {
    inspeccion: (inspectionsQuery.data ?? []).some((item) => item.status === "in_progress"),
    profiling: false,
    configuracion: false,
    entrenamiento: (modelsQuery.data ?? []).some((item) => item.status === "in_progress"),
    generacion: (simulationsQuery.data ?? []).some((item) => item.status === "in_progress"),
    auditoria: (evaluationsQuery.data ?? []).some((item) => item.status === "in_progress"),
  } as const;
  const anyRunning = Object.values(runningBySlug).some(Boolean);

  const itemBase =
    "flex w-full items-center gap-2.5 border-l-[3px] px-4 py-2 text-[13px] transition-colors";
  const itemActive =
    "border-l-sidebar-primary bg-sidebar-accent font-bold text-sidebar-accent-foreground";
  const itemIdle =
    "border-l-transparent text-sidebar-foreground/85 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground";

  return (
    <aside className="flex w-60 shrink-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      <nav className="flex-1 overflow-y-auto py-3">
        <div className="px-4 pb-1 pt-3 text-[10px] font-bold uppercase tracking-[0.08em] text-sidebar-foreground/50">
          Visión general
        </div>

        <Link href="/" className={cn(itemBase, isLanding ? itemActive : itemIdle)}>
          <Home
            className={cn(
              "h-3.5 w-3.5 shrink-0",
              isLanding ? "text-sidebar-accent-foreground" : "text-sidebar-foreground/55",
            )}
          />
          <span className="truncate">Inicio</span>
        </Link>

        <Link href="/panel" className={cn(itemBase, isPanel ? itemActive : itemIdle)}>
          <LayoutDashboard
            className={cn(
              "h-3.5 w-3.5 shrink-0",
              isPanel ? "text-sidebar-accent-foreground" : "text-sidebar-foreground/55",
            )}
          />
          <span className="truncate">Sesiones</span>
        </Link>

        <div className="flex items-center gap-2 px-4 pb-1 pt-4 text-[10px] font-bold uppercase tracking-[0.08em] text-sidebar-foreground/50">
          <span>Flujo de trabajo</span>
          {anyRunning && <LoaderCircle className="h-3.5 w-3.5 animate-spin text-primary" />}
        </div>
        <ul>
          {PIPELINE_STEPS.map((step, i) => {
            const href = stepHref(step);
            const isActive = i === activeIndex;
            const Icon = STEP_ICONS[step.slug] ?? Folder;
            const isRunning = runningBySlug[step.slug as keyof typeof runningBySlug];
            return (
              <li key={step.slug}>
                <Link href={href} className={cn(itemBase, isActive ? itemActive : itemIdle)}>
                  <Icon
                    className={cn(
                      "h-3.5 w-3.5 shrink-0",
                      isActive
                        ? "text-sidebar-accent-foreground"
                        : "text-sidebar-foreground/55",
                    )}
                  />
                  <span className="truncate">{step.label}</span>
                  {isRunning && (
                    <LoaderCircle className="ml-auto h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>

        {isDev && (
          <>
            <div className="px-4 pb-1 pt-4 text-[10px] font-bold uppercase tracking-[0.08em] text-sidebar-foreground/50">
              Desarrollo
            </div>
            <Link href="/pipelines" className={cn(itemBase, isPipelinesPage ? itemActive : itemIdle)}>
              <Workflow
                className={cn(
                  "h-3.5 w-3.5 shrink-0",
                  isPipelinesPage
                    ? "text-sidebar-accent-foreground"
                    : "text-sidebar-foreground/55",
                )}
              />
              <span className="truncate">Pipelines</span>
            </Link>
          </>
        )}
      </nav>

      <div className="flex flex-col gap-2 border-t border-sidebar-border bg-white px-4 py-3 dark:bg-white/95">
        <div className="grid grid-cols-2 items-center gap-x-2 gap-y-2">
          <img
            src="/ends-assets/financiado-por-la-union-europea.png"
            alt="Financiado por la Unión Europea — NextGenerationEU"
            className="h-7 w-auto max-w-full object-contain"
          />
          <img
            src="/ends-assets/plan-recuperacion.png"
            alt="Plan de Recuperación, Transformación y Resiliencia"
            className="h-7 w-auto max-w-full object-contain"
          />
          <img
            src="/ends-assets/mtdyfp.png"
            alt="Ministerio para la Transformación Digital y de la Función Pública"
            className="h-7 w-auto max-w-full object-contain"
          />
          <img
            src="/ends-assets/sanidad.png"
            alt="Ministerio de Sanidad"
            className="h-7 w-auto max-w-full object-contain"
          />
        </div>
      </div>
    </aside>
  );
}
