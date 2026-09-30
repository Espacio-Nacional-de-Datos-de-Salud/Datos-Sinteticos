// Help content for the Generación instructions manual.
//
// One entry per top-level page section (WorkflowGroup); the `id` matches the
// section's DOM id. Structurally a sibling of the other instructions-content
// files; presentational helpers are duplicated here so this module stays
// self-contained.

"use client";

import {
  MousePointerClick,
  Pencil,
  Download,
  XCircle,
  Trash2,
  Sparkles,
  type LucideIcon,
} from "lucide-react";
import type { InstructionsEntry } from "@/components/layout/instructions-panel";
import { AdvancedBadge } from "../ui/advanced-section";

// ── Brand palette ───────────────────────────────────────────────────────────
const NAVY = "#00215C";
const BLUE = "#114da6";
const SKY = "#c9d4ea";
const AMBER = "#C79200";
const INK = "#2b3a52";
// Violet of the "advanced / optional" sparkle (matches the sidebar nav marker
// and AdvancedBadge) — used to flag advanced steps in the overview stepper.
const VIOLET = "#a78bfa";

// ── Presentational helpers ──────────────────────────────────────────────────
function Lead({ children }: { children: React.ReactNode }) {
  return <p>{children}</p>;
}

function Subtitle({
  children,
  badge,
}: {
  children: React.ReactNode;
  badge?: React.ReactNode;
}) {
  return (
    <h4 className="mt-3.5 flex items-center gap-1.5 first:mt-0">
      <span className="text-[13.5px] font-bold uppercase tracking-wide text-[#16386f] underline decoration-[#FFDB00] decoration-2 underline-offset-4 dark:text-[#dce8ff]">
        {children}
      </span>
      {badge}
    </h4>
  );
}

function Diagram({ children }: { children: React.ReactNode }) {
  return <div className="my-1 flex justify-center">{children}</div>;
}

function OptionList({
  items,
}: {
  items: Array<{ name: string; desc: React.ReactNode; badge?: React.ReactNode }>;
}) {
  return (
    <ul className="space-y-1">
      {items.map((it, i) => (
        <li key={i} className="flex gap-2">
          <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
          <span>
            <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
              {it.name}
            </span>
            {it.badge ? (
              <span className="ml-1 inline-flex items-center gap-1 align-middle">
                {it.badge}
              </span>
            ) : null}{" "}
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

function AdvancedTip({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#c8d0ee] bg-[#f5f6fe] dark:border-[#34306a] dark:bg-[#13112b]">
      <div className="flex items-center gap-1.5 bg-[#5b53d6] px-2.5 py-1">
        <Sparkles className="h-3.5 w-3.5 text-white" aria-hidden />
        <span className="text-[10.5px] font-bold uppercase tracking-wide text-white">
          Avanzado
        </span>
      </div>
      <div className="space-y-2 px-2.5 py-1.5 text-[12px] text-[#3a3568] dark:text-[#b8b2e6]">
        {children}
      </div>
    </div>
  );
}

function StepTable({ steps }: { steps: Array<{ name: string; desc: string; badge?: React.ReactNode }> }) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#cdd9ec] shadow-[0_1px_3px_rgba(16,40,80,0.06)] dark:border-[#26375f]">
      <div className="grid grid-cols-[42%_58%] bg-[#16386f] text-[10px] font-bold uppercase tracking-[0.06em] text-white">
        <div className="px-3 py-2">Fase</div>
        <div className="border-l border-white/15 px-3 py-2">Explicación</div>
      </div>
      {steps.map((s, i) => (
        <div
          key={s.name}
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
            {s.badge}
          </div>
          <div className="border-l border-[#e5ebf6] px-3 py-2.5 text-[12px] leading-snug text-[#3a4a63] dark:border-[#26375f] dark:text-[#aebdd9]">
            <div className="flex items-center gap-2">
              <span>{s.desc}</span>
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

function OptionCallout({
  name,
  state,
  badge,
  children,
}: {
  name: string;
  state: string;
  badge?: React.ReactNode;
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
        {badge}
      </div>
      <div className="mt-1">
        <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
          {name}
        </span>{" "}
        — {children}
      </div>
    </div>
  );
}

// A caution note: warm amber accent + ⚠ marker, visually distinct from the
// yellow "Opción activable" callouts so it reads as a warning, not an option.
// Mirrors the CautionNote used in the Reglas de negocio manual.
function CautionNote({
  title,
  badge,
  children,
}: {
  title: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border-l-4 border-[#E8890C] bg-[#fff5e8] py-2 pl-2.5 pr-3 dark:bg-[#3a2a10]">
      <div className="flex items-center gap-1.5">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0" aria-hidden>
          <path
            d="M8 1.5 15 14H1z"
            fill="none"
            stroke="#C56A00"
            strokeWidth={1.6}
            strokeLinejoin="round"
          />
          <line
            x1={8}
            y1={6}
            x2={8}
            y2={10}
            stroke="#C56A00"
            strokeWidth={1.6}
            strokeLinecap="round"
          />
          <circle cx={8} cy={12} r={0.9} fill="#C56A00" />
        </svg>
        <span className="text-[10.5px] font-bold uppercase tracking-wide text-[#C56A00] dark:text-[#f0b366]">
          {title}
        </span>
        {badge}
      </div>
      <div className="mt-1 space-y-1.5">{children}</div>
    </div>
  );
}

const svgBase = {
  preserveAspectRatio: "xMidYMid meet" as const,
  fontFamily: "inherit",
  // Figures are drawn with light-theme brand colors (navy text, white table
  // bodies), so they need a light "paper" to stay legible. In dark mode we use
  // a muted slate paper instead of bright white so the figure blends into the
  // dark rail rather than glaring — still light enough for the dark ink on top.
  className: "rounded-lg border border-[#e3e9f4] bg-[#f7f9fd] p-2 dark:border-[#2a3a5e] dark:bg-[#c3cee2]",
};

// The exact lucide-react "Sparkles" icon (the ✦ used to flag advanced steps in
// the sidebar nav), embedded so the diagram marker is visually identical.
// Lucide's source viewBox is 24×24; we place it centred at (cx, cy) and scale
// to `size`. Drawn stroked in violet like the nav icon.
const SPARKLES_NODES = [
  "M11.017 2.814a1 1 0 0 1 1.966 0l1.051 5.558a2 2 0 0 0 1.594 1.594l5.558 1.051a1 1 0 0 1 0 1.966l-5.558 1.051a2 2 0 0 0-1.594 1.594l-1.051 5.558a1 1 0 0 1-1.966 0l-1.051-5.558a2 2 0 0 0-1.594-1.594l-5.558-1.051a1 1 0 0 1 0-1.966l5.558-1.051a2 2 0 0 0 1.594-1.594z",
  "M20 2v4",
  "M22 4h-4",
] as const;

function SparkleMark({ cx, cy, size = 12 }: { cx: number; cy: number; size?: number }) {
  const s = size / 24;
  return (
    <g
      transform={`translate(${cx - size / 2} ${cy - size / 2}) scale(${s})`}
      fill="none"
      stroke={VIOLET}
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      {SPARKLES_NODES.map((d) => (
        <path key={d} d={d} />
      ))}
      <circle cx={4} cy={20} r={2} />
    </g>
  );
}

// Horizontal numbered stepper — used for the Resumen overview. Steps flagged
// `optional` carry a violet sparkle above their node. Unlike the other figures,
// this one carries its own surface classes so it can blend into the dark rail
// (the brand-colored schematics keep the shared light "paper" of `svgBase`).
type Step = { lines: string[]; optional?: boolean };

function StepFlowH({ steps }: { steps: readonly Step[] }) {
  const colW = 92;
  const width = steps.length * colW;
  // Extra room above for the sparkle marker.
  const cy = 25;
  const height = 68;
  return (
    <svg
      preserveAspectRatio="xMidYMid meet"
      fontFamily="inherit"
      // Blended surfaces: light paper in day, deep navy that melts into the
      // rail (`dark:bg-[#0c1730]`) at night. Text/marker colors adapt via CSS
      // vars set per-theme on the <svg> so the stepper stays legible.
      className="rounded-lg border border-[#e3e9f4] bg-[#f7f9fd] p-2 [--node:#00215C] [--ink:#2b3a52] [--track:#c9d4ea] dark:border-[#23335b] dark:bg-[#0e1a36] dark:[--node:#2a4a85] dark:[--ink:#aebdd9] dark:[--track:#2c416e]"
      width="100%"
      style={{ maxWidth: width }}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={steps
        .map((s) => s.lines.join(" ") + (s.optional ? " (avanzado)" : ""))
        .join("; ")}
    >
      <line
        x1={colW / 2}
        y1={cy}
        x2={width - colW / 2}
        y2={cy}
        stroke="var(--track)"
        strokeWidth={2.5}
        strokeLinecap="round"
      />
      {steps.map((step, i) => {
        const cx = colW / 2 + i * colW;
        return (
          <g key={i}>
            <circle cx={cx} cy={cy} r={15} fill="var(--node)" opacity={0.18} />
            <circle cx={cx} cy={cy} r={11} fill="var(--node)" />
            <text x={cx} y={cy + 4.5} fontSize={12.5} fontWeight={700}
              fill="#fff" textAnchor="middle">
              {i + 1}
            </text>
            {/* advanced marker — lucide sparkle just above the node, nudged out
                so it clears the number */}
            {step.optional && <SparkleMark cx={cx + 17} cy={cy - 15} size={12} />}
            {step.lines.map((ln, j) => (
              <text key={j} x={cx} y={cy + 28 + j * 10} fontSize={9} fontWeight={600}
                fill="var(--ink)" textAnchor="middle">
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
        { lines: ["Selección", "de modelo"] },
        { lines: ["Configuración", "de volumen"] },
        { lines: ["Condicionar", "la generación"], optional: true },
        { lines: ["Revisión del", "historial"] },
      ]}
    />
  );
}

// Diagram showing the two sample-size modes: standard (mother fixed) vs
// fixed-target (child fixed, mother floats adaptively).
function SampleSizeDiagram() {
  return (
    <svg {...svgBase} width="320" height="148" viewBox="0 0 320 148" role="img"
      aria-label="Modo estándar: tabla maestra fija, hijos en cascada. Objetivo fijo: tabla hija fija, maestra libre">
      {/* ── Left column: Modo estándar ────────────────────────────── */}
      <text x={75} y={13} fontSize={10} fontWeight={700} fill={NAVY} textAnchor="middle">
        Modo estándar
      </text>
      <text x={75} y={24} fontSize={8.5} fill="#5f83be" textAnchor="middle">
        maestra fija · hijos en cascada
      </text>
      {/* mother box — filled navy (fixed) */}
      <rect x={10} y={30} width={130} height={28} rx={6} fill={NAVY} />
      <text x={75} y={48} fontSize={11} fontWeight={700} fill="#fff" textAnchor="middle">
        pacientes · fijas
      </text>
      {/* arrow down */}
      <line x1={75} y1={58} x2={75} y2={73} stroke={SKY} strokeWidth={2} strokeLinecap="round" />
      <path d="M68 69 l7 7 l7-7" stroke={SKY} strokeWidth={2} fill="none"
        strokeLinecap="round" strokeLinejoin="round" />
      {/* child box — outline (cascades) */}
      <rect x={10} y={77} width={130} height={28} rx={6} fill="#eef3ff"
        stroke={NAVY} strokeWidth={1.5} />
      <text x={75} y={95} fontSize={10.5} fill={INK} textAnchor="middle">
        episodios · en cascada
      </text>

      {/* ── Right column: Objetivo fijo ───────────────────────────── */}
      <text x={245} y={13} fontSize={10} fontWeight={700} fill={NAVY} textAnchor="middle">
        Objetivo fijo
      </text>
      <text x={245} y={24} fontSize={8.5} fill="#5f83be" textAnchor="middle">
        hija fija · maestra libre
      </text>
      {/* mother box — dashed (floats) */}
      <rect x={180} y={30} width={130} height={28} rx={6} fill="#f5f8fd"
        stroke={SKY} strokeWidth={1.5} strokeDasharray="5 3" />
      <text x={245} y={48} fontSize={10.5} fill="#8da0be" textAnchor="middle">
        pacientes · libre
      </text>
      {/* arrow down */}
      <line x1={245} y1={58} x2={245} y2={73} stroke={SKY} strokeWidth={2} strokeLinecap="round" />
      <path d="M238 69 l7 7 l7-7" stroke={SKY} strokeWidth={2} fill="none"
        strokeLinecap="round" strokeLinejoin="round" />
      {/* child box — filled navy (fixed target) */}
      <rect x={180} y={77} width={130} height={28} rx={6} fill={NAVY} />
      <text x={245} y={95} fontSize={11} fontWeight={700} fill="#fff" textAnchor="middle">
        episodios · fijas
      </text>

      {/* ── Legend ────────────────────────────────────────────────── */}
      <rect x={10} y={122} width={14} height={11} rx={3} fill={NAVY} />
      <text x={28} y={131} fontSize={9.5} fill={INK}>tabla con filas fijas</text>
      <rect x={170} y={122} width={14} height={11} rx={3} fill="#f5f8fd"
        stroke={SKY} strokeWidth={1.5} strokeDasharray="4 2" />
      <text x={188} y={131} fontSize={9.5} fill={INK}>tabla con filas libres</text>
    </svg>
  );
}

// Diagram illustrating conditional generation: some columns are pinned
// by user-defined conditions; the rest are freely synthesized by the model.
function ConditionalDiagram() {
  return (
    <svg {...svgBase} width="320" height="96" viewBox="0 0 320 96" role="img"
      aria-label="Columnas condicionadas (valor fijo o proporción) y columnas libres sintetizadas por el modelo">
      {/* header bar */}
      <rect x={2} y={2} width={316} height={20} rx={4} fill={NAVY} />
      <text x={160} y={16} fontSize={9.5} fontWeight={700} fill="#fff" textAnchor="middle">
        fila sintetizada
      </text>
      {/* row background */}
      <rect x={2} y={22} width={316} height={34} rx={4} fill="#fff"
        stroke={NAVY} strokeWidth={1.2} />
      {/* col 1: fixed (conditioned) */}
      <rect x={6} y={26} width={76} height={26} rx={3}
        fill={AMBER} fillOpacity={0.18} stroke={AMBER} strokeWidth={1.4} />
      <text x={44} y={38} fontSize={9} fontWeight={700} fill={AMBER} textAnchor="middle">sexo</text>
      <text x={44} y={48} fontSize={8.5} fill={INK} textAnchor="middle">= "F" (fijo)</text>
      {/* col 2: free */}
      <rect x={86} y={26} width={76} height={26} rx={3}
        fill="#eef3ff" stroke={BLUE} strokeWidth={1.4} />
      <text x={124} y={38} fontSize={9} fontWeight={700} fill={BLUE} textAnchor="middle">edad</text>
      <text x={124} y={48} fontSize={8.5} fill={INK} textAnchor="middle">← modelo</text>
      {/* col 3: proportions (conditioned) */}
      <rect x={166} y={26} width={84} height={26} rx={3}
        fill={AMBER} fillOpacity={0.18} stroke={AMBER} strokeWidth={1.4} />
      <text x={208} y={38} fontSize={9} fontWeight={700} fill={AMBER} textAnchor="middle">servicio</text>
      <text x={208} y={48} fontSize={8.5} fill={INK} textAnchor="middle">60 % URG (prop.)</text>
      {/* col 4: free */}
      <rect x={254} y={26} width={62} height={26} rx={3}
        fill="#eef3ff" stroke={BLUE} strokeWidth={1.4} />
      <text x={285} y={38} fontSize={9} fontWeight={700} fill={BLUE} textAnchor="middle">dx</text>
      <text x={285} y={48} fontSize={8.5} fill={INK} textAnchor="middle">← modelo</text>
      {/* legend */}
      <rect x={6} y={68} width={12} height={10} rx={2}
        fill={AMBER} fillOpacity={0.25} stroke={AMBER} strokeWidth={1.2} />
      <text x={22} y={77} fontSize={9} fill={INK}>columna condicionada</text>
      <rect x={168} y={68} width={12} height={10} rx={2}
        fill="#eef3ff" stroke={BLUE} strokeWidth={1.2} />
      <text x={184} y={77} fontSize={9} fill={INK}>columna libre (modelo)</text>
    </svg>
  );
}

function HistorialDiagram() {
  return (
    <svg {...svgBase} width="320" height="120" viewBox="0 0 320 120" role="img"
      aria-label="Historial de generaciones con la activa resaltada">
      {[0, 1, 2].map((i) => {
        const y = 6 + i * 38;
        const active = i === 0;
        return (
          <g key={i}>
            <rect x={4} y={y} width={312} height={30} rx={7}
              fill={active ? "#eef3ff" : "#fff"} stroke={active ? NAVY : SKY}
              strokeWidth={active ? 2.5 : 1.6} />
            <text x={18} y={y + 20} fontSize={13.5} fontWeight={active ? 700 : 400} fill={INK}>
              Generación {i + 1}{active ? "  ·  activa" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Entries ─────────────────────────────────────────────────────────────────
export function getGeneracionInstructions(): readonly InstructionsEntry[] {
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
            Elige el modelo entrenado, configura el volumen de datos, añade
            condiciones opcionales y lanza la generación. Sigue estos pasos:
          </Lead>
          <StepTable
            steps={[
              {
                name: "Seleccionar modelo",
                desc: "Elige el modelo entrenado del que se generarán los datos. Solo aparecen los modelos con estado completado.",
              },
              {
                name: "Elegir formato",
                desc: "Selecciona CSV o Parquet para la descarga. CSV es universal; Parquet es más compacto y eficiente para conjuntos grandes.",
              },
              {
                name: "Configurar volumen",
                desc: "Indica cuántas filas generar. El modo estándar fija la tabla maestra; el modo objetivo fijo fija una tabla hija y deja la maestra flotante.",
              },
              {
                name: "Añadir condiciones",
                desc: "Restringe el valor de columnas concretas para guiar la síntesis hacia un subgrupo de la distribución.",
                badge: <AdvancedBadge tooltip="Avanzado" />,
              },
              {
                name: "Iniciar generación",
                desc: "Lanza el proceso. Al terminar, los datos sintéticos quedarán disponibles para descargar y previsualizar.",
              },
            ]}
          />

          <Subtitle>Volumen de datos</Subtitle>
          <p>
            El motor de síntesis solo permite definir un objetivo de filas para la tabla maestra del esquema. El tamaño de las demás tablas se genera automáticamente según las relaciones que el modelo haya aprendido, por lo que no puede controlarse al mismo tiempo que el de la maestra. Aun así, sí es posible controlar el tamaño de las tablas hijas: para lograrlo, dejamos de fijar un tamaño para la tabla maestra.</p>
          <Diagram>
            <SampleSizeDiagram />
          </Diagram>
          <OptionList
            items={[
              {
                name: "Modo estándar (maestra fija)",
                desc: "Fija el número de filas de la tabla maestra. Las tablas hijas se generan en cascada con las proporciones aprendidas durante el entrenamiento.",
              },
              {
                name: "Objetivo fijo (tabla hija)",
                badge: (
                  <AdvancedBadge tooltip="Uso avanzado: fija una tabla hija y deja flotar la maestra; el motor la sobresimula de forma adaptativa, por lo que la generación puede tardar más." />
                ),
                desc: "Fija el número de filas de una tabla hija. La tabla maestra se sobresimula de forma adaptativa hasta alcanzar el objetivo en la hija, por lo que la generación puede tardar más.",
              },
            ]}
          />
          <OptionCallout
            name="Sobregeneración y reintentos"
            state="Parámetros avanzados"
            badge={
              <AdvancedBadge tooltip="Parámetros avanzados: solo aparecen cuando el motor necesita sobresimular (objetivo de tabla hija o muestreo por rechazo activo)." />
            }
          >
            Cuando el motor necesita sobresimular — por objetivo de tabla hija o
            por muestreo por rechazo activo — aparecen dos parámetros adicionales:
            <ul className="mt-1.5 space-y-1.5">
              <li className="flex gap-2">
                <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
                <span>
                  <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
                    Factor de sobregeneración
                  </span>{" "}
                  — cuántas filas de más generar en un solo lote.
                </span>
              </li>
              <li className="flex gap-2">
                <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
                <span>
                  <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
                    Reintentos máximos
                  </span>{" "}
                  — cuántas veces puede rearrancar el motor si el lote no basta.
                </span>
              </li>
            </ul>
            <span className="mt-1.5 block">
              Aumentar el factor es siempre más barato que añadir reintentos, ya
              que cada reintento rearranca el motor desde cero.
            </span>
          </OptionCallout>
          <CautionNote
            title="Conflicto entre el muestreo por rechazo y el volumen de datos"
            badge={
              <AdvancedBadge tooltip="Uso avanzado: relevante solo si alguna regla de negocio usa el modo muestreo por rechazo." />
            }
          >
            <p>
              Si alguna regla de negocio usa el modo{" "}
              <strong>muestreo por rechazo</strong> (Configuración → Reglas de
              negocio), conviene entender cómo encaja con el tamaño que fijas
              aquí. El rechazo <strong>siempre elimina</strong> las filas que
              incumplen la regla, de modo que el dataset sintético solo contendrá
              filas válidas. Lo que no siempre se respeta es el{" "}
              <strong>número de filas</strong>.
            </p>
            <p>
              El motor solo resimula intentando acercarse al objetivo cuando la
              tabla cuyo tamaño has fijado <strong>coincide</strong> con la tabla
              sobre la que se aplica la regla. En el{" "}
              <strong>modo estándar</strong> fijas el tamaño de la{" "}
              <strong>maestra</strong>: si la regla afecta a esa misma maestra, el
              motor reintenta hasta acercarse al total pedido. Pero si la regla
              afecta a una <strong>hija</strong>, el esquema se simula una sola
              vez (la maestra impone su número de filas y las hijas caen en
              cascada): tras descartar las filas de la hija que incumplen{" "}
              <strong>no se resimula</strong> para reponerlas. Tendrás la certeza
              de que las filas de la hija cumplen la regla, pero pueden
              ser <strong>menos de las esperadas</strong>.
            </p>
            <p>
              Para que el total de filas también se respete sobre la tabla de la
              regla, usa el modo <strong>«Objetivo fijo»</strong> y fija el tamaño
              de <em>esa</em> tabla: así el motor sobresimula la maestra de forma
              adaptativa hasta alcanzar el objetivo en la tabla de la regla,
              contando solo las filas que la cumplen.
            </p>
          </CautionNote>

          <Subtitle
            badge={
              <AdvancedBadge tooltip="Uso avanzado: guía al modelo para que genere registros que cumplan condiciones sobre columnas concretas." />
            }
          >
            Generación condicional
          </Subtitle>
          <p>
            Permite guiar al modelo para que genere registros que cumplan una o
            varias condiciones sobre columnas concretas de la tabla seleccionada.
          </p>
          <Diagram>
            <ConditionalDiagram />
          </Diagram>
          <OptionList
            items={[
              {
                name: "Valor fijo",
                desc: "Todas las filas generadas tienen exactamente ese valor en la columna indicada.",
              },
              {
                name: "Proporciones",
                desc: "Los valores se distribuyen según los pesos especificados, útil para sobre- o infrarrepresentar un subgrupo.",
              },
              {
                name: "Rango numérico",
                desc: "Los valores numéricos se generan dentro de un intervalo con distribución uniforme o normal. Solo disponible para columnas numéricas.",
              },
              {
                name: "Rango de fechas",
                desc: "Los valores de fecha se generan uniformemente entre dos fechas. Solo disponible para columnas de tipo fecha.",
              },
            ]}
          />
          <Example>
            Para generar solo pacientes de entre 18 y 65 años, selecciona la
            tabla <code>pacientes</code>, añade una condición sobre{" "}
            <code>edad</code> con modo{" "}
            <span className="font-semibold">Rango numérico</span>, mínimo 18 y
            máximo 65.
          </Example>
          <AdvancedTip>
            <p>
              Si en pasos previos creaste una{" "}
              <strong>variable estratificada</strong>, condicionar sobre ella es
              una buena opción para aprovechar lo que el modelo aprendió de cada
              subgrupo. Por ejemplo, con la variable <code>is_adult</code> a{" "}
              <code>false</code> generas solo niños reproduciendo sus patrones
              propios.
            </p>
            <p>
              Esto también es posible definiendo un rango numérico entre 1 y 18
              años, pero en este caso nosotros forzamos las proporciones{" "}
              de aparición de las edades dentro de ese rango (uniforme o
              normal), mientras que la variable estratificada permite al modelo
              generar la distribución de edades que aprendió de los datos
              reales.
            </p>
          </AdvancedTip>
        </>
      ),
    },
    {
      id: "resultados",
      title: "Resultados",
      content: (
        <>
          <Lead>
            Una vez lanzada la generación, aquí se muestra su progreso y, al
            completarse, el informe de sanidad, las estadísticas de rechazo y la
            vista previa del dataset sintético.
          </Lead>

          <Subtitle>Generación actual</Subtitle>
          <p>
            Muestra el estado de la generación en curso o de la última iniciada:
            fase actual, modelo utilizado y número de filas configurado. Al
            completarse, se habilita la descarga directa del dataset.
          </p>
          <OptionList
            items={[
              {
                name: "Cancelar",
                desc: "Detiene una generación en curso. Los artefactos parciales se conservan en el historial marcados como cancelados.",
              },
              {
                name: "Descargar datos sintéticos",
                desc: "Descarga el dataset en el formato elegido (CSV o Parquet) directamente desde la generación activa.",
              },
              {
                name: "Tiempos de ejecución",
                desc: "Despliega los tiempos por fase una vez la generación ha terminado, útil para identificar cuellos de botella.",
              },
            ]}
          />

          <Subtitle
            badge={
              <AdvancedBadge tooltip="Uso avanzado: verificación detallada de que los datos sintéticos cumplen las restricciones e integridad referencial definidas." />
            }
          >
            Informe de sanidad
          </Subtitle>
          <p>
            El informe de sanidad verifica automáticamente que los datos
            sintéticos cumplen las restricciones definidas en la Carga de Datos y
            en la Configuración: integridad referencial, consistencia de claves
            foráneas y todas las reglas de negocio.
          </p>
          <OptionList
            items={[
              {
                name: "Comprobaciones generales",
                desc: "Integridad referencial (FK apuntan a registros existentes) y consistencia FK contextual dentro de grupos de contexto.",
              },
              {
                name: "Comprobaciones de reglas",
                desc: "Cada regla de negocio (relación de fechas, relación numérica, consistencia semántica, composición de fecha, columnas derivadas) se verifica individualmente, reportando las filas que la incumplen.",
              },
            ]}
          />

          <Subtitle
            badge={
              <AdvancedBadge tooltip="Uso avanzado: métricas del muestreo por rechazo (filas generadas, aceptadas, rechazadas y reintentos), solo relevantes si alguna regla usa este modo." />
            }
          >
            Estadísticas de muestreo por rechazo
          </Subtitle>
          <p>
            Cuando alguna regla de negocio usa el modo muestreo por rechazo, esta
            tarjeta detalla el rendimiento del proceso. En cada intento se generan
            más filas de las necesarias (sobre-generación) y se aplican las reglas
            de rechazo; el reparto final de cada tabla se desglosa por columnas:
          </p>
          <OptionList
            items={[
              {
                name: "Generadas",
                desc: "Filas producidas en total por el modelo, sumando todos los intentos.",
              },
              {
                name: "Aceptadas",
                desc: "Filas que cumplen la regla y se conservan en el resultado final.",
              },
              {
                name: "Objetivo",
                desc: "Filas que se querían obtener en cada tabla, a escala de los datos reales. La tabla fijada (marcada con un pin) es la que el muestreo intenta alcanzar —la maestra en el modo estándar, o la hija elegida en «objetivo fijo»—; las demás cascadean a partir de ella. Ningún objetivo está garantizado: con reglas muy restrictivas ni la fijada se alcanza y el resultado sale «parcial»; en ese caso, resimula subiendo los intentos o el factor de sobre-generación.",
              },
              {
                name: "Rechazadas",
                desc: "Filas descartadas por incumplir la regla; no incluye las sobrantes. Al descartar una fila también caen sus hijas en cascada, por lo que una tabla sin reglas propias puede mostrar muchas rechazadas: son hijas de filas rechazadas en su tabla padre, no incumplimientos suyos.",
              },
              {
                name: "Sobrantes",
                desc: "Filas que sí cumplían la regla pero se descartaron por exceder el tamaño solicitado en la tabla fijada, y que no se contabilizan como incumplimientos. Nunca habrá filas sobrantes en tablas no fijadas.",
              },
              {
                name: "% incumplimiento",
                desc: "Rechazadas ÷ (rechazadas + aceptadas). Mide cuántas filas válidas hubo que tirar por la regla; cuanto más bajo, menos restrictiva resulta la regla sobre los datos del modelo.",
              },
            ]}
          />
          <p>
            Esto explica un caso que suele sorprender:{" "}
            <strong>por qué hay filas generadas «sobrantes» con 0 rechazadas</strong>.
            Para cumplir exactamente con el número de filas solicitado, cada
            intento sobre-genera datos. Las filas que cumplen las reglas pero
            superan el tamaño objetivo se descartan como <em>sobrantes</em>. Por
            eso es normal que las generadas superen a las aceptadas aunque ninguna
            fila haya sido rechazada por incumplir la regla.
          </p>
          <p>
            La cabecera muestra además los <strong>intentos usados</strong> sobre el
            máximo permitido y el <strong>factor de sobre-generación</strong>
            (p. ej. ×2.0) aplicado en cada intento. Si se alcanza el máximo de
            intentos sin llegar al objetivo, el resultado se marca como{" "}
            <em>parcial</em>: la regla era demasiado restrictiva para los datos que
            el modelo es capaz de producir.
          </p>

          <Subtitle>Datos sintéticos</Subtitle>
          <p>
            Vista previa tabular del dataset generado. Permite inspeccionar una
            muestra de cada tabla directamente en el navegador sin descargar el
            fichero completo.
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
            Catálogo completo de generaciones en el servidor. Permite retomar
            una generación anterior y acceder a sus datos sintéticos sin volver a
            ejecutar.
          </Lead>
          <Diagram>
            <HistorialDiagram />
          </Diagram>
          <IconOptionList
            items={[
              {
                Icon: MousePointerClick,
                name: "Seleccionar",
                desc: "haz clic en una fila para cargar esa generación como activa; sus resultados vuelven a mostrarse en la sección de Resultados.",
              },
              {
                Icon: Pencil,
                name: "Renombrar",
                desc: "asigna un nombre funcional para identificar la generación en el catálogo.",
              },
              {
                Icon: Download,
                name: "Descargar",
                desc: "exporta directamente el dataset sintético o la carpeta completa con todos los artefactos (dataset, configuración, informe de sanidad).",
              },
              {
                Icon: XCircle,
                name: "Cancelar",
                desc: "detiene una generación en curso desde el propio catálogo.",
              },
              {
                Icon: Trash2,
                name: "Eliminar",
                desc: "borra la generación y todos sus datos sintéticos. No se puede deshacer.",
              },
              {
                Icon: Trash2,
                name: "Limpiar sesiones incompletas",
                desc: "elimina carpetas vacías y ejecuciones huérfanas — útil tras varias cancelaciones.",
              },
              {
                Icon: Trash2,
                name: "Limpiar todas las sesiones",
                desc: "elimina TODAS las generaciones — úsalo con cuidado.",
              },
            ]}
          />
        </>
      ),
    },
  ];
}
