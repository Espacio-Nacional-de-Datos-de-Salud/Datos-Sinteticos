"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useQueries } from "@tanstack/react-query";
import {
  Brain,
  Folder,
  Home,
  LoaderCircle,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  ShieldCheck,
  Sparkles,
  Wand2,
  Workflow,
} from "lucide-react";
import { api, type EvaluationSummary, type InspectionSummary, type ModelSummary, type SimulationSummary } from "@/lib/api";
import { stepHref, PIPELINE_STEPS } from "@/lib/pipeline-steps";
import { usePersistentState } from "@/lib/use-persistent-state";
import { cn } from "@/lib/utils";
import { ENABLE_PIPELINES } from "@/lib/features";

const STEP_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  inspeccion: Folder,
  configuracion: Settings,
  entrenamiento: Brain,
  generacion: Wand2,
  auditoria: ShieldCheck,
};

// Steps that are advanced/optional get a small ✦ marker on their nav tab, the
// same Sparkles language used by AdvancedBadge across the app.
const ADVANCED_STEP_SLUGS = new Set(["configuracion"]);

export function Sidebar() {
  const pathname = usePathname();
  const steps = PIPELINE_STEPS;
  const activeIndex = steps.findIndex((s) => pathname?.startsWith(stepHref(s)));
  const isLanding = pathname === "/" || pathname === "";
  const isPipelinesPage = pathname?.startsWith("/pipelines") ?? false;
  const [collapsed, setCollapsed] = usePersistentState("ends.ui.sidebar.collapsed", false);

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

  // Collapsed: a thin icon-only rail so the user can reclaim horizontal space
  // while keeping the workflow steps one click away.
  if (collapsed) {
    const iconBtn =
      "flex h-9 w-9 items-center justify-center rounded-md border-l-[3px] transition-colors";
    return (
      <aside className="flex w-12 shrink-0 flex-col items-center overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
        <div className="flex h-10 w-full items-center justify-center border-b border-sidebar-border/70">
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            title="Expandir menú"
            aria-label="Expandir menú"
            className="flex h-7 w-7 items-center justify-center rounded text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
          >
            <PanelLeftOpen className="h-4 w-4" />
          </button>
        </div>
        <nav className="flex flex-1 flex-col items-center gap-1 overflow-y-auto py-2">
          <Link
            href="/"
            title="Inicio"
            className={cn(
              iconBtn,
              isLanding ? itemActive : "border-l-transparent text-sidebar-foreground/70 hover:bg-sidebar-accent/60",
            )}
          >
            <Home className="h-4 w-4" />
          </Link>
          {steps.map((step, i) => {
            const Icon = STEP_ICONS[step.slug] ?? Folder;
            const isActive = i === activeIndex;
            const isRunning = runningBySlug[step.slug as keyof typeof runningBySlug];
            const isAdvanced = ADVANCED_STEP_SLUGS.has(step.slug);
            return (
              <Link
                key={step.slug}
                href={stepHref(step)}
                title={isAdvanced ? `${step.label} · avanzado` : step.label}
                className={cn(
                  iconBtn,
                  "relative",
                  isActive ? itemActive : "border-l-transparent text-sidebar-foreground/70 hover:bg-sidebar-accent/60",
                )}
              >
                {isRunning ? (
                  <LoaderCircle className="h-4 w-4 animate-spin text-primary" />
                ) : (
                  <Icon className="h-4 w-4" />
                )}
                {isAdvanced && !isRunning && (
                  <Sparkles className="absolute right-0.5 top-0.5 h-2.5 w-2.5 text-violet-400" />
                )}
              </Link>
            );
          })}
          {ENABLE_PIPELINES && (
            <Link
              href="/pipelines"
              title="Pipelines · avanzado"
              className={cn(
                iconBtn,
                "relative",
                isPipelinesPage ? itemActive : "border-l-transparent text-sidebar-foreground/70 hover:bg-sidebar-accent/60",
              )}
            >
              <Workflow className="h-4 w-4" />
              <Sparkles className="absolute right-0.5 top-0.5 h-2.5 w-2.5 text-violet-400" />
            </Link>
          )}
        </nav>
      </aside>
    );
  }

  return (
    <aside className="flex w-60 shrink-0 flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground">
      <div className="flex h-10 items-center justify-between gap-2 border-b border-sidebar-border/70 px-4">
        <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-sidebar-foreground/50">
          Menú
        </span>
        <button
          type="button"
          onClick={() => setCollapsed(true)}
          title="Contraer menú"
          aria-label="Contraer menú"
          className="flex h-6 w-6 items-center justify-center rounded text-sidebar-foreground/60 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground"
        >
          <PanelLeftClose className="h-4 w-4" />
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto pb-3 pt-1">
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

        <div className="flex items-center gap-2 px-4 pb-1 pt-4 text-[10px] font-bold uppercase tracking-[0.08em] text-sidebar-foreground/50">
          <span>Flujo de trabajo</span>
          {anyRunning && <LoaderCircle className="h-3.5 w-3.5 animate-spin text-primary" />}
        </div>
        <ul>
          {steps.map((step, i) => {
            const href = stepHref(step);
            const isActive = i === activeIndex;
            const Icon = STEP_ICONS[step.slug] ?? Folder;
            const isRunning = runningBySlug[step.slug as keyof typeof runningBySlug];
            const isAdvanced = ADVANCED_STEP_SLUGS.has(step.slug);
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
                  {isAdvanced && (
                    <Sparkles
                      className="ml-1 h-3 w-3 shrink-0 text-violet-400"
                      aria-label="avanzado"
                    />
                  )}
                  {isRunning && (
                    <LoaderCircle className="ml-auto h-3.5 w-3.5 shrink-0 animate-spin text-primary" />
                  )}
                </Link>
              </li>
            );
          })}
        </ul>

        {ENABLE_PIPELINES && (
          <>
            <div className="px-4 pb-1 pt-4 text-[10px] font-bold uppercase tracking-[0.08em] text-sidebar-foreground/50">
              Avanzado
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
              <Sparkles className="ml-1 h-3 w-3 shrink-0 text-violet-400" aria-label="avanzado" />
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
