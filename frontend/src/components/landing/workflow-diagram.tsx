"use client";

import { Fragment, useState } from "react";
import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import {
  ArrowRight,
  Brain,
  ChevronDown,
  ChevronRight,
  ChevronsDownUp,
  ChevronsUpDown,
  Folder,
  Settings,
  ShieldCheck,
  Sparkles,
  Wand2,
} from "lucide-react";

import { cn } from "@/lib/utils";

// ── Workflow model ──────────────────────────────────────────────────────────
// Each stage maps to a /pipeline/<slug> page. Its groups + children mirror the
// real page outline (PageOutline items), so every row deep-links to the exact
// section it describes via /pipeline/<slug>#<id>. Each row also carries a very
// short, executive `desc` so the diagram reads on its own, not only as a link.

type SubSubStep = { id: string; label: string; desc: string; advanced?: boolean };
type SubStep = { id: string; label: string; desc: string; advanced?: boolean; children?: SubSubStep[] };
type SubGroup = {
  id: string;
  label: string;
  desc: string;
  advanced?: boolean;
  children?: SubStep[];
};
type Stage = {
  slug: string;
  title: string;
  text: string;
  Icon: LucideIcon;
  advanced?: boolean;
  groups: SubGroup[];
};

const STAGES: Stage[] = [
  {
    slug: "inspeccion",
    title: "Carga de Datos",
    text: "Carga y análisis inicial de las tablas, con detección de claves, tipos y estructura e informes de profiling.",
    Icon: Folder,
    groups: [
      {
        id: "preparacion",
        label: "Selección de ficheros",
        desc: "Sube los ficheros origen y lanza la carga.",
        children: [
          { id: "seleccion-ficheros", label: "Seleccionar ficheros", desc: "Elige los CSV/Excel de entrada." },
          { id: "visualizacion-columnas", label: "Visualización y eliminación de columnas", desc: "Revisa y descarta columnas." },
          { id: "ejecutar-carga", label: "Ejecución de la carga", desc: "Lanza el análisis inicial." },
        ],
      },
      {
        id: "resultados",
        label: "Autodetección",
        desc: "La herramienta infiere la estructura de los datos.",
        children: [
          { id: "tablas-detectadas", label: "Tablas detectadas", desc: "Tablas y su tamaño." },
          { id: "relaciones-detectadas", label: "Relaciones detectadas", desc: "Se puede revisar lo detectado.", children: [
            { id: "relaciones-modificar", label: "Modificar relaciones", desc: "Edita o añade claves foráneas manualmente.", advanced: true },
          ]},
          { id: "tipos-codificacion", label: "Tipos de codificación", desc: "Se puede revisar lo detectado.", children: [
            { id: "tipos-modificar", label: "Modificar tipos", desc: "Cambia el tipo de codificación por columna.", advanced: true },
          ]},
        ],
      },
      {
        id: "datos-preprocesados",
        label: "Datos preprocesados",
        desc: "Vista de los datos ya cargados.",
        children: [{ id: "visualizacion-datos", label: "Visualización de datos", desc: "Previsualiza las filas resultantes." }],
      },
      {
        id: "profiling",
        label: "Perfilado",
        desc: "Informe estadístico exploratorio.",
        children: [{ id: "informes-profiling", label: "Informes de perfilado", desc: "Abre los informes de profiling." }],
      },
      {
        id: "historial",
        label: "Historial",
        desc: "Cargas anteriores.",
        children: [{ id: "inspecciones-previas", label: "Cargas de Datos previas", desc: "Reabre una carga anterior." }],
      },
    ],
  },
  {
    slug: "configuracion",
    title: "Reglas de negocio",
    text: "Definición de reglas de preprocesamiento, exclusión de columnas y validaciones aplicadas antes de entrenar.",
    Icon: Settings,
    advanced: true,
    groups: [
      { id: "biblioteca-reglas", label: "Biblioteca de reglas", desc: "Gestiona sets de reglas guardados.", advanced: true, children: [
        { id: "biblioteca-cargar", label: "Cargar configuración guardada", desc: "Recupera un set de reglas de la biblioteca o de una ejecución anterior." },
        { id: "biblioteca-guardar", label: "Guardar set de reglas", desc: "Archiva las reglas actuales para reutilizarlas sin necesidad de ejecutar." },
      ]},
      {
        id: "columnas",
        label: "Crear / eliminar columnas",
        desc: "Ajusta el esquema de columnas.",
        children: [
          { id: "columnas-derivadas", label: "Columnas derivadas", desc: "Crea columnas calculadas.", advanced: true },
          { id: "columnas-eliminar", label: "Eliminar columnas", desc: "Quita columnas no deseadas." },
        ],
      },
      {
        id: "reglas-logicas",
        label: "Reglas lógicas / de negocio",
        desc: "Restricciones y validaciones de dominio.",
        advanced: true,
        children: [{ id: "reglas-logicas-editor", label: "Editor de reglas", desc: "Define las reglas en el editor.", advanced: true }],
      },
      {
        id: "resultados",
        label: "Preprocesamiento de datos",
        desc: "Aplica las reglas sobre los datos.",
        children: [
          { id: "ejecucion-preprocesamiento", label: "Ejecución de preprocesamiento", desc: "Lanza el preprocesamiento." },
          { id: "resumen-cambios", label: "Resumen de cambios aplicados", desc: "Qué cambió tras aplicar." },
          { id: "datos-preprocesados", label: "Visualización de datos", desc: "Previsualiza el resultado." },
        ],
      },
      {
        id: "historial",
        label: "Historial",
        desc: "Configuraciones previas.",
        children: [{ id: "ejecuciones-previas", label: "Ejecuciones previas", desc: "Reabre una ejecución." }],
      },
    ],
  },
  {
    slug: "entrenamiento",
    title: "Entrenamiento",
    text: "Configuración y entrenamiento del generador a partir de una carga de datos validada.",
    Icon: Brain,
    groups: [
      {
        id: "preparacion",
        label: "Configuración",
        desc: "Prepara y lanza el entrenamiento.",
        children: [
          { id: "nuevo-entrenamiento", label: "Selector de reglas", desc: "Elige el conjunto de reglas." },
          { id: "configuracion-modelo", label: "Configuración del modelo", desc: "Hiperparámetros del generador.", children: [
            { id: "configuracion-modelo-per-table", label: "Configuración por tabla", desc: "Ajusta hiperparámetros individualmente por tabla.", advanced: true },
          ]},
          { id: "ejecutar-entrenamiento", label: "Ejecución del entrenamiento", desc: "Lanza el entrenamiento." },
        ],
      },
      {
        id: "resultados",
        label: "Resultados",
        desc: "Estado del modelo entrenado.",
        children: [{ id: "entrenamiento-actual", label: "Entrenamiento actual", desc: "Progreso y métricas." }],
      },
      {
        id: "historial",
        label: "Historial",
        desc: "Modelos anteriores.",
        children: [{ id: "modelos-entrenados", label: "Modelos entrenados", desc: "Reutiliza un modelo previo." }],
      },
    ],
  },
  {
    slug: "generacion",
    title: "Generación",
    text: "Producción de datos sintéticos con controles de tamaño, formato y condiciones.",
    Icon: Wand2,
    groups: [
      {
        id: "preparacion",
        label: "Preparación",
        desc: "Configura y lanza la generación.",
        children: [
          { id: "nueva-generacion", label: "Selección de modelo", desc: "Elige el modelo entrenado." },
          { id: "configuracion-volumen", label: "Configuración de volumen", desc: "Nº de filas a generar.", children: [
            { id: "configuracion-volumen-tablas", label: "Volumen por tabla hija", desc: "Ajusta el volumen de cada tabla hija individualmente.", advanced: true },
          ]},
          { id: "condiciones", label: "Condicionar la generación", desc: "Fija valores condicionales.", advanced: true },
          { id: "ejecutar-generacion", label: "Ejecutar generación", desc: "Lanza la generación." },
        ],
      },
      {
        id: "resultados",
        label: "Resultados",
        desc: "Salida sintética producida.",
        children: [
          { id: "generacion-actual", label: "Generación actual", desc: "Estado de la generación." },
          { id: "datos-sinteticos", label: "Datos sintéticos", desc: "Previsualiza y descarga." },
        ],
      },
      {
        id: "historial",
        label: "Historial",
        desc: "Generaciones previas.",
        children: [{ id: "generaciones", label: "Generaciones", desc: "Reabre una generación." }],
      },
    ],
  },
  {
    slug: "auditoria",
    title: "Auditoría",
    text: "Evaluación final de utilidad, calidad y privacidad del resultado sintético.",
    Icon: ShieldCheck,
    groups: [
      {
        id: "preparacion",
        label: "Preparación",
        desc: "Configura y lanza la evaluación.",
        children: [
          { id: "nueva-evaluacion", label: "Nueva evaluación", desc: "Elige qué resultado evaluar." },
          { id: "reglas-preprocesamiento", label: "Reglas de negocio", desc: "Reglas de referencia." },
          { id: "configuracion-avanzada", label: "Configuración avanzada", desc: "Ajustes de los ejes de evaluación.", children: [
            { id: "config-privacidad", label: "Privacidad", desc: "Umbrales y métricas de privacidad." },
            { id: "config-fidelidad", label: "Fidelidad", desc: "Métricas de similitud estadística." },
            { id: "config-utilidad", label: "Utilidad", desc: "Métricas de validez para casos de uso reales.", advanced: true },
          ]},
          { id: "ejecutar-evaluacion", label: "Ejecutar evaluación", desc: "Lanza la evaluación." },
        ],
      },
      {
        id: "resultados",
        label: "Resultados",
        desc: "Métricas de calidad y privacidad.",
        children: [{ id: "evaluacion-actual", label: "Evaluación actual", desc: "Estado de la evaluación." }],
      },
      {
        id: "reporte",
        label: "Reporte",
        desc: "Informe final de la auditoría.",
        children: [{ id: "reporte-evaluacion", label: "Detalle del reporte", desc: "Fidelidad, utilidad y privacidad." }],
      },
      {
        id: "historial",
        label: "Historial",
        desc: "Evaluaciones previas.",
        children: [{ id: "evaluaciones", label: "Evaluaciones", desc: "Reabre una evaluación." }],
      },
    ],
  },
];

const stepHref = (slug: string, id: string) => `/pipeline/${slug}#${id}`;

// ── Detail panel (groups → children of the selected stage) ───────────────────

function StageDetail({ stage }: { stage: Stage }) {
  const groupsWithChildren = stage.groups.filter((g) => g.children && g.children.length > 0);
  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(stage.groups.map((g) => [g.id, true])),
  );

  const allOpen = groupsWithChildren.every((g) => openGroups[g.id]);
  const toggleAll = () =>
    setOpenGroups(Object.fromEntries(stage.groups.map((g) => [g.id, !allOpen])));

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-[#00215C] dark:text-white">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-[#00215C] text-[#FFDB00] dark:bg-[#FFDB00] dark:text-[#00215C]">
            <stage.Icon className="h-4 w-4" />
          </span>
          Pasos dentro de «{stage.title}»
        </div>
        <div className="flex items-center gap-2">
          {groupsWithChildren.length > 0 && (
            <button
              type="button"
              onClick={toggleAll}
              className="inline-flex items-center gap-1 rounded-full border border-[#d8e3f4] bg-white px-2.5 py-1 text-xs font-medium text-[#114da6] transition-colors hover:bg-[#eef3ff] dark:border-border dark:bg-card dark:text-[#FFDB00] dark:hover:bg-accent"
            >
              {allOpen ? <ChevronsDownUp className="h-3.5 w-3.5" /> : <ChevronsUpDown className="h-3.5 w-3.5" />}
              {allOpen ? "Contraer todo" : "Expandir todo"}
            </button>
          )}
          <Link
            href={`/pipeline/${stage.slug}`}
            className="inline-flex items-center gap-1 rounded-full bg-[#FFDB00] px-3 py-1 text-xs font-semibold text-[#00215C] transition-colors hover:bg-[#ffe54d]"
          >
            Ir a la etapa
            <ArrowRight className="h-3.5 w-3.5" />
          </Link>
        </div>
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2 xl:grid-cols-3">
        {stage.groups.map((group, gi) => {
          const hasChildren = !!group.children?.length;
          const isOpen = openGroups[group.id];
          const groupNum = gi + 1;
          return (
            <div
              key={group.id}
              className="rounded-xl border border-[#d8e3f4] bg-white shadow-sm dark:border-border dark:bg-card"
            >
              <div className="flex items-stretch">
                <Link
                  href={stepHref(stage.slug, group.id)}
                  className="group flex flex-1 items-start gap-2.5 px-3 py-2.5 text-left"
                >
                  <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md bg-[#00215C] text-[11px] font-bold text-white dark:bg-[#FFDB00] dark:text-[#00215C]">
                    {groupNum}
                  </span>
                  <span className="min-w-0">
                    <span className="flex items-center gap-1 text-sm font-semibold text-[#00215C] dark:text-white">
                      <span className="group-hover:underline">{group.label}</span>
                      {group.advanced && (
                        <Sparkles className="h-3 w-3 shrink-0 text-violet-400" aria-label="avanzado" />
                      )}
                    </span>
                    <span className="mt-0.5 block text-[11px] leading-snug text-slate-500 dark:text-muted-foreground">
                      {group.desc}
                    </span>
                  </span>
                </Link>
                {hasChildren && (
                  <button
                    type="button"
                    aria-label={isOpen ? `Contraer ${group.label}` : `Expandir ${group.label}`}
                    aria-expanded={isOpen}
                    onClick={() =>
                      setOpenGroups((prev) => ({ ...prev, [group.id]: !prev[group.id] }))
                    }
                    className="flex w-9 shrink-0 items-center justify-center rounded-r-xl border-l border-[#eef0f6] text-[#114da6] transition-colors hover:bg-[#eef3ff] dark:border-border dark:text-[#FFDB00] dark:hover:bg-accent"
                  >
                    {isOpen ? (
                      <ChevronDown className="h-4 w-4" />
                    ) : (
                      <ChevronRight className="h-4 w-4" />
                    )}
                  </button>
                )}
              </div>
              {hasChildren && isOpen && (
                <ul className="space-y-0.5 border-t border-[#eef0f6] px-2 py-1.5 dark:border-border">
                  {group.children!.map((child, ci) => (
                    <li key={child.id}>
                      <Link
                        href={stepHref(stage.slug, child.id)}
                        className="group flex items-start gap-2 rounded-lg px-2 py-1.5 transition-colors hover:bg-[#eef3ff] dark:hover:bg-accent"
                      >
                        <span className="mt-0.5 shrink-0 text-[10px] font-bold tabular-nums text-[#9fb1cf] group-hover:text-[#114da6] dark:group-hover:text-[#FFDB00]">
                          {groupNum}.{ci + 1}
                        </span>
                        <span className="min-w-0">
                          <span className="flex items-center gap-1 text-xs font-medium text-slate-700 group-hover:text-[#00215C] dark:text-muted-foreground dark:group-hover:text-white">
                            {child.label}
                            {child.advanced && (
                              <Sparkles className="h-2.5 w-2.5 shrink-0 text-violet-400" aria-label="avanzado" />
                            )}
                          </span>
                          <span className="block text-[11px] leading-snug text-slate-400 dark:text-muted-foreground/70">
                            {child.desc}
                          </span>
                        </span>
                      </Link>
                      {child.children && child.children.length > 0 && (
                        <ul className="ml-6 mt-0.5 space-y-0.5 border-l border-[#eef0f6] pl-2 dark:border-border">
                          {child.children.map((sub, si) => (
                            <li key={sub.id}>
                              <Link
                                href={stepHref(stage.slug, sub.id)}
                                className="group flex items-start gap-2 rounded-lg px-2 py-1 transition-colors hover:bg-[#eef3ff] dark:hover:bg-accent"
                              >
                                <span className="mt-0.5 shrink-0 text-[10px] font-bold tabular-nums text-[#c4d2e6] group-hover:text-[#114da6] dark:group-hover:text-[#FFDB00]">
                                  {groupNum}.{ci + 1}.{si + 1}
                                </span>
                                <span className="min-w-0">
                                  <span className="flex items-center gap-1 text-xs font-medium text-slate-600 group-hover:text-[#00215C] dark:text-muted-foreground dark:group-hover:text-white">
                                    {sub.label}
                                    {sub.advanced && (
                                      <Sparkles className="h-2.5 w-2.5 shrink-0 text-violet-400" aria-label="avanzado" />
                                    )}
                                  </span>
                                  <span className="block text-[11px] leading-snug text-slate-400 dark:text-muted-foreground/70">
                                    {sub.desc}
                                  </span>
                                </span>
                              </Link>
                            </li>
                          ))}
                        </ul>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Public component ─────────────────────────────────────────────────────────

export function WorkflowDiagram() {
  // Index of the expanded stage, or null when the flow is fully collapsed.
  const [selected, setSelected] = useState<number | null>(null);
  const selectedStage = selected === null ? null : STAGES[selected];

  return (
    <div className="space-y-4">
      {/* Big picture: a connected flow of stage cards. Click to disaggregate. */}
      <div className="relative">
        <div className="flex flex-col gap-2 lg:flex-row lg:items-stretch lg:gap-1">
          {STAGES.map((stage, index) => {
            const isSelected = index === selected;
            const StageIcon = stage.Icon;
            return (
              <Fragment key={stage.slug}>
                <button
                  type="button"
                  aria-expanded={isSelected}
                  onClick={() => setSelected(isSelected ? null : index)}
                  className={cn(
                    "group relative flex flex-1 flex-col gap-2 rounded-2xl border p-4 text-left transition-all",
                    isSelected
                      ? "border-[#114da6] bg-[#00215C] text-white shadow-lg dark:border-[#FFDB00] dark:bg-[#FFDB00] dark:text-[#00215C]"
                      : "border-[#d8e3f4] bg-white text-[#00215C] shadow-sm hover:-translate-y-0.5 hover:border-[#114da6]/50 hover:shadow-md dark:border-border dark:bg-card dark:text-white",
                  )}
                >
                  <div className="flex items-center justify-between">
                    <span
                      className={cn(
                        "flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold ring-2",
                        isSelected
                          ? "bg-[#FFDB00] text-[#00215C] ring-white/30 dark:bg-[#00215C] dark:text-[#FFDB00] dark:ring-[#00215C]/30"
                          : "bg-[#00215C] text-white ring-[#eef3ff] dark:bg-[#FFDB00] dark:text-[#00215C] dark:ring-accent",
                      )}
                    >
                      {index + 1}
                    </span>
                    <span className="flex items-center gap-1.5">
                      {stage.advanced && (
                        <Sparkles
                          className={cn(
                            "h-3.5 w-3.5",
                            isSelected ? "text-[#FFDB00] dark:text-[#00215C]" : "text-violet-400",
                          )}
                          aria-label="avanzado"
                        />
                      )}
                      <StageIcon
                        className={cn(
                          "h-5 w-5",
                          isSelected
                            ? "text-[#FFDB00] dark:text-[#00215C]"
                            : "text-[#114da6] dark:text-[#FFDB00]",
                        )}
                      />
                    </span>
                  </div>
                  <h3 className="text-sm font-bold">
                    <span className="opacity-60">{index + 1}.</span> {stage.title}
                  </h3>
                  <p
                    className={cn(
                      "text-xs leading-relaxed",
                      isSelected
                        ? "text-white/80 dark:text-[#00215C]/80"
                        : "text-slate-500 dark:text-muted-foreground",
                    )}
                  >
                    {stage.text}
                  </p>
                  <span
                    className={cn(
                      "mt-auto inline-flex items-center gap-1 pt-1 text-[11px] font-semibold",
                      isSelected
                        ? "text-white/90 dark:text-[#00215C]/90"
                        : "text-[#114da6] dark:text-[#FFDB00]",
                    )}
                  >
                    {isSelected ? "Ocultar pasos" : "Ver pasos"}
                    <ChevronDown
                      className={cn("h-3.5 w-3.5 transition-transform", isSelected && "rotate-180")}
                    />
                  </span>
                </button>

                {/* Connector between cards — arrow on desktop, down-chevron on mobile */}
                {index < STAGES.length - 1 && (
                  <div className="flex shrink-0 items-center justify-center lg:px-0.5">
                    <ArrowRight className="hidden h-5 w-5 text-[#c9d7ec] lg:block dark:text-border" />
                    <ChevronDown className="h-4 w-4 text-[#c9d7ec] lg:hidden dark:text-border" />
                  </div>
                )}
              </Fragment>
            );
          })}
        </div>

        {/* Pointer triangle aligned under the selected card (desktop only) */}
        {selected !== null && (
          <div
            className="pointer-events-none absolute -bottom-2 hidden h-4 w-4 rotate-45 border-b border-r border-[#114da6] bg-[#f7fbff] lg:block dark:border-[#FFDB00] dark:bg-accent/40"
            style={{
              left: `calc(${((selected + 0.5) / STAGES.length) * 100}% - 0.5rem)`,
            }}
          />
        )}
      </div>

      {/* Disaggregated detail of the selected stage */}
      {selectedStage && (
        <div className="rounded-2xl border border-[#114da6]/40 bg-[#f7fbff] p-4 dark:border-[#FFDB00]/40 dark:bg-accent/40">
          <StageDetail key={selectedStage.slug} stage={selectedStage} />
        </div>
      )}

      {selected === null && (
        <p className="text-center text-xs text-slate-500 dark:text-muted-foreground">
          Pulsa cualquier etapa para desplegar sus pasos intermedios y opciones de configuración.
        </p>
      )}
    </div>
  );
}
