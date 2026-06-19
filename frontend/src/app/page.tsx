"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  ArrowDown,
  ArrowRight,
  ArrowUp,
  BookOpen,
  ChevronDown,
  ChevronRight,
  Database,
  FileCog,
  Layers3,
  Library,
  ListChecks,
  Settings2,
  ShieldCheck,
  Sparkles,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";
import { WorkflowDiagram } from "@/components/landing/workflow-diagram";
import { IconLegend } from "@/components/landing/icon-legend";
import { InfoGroup } from "@/components/landing/info-group";

type SectionData = {
  id: string;
  title: string;
  summary: string;
  content: React.ReactNode;
  Icon: LucideIcon;
};

const LIBRARIES = [
  {
    name: "MostlyAI",
    logo: "/logos/mostlyai.png",
    desc: "Motor de generación de datos sintéticos tabulares mediante deep learning.",
    href: "https://mostly.ai/",
  },
  {
    name: "FastAPI",
    logo: "/logos/fastapi.svg",
    desc: "Framework que expone la API del backend de la herramienta.",
    href: "https://fastapi.tiangolo.com/",
  },
  {
    name: "pandas",
    logo: "/logos/pandas.svg",
    desc: "Manipulación y análisis de los datos tabulares.",
    href: "https://pandas.pydata.org/",
  },
  {
    name: "ydata-profiling",
    logo: "/logos/ydata.png",
    desc: "Generación de los informes de profiling exploratorio.",
    href: "https://github.com/ydataai/ydata-profiling",
  },
  {
    name: "Next.js",
    logo: "/logos/nextdotjs.svg",
    desc: "Framework de React sobre el que se construye esta interfaz.",
    href: "https://nextjs.org/",
  },
  {
    name: "Tailwind CSS",
    logo: "/logos/tailwindcss.svg",
    desc: "Sistema de estilos de la interfaz de usuario.",
    href: "https://tailwindcss.com/",
  },
] as const;

const ALL_SECTIONS: SectionData[] = [
  {
    id: "guia-iconos",
    title: "Guía de iconos",
    summary:
      "Referencia de los iconos y controles globales de la herramienta: dónde encontrarlos y qué hacen o indican.",
    content: null,
    Icon: ListChecks,
  },
  {
    id: "flujo-de-trabajo",
    title: "Flujo de trabajo",
    summary:
      "La herramienta sigue un flujo estructurado en cinco etapas que te guían desde la carga de los datos originales hasta la generación y validación de los datos sintéticos.",
    content: null,
    Icon: Workflow,
  },
  {
    id: "generador",
    title: "Modelos generadores de datos sintéticos",
    summary:
      "Esta herramienta usa la librería MostlyAI como motor de generación, que aprende relaciones complejas entre columnas y tablas para producir datos sintéticos de alta fidelidad.",
    content: (
      <div className="space-y-3">
        <p>
          <strong>MostlyAI</strong> es una librería de Python especializada en la generación de datos
          sintéticos tabulares mediante modelos de deep learning. A diferencia de los métodos estadísticos
          clásicos, MostlyAI aprende distribuciones conjuntas de columnas, relaciones entre tablas y
          dependencias temporales, produciendo datos que se comportan como los originales en análisis
          posteriores.
        </p>
      </div>
    ),
    Icon: Layers3,
  },
  {
    id: "que-son",
    title: "¿Qué son los datos sintéticos?",
    summary:
      "Los datos sintéticos son registros generados artificialmente por IA que replican los patrones estadísticos de datos reales sin contener información de ninguna persona real.",
    content: (
      <div className="space-y-3">
        <p>
          Los datos sintéticos son conjuntos de datos generados por modelos de aprendizaje automático
          entrenados sobre datos reales. El modelo aprende las distribuciones, correlaciones y relaciones
          presentes en los datos originales, y a partir de ese conocimiento produce registros nuevos que
          no corresponden a ningún individuo u organización real.
        </p>
        <p>
          A diferencia de la <strong>anonimización</strong>, que transforma registros existentes, los
          datos sintéticos se crean desde cero. Esto garantiza que no sea posible rastrear un registro
          sintético hasta un individuo real, incluso mediante ataques de re-identificación sofisticados.
        </p>
        <p>
          Se usan principalmente cuando los datos reales son sensibles o de difícil acceso:{" "}
          <strong>investigación clínica</strong> (compartir datos de pacientes sin exponer información
          personal), <strong>desarrollo de software</strong> (entornos de prueba con datos realistas),{" "}
          <strong>entrenamiento de modelos de IA</strong> (ampliar o equilibrar datasets) y{" "}
          <strong>auditoría y cumplimiento</strong> (validar procesos sin acceder a producción).
        </p>
      </div>
    ),
    Icon: BookOpen,
  },
  {
    id: "conceptos-basicos",
    title: "Conceptos básicos sobre datos sintéticos",
    summary:
      "Fidelidad estadística, privacidad y utilidad son los tres ejes que determinan la calidad de un conjunto de datos sintéticos.",
    content: (
      <ul className="space-y-3">
        {[
          {
            term: "Fidelidad estadística",
            def: "Grado en que los datos sintéticos reproducen las distribuciones marginales y conjuntas de los datos originales, incluidas correlaciones, valores extremos y distribuciones condicionales.",
          },
          {
            term: "Privacidad diferencial",
            def: "Garantía formal de que un registro sintético no puede rastrearse hasta ningún individuo real. MostlyAI incorpora métricas de distancia al vecino más cercano para cuantificar este riesgo.",
          },
          {
            term: "Utilidad",
            def: "Medida del rendimiento de modelos predictivos entrenados sobre datos sintéticos frente a los entrenados sobre datos reales. Alta utilidad implica que los datos sintéticos son un sustituto válido.",
          },
          {
            term: "Integridad referencial",
            def: "Propiedad que garantiza que las relaciones de clave foránea entre tablas se preservan en los datos sintéticos, manteniendo la coherencia en bases de datos relacionales.",
          },
        ].map(({ term, def }) => (
          <li key={term} className="flex gap-2">
            <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-[#00215C] dark:bg-[#FFDB00]" />
            <span>
              <strong>{term}:</strong> {def}
            </span>
          </li>
        ))}
      </ul>
    ),
    Icon: Database,
  },
  {
    id: "usos-principales",
    title: "¿Cuáles son los principales usos de esta herramienta?",
    summary:
      "Diseñada para investigación, desarrollo, formación y auditoría en contextos donde los datos reales son sensibles o de difícil acceso.",
    content: (
      <ul className="space-y-3">
        {[
          {
            title: "Investigación y análisis",
            desc: "Comparte datasets con investigadores externos sin exponer datos reales de pacientes u organizaciones, cumpliendo con la normativa de protección de datos (RGPD, LOPD-GDD).",
          },
          {
            title: "Desarrollo y pruebas de software",
            desc: "Proporciona entornos de QA con datos realistas que mantienen la estructura y complejidad de producción sin riesgo de filtración.",
          },
          {
            title: "Entrenamiento de modelos de IA",
            desc: "Amplía datasets escasos, corrige desequilibrios de clases o genera variantes controladas para mejorar la robustez de modelos predictivos.",
          },
          {
            title: "Auditoría y cumplimiento",
            desc: "Permite ejecutar auditorías internas y pruebas de conformidad con datos que replican el comportamiento real sin comprometer la privacidad.",
          },
          {
            title: "Formación y demostraciones",
            desc: "Facilita la formación de equipos técnicos y la realización de demos de producto con datos de apariencia real pero sin información sensible.",
          },
        ].map(({ title, desc }) => (
          <li key={title} className="flex gap-2">
            <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-[#00215C] dark:bg-[#FFDB00]" />
            <span>
              <strong>{title}:</strong> {desc}
            </span>
          </li>
        ))}
      </ul>
    ),
    Icon: Sparkles,
  },
  {
    id: "configuraciones-avanzadas",
    title: "Configuraciones avanzadas",
    summary:
      "La herramienta permite definir reglas de preprocesamiento, generación condicional, control de tamaños de muestra y ajuste de hiperparámetros del modelo.",
    content: (
      <ul className="space-y-3">
        {[
          {
            title: "Reglas de preprocesamiento",
            desc: "Define reglas personalizadas aplicadas antes del entrenamiento para estandarizar valores, recodificar categorías o excluir columnas irrelevantes.",
          },
          {
            title: "Generación condicional",
            desc: "Fija valores de determinadas columnas en la generación para producir subconjuntos de datos que cumplen condiciones específicas de negocio.",
          },
          {
            title: "Configuración del modelo",
            desc: "Ajusta hiperparámetros del generador MostlyAI (épocas, tamaño de batch, etc.) para optimizar el equilibrio entre fidelidad y tiempo de entrenamiento.",
          },
          {
            title: "Relaciones entre tablas",
            desc: "La herramienta detecta automáticamente claves foráneas y preserva la integridad referencial entre tablas relacionadas en los datos generados.",
          },
        ].map(({ title, desc }) => (
          <li key={title} className="flex gap-2">
            <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-[#00215C] dark:bg-[#FFDB00]" />
            <span>
              <strong>{title}:</strong> {desc}
            </span>
          </li>
        ))}
      </ul>
    ),
    Icon: Settings2,
  },
  {
    id: "consideraciones",
    title: "Consideraciones y limitaciones de la herramienta",
    summary:
      "La calidad de los datos sintéticos depende de los datos de origen y requiere validación antes de su uso en producción o investigación.",
    content: (
      <ul className="space-y-3">
        {[
          {
            title: "Calidad dependiente del origen",
            desc: "Datos originales sesgados, incompletos o poco representativos producirán datos sintéticos con los mismos sesgos. Los datos de entrenamiento deben revisarse antes de iniciar el flujo.",
          },
          {
            title: "Eventos raros",
            desc: "Los generadores tienen dificultades para reproducir con fidelidad eventos muy infrecuentes. Las distribuciones de cola pueden no representarse correctamente en datasets pequeños.",
          },
          {
            title: "Volumen mínimo recomendado",
            desc: "Para obtener datos de calidad, el conjunto de entrenamiento debe contener al menos varios cientos de filas por tabla. Con volúmenes muy bajos, la fidelidad decrece significativamente.",
          },
          {
            title: "Validación obligatoria",
            desc: "Antes de usar datos sintéticos en producción o investigación, revisa el informe de calidad y verifica que fidelidad y privacidad cumplen los requisitos del proyecto.",
          },
          {
            title: "No sustituye a la anonimización certificada",
            desc: "Los datos sintéticos no reemplazan los procesos de anonimización certificada en todos los contextos regulatorios. Consulta con el responsable de protección de datos de tu organización.",
          },
        ].map(({ title, desc }) => (
          <li key={title} className="flex gap-2">
            <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-[#00215C] dark:bg-[#FFDB00]" />
            <span>
              <strong>{title}:</strong> {desc}
            </span>
          </li>
        ))}
      </ul>
    ),
    Icon: ShieldCheck,
  },
  {
    id: "casos-de-uso",
    title: "Ejemplos de casos de uso",
    summary:
      "Aplicaciones representativas de la herramienta en el contexto del ENDS y la gestión de datos sanitarios.",
    content: (
      <ul className="space-y-3">
        {[
          {
            title: "Historia clínica electrónica",
            desc: "Generación de registros sintéticos de pacientes que replican diagnósticos, tratamientos y evoluciones, permitiendo a investigadores externos desarrollar y validar modelos clínicos sin acceder a datos reales.",
          },
          {
            title: "Atención primaria",
            desc: "Creación de datasets de consultas médicas sintéticos para entrenar modelos de triaje automático o predicción de riesgo, manteniendo la distribución real de patologías y perfiles demográficos.",
          },
          {
            title: "Facturación sanitaria",
            desc: "Producción de datos de facturación hospitalaria sintéticos para pruebas de integración de sistemas de información y auditorías de procesos administrativos.",
          },
          {
            title: "Formación y concursos",
            desc: "Generación de datasets sanitarios realistas para hackathons, formaciones universitarias y proyectos de ciencia de datos sin comprometer la privacidad de los pacientes.",
          },
        ].map(({ title, desc }) => (
          <li key={title} className="flex gap-2">
            <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-[#00215C] dark:bg-[#FFDB00]" />
            <span>
              <strong>{title}:</strong> {desc}
            </span>
          </li>
        ))}
      </ul>
    ),
    Icon: FileCog,
  },
  {
    id: "tecnologias",
    title: "Tecnologías y librerías",
    summary:
      "La herramienta se apoya en librerías de código abierto consolidadas en la comunidad de ciencia de datos y desarrollo web.",
    content: (
      <div className="space-y-4">
        <p>
          Esta herramienta combina librerías de código abierto ampliamente adoptadas, tanto para el
          procesamiento y la generación de los datos como para la interfaz web. Estas son las
          principales:
        </p>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {LIBRARIES.map((lib) => (
            <a
              key={lib.name}
              href={lib.href}
              target="_blank"
              rel="noopener noreferrer"
              className="group flex flex-col items-center gap-3 rounded-xl border border-[#d8e3f4] bg-white p-4 text-center shadow-sm transition-all hover:-translate-y-0.5 hover:border-[#114da6]/40 hover:shadow-md dark:border-border dark:bg-card"
            >
              <span className="flex h-14 w-14 items-center justify-center rounded-lg bg-white p-2 ring-1 ring-black/5">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={lib.logo}
                  alt={`Logo de ${lib.name}`}
                  className="h-full w-full object-contain"
                  loading="lazy"
                />
              </span>
              <span>
                <span className="block text-sm font-semibold text-[#00215C] dark:text-white">
                  {lib.name}
                </span>
                <span className="mt-1 block text-xs leading-relaxed text-slate-500 dark:text-muted-foreground">
                  {lib.desc}
                </span>
              </span>
            </a>
          ))}
        </div>
      </div>
    ),
    Icon: Library,
  },
];

// Purely descriptive sections (the Q&A / conceptual blocks) are collapsed into a
// single group so the landing page doesn't sprawl. The interactive pieces
// (icon guide, workflow) and the tech stack stay as their own top-level cards.
const INFO_IDS = new Set([
  "generador",
  "que-son",
  "conceptos-basicos",
  "usos-principales",
  "configuraciones-avanzadas",
  "consideraciones",
  "casos-de-uso",
]);

const INFO_SUBSECTIONS = ALL_SECTIONS.filter((s) => INFO_IDS.has(s.id));

const byId = (id: string) => ALL_SECTIONS.find((s) => s.id === id)!;

const CONTENT_SECTIONS: SectionData[] = [
  byId("flujo-de-trabajo"),
  byId("guia-iconos"),
  {
    id: "conceptos",
    title: "Información y conceptos",
    summary:
      "Todo lo que conviene saber sobre los datos sintéticos: qué son, cómo funcionan, usos, configuraciones avanzadas, limitaciones y casos de uso.",
    content: null,
    Icon: BookOpen,
  },
  byId("tecnologias"),
];

export default function LandingPage() {
  const [openSections, setOpenSections] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(CONTENT_SECTIONS.map((s) => [s.id, true])),
  );
  const [activeId, setActiveId] = useState<string>(CONTENT_SECTIONS[0].id);
  const [showScrollHint, setShowScrollHint] = useState(true);
  // Floating "Volver arriba" button — shown once the user has scrolled past the
  // hero so it's reachable at any point, not just at the end of the page.
  const [showBackToTop, setShowBackToTop] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const lockUntilRef = useRef(0);

  // Scroll-hint visibility
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const onScroll = () => {
      setShowScrollHint(container.scrollTop < 80);
      setShowBackToTop(container.scrollTop > 320);
    };
    onScroll();
    container.addEventListener("scroll", onScroll, { passive: true });
    return () => container.removeEventListener("scroll", onScroll);
  }, []);

  // Active-section tracking via scroll events (reliable replacement for IntersectionObserver)
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;

    const updateActive = () => {
      if (Date.now() < lockUntilRef.current) return;
      if (container.scrollTop + container.clientHeight >= container.scrollHeight - 2) {
        setActiveId(CONTENT_SECTIONS[CONTENT_SECTIONS.length - 1].id);
        return;
      }
      const threshold = container.getBoundingClientRect().top + 120;
      let next = CONTENT_SECTIONS[0].id;
      for (const s of CONTENT_SECTIONS) {
        const el = document.getElementById(s.id);
        if (el && el.getBoundingClientRect().top <= threshold) next = s.id;
      }
      setActiveId(next);
    };

    updateActive();
    container.addEventListener("scroll", updateActive, { passive: true });
    return () => container.removeEventListener("scroll", updateActive);
  }, []);

  const scrollToSection = (id: string) => {
    setActiveId(id);
    lockUntilRef.current = Date.now() + 800;
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const scrollToTop = () => {
    lockUntilRef.current = Date.now() + 800;
    setActiveId(CONTENT_SECTIONS[0].id);
    scrollRef.current?.scrollTo({ top: 0, behavior: "smooth" });
  };

  return (
    <div
      ref={scrollRef}
      data-landing-scroll
      className="h-full overflow-y-auto bg-[radial-gradient(circle_at_top_left,_rgba(9,187,217,0.10),_transparent_28%),linear-gradient(180deg,#f7fbff_0%,#eff5fb_48%,#e8effa_100%)] dark:bg-background dark:bg-none"
    >
      {/* ── Hero ── */}
      <section className="relative flex min-h-[calc(100vh-3.5rem)] items-center overflow-hidden border-b-4 border-[#FFDB00] bg-[#00215C] px-8 pt-14 pb-44 text-white">
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
                Bienvenido a la herramienta de generación de datos sintéticos impulsada por el Espacio Nacional de Datos de Salud (ENDS).
                Esta plataforma te permite crear conjuntos de datos sintéticos realistas y seguros,
                ideales para investigación, desarrollo y testeo, sin comprometer la privacidad de los
                datos reales.
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
          </div>
        </div>

        {/* Scroll hint */}
        <button
          type="button"
          onClick={() => scrollToSection(CONTENT_SECTIONS[0].id)}
          aria-label="Desplazarse hacia abajo para ver más contenido"
          className={cn(
            "group absolute bottom-8 left-1/2 z-10 flex -translate-x-1/2 flex-col items-center gap-4 transition-opacity duration-500",
            showScrollHint ? "opacity-100" : "pointer-events-none opacity-0",
          )}
        >
          <span className="text-lg font-semibold uppercase tracking-[0.18em] text-white group-hover:text-white/90">
            Desplázate para saber más
          </span>
          <span className="flex h-16 w-16 animate-bounce items-center justify-center rounded-full border-2 border-[#FFDB00] bg-[#FFDB00]/20 text-[#FFDB00] backdrop-blur transition-colors group-hover:bg-[#FFDB00]/30">
            <ArrowDown className="h-8 w-8" />
          </span>
        </button>
      </section>

      {/* ── Sticky tab bar ── */}
      <div className="sticky top-0 z-20 border-b border-border/70 bg-background/95 px-8 py-2 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap gap-1.5">
          {CONTENT_SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => scrollToSection(section.id)}
              className={cn(
                "rounded-full border px-2.5 py-1 text-xs transition-colors",
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

      {/* ── Content area ── */}
      <div className="mx-auto w-full max-w-7xl space-y-3 px-8 py-6">
        {CONTENT_SECTIONS.map((section) => {
          const Icon = section.Icon;
          const isOpen = openSections[section.id];
          return (
            <section
              key={section.id}
              id={section.id}
              className="scroll-mt-28 rounded-2xl border border-[#d8e3f4] bg-white/92 shadow-[0_12px_32px_rgba(0,33,92,0.06)] backdrop-blur dark:border-border dark:bg-card dark:shadow-[0_12px_32px_rgba(0,0,0,0.4)]"
            >
              <button
                type="button"
                onClick={() => {
                  setOpenSections((prev) => ({ ...prev, [section.id]: !prev[section.id] }));
                  requestAnimationFrame(() => {
                    document
                      .getElementById(section.id)
                      ?.scrollIntoView({ behavior: "smooth", block: "start" });
                  });
                }}
                className="flex w-full items-center justify-between gap-4 px-5 py-3.5 text-left"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-[#00215C] text-[#FFDB00] dark:bg-[#FFDB00] dark:text-[#00215C]">
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <h2 className="text-lg font-bold text-[#00215C] dark:text-white">{section.title}</h2>
                    <p className="mt-0.5 text-xs text-slate-600 dark:text-muted-foreground">{section.summary}</p>
                  </div>
                </div>
                {isOpen ? (
                  <ChevronDown className="h-5 w-5 shrink-0 text-[#114da6] dark:text-[#FFDB00]" />
                ) : (
                  <ChevronRight className="h-5 w-5 shrink-0 text-[#114da6] dark:text-[#FFDB00]" />
                )}
              </button>

              {isOpen && (
                <div className="border-t border-border/70 px-5 py-4">
                  {section.id === "guia-iconos" ? (
                    <IconLegend />
                  ) : section.id === "flujo-de-trabajo" ? (
                    <WorkflowDiagram />
                  ) : section.id === "conceptos" ? (
                    <InfoGroup sections={INFO_SUBSECTIONS} />
                  ) : (
                    <div className="rounded-2xl border border-[#d8e3f4] bg-[#f7fbff] p-5 text-sm leading-7 text-slate-700 dark:border-border dark:bg-accent/40 dark:text-muted-foreground">
                      {section.content}
                    </div>
                  )}
                </div>
              )}
            </section>
          );
        })}

        {/* Back-to-top: closes the page so the user doesn't have to scroll
            all the way back up the long content column by hand. */}
        <div className="flex justify-center pt-2">
          <button
            type="button"
            onClick={scrollToTop}
            className="inline-flex items-center gap-2 rounded-full border border-[#114da6]/30 bg-white px-5 py-2.5 text-sm font-semibold text-[#00215C] shadow-sm transition-colors hover:bg-[#eef3ff] dark:border-border dark:bg-card dark:text-white dark:hover:bg-accent"
          >
            <ArrowUp className="h-4 w-4" />
            Volver arriba
          </button>
        </div>
      </div>

      {/* Floating back-to-top — appears once scrolled past the hero so the
          action is reachable at any scroll position, not only at the page end. */}
      <button
        type="button"
        onClick={scrollToTop}
        aria-label="Volver arriba"
        className={cn(
          "fixed bottom-6 right-6 z-30 inline-flex items-center gap-2 rounded-full border border-[#114da6]/30 bg-white px-4 py-2.5 text-sm font-semibold text-[#00215C] shadow-lg transition-all hover:bg-[#eef3ff] dark:border-border dark:bg-card dark:text-white dark:hover:bg-accent",
          showBackToTop
            ? "opacity-100 translate-y-0"
            : "pointer-events-none translate-y-3 opacity-0",
        )}
      >
        <ArrowUp className="h-4 w-4" />
        Volver arriba
      </button>
    </div>
  );
}
