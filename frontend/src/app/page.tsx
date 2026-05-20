"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import {
  ArrowDown,
  ArrowRight,
  BookOpen,
  Brain,
  ChevronDown,
  ChevronRight,
  Database,
  FileCog,
  Layers3,
  Settings2,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";

const CONTENT_SECTIONS = [
    {
    id: "flujo-de-trabajo",
    title: "Flujo de trabajo",
    body:
      "Con esta herramienta podrás generar datos sintéticos basados en tablas de datos reales, dando lugar a datos que se ajusten a tu contexto de negocio específico. Los modelos que podrás entrenar no reproducen simplemente distribuciones estadísticas de los datos de origen, sino que aprenden sobre relaciones complejas existentes en los datos. El flujo de trabajo de la herramienta consta de las siguientes etapas:",
    Icon: Workflow,
  },
  {
    id: "generador",
    title: "Modelos generadores de datos sintéticos",
    summary:
      "Esta herramienta hace uso de la librería de python MostlyAI como motor de generación.",
    content:
      "MostlyAI permite crear datos sintéticos realistas a partir de ejemplos reales y ofrece controles de privacidad integrados.",
    Icon: Layers3,
  },
  {
    id: "que-son",
    title: "¿Qué son los datos sintéticos?",
    body:
      "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed commodo augue ut facilisis scelerisque. Praesent at lectus vel urna blandit pulvinar vel sed est.",
    Icon: BookOpen,
  },
  {
    id: "conceptos-basicos",
    title: "Conceptos básicos sobre datos sintéticos",
    body:
      "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Vestibulum ac urna sed risus placerat aliquam. Integer hendrerit velit ac neque fermentum, vitae pulvinar tortor dignissim.",
    Icon: Database,
  },
  {
    id: "usos-principales",
    title: "¿Cuáles son los principales usos de esta herramienta?",
    body:
      "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Nulla facilisi. Cras interdum, tellus non rhoncus efficitur, risus nibh consequat arcu, eu suscipit augue sem sit amet tortor.",
    Icon: Sparkles,
  },
  {
    id: "configuraciones-avanzadas",
    title: "Configuraciones avanzadas",
    body:
      "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Aenean venenatis lectus a sapien posuere, a pretium erat consequat. Suspendisse non eros nisi.",
    Icon: Settings2,
  },
  {
    id: "consideraciones",
    title: "Consideraciones y limitaciones de la herramienta",
    body:
      "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Aliquam erat volutpat. Sed bibendum, mauris at volutpat porttitor, nulla odio fermentum est, sed cursus neque libero vitae lectus.",
    Icon: ShieldCheck,
  },
  {
    id: "casos-de-uso",
    title: "Ejemplos de casos de uso",
    body:
      "Lorem ipsum dolor sit amet, consectetur adipiscing elit. In hac habitasse platea dictumst. Nam sodales congue orci, nec hendrerit nisi bibendum sed.",
    Icon: FileCog,
  },
] as const;

const WORKFLOW_STEPS = [
  {
    title: "Inspección",
    text: "Análisis inicial de tablas, claves, tipos y estructura de los datos de entrada.",
    Icon: Database,
  },
  {
    title: "Profiling",
    text: "Lectura visual de informes para entender tablas, distribuciones y anomalías.",
    Icon: BookOpen,
  },
  {
    title: "Entrenamiento",
    text: "Configuración y entrenamiento del generador a partir de una inspección validada.",
    Icon: Brain,
  },
  {
    title: "Generación",
    text: "Producción de datos sintéticos con controles de tamaño, formato y condiciones.",
    Icon: Sparkles,
  },
  {
    title: "Auditoría",
    text: "Evaluación final de utilidad, calidad y privacidad del resultado sintético.",
    Icon: ShieldCheck,
  },
] as const;

export default function LandingPage() {
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(CONTENT_SECTIONS.map((section) => [section.id, true])),
  );
  const [activeId, setActiveId] = useState(CONTENT_SECTIONS[0].id);

  useEffect(() => {
    const elements = CONTENT_SECTIONS.map((section) => document.getElementById(section.id)).filter(
      (element): element is HTMLElement => Boolean(element),
    );
    if (elements.length === 0) return;

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length > 0) setActiveId(visible[0].target.id);
      },
      {
        rootMargin: "-18% 0px -65% 0px",
        threshold: [0, 0.2, 0.5, 1],
      },
    );

    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, []);

  return (
    <div className="h-full overflow-y-auto bg-[radial-gradient(circle_at_top_left,_rgba(9,187,217,0.10),_transparent_28%),linear-gradient(180deg,#f7fbff_0%,#eff5fb_48%,#e8effa_100%)]">
      <section className="relative flex min-h-[calc(100vh-3.5rem)] items-center overflow-hidden border-b-4 border-[#FFDB00] bg-[#00215C] px-8 py-14 text-white">
        <div className="absolute inset-y-0 right-0 w-[40rem] bg-[radial-gradient(circle_at_center,_rgba(255,255,255,0.16),_transparent_58%)]" />
        <div className="absolute left-0 right-0 top-0 h-full bg-[linear-gradient(135deg,transparent_0%,transparent_58%,rgba(255,255,255,0.05)_100%)]" />
        <div className="relative mx-auto flex w-full max-w-7xl flex-col gap-10 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-4xl space-y-5">
            <span className="inline-flex items-center rounded-full border border-white/18 bg-white/10 px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.14em] text-white/78">
              Espacio Nacional de Datos de Salud
            </span>
            <div className="space-y-4">
              <h1 className="max-w-4xl text-4xl font-bold tracking-tight text-white sm:text-5xl lg:text-6xl">
                Generador de datos sintéticos tabulares del ENDS
              </h1>
              <p className="max-w-3xl text-base leading-8 text-white/76">
                Bienvenido a la herramienta de generación de datos sintéticos impulsada por el ENDS. Esta plataforma te permite crear conjuntos de datos sintéticos realistas y seguros, ideales para investigación, desarrollo y testeo, sin comprometer la privacidad de los datos reales. En esta página encontrarás contenido informativo sobre la herramienta y sus capacidades.
              </p>
            </div>
          </div>

          <div className="grid gap-3 sm:grid-cols-2 lg:min-w-[25rem]">
            <Link
              href="/pipeline/inspeccion"
              className="inline-flex items-center justify-center gap-2 rounded-xl bg-[#FFDB00] px-5 py-3 text-sm font-semibold text-[#00215C] transition-colors hover:bg-[#ffe54d]"
            >
              Empezar flujo
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              href="/panel"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/24 bg-white/10 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/16"
            >
              Abrir panel
              <Workflow className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>

      <div className="sticky top-0 z-20 border-b border-border/70 bg-background/95 px-8 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap gap-2">
          {CONTENT_SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => {
                document.getElementById(section.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
              }}
              className={cn(
                "rounded-full border px-3 py-1.5 text-sm transition-colors",
                activeId === section.id
                  ? "border-primary bg-accent text-accent-foreground"
                  : "border-border bg-card text-muted-foreground hover:bg-accent/70 hover:text-foreground",
              )}
            >
              {section.title}
            </button>
          ))}
        </div>
      </div>

      <div className="mx-auto flex w-full max-w-7xl flex-col gap-5 px-8 py-8">
        {CONTENT_SECTIONS.map((section) => {
          const Icon = section.Icon;
          const isOpen = openSections[section.id];
          return (
            <section
              key={section.id}
              id={section.id}
              className="scroll-mt-28 rounded-3xl border border-[#d8e3f4] bg-white/92 shadow-[0_18px_48px_rgba(0,33,92,0.08)] backdrop-blur"
            >
              <button
                type="button"
                onClick={() => {
                  setOpenSections((prev) => ({ ...prev, [section.id]: !prev[section.id] }));
                  requestAnimationFrame(() => {
                    document.getElementById(section.id)?.scrollIntoView({ behavior: "smooth", block: "start" });
                  });
                }}
                className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left"
              >
                <div className="flex min-w-0 items-center gap-4">
                  <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-[#00215C] text-[#FFDB00]">
                    <Icon className="h-5 w-5" />
                  </div>
                  <div>
                    <h2 className="text-2xl font-bold text-[#00215C]">{section.title}</h2>
                    <p className="mt-1 text-sm text-slate-600">{section.body}</p>
                  </div>
                </div>
                {isOpen ? (
                  <ChevronDown className="h-5 w-5 shrink-0 text-[#114da6]" />
                ) : (
                  <ChevronRight className="h-5 w-5 shrink-0 text-[#114da6]" />
                )}
              </button>

              {isOpen && (
                <div className="border-t border-border/70 px-6 py-6">
                  {section.id === "flujo-de-trabajo" ? (
                    <div className="grid gap-5 lg:grid-cols-[minmax(0,280px)_56px_minmax(0,280px)_56px_minmax(0,280px)] xl:grid-cols-[repeat(5,minmax(0,1fr))] xl:items-stretch">
                      {WORKFLOW_STEPS.map((step, index) => {
                        const StepIcon = step.Icon;
                        const isLast = index === WORKFLOW_STEPS.length - 1;
                        return (
                          <div key={step.title} className="contents">
                            <article className="relative overflow-hidden rounded-3xl border border-[#d7e1f0] bg-[linear-gradient(180deg,#ffffff_0%,#f7fbff_100%)] p-5 shadow-[0_10px_30px_rgba(0,33,92,0.08)]">
                              <div className="mb-4 flex items-center justify-between gap-3">
                                <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-[#e8effa] text-[#00215C]">
                                  <StepIcon className="h-5 w-5" />
                                </div>
                                <span className="rounded-full bg-[#00215C] px-2.5 py-1 text-[10px] font-bold uppercase tracking-[0.12em] text-white">
                                  Etapa {index + 1}
                                </span>
                              </div>
                              <h3 className="mb-2 text-lg font-bold text-[#00215C]">{step.title}</h3>
                              <p className="text-sm leading-6 text-slate-600">{step.text}</p>
                              <div className="pointer-events-none absolute -right-8 -top-8 h-24 w-24 rounded-full bg-[#09BBD9]/10" />
                            </article>
                            {!isLast && (
                              <div className="hidden items-center justify-center xl:flex">
                                <div className="flex h-12 w-12 items-center justify-center rounded-full border border-[#c9d7ec] bg-white text-[#114da6] shadow-sm">
                                  <ArrowRight className="h-4 w-4" />
                                </div>
                              </div>
                            )}
                            {!isLast && (
                              <div className="flex items-center justify-center xl:hidden">
                                <div className="flex h-10 w-10 items-center justify-center rounded-full border border-[#c9d7ec] bg-white text-[#114da6] shadow-sm">
                                  <ArrowDown className="h-4 w-4" />
                                </div>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <div className="rounded-2xl border border-[#d8e3f4] bg-[#f7fbff] p-5 text-sm leading-7 text-slate-700">
                      <p>
                        {section.body}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </section>
          );
        })}
      </div>
    </div>
  );
}
