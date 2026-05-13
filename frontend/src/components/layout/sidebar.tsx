"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Folder, Brain, Sparkles, ShieldCheck, Home, Workflow } from "lucide-react";
import { PIPELINE_STEPS, stepHref } from "@/lib/pipeline-steps";
import { useIsDev } from "@/lib/mode";
import { cn } from "@/lib/utils";

const STEP_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  inspeccion: Folder,
  entrenamiento: Brain,
  generacion: Sparkles,
  auditoria: ShieldCheck,
};

export function Sidebar() {
  const pathname = usePathname();
  const activeIndex = PIPELINE_STEPS.findIndex((s) =>
    pathname?.startsWith(stepHref(s)),
  );
  const isHome = pathname === "/" || pathname === "";
  const isPipelinesPage = pathname?.startsWith("/pipelines") ?? false;
  const isDev = useIsDev();

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
          Área privada
        </div>

        <Link href="/" className={cn(itemBase, isHome ? itemActive : itemIdle)}>
          <Home
            className={cn(
              "h-3.5 w-3.5 shrink-0",
              isHome ? "text-sidebar-accent-foreground" : "text-sidebar-foreground/55",
            )}
          />
          <span className="truncate">Inicio</span>
        </Link>

        <div className="px-4 pb-1 pt-4 text-[10px] font-bold uppercase tracking-[0.08em] text-sidebar-foreground/50">
          Pipeline
        </div>
        <ul>
          {PIPELINE_STEPS.map((step, i) => {
            const href = stepHref(step);
            const isActive = i === activeIndex;
            const Icon = STEP_ICONS[step.slug] ?? Folder;
            return (
              <li key={step.slug}>
                <Link
                  href={href}
                  className={cn(itemBase, isActive ? itemActive : itemIdle)}
                >
                  <Icon
                    className={cn(
                      "h-3.5 w-3.5 shrink-0",
                      isActive
                        ? "text-sidebar-accent-foreground"
                        : "text-sidebar-foreground/55",
                    )}
                  />
                  <span className="truncate">{step.label}</span>
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
            <Link
              href="/pipelines"
              className={cn(itemBase, isPipelinesPage ? itemActive : itemIdle)}
            >
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
