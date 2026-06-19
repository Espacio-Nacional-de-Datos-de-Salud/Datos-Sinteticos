// Help content for the Auditoría instructions manual.
//
// One entry per top-level page section (WorkflowGroup); the `id` matches the
// section's DOM id. Structurally a sibling of the other instructions-content
// files; presentational helpers are duplicated here so this module stays
// self-contained.

"use client";

import { useState } from "react";
import {
  MousePointerClick,
  Pencil,
  FileText,
  Download,
  XCircle,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import type { InstructionsEntry } from "@/components/layout/instructions-panel";
import { AdvancedBadge } from "@/components/ui/advanced-section";

// ── Brand palette ───────────────────────────────────────────────────────────
const NAVY = "#00215C";
const BLUE = "#114da6";
const SKY = "#c9d4ea";
const INK = "#2b3a52";

// ── Presentational helpers ──────────────────────────────────────────────────
function Lead({ children }: { children: React.ReactNode }) {
  return <p>{children}</p>;
}

function Subtitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="mt-3.5 text-[13.5px] font-bold uppercase tracking-wide text-[#16386f] underline decoration-[#FFDB00] decoration-2 underline-offset-4 first:mt-0 dark:text-[#dce8ff]">
      {children}
    </h4>
  );
}

function Diagram({ children }: { children: React.ReactNode }) {
  return <div className="my-1 flex justify-center">{children}</div>;
}

function OptionList({ items }: { items: Array<{ name: string; desc: string }> }) {
  return (
    <ul className="space-y-1">
      {items.map((it) => (
        <li key={it.name} className="flex gap-2">
          <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
          <span>
            <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
              {it.name}
            </span>{" "}
            — {it.desc}
          </span>
        </li>
      ))}
    </ul>
  );
}

// Like a plain bullet list, but each item carries the same icon the page shows
// for that action, so the help mirrors the buttons the user actually sees
// (matches the IconOptionList used in the Carga de Datos manual).
function IconOptionList({
  items,
}: {
  items: Array<{ Icon: LucideIcon; name: string; desc: string }>;
}) {
  return (
    <ul className="space-y-1.5">
      {items.map((it) => (
        <li key={it.name} className="flex gap-2">
          <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded bg-[#eef3ff] text-[#16386f] dark:bg-[#16284d] dark:text-[#9db4dc]">
            <it.Icon className="h-3.5 w-3.5" />
          </span>
          <span>
            <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
              {it.name}
            </span>{" "}
            — {it.desc}
          </span>
        </li>
      ))}
    </ul>
  );
}

// Configuration parameters grouped by the quality axis they affect, so the
// reader sees at a glance which knobs touch privacy vs. fidelity vs. utility.
// Colour-coded to match the categories shown in the evaluation report.
type ParamItem = {
  name?: string;
  desc?: React.ReactNode;
  // "métrica" = casilla activable en metrics.default; "ajuste" = valor escalar
  // o estructura de configuración. Omitido = se renderiza sin etiqueta.
  tag?: "métrica" | "ajuste";
  // Dirección ideal de una métrica (p. ej. "↓ 0", "≈ 0.5"), si aplica.
  ideal?: string;
  // Si está presente, la entrada se renderiza como subtítulo de sub-bloque
  // (con un `desc` opcional como intro) en lugar de como fila de métrica.
  heading?: string;
};

function ItemTag({ tag, color }: { tag: "métrica" | "ajuste"; color: string }) {
  const isMetric = tag === "métrica";
  return (
    <span
      className="ml-1 inline-block rounded px-1 py-px text-[8.5px] font-bold uppercase tracking-wide align-[1px]"
      style={
        isMetric
          ? { background: `${color}1f`, color }
          : { background: "#e7edf6", color: "#5a6b85" }
      }
    >
      {tag}
    </span>
  );
}

function ParamGroups({
  groups,
  active: activeProp,
  onActiveChange,
}: {
  groups: Array<{
    category: string;
    color: string;
    blurb: string;
    items: ParamItem[];
  }>;
  active?: string;
  onActiveChange?: (category: string) => void;
}) {
  const [localActive, setLocalActive] = useState(groups[0]?.category ?? "");
  const active = activeProp ?? localActive;
  const setActive = (cat: string) => {
    setLocalActive(cat);
    onActiveChange?.(cat);
  };
  const g = groups.find((x) => x.category === active) ?? groups[0];
  return (
    <div className="space-y-0">
      {/* Tab strip */}
      <div className="flex gap-1 overflow-x-auto pb-1">
        {groups.map((grp) => {
          const selected = grp.category === g?.category;
          return (
            <button
              key={grp.category}
              type="button"
              onClick={() => setActive(grp.category)}
              className="flex shrink-0 items-center gap-1.5 rounded-md px-2.5 py-1 text-[10.5px] font-bold uppercase tracking-wide transition-colors"
              style={
                selected
                  ? { background: `${grp.color}18`, color: grp.color, boxShadow: `0 0 0 1.5px ${grp.color}55` }
                  : { color: "#7a8fab" }
              }
            >
              <span
                className="inline-block h-1.5 w-1.5 shrink-0 rounded-full"
                style={{ background: selected ? grp.color : "#c0cad9" }}
              />
              {grp.category}
            </button>
          );
        })}
      </div>

      {/* Active group content */}
      {g && (
        <div
          className="overflow-hidden rounded-lg border border-[#cdd9ec] shadow-[0_1px_3px_rgba(16,40,80,0.06)] dark:border-[#26375f]"
          style={{ borderLeftColor: g.color, borderLeftWidth: 3 }}
        >
          <div
            className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5 px-3 py-1.5"
            style={{ background: `${g.color}14` }}
          >
            <span className="text-[10.5px] leading-snug text-[#5a6b85] dark:text-[#8fa3c4]">
              {g.blurb}
            </span>
          </div>
          <ul className="space-y-1.5 px-3 py-2">
            {g.items.map((it, idx) =>
              it.heading ? (
                <li
                  key={`h-${idx}`}
                  className="!mt-3 border-t border-[#e5ebf6] pt-2 first:!mt-0 first:border-0 first:pt-0 dark:border-[#26375f]"
                >
                  <div
                    className="text-[10.5px] font-bold uppercase tracking-wide"
                    style={{ color: g.color }}
                  >
                    {it.heading}
                  </div>
                  {it.desc ? (
                    <p className="mt-0.5 text-[11px] leading-snug text-[#5a6b85] dark:text-[#8fa3c4]">
                      {it.desc}
                    </p>
                  ) : null}
                </li>
              ) : (
                <li key={it.name} className="flex gap-2">
                  <span
                    className="mt-[6px] h-1.5 w-1.5 shrink-0 rounded-sm"
                    style={{ background: g.color }}
                  />
                  <span>
                    <code className="rounded bg-[#eef3ff] px-1 py-px text-[11px] font-semibold text-[#16386f] dark:bg-[#16284d] dark:text-[#dce8ff]">
                      {it.name}
                    </code>
                    {it.tag ? <ItemTag tag={it.tag} color={g.color} /> : null}{" "}
                    — {it.desc}
                    {it.ideal ? (
                      <>
                        {" "}
                        <span
                          className="whitespace-nowrap rounded bg-[#f3f6fc] px-1 py-px font-mono text-[10px] font-semibold dark:bg-[#16284d]"
                          style={{ color: g.color }}
                        >
                          ideal {it.ideal}
                        </span>
                      </>
                    ) : null}
                  </span>
                </li>
              ),
            )}
          </ul>
        </div>
      )}
    </div>
  );
}

function StepTable({ steps }: { steps: Array<{ name: React.ReactNode; desc: string }> }) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#cdd9ec] shadow-[0_1px_3px_rgba(16,40,80,0.06)] dark:border-[#26375f]">
      <div className="grid grid-cols-[42%_58%] bg-[#16386f] text-[10px] font-bold uppercase tracking-[0.06em] text-white">
        <div className="px-3 py-2">Fase</div>
        <div className="border-l border-white/15 px-3 py-2">Explicación</div>
      </div>
      {steps.map((s, i) => (
        <div
          key={i}
          className={
            "grid grid-cols-[42%_58%] border-t border-[#e5ebf6] dark:border-[#26375f] " +
            (i % 2 === 0
              ? "bg-white dark:bg-[#0c1730]"
              : "bg-[#f5f8fd] dark:bg-[#0e1b36]")
          }
        >
          <div className="flex items-start gap-2 px-3 py-2.5">
            <span className="mt-px flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-[#00215C] text-[10px] font-bold text-white">
              {i + 1}
            </span>
            <span className="text-[12px] font-semibold leading-snug text-[#16386f] dark:text-[#dce8ff]">
              {s.name}
            </span>
          </div>
          <div className="border-l border-[#e5ebf6] px-3 py-2.5 text-[12px] leading-snug text-[#3a4a63] dark:border-[#26375f] dark:text-[#aebdd9]">
            {s.desc}
          </div>
        </div>
      ))}
    </div>
  );
}

function OptionCallout({
  name,
  state,
  children,
}: {
  name: React.ReactNode;
  state: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative rounded-md border-l-4 border-[#FFDB00] bg-[#eef3ff] py-2 pl-2.5 pr-3 dark:bg-[#16284d]">
      <span className="absolute right-0 top-0 rounded-bl-md rounded-tr-[3px] bg-[#FFDB00] px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-[#00215C]">
        {state}
      </span>
      <div className="flex items-center gap-1.5">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0" aria-hidden>
          <g stroke="#5f83be" strokeWidth={1.6} strokeLinecap="round">
            <line x1={2.5} y1={4} x2={13.5} y2={4} />
            <line x1={2.5} y1={8} x2={13.5} y2={8} />
            <line x1={2.5} y1={12} x2={13.5} y2={12} />
          </g>
          <g fill="#5f83be">
            <circle cx={5.5} cy={4} r={2.2} />
            <circle cx={10.5} cy={8} r={2.2} />
            <circle cx={6.5} cy={12} r={2.2} />
          </g>
        </svg>
        <span className="text-[10.5px] font-bold uppercase tracking-wide text-[#5f83be] dark:text-[#9db4dc]">
          Opción activable
        </span>
      </div>
      {/* div, not p: `name` may contain an AdvancedBadge (which renders a
          Tooltip <div>), and a <div> cannot be nested inside a <p>. */}
      <div className="mt-1">
        <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
          {name}
        </span>{" "}
        — {children}
      </div>
    </div>
  );
}

const svgBase = {
  preserveAspectRatio: "xMidYMid meet" as const,
  fontFamily: "inherit",
  // Figures are drawn with light-theme brand colors, so they always sit on a
  // light "paper" surface — keeps contrast correct in dark mode too.
  className: "rounded-lg border border-[#e3e9f4] bg-[#f7f9fd] p-2 dark:border-[#2a3a5e]",
};

function StepFlowH({ steps }: { steps: readonly string[][] }) {
  const colW = 104;
  const width = steps.length * colW;
  const height = 56;
  const cy = 13;
  return (
    <svg
      {...svgBase}
      width="100%"
      style={{ maxWidth: width }}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={steps.map((s) => s.join(" ")).join("; ")}
    >
      <line
        x1={colW / 2}
        y1={cy}
        x2={width - colW / 2}
        y2={cy}
        stroke={SKY}
        strokeWidth={2.5}
        strokeLinecap="round"
      />
      {steps.map((lines, i) => {
        const cx = colW / 2 + i * colW;
        return (
          <g key={i}>
            <circle cx={cx} cy={cy} r={15} fill={NAVY} opacity={0.12} />
            <circle cx={cx} cy={cy} r={11} fill={NAVY} />
            <text x={cx} y={cy + 4.5} fontSize={12.5} fontWeight={700}
              fill="#fff" textAnchor="middle">
              {i + 1}
            </text>
            {lines.map((ln, j) => (
              <text key={j} x={cx} y={40 + j * 10} fontSize={9} fontWeight={600}
                fill={INK} textAnchor="middle">
                {ln}
              </text>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

function OverviewDiagram() {
  return (
    <StepFlowH
      steps={[
        ["Seleccionar", "generación"],
        ["Configurar", "evaluación"],
        ["Ejecutar", "evaluación"],
        ["Revisar", "informe"],
      ]}
    />
  );
}

// Four score boxes arranged in a 2×2 grid, matching the dashboard layout
// shown in the evaluation report section.
function ScoresDiagram() {
  const scores = [
    { label: "Global", sub: "puntuación compuesta", color: "#1a56db" },
    { label: "Fidelidad", sub: "distribuciones y correlaciones", color: "#166534" },
    { label: "Privacidad", sub: "riesgo de re-identificación", color: "#9a3412" },
    { label: "Utilidad", sub: "valor predictivo sintético", color: "#6b21a8" },
  ];
  const boxW = 140;
  const boxH = 52;
  const gapX = 12;
  const gapY = 10;
  const totalW = 2 * boxW + gapX;
  const totalH = 2 * boxH + gapY;
  return (
    <svg {...svgBase} width={totalW} height={totalH + 4}
      viewBox={`0 0 ${totalW} ${totalH + 4}`} role="img"
      aria-label="Cuatro puntuaciones compuestas: global, fidelidad, privacidad, utilidad">
      {scores.map((s, i) => {
        const col = i % 2;
        const row = Math.floor(i / 2);
        const x = col * (boxW + gapX);
        const y = row * (boxH + gapY);
        return (
          <g key={s.label}>
            <rect x={x} y={y} width={boxW} height={boxH} rx={8}
              fill={s.color} fillOpacity={0.08}
              stroke={s.color} strokeOpacity={0.35} strokeWidth={1.5} />
            <text x={x + boxW / 2} y={y + 18} fontSize={9.5} fontWeight={700}
              fill={s.color} textAnchor="middle" opacity={0.8}>
              {s.label.toUpperCase()}
            </text>
            {/* mock score bar */}
            <rect x={x + 16} y={y + 27} width={boxW - 32} height={8} rx={4}
              fill={s.color} fillOpacity={0.12} />
            <rect x={x + 16} y={y + 27} width={(boxW - 32) * 0.82} height={8} rx={4}
              fill={s.color} fillOpacity={0.5} />
            <text x={x + boxW / 2} y={y + boxH - 7} fontSize={8}
              fill={s.color} textAnchor="middle" opacity={0.65}>
              {s.sub}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

function Example({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#ecd96b] bg-[#fffdf0] dark:border-[#5a4e16] dark:bg-[#211d0b]">
      <div className="flex items-center gap-1.5 bg-[#FFDB00] px-2.5 py-1">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
          <path
            d="M8 1.5a4.5 4.5 0 0 0-2.7 8.1c.4.3.7.8.7 1.3v.6h4v-.6c0-.5.3-1 .7-1.3A4.5 4.5 0 0 0 8 1.5Z"
            fill="#00215C"
          />
          <rect x={6} y={12.5} width={4} height={1.6} rx={0.8} fill="#00215C" />
          <rect x={6.6} y={14.6} width={2.8} height={1.3} rx={0.65} fill="#00215C" />
        </svg>
        <span className="text-[10.5px] font-bold uppercase tracking-wide text-[#00215C]">
          Ejemplo
        </span>
      </div>
      <p className="px-2.5 py-1.5 text-[12px] text-[#4a4214] dark:text-[#d8c98a]">
        {children}
      </p>
    </div>
  );
}

// Three-column metrics reference table: category, metric name, direction.
function MetricsReferenceTable() {
  const rows: Array<{ category: string; name: string; ideal: string }> = [
    { category: "Fidelidad", name: "JSD marginal", ideal: "↓ 0" },
    { category: "Fidelidad", name: "KL divergencia inversa", ideal: "↑ 1" },
    { category: "Fidelidad", name: "TVD complementaria media", ideal: "↑ 1" },
    { category: "Fidelidad", name: "Dist. matriz correlación", ideal: "↓ 0" },
    { category: "Privacidad", name: "DCR (vecino más cercano)", ideal: "↑ mayor" },
    { category: "Privacidad", name: "NNDR", ideal: "↑ 1" },
    { category: "Privacidad", name: "k-anonimato", ideal: "↑ ≥ 5" },
    { category: "Privacidad", name: "Coincidencias exactas (EMR)", ideal: "↓ 0" },
    { category: "Privacidad", name: "Proporción de filas comunes (CRP)", ideal: "↓ 0 %" },
    { category: "Privacidad", name: "Detección MLP", ideal: "≈ 0.5" },
    { category: "Utilidad", name: "Regresión lineal (OOD)", ideal: "↑ mayor" },
    { category: "Utilidad", name: "MLP (OOD)", ideal: "↑ mayor" },
    { category: "Utilidad", name: "Precisión relativa", ideal: "↑ 1" },
  ];

  const catColors: Record<string, string> = {
    Fidelidad: "#166534",
    Privacidad: "#9a3412",
    Utilidad: "#6b21a8",
  };

  return (
    <div className="overflow-hidden rounded-lg border border-[#cdd9ec] shadow-[0_1px_3px_rgba(16,40,80,0.06)] dark:border-[#26375f]">
      <div className="grid grid-cols-[30%_50%_20%] bg-[#16386f] text-[9.5px] font-bold uppercase tracking-[0.06em] text-white">
        <div className="px-2.5 py-1.5">Categoría</div>
        <div className="border-l border-white/15 px-2.5 py-1.5">Métrica</div>
        <div className="border-l border-white/15 px-2.5 py-1.5 text-right">Ideal</div>
      </div>
      {rows.map((r, i) => (
        <div
          key={r.name}
          className={
            "grid grid-cols-[30%_50%_20%] border-t border-[#e5ebf6] dark:border-[#26375f] " +
            (i % 2 === 0
              ? "bg-white dark:bg-[#0c1730]"
              : "bg-[#f5f8fd] dark:bg-[#0e1b36]")
          }
        >
          <div className="flex items-center px-2.5 py-1.5">
            <span
              className="inline-block h-2 w-2 shrink-0 rounded-full mr-1.5"
              style={{ background: catColors[r.category] ?? NAVY }}
            />
            <span
              className="text-[10.5px] font-semibold"
              style={{ color: catColors[r.category] ?? NAVY }}
            >
              {r.category}
            </span>
          </div>
          <div className="border-l border-[#e5ebf6] px-2.5 py-1.5 text-[11px] leading-snug text-[#3a4a63] dark:border-[#26375f] dark:text-[#aebdd9]">
            {r.name}
          </div>
          <div className="border-l border-[#e5ebf6] px-2.5 py-1.5 text-right text-[11px] font-mono font-semibold text-[#16386f] dark:border-[#26375f] dark:text-[#9db4dc]">
            {r.ideal}
          </div>
        </div>
      ))}
    </div>
  );
}

function HistorialDiagram() {
  return (
    <svg {...svgBase} width="320" height="120" viewBox="0 0 320 120" role="img"
      aria-label="Historial de evaluaciones con la activa resaltada">
      {[0, 1, 2].map((i) => {
        const y = 6 + i * 38;
        const active = i === 0;
        return (
          <g key={i}>
            <rect x={4} y={y} width={312} height={30} rx={7}
              fill={active ? "#eef3ff" : "#fff"} stroke={active ? NAVY : SKY}
              strokeWidth={active ? 2.5 : 1.6} />
            <text x={18} y={y + 20} fontSize={13.5} fontWeight={active ? 700 : 400} fill={INK}>
              Evaluación {i + 1}{active ? "  ·  activa" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Entries ─────────────────────────────────────────────────────────────────
export function buildAuditoriaInstructions(
  activeAxis: string,
  onAxisChange: (axis: string) => void,
): readonly InstructionsEntry[] {
  return [
    {
      id: "resumen",
      title: "Resumen",
      overview: true,
      content: (
        <div className="flex justify-center">
          <OverviewDiagram />
        </div>
      ),
    },
    {
      id: "preparacion",
      title: "Preparación",
      content: (
        <>
          <Lead>
            Selecciona la generación a evaluar, revisa la configuración de
            métricas y lanza la evaluación. Sigue estos pasos:
          </Lead>
          <StepTable
            steps={[
              {
                name: "Seleccionar generación",
                desc: "Elige una generación completada en el paso anterior. La evaluación comparará ese dataset sintético con los datos reales del modelo que lo originó.",
              },
              {
                name: (
                  <span className="inline-flex items-center gap-1">
                    Configurar evaluación
                    <AdvancedBadge tooltip="Avanzado · personaliza qué métricas se calculan y con qué parámetros" />
                  </span>
                ),
                desc: "Edita la configuración de evaluación para activar o desactivar métricas, cambiar umbrales o ajustar parámetros de privacidad. Los valores por defecto son adecuados para la mayoría de los casos.",
              },
              {
                name: "Iniciar evaluación",
                desc: "Lanza la suite de evaluación. Al terminar, el informe con puntuaciones y métricas quedará disponible.",
              },
            ]}
          />
          <OptionCallout
            name={
              <span className="inline-flex items-center gap-1">
                Configuración
                <AdvancedBadge tooltip="Avanzado · personaliza qué métricas se calculan y con qué parámetros" />
              </span>
            }
            state="Opcional"
          >
            Permite personalizar qué métricas se calculan y con qué parámetros.
            El fichero se edita directamente en el panel de configuración. Entre
            las opciones habituales: activar / desactivar categorías de métricas
            (fidelidad, privacidad, utilidad), seleccionar la columna objetivo
            para las métricas de utilidad o ajustar el número de vecinos{" "}
            <em>k</em> para el cálculo de k-anonimato.
          </OptionCallout>

          <Subtitle>
            <span className="inline-flex items-center gap-1.5">
              Métricas y ajustes
              <AdvancedBadge tooltip="Avanzado · personaliza qué métricas se calculan y con qué parámetros" />
            </span>
          </Subtitle>
          <p>
            El panel de configuración de evaluación agrupa las opciones por eje —privacidad,
            fidelidad y utilidad—, los mismos que verás en el informe. En cada
            bloque predominan las{" "}
            <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
              métricas
            </span>{" "}
            (casillas que activas o desactivas; cada una añade un cálculo, pero también un
            coste de cómputo), potencialmente acompañadas de algún{" "}
            <span className="font-semibold text-[#5a6b85] dark:text-[#8fa3c4]">
              ajuste
            </span>{" "}
            (valores o columnas que afinan cómo se calcula una métrica).
          </p>
          <p>
            Con los valores por defecto, privacidad y fidelidad ya se calculan
            sin tocar nada. La{" "}
            <span className="font-semibold text-[#6b21a8] dark:text-[#d6b8f0]">
              utilidad
            </span>{" "}
            es la excepción: necesita que definas el caso de uso (qué columna
            predecir y el tipo de tarea, o qué estadísticos analizar) o no podrá
            calcularse y aparecerá como «—».
          </p>
          <ParamGroups
            active={activeAxis}
            onActiveChange={onAxisChange}
            groups={[
              {
                category: "Privacidad",
                color: "#9a3412",
                blurb: "Evalúa el riesgo de reidentificación de pacientes, la memorización de registros y la inferencia de atributos.",
                items: [
                  {
                    heading: "Distancia a los datos reales",
                    desc: "Cuánto se separa cada fila sintética del registro real más parecido.",
                  },
                  {
                    name: "dcr",
                    tag: "métrica",
                    desc: "Distance to Closest Record: distancia de cada fila sintética a la fila real más parecida. Cuanto mayor, menos «copia» a un individuo concreto.",
                  },
                  {
                    name: "nndr",
                    tag: "métrica",
                    desc: "Nearest Neighbor Distance Ratio: cociente entre la distancia al 1.er y al 2.º vecino real. Cerca de 1 = la fila no está pegada a un único registro real.",
                  },
                  {
                    heading: "Anonimato por grupos (k / l)",
                    desc: "Si los cuasi-identificadores permiten singularizar o inferir datos de una persona.",
                  },
                  {
                    name: "k-anonymization",
                    tag: "métrica",
                    desc: (
                      <>
                        k-anonimato: tamaño del grupo más pequeño de filas
                        indistinguibles entre sí mirando solo los
                        cuasi-identificadores. Un k = 3 significa que cualquier
                        combinación de esos atributos la comparten al menos 3
                        registros, así que no se puede aislar a una persona
                        concreta. Cuanto mayor k, más anonimato (≥ 5 suele
                        considerarse aceptable). Se evalúa sobre los grupos de{" "}
                        <code>quasi_identifier_subsets</code>.
                      </>
                    ),
                  },
                  {
                    name: "distinct l-diversity",
                    tag: "métrica",
                    desc: (
                      <>
                        l-diversidad (distinct): afina el k-anonimato mirando el
                        atributo sensible. No basta con que un grupo tenga k
                        personas: si todas comparten el mismo valor sensible
                        (p. ej. todas fallecieron), el grupo lo revela igual. l
                        cuenta cuántos valores distintos del atributo sensible hay
                        en cada grupo k-anónimo; cuantos más, menos se puede
                        inferir. Requiere <code>sensitive_columns</code> y{" "}
                        <code>quasi_identifier_subsets</code>; si faltan, se omite.
                      </>
                    ),
                  },
                  {
                    heading: "Copias exactas",
                    desc: "Filas sintéticas que reproducen literalmente un registro real.",
                  },
                  {
                    name: "common_rows_proportion",
                    tag: "métrica",
                    desc: "Proporción de filas sintéticas que coinciden exactamente con alguna fila real en todas las columnas compartidas. Chequeo de sanidad rápido: debería ser 0; cualquier valor > 0 indica que el modelo replicó registros reales tal cual.",
                  },
                  {
                    name: "exact_match_rows",
                    tag: "métrica",
                    desc: "Desglose detallado de esas coincidencias: para cada combinación de columnas (la completa y dejando una fuera) calcula la proporción de filas que coinciden y extrae los registros concretos. Donde common_rows_proportion dice «cuántas», exact_match_rows dice «cuáles y por qué columnas se filtran».",
                  },
                  {
                    name: "exact_match.show_filtered_rows",
                    tag: "ajuste",
                    desc: "Si exact_match_rows está activo, decide si el reporte muestra las filas reales copiadas literalmente por el sintético. Desactivado por defecto, porque son registros reales y deben tratarse como confidenciales.",
                  },
                  {
                    heading: "Indistinguibilidad y ataques",
                    desc: "Si un adversario puede separar lo sintético de lo real o deducir quién estuvo en el entrenamiento.",
                  },
                  {
                    name: "detection_mlp",
                    tag: "métrica",
                    desc: "Un clasificador intenta distinguir filas reales de sintéticas. Cerca de 0.5 = indistinguibles (bueno); cerca de 1 = el modelo las separa con facilidad.",
                  },
                  {
                    name: "DomiasMIA_BNAF",
                    tag: "métrica",
                    desc: (
                      <>
                        Ataque de inferencia de membresía (MIA): simula a un
                        atacante que, partiendo del registro de una persona,
                        intenta averiguar si esa persona formaba parte de los
                        datos reales con los que se entrenó el modelo. Si el
                        sintético «recuerda» demasiado a los individuos de
                        entrenamiento, el ataque acierta y hay fuga de privacidad;
                        si no consigue distinguirlos, los datos protegen la
                        pertenencia. Muy costoso: desactivado por defecto,
                        actívalo solo para auditorías exhaustivas.
                      </>
                    ),
                  },
                  {
                    heading: "Ajustes",
                    desc: "Definen sobre qué columnas operan el k-anonimato y la l-diversidad.",
                  },
                  {
                    name: "quasi_identifier_subsets",
                    tag: "ajuste",
                    desc: (
                      <>
                        Cuasi-identificadores: columnas que por sí solas no
                        identifican a nadie, pero combinadas sí pueden
                        singularizar a una persona (p. ej. sexo + fecha de
                        nacimiento + código postal). Cada subconjunto es una de
                        esas combinaciones que un atacante podría cruzar con
                        fuentes externas.{" "}
                        <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
                          Cómo elegirlos:
                        </span>{" "}
                        incluye las columnas observables o públicas (demografía,
                        fechas, ubicaciones) y agrúpalas tal como las cruzaría el
                        atacante; deja fuera lo que nadie podría conocer de
                        antemano. Vacío ⇒ el k-anonimato se calcula solo por pares
                        de columnas y la l-diversidad se omite.
                      </>
                    ),
                  },
                  {
                    name: "sensitive_columns",
                    tag: "ajuste",
                    desc: "Atributo(s) cuyo secreto quieres proteger (p. ej. EXPIRE_FLAG). Es lo que l-diversidad evalúa; vacío ⇒ l-diversidad no se calcula.",
                  },
                ],
              },
              {
                category: "Fidelidad",
                color: "#166534",
                blurb: "¿Se parece estadísticamente el dataset sintético al real? Propiedad intrínseca de los datos, evaluada siempre igual y sin tarea downstream. Es una evaluación fija.",
                items: [
                  {
                    heading: "Distribuciones marginales",
                    desc: "Las tres comparan la forma de las distribuciones; se diferencian en cómo penalizan y si miran columnas aisladas o también combinaciones.",
                  },
                  {
                    name: "jensenshannon_dist",
                    tag: "métrica",
                    desc: "Distancia de Jensen-Shannon entre cada distribución marginal real y su sintética, promediada. Simétrica y acotada: 0 = idénticas, valores altos = se separan. Mira cada columna por separado.",
                  },
                  {
                    name: "inv_kl_divergence",
                    tag: "métrica",
                    desc: "KL inversa normalizada (acotada a 0–1, 1 = sin pérdida). También compara las marginales columna a columna, pero penaliza con más dureza que la JSD cuando el sintético casi nunca produce un valor que en lo real sí aparece.",
                  },
                  {
                    name: "distribution_comparison_report",
                    tag: "métrica",
                    desc: (
                      <>
                        <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
                          Complemento de la TVD
                        </span>{" "}
                        (1 − Total Variation Distance), promediado para
                        combinaciones de 1, 2 y 3 columnas. A diferencia de la JSD
                        y la KL inversa —que solo miran columnas aisladas—, también
                        comprueba si se conservan las distribuciones conjuntas
                        (pares y tríos de columnas). 1 = solapamiento total.
                      </>
                    ),
                  },
                  {
                    heading: "Relaciones entre columnas",
                    desc: "No la forma de cada columna, sino cómo se relacionan entre sí.",
                  },
                  {
                    name: "correlation_matrix_distance",
                    tag: "métrica",
                    desc: "Distancia entre la matriz de correlación real y la sintética. Comprueba que se conservan las correlaciones por pares entre todas las columnas. Menor = relaciones mejor preservadas.",
                  },
                  {
                    heading: "Ajustes",
                  },
                  {
                    name: "tvd_n_bins",
                    tag: "ajuste",
                    desc: "Intervalos (bins) con que se discretizan las columnas continuas al calcular la TVD / complemento de la TVD (por defecto 10).",
                  },
                ],
              },
              {
                category: "Utilidad",
                color: "#6b21a8",
                blurb: "¿Sirve el dataset sintético para hacer lo mismo que harías con el real? Propiedad funcional, orientada a una tarea concreta. Es una evaluación específica para cada caso.",
                items: [
                  {
                    heading: "Utilidad predictiva (TSTR vs TRTR)",
                    desc: (
                      <>
                        Para evaluar la utilidad predictiva se coge un predictor sencillo y se le pide
                        aprender una tarea concreta: predecir{" "}
                        <code>target_column</code> a partir del resto de columnas.
                        <br />
                        <br />
                        Ese predictor se entrena{" "}
                        <span className="font-semibold">dos veces</span> por separado, cambiando
                        solo con qué datos aprende, y en ambos casos se le examina
                        con el <em>mismo</em> conjunto de datos reales reservados:
                        <ul className="ml-4 mt-1 list-disc space-y-0.5">
                          <li>
                            <span className="font-semibold">TRTR</span> (
                            <em>Train on Real, Test on Real</em>): aprende de los
                            datos <span className="font-semibold">reales</span>. Es
                            la referencia: lo mejor a lo que podemos aspirar.
                          </li>
                          <li>
                            <span className="font-semibold">TSTR</span> (
                            <em>Train on Synthetic, Test on Real</em>): aprende de
                            los datos <span className="font-semibold">sintéticos</span>{" "}
                            y se enfrenta al mismo examen real.
                          </li>
                        </ul>
                        <br />
                        Se mide la diferencia entre el rendimiento TRTR y el TSTR, no el acierto absoluto. Si quedan parejos, el sintético
                        enseña lo mismo que el real y vale para entrenar. La
                        utilidad es, por tanto, una medida{" "}
                        <span className="font-semibold text-[#6b21a8] dark:text-[#d6b8f0]">
                          relativa
                        </span>
                        .
                      </>
                    ),
                  },
                  {
                    name: "linear_model",
                    tag: "métrica",
                    desc: "Métrica que mide lo explicado anteriormente usando un modelo lineal.",
                  },
                  {
                    name: "mlp",
                    tag: "métrica",
                    desc: "Métrica que mide lo explicado anteriormente usando una red neuronal (perceptrón multicapa).",
                  },
                  {
                    name: "tstr.target_column",
                    tag: "ajuste",
                    desc: "Columna a predecir. Imprescindible: sin ella la utilidad predictiva no se calcula y aparece como «—». Debe ser una variable realmente predecible del dataset (p. ej. expire_flag).",
                  },
                  {
                    name: "tstr.task_type",
                    tag: "ajuste",
                    desc: "classification (objetivo categórico) o regression (objetivo numérico continuo). Junto con target_column define la tarea predictiva.",
                  },
                  {
                    heading: "Utilidad estadística",
                    desc: (
                      <>
                        Compara si podemos obtener las mismas conclusiones en análisis estadísticos agregados en el dataset real y el sintético.
                        <br />
                        <br />
                        Las agregaciones pueden escogerse entre los estadísticos predefinidos o definirse a medida. Para cada una se calcula una discrepancia relativa simétrica y acotada, |real − sintético| / (|real| + |sintético|) (entre 0 y 1, sin depender de cuál sea mayor), y la precisión como 1 − discrepancia. La utilidad estadística es la media ponderada de esas precisiones.
                      </>
                    ),
                  },
                  {
                    name: "Precisión",
                    tag: "métrica",
                    desc: "Mide cuánto se aproxima el valor de una agregación en los datos sintéticos al valor en los reales. Se calcula como 1- discrepancia =1 -|s-r|/|s+r| , con “s” y “r” cómo valores síntetico y real resultantes de la agregación, respectivamente. Se trata de una métrica simétrica y acotada en [0,1], donde 1 indica coincidencia exacta y 0 la máxima discrepancia relativa.",
                  },
                  {
                    name: "Agregaciones a comparar",
                    tag: "ajuste",
                    desc: (
                      <>
                        Lista de agregaciones a comparar, definidas con el editor
                        guiado («Añadir agregación»). A cada agregación le pones un{" "}
                        <code>nombre</code> y eliges entre dos modos:
                        <br />
                        <br />
                        <strong>Predefinida</strong> — escoges una operación del
                        desplegable y rellenas los campos que pida. Junto a la métrica
                        indicas la <code>tabla</code> y, según la métrica, una{" "}
                        <code>columna</code>. Operaciones disponibles:
                        <ul style={{ margin: "0.4em 0", paddingLeft: "1.2em" }}>
                          <li>
                            <code>count</code> (conteo) y <code>proportion</code>{" "}
                            (proporción) — trabajan sobre el número de filas, no
                            necesitan columna. <strong>Aquí el filtro es lo que da
                              sentido a la métrica</strong>: sin él, el conteo es solo el
                            total de filas de la tabla y la proporción es siempre 1, así
                            que la comparación no aporta nada. Con filtro mides cuántas
                            filas (o qué fracción) cumplen una condición, p. ej. clientes
                            con <code>EXPIRE_FLAG == 1</code>.
                          </li>
                          <li>
                            <code>mean</code>, <code>median</code>, <code>sum</code>,{" "}
                            <code>std</code>, <code>min</code>, <code>max</code> —
                            estadísticos sobre una columna numérica.
                          </li>
                          <li>
                            <code>nunique</code> — número de valores distintos de una
                            columna.
                          </li>
                          <li>
                            <code>percentile</code> — percentil de una columna; pide el
                            valor del percentil entre 0 y 1 (0.5 = mediana).
                          </li>
                          <li>
                            <code>rate</code> (tasa) y <code>ratio</code> (razón) —
                            cociente <code>numerador / denominador</code>; cada parte es
                            a su vez una agregación con su métrica, tabla, columna y
                            filtro (p. ej. proporción de impagos = count con filtro /
                            count total).
                          </li>
                        </ul>
                        El <code>filtro</code> es una expresión pandas que se evalúa
                        sobre las columnas de la tabla y restringe las filas antes de
                        calcular la métrica (operadores <code>== != &gt; &gt;= &lt;</code>,{" "}
                        <code>and</code>/<code>or</code>; p. ej.{" "}
                        <code>age &gt;= 65</code> o{" "}
                        <code>gender == &quot;F&quot; and charges &gt; 1000</code>). Es
                        obligatorio de hecho en <code>count</code>/<code>proportion</code>{" "}
                        (sin él no distinguen ningún subconjunto) y opcional en las
                        demás, donde sirve para comparar la métrica sobre un subgrupo:
                        p. ej. la <code>mean</code> de <code>charges</code> con filtro{" "}
                        <code>smoker == &quot;yes&quot;</code> comprueba si el sintético
                        conserva el gasto medio de los fumadores, no solo el global.
                        <br />
                        <br />
                        <strong>Personalizada</strong>{" "}
                        <AdvancedBadge tooltip="Modo avanzado: define una fórmula propia sobre una o varias columnas." />{" "}
                        — para casos que las predefinidas no cubren. Escribes una
                        fórmula sobre <code>df</code> (el dataframe ya filtrado), con{" "}
                        <code>np</code> y <code>pd</code> disponibles, combinando una o
                        varias columnas, p. ej.{" "}
                        <code>df[&apos;charges&apos;].sum() / df[&apos;age&apos;].mean()</code>.
                        Es el modo más flexible, pero exige escribir la expresión a mano.
                        <br />
                        <br />
                        En ambos modos puedes asignar un <code>peso</code> opcional
                        (por defecto 1) que pondera esa agregación en la media. El
                        reporte muestra, para cada agregación, el valor real y
                        sintético, la discrepancia relativa, la precisión relativa
                        (1 − discrepancia) y la desviación estándar de cada uno.
                      </>
                    ),
                  },
                ],
              },
            ]}
          />
        </>
      ),
    },
    {
      id: "resultados",
      title: "Resultados",
      content: (
        <>
          <Lead>
            Muestra el estado de la evaluación en curso y, al completarse, la
            lista de métricas calculadas.
          </Lead>

          <Subtitle>Evaluación actual</Subtitle>
          <p>
            Indica el estado de la evaluación activa (en curso, completada o con
            error), la generación evaluada y el modelo subyacente. Cuando
            termina, aparecen los identificadores de las métricas calculadas.
          </p>
          <OptionList
            items={[
              {
                name: "Cancelar",
                desc: "Detiene la evaluación en curso. Los resultados parciales no quedan disponibles.",
              },
              {
                name: "Métricas calculadas",
                desc: "Lista de métricas que se ejecutaron (por ejemplo: jsd, dcr, k_anonymity). Sirve para verificar que la configuración activó las categorías esperadas.",
              },
              {
                name: "Tiempos de ejecución",
                desc: "Despliega el tiempo invertido en cada fase de la evaluación al completarse.",
              },
            ]}
          />
        </>
      ),
    },
    {
      id: "reporte",
      title: "Reporte",
      content: (
        <>
          <Lead>
            El reporte de evaluación se despliega por defecto en la página y
            contiene todo el detalle: las cuatro puntuaciones compuestas y el
            desglose de cada métrica individual con su valor bruto, dirección
            ideal y semáforo de calidad. Desde el mismo panel puedes abrirlo en
            una nueva pestaña o descargar el ZIP con todos los artefactos.
          </Lead>

          <Subtitle>Puntuaciones compuestas</Subtitle>
          <p>
            Las cuatro puntuaciones resumen los ejes de calidad del dataset
            sintético. Todas están normalizadas a 0–1 y siguen la convención
            "mayor es mejor":
          </p>
          <Diagram>
            <ScoresDiagram />
          </Diagram>
          <OptionList
            items={[
              {
                name: "Global",
                desc: "Media ponderada de las tres puntuaciones dimensionales. Es el indicador de resumen más directo de la calidad general del dataset.",
              },
              {
                name: "Fidelidad",
                desc: "Mide cuánto se parecen las distribuciones y correlaciones de los datos sintéticos a los reales. Una puntuación alta indica que el modelo aprendió bien los patrones estadísticos.",
              },
              {
                name: "Privacidad",
                desc: "Mide la distancia entre los datos sintéticos y los reales en el espacio de características. Una puntuación alta implica menor riesgo de re-identificación.",
              },
              {
                name: "Utilidad",
                desc: "Mide la utilidad RELATIVA: compara un modelo entrenado con datos sintéticos frente al mismo modelo entrenado con los reales. No evalúa si el sintético predice «bien» en términos absolutos — si los datos reales también predicen mal, pero el sintético predice igual de mal (o de la misma manera), la utilidad relativa será alta. Puede aparecer en gris como «—» (sin resultado): no es un fallo, sino que falta definir el caso de uso (columna objetivo y tipo de tarea, o análisis estadísticos) en la configuración.",
              },
            ]}
          />

          <Subtitle>Dirección ideal y semáforo</Subtitle>
          <p>
            Cada puntuación compuesta se desglosa en métricas individuales con
            su valor bruto y una indicación de la dirección ideal (↑ mayor /
            ↓ menor / ≈ objetivo). El semáforo (verde / ámbar / rojo) aplica
            umbrales específicos por métrica. Para saber qué mide cada métrica y
            cómo interpretarla dentro de su eje, consulta{" "}
            <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
              «Métricas y ajustes»
            </span>{" "}
            en el paso Preparación. Referencia rápida de direcciones:
          </p>
          <MetricsReferenceTable />
          <Example>
            Un <code>JSD marginal</code> de 0.02 es excelente (muy por debajo del
            umbral de 0.05) porque indica que las distribuciones marginales de
            los sintéticos son casi idénticas a las reales. Una{" "}
            <code>Proporción de filas comunes (CRP)</code> de 2 % (que equivale a un <code>EMR</code> de 20 coincidencias en un dataset de 1000 filas) sería preocupante porque significa que 1 de
            cada 50 filas sintéticas es idéntica a una real.
          </Example>

          <Subtitle>Informe HTML completo</Subtitle>
          <p>
            El informe HTML completo se muestra desplegado por defecto, embebido
            en la página (puedes plegarlo una vez consultado). Desde el mismo
            panel también puedes abrirlo en una nueva pestaña o descargar el
            archivo ZIP con todos los artefactos de la evaluación.
          </p>
        </>
      ),
    },
    {
      id: "historial",
      title: "Historial",
      content: (
        <>
          <Lead>
            Catálogo completo de evaluaciones en el servidor. Permite retomar una
            evaluación anterior y acceder a su informe sin volver a ejecutar.
          </Lead>
          <Diagram>
            <HistorialDiagram />
          </Diagram>
          <IconOptionList
            items={[
              {
                Icon: MousePointerClick,
                name: "Seleccionar",
                desc: "haz clic en una fila para cargar esa evaluación como activa; sus métricas y reporte vuelven a mostrarse.",
              },
              {
                Icon: Pencil,
                name: "Renombrar",
                desc: "asigna un nombre funcional para identificar la evaluación en el catálogo.",
              },
              {
                Icon: FileText,
                name: "Ver informe",
                desc: "abre el informe HTML en una nueva pestaña directamente desde el historial.",
              },
              {
                Icon: Download,
                name: "Descargar",
                desc: "exporta el informe HTML por separado o la carpeta completa con todos los artefactos (informe, métricas JSON, configuración).",
              },
              {
                Icon: XCircle,
                name: "Cancelar",
                desc: "detiene una evaluación en curso desde el propio catálogo.",
              },
              {
                Icon: Trash2,
                name: "Eliminar",
                desc: "borra la evaluación y todos sus resultados. No se puede deshacer.",
              },
              {
                Icon: Trash2,
                name: "Limpiar sesiones incompletas",
                desc: "elimina carpetas vacías y ejecuciones huérfanas — útil tras varias cancelaciones.",
              },
              {
                Icon: Trash2,
                name: "Limpiar todas las sesiones",
                desc: "elimina TODAS las evaluaciones — úsalo con cuidado.",
              },
            ]}
          />
        </>
      ),
    },
  ];
}
