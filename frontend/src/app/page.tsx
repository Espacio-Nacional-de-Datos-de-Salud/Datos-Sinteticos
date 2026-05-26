"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
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

type SectionData = {
  id: string;
  title: string;
  summary: string;
  content: React.ReactNode;
  Icon: LucideIcon;
};

const CONTENT_SECTIONS: SectionData[] = [
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
        <p>
          El motor incluye mecanismos de privacidad diferencial y genera automáticamente un{" "}
          <strong>informe de calidad</strong> que cuantifica la fidelidad estadística y el riesgo de
          re-identificación de cada modelo entrenado.
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
            term: "Informe de calidad",
            def: "Documento generado automáticamente por MostlyAI tras cada entrenamiento que detalla las métricas de fidelidad y privacidad del modelo, permitiendo validar su idoneidad antes de usar los datos.",
          },
          {
            term: "Integridad referencial",
            def: "Propiedad que garantiza que las relaciones de clave foránea entre tablas se preservan en los datos sintéticos, manteniendo la coherencia en bases de datos relacionales.",
          },
        ].map(({ term, def }) => (
          <li key={term} className="flex gap-2">
            <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-[#00215C]" />
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
            <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-[#00215C]" />
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
            title: "Control de tamaños de muestra",
            desc: "Define el número exacto de filas a generar por tabla, independientemente del tamaño del conjunto de entrenamiento.",
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
            <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-[#00215C]" />
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
            <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-[#00215C]" />
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
            <span className="mt-2.5 h-2 w-2 shrink-0 rounded-full bg-[#00215C]" />
            <span>
              <strong>{title}:</strong> {desc}
            </span>
          </li>
        ))}
      </ul>
    ),
    Icon: FileCog,
  },
];

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
    Object.fromEntries(CONTENT_SECTIONS.map((s) => [s.id, true])),
  );
  const [activeId, setActiveId] = useState<string>(CONTENT_SECTIONS[0].id);
  const [showScrollHint, setShowScrollHint] = useState(true);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const lockUntilRef = useRef(0);

  // Scroll-hint visibility
  useEffect(() => {
    const container = scrollRef.current;
    if (!container) return;
    const onScroll = () => setShowScrollHint(container.scrollTop < 80);
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

  return (
    <div
      ref={scrollRef}
      data-landing-scroll
      className="h-full overflow-y-auto bg-[radial-gradient(circle_at_top_left,_rgba(9,187,217,0.10),_transparent_28%),linear-gradient(180deg,#f7fbff_0%,#eff5fb_48%,#e8effa_100%)]"
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
                Bienvenido a la herramienta de generación de datos sintéticos impulsada por el ENDS.
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
            <Link
              href="/panel"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-white/24 bg-white/10 px-5 py-3 text-sm font-semibold text-white transition-colors hover:bg-white/16"
            >
              Abrir panel
              <Workflow className="h-4 w-4" />
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
      <div className="sticky top-0 z-20 border-b border-border/70 bg-background/95 px-8 py-4 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap gap-2">
          {CONTENT_SECTIONS.map((section) => (
            <button
              key={section.id}
              type="button"
              onClick={() => scrollToSection(section.id)}
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

      {/* ── Content area ── */}
      <div className="mx-auto w-full max-w-7xl space-y-5 px-8 py-8">
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
                      document
                        .getElementById(section.id)
                        ?.scrollIntoView({ behavior: "smooth", block: "start" });
                    });
                  }}
                  className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left"
                >
                  <div className="flex min-w-0 items-center gap-4">
                    <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-[#00215C] text-[#FFDB00]">
                      <Icon className="h-5 w-5" />
                    </div>
                    <div className="min-w-0">
                      <h2 className="text-2xl font-bold text-[#00215C]">{section.title}</h2>
                      <p className="mt-1 text-sm text-slate-600">{section.summary}</p>
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
                      <div>
                        {/* Desktop: numbered nodes on a connecting track */}
                        <div className="relative hidden lg:flex">
                          {/* Solid connecting line behind the circles */}
                          <div className="absolute left-[10%] right-[10%] top-6 h-0.5 bg-[#c9d7ec]" />
                          {WORKFLOW_STEPS.map((step, index) => {
                            const StepIcon = step.Icon;
                            return (
                              <div
                                key={step.title}
                                className="relative flex flex-1 flex-col items-center px-3 text-center"
                              >
                                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-[#00215C] text-base font-bold text-white ring-4 ring-white">
                                  {index + 1}
                                </div>
                                <div className="mt-3 flex h-9 w-9 items-center justify-center rounded-xl bg-[#eef3ff] text-[#114da6]">
                                  <StepIcon className="h-4 w-4" />
                                </div>
                                <h3 className="mb-1 mt-2 text-sm font-semibold text-[#00215C]">
                                  {step.title}
                                </h3>
                                <p className="text-xs leading-relaxed text-slate-500">{step.text}</p>
                              </div>
                            );
                          })}
                        </div>

                        {/* Mobile: vertical numbered list */}
                        <div className="flex flex-col gap-3 lg:hidden">
                          {WORKFLOW_STEPS.map((step, index) => {
                            const StepIcon = step.Icon;
                            return (
                              <div key={step.title} className="flex items-start gap-3">
                                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-[#00215C] text-sm font-bold text-white">
                                  {index + 1}
                                </span>
                                <div className="flex-1 rounded-xl border border-[#d7e1f0] bg-white p-3 shadow-sm">
                                  <div className="mb-1 flex items-center justify-between">
                                    <h3 className="text-sm font-semibold text-[#00215C]">{step.title}</h3>
                                    <StepIcon className="h-4 w-4 shrink-0 text-[#114da6]" />
                                  </div>
                                  <p className="text-xs leading-relaxed text-slate-500">{step.text}</p>
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : (
                      <div className="rounded-2xl border border-[#d8e3f4] bg-[#f7fbff] p-5 text-sm leading-7 text-slate-700">
                        {section.content}
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
