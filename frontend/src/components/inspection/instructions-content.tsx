// Help content for the Carga de Datos instructions manual.
//
// One entry per page section (WorkflowGroup); the `id` matches the section's
// DOM id. Each entry combines concise prose, the meaning of the available
// options, a small inline schematic, and a concrete usage example.

"use client";

import { useState } from "react";
import {
  AlertOctagon,
  BarChart3,
  CalendarClock,
  ChevronDown,
  Download,
  Droplet,
  ExternalLink,
  Maximize2,
  MousePointerClick,
  Pencil,
  Trash2,
  XCircle,
  type LucideIcon,
} from "lucide-react";

import {
  ENCODING_TYPES,
  ENCODING_TYPE_DESCRIPTIONS,
  ENCODING_TYPE_LABELS,
} from "@/lib/api";
import { NativeSelect } from "@/components/ui/native-select";
import type { InstructionsEntry } from "@/components/layout/instructions-panel";

// ── Brand palette ───────────────────────────────────────────────────────────
const NAVY = "#00215C";
const BLUE = "#114da6";
const SKY = "#c9d4ea";
// Darker amber for the PK key marker — the brand yellow is too light to read.
const AMBER = "#C79200";
const INK = "#2b3a52";
// Violet of the "advanced / optional" sparkle (matches AdvancedBadge's
// text-violet-400) — used to flag optional steps in the overview stepper.
const VIOLET = "#a78bfa";

// ── Presentational helpers ──────────────────────────────────────────────────
function Lead({ children }: { children: React.ReactNode }) {
  return <p>{children}</p>;
}

// A sub-section heading inside a help block: a slightly larger title with a
// yellow underline.
function Subtitle({ children }: { children: React.ReactNode }) {
  return (
    <h4 className="mt-3.5 text-[13.5px] font-bold uppercase tracking-wide text-[#16386f] underline decoration-[#FFDB00] decoration-2 underline-offset-4 first:mt-0 dark:text-[#dce8ff]">
      {children}
    </h4>
  );
}

// Borderless diagram slot — the SVG sits directly on the white panel.
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

// Like OptionList, but each item carries the same icon the page shows for that
// action, so the help mirrors the buttons the user actually sees.
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
      <div className="px-2.5 py-1.5 text-[12px] text-[#4a4214] dark:text-[#d8c98a]">
        {children}
      </div>
    </div>
  );
}

// A note describing an activatable (opt-in / opt-out) option. Styled to stand
// out gently — a soft navy-tinted card with a yellow accent edge, a small
// sliders icon, and a yellow state badge pinned to the top-right corner.
function OptionCallout({
  name,
  state,
  children,
}: {
  name: string;
  /** Short tag describing the default, e.g. "Activada por defecto". */
  state: string;
  children: React.ReactNode;
}) {
  return (
    <div className="relative rounded-md border-l-4 border-[#FFDB00] bg-[#eef3ff] py-2 pl-2.5 pr-3 dark:bg-[#16284d]">
      {/* state badge — yellow, pinned to the top-right corner */}
      <span className="absolute right-0 top-0 rounded-bl-md rounded-tr-[3px] bg-[#FFDB00] px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-[#00215C]">
        {state}
      </span>
      <div className="flex items-center gap-1.5">
        {/* sliders / adjustable-setting icon */}
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
      <p className="mt-1">
        <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
          {name}
        </span>{" "}
        — {children}
      </p>
    </div>
  );
}

// A prominent select dropdown for the manual's interactive explorers — a
// navy-bordered field with a soft tint and a clear chevron, so it stands out
// as an actionable control rather than plain text.
function SelectMenu({
  value,
  onChange,
  options,
  groups,
}: {
  value: string;
  onChange: (v: string) => void;
  /** Flat option list. Ignored when `groups` is provided. */
  options?: Array<{ value: string; label: string }>;
  /** Grouped options rendered as <optgroup> sections (takes precedence). */
  groups?: Array<{ label: string; options: Array<{ value: string; label: string }> }>;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full appearance-none rounded-lg border-2 border-[#16386f] bg-[#eef3ff] pl-3 pr-9 text-[13px] font-semibold text-[#16386f] shadow-sm transition-colors hover:bg-[#e2eaff] focus:outline-none focus:ring-2 focus:ring-[#5f83be] dark:border-[#5f83be] dark:bg-[#16284d] dark:text-[#dce8ff]"
      >
        {groups
          ? groups.map((g) => (
            <optgroup key={g.label} label={g.label}>
              {g.options.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </optgroup>
          ))
          : (options ?? []).map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
      </select>
      <svg
        viewBox="0 0 12 12"
        className="pointer-events-none absolute right-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-[#16386f] dark:text-[#dce8ff]"
        aria-hidden
      >
        <path d="M2 4l4 4 4-4" stroke="currentColor" strokeWidth={2}
          fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
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
// the sidebar nav for e.g. "Reglas de negocio"), embedded so the diagram marker
// is visually identical. Lucide's source viewBox is 24×24; we place it centred
// at (cx, cy) and scale to `size`. Drawn stroked in violet like the nav icon.
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

// Horizontal numbered stepper: numbered nodes on a connecting track, with a
// short label beneath each. Clean and compact — used for the Resumen overview.
// Steps flagged `optional` carry a violet sparkle above their node and a legend
// is shown below so the marker's meaning is explicit. Unlike the other figures,
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
      // rail (`dark:bg-[#0c1730]`) at night. Text/marker colors below adapt via
      // CSS vars set per-theme on the <svg> so the stepper stays legible.
      className="rounded-lg border border-[#e3e9f4] bg-[#f7f9fd] p-2 [--node:#00215C] [--ink:#2b3a52] [--track:#c9d4ea] dark:border-[#23335b] dark:bg-[#0e1a36] dark:[--node:#2a4a85] dark:[--ink:#aebdd9] dark:[--track:#2c416e]"
      width="100%"
      style={{ maxWidth: width }}
      viewBox={`0 0 ${width} ${height}`}
      role="img"
      aria-label={steps
        .map((s) => s.lines.join(" ") + (s.optional ? " (avanzado)" : ""))
        .join("; ")}
    >
      {/* connecting track */}
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
            {/* soft halo */}
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
        { lines: ["Carga de", "ficheros"] },
        { lines: ["Revisión de", "relaciones"], optional: true },
        { lines: ["Revisión de", "tipos"], optional: true },
        { lines: ["Visualización", "de datos"] },
        { lines: ["Visualización", "de perfilado"] },
        { lines: ["Revisión del", "historial"] },
      ]}
    />
  );
}

// A two-column table: the phase name on the left, its explanation on the
// right, one row per step, with a header row.
function StepTable({
  steps,
}: {
  steps: Array<{ name: string; desc: string }>;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#cdd9ec] shadow-[0_1px_3px_rgba(16,40,80,0.06)] dark:border-[#26375f]">
      {/* header row */}
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
          </div>
          <div className="border-l border-[#e5ebf6] px-3 py-2.5 text-[12px] leading-snug text-[#3a4a63] dark:border-[#26375f] dark:text-[#aebdd9]">
            {s.desc}
          </div>
        </div>
      ))}
    </div>
  );
}

// One table card for the relationships diagram: a header, one or two
// highlighted key rows (PK/FK), plain rows, and a role caption underneath.
type KeyRow = { col: string; color: string; tag: string };
function RelTable({
  x,
  name,
  role,
  keys,
  rows,
}: {
  x: number;
  name: string;
  role: string;
  keys: KeyRow[];
  rows: string[];
}) {
  const rowH = 21;
  const top = 26; // leaves room for the role pill above the table
  return (
    <g transform={`translate(${x} 0)`}>
      {/* role caption — a small pill so it reads clearly above the table */}
      <rect x={18} y={2} width={104} height={17} rx={8.5} fill={NAVY} />
      <text x={70} y={14} fontSize={10} fontWeight={700} fill="#fff" textAnchor="middle">
        {role}
      </text>
      <g transform={`translate(0 ${top})`}>
        <rect width={140} height={118} rx={8} fill="#fff" stroke={NAVY} strokeWidth={2} />
        <rect width={140} height={26} rx={8} fill={NAVY} />
        <rect y={18} width={140} height={8} fill={NAVY} />
        <text x={70} y={18} fontSize={13} fontWeight={700} fill="#fff" textAnchor="middle">
          {name}
        </text>
        {keys.map((k, i) => {
          const y = 30 + i * rowH;
          return (
            <g key={k.col}>
              <rect x={4} y={y} width={132} height={rowH - 2} rx={4}
                fill={k.color} fillOpacity={0.16} />
              <circle cx={16} cy={y + 9.5} r={5.5} fill={k.color}
                stroke={NAVY} strokeWidth={1.2} />
              <text x={28} y={y + 13} fontSize={11} fontWeight={600} fill={INK}>
                {k.col}
              </text>
              <text x={132} y={y + 13} fontSize={9.5} fontWeight={700}
                fill={k.color} textAnchor="end">
                {k.tag}
              </text>
            </g>
          );
        })}
        {rows.map((r, i) => (
          <text key={r} x={28} y={30 + (keys.length + i) * rowH + 13}
            fontSize={11} fill={INK}>
            {r}
          </text>
        ))}
      </g>
    </g>
  );
}

// Two health-domain tables linked by a PK → FK relationship.
function RelacionesDiagram() {
  return (
    <svg {...svgBase} width="340" height="196" viewBox="0 0 340 196" role="img"
      aria-label="Relación entre una tabla padre y una tabla hija mediante clave primaria y foránea">
      <RelTable
        x={2}
        name="pacientes"
        role="Tabla padre"
        keys={[{ col: "id_paciente", color: AMBER, tag: "PK" }]}
        rows={["nombre", "fecha_nac.", "sexo"]}
      />
      <RelTable
        x={198}
        name="episodios"
        role="Tabla hija"
        keys={[
          { col: "id_episodio", color: AMBER, tag: "PK" },
          { col: "id_paciente", color: BLUE, tag: "FK" },
        ]}
        rows={["diagnóstico", "fecha_alta"]}
      />
      {/* relationship link: pacientes.id PK (left key row, y≈66) →
          episodios.id_paciente FK (second key row, y≈87) */}
      <path
        d="M142 66 C 164 66, 176 87, 198 87 m-9 -6 l9 6 l-9 6"
        stroke={BLUE}
        strokeWidth={2.5}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <text x={170} y={70} fontSize={10} fill={BLUE} textAnchor="middle" fontWeight={600}>
        1 : N
      </text>
      {/* legend */}
      <g transform="translate(2 174)">
        <circle cx={7} cy={7} r={6} fill={AMBER} stroke={NAVY} strokeWidth={1.4} />
        <text x={19} y={11} fontSize={11} fill={INK}>PK · clave primaria</text>
        <circle cx={172} cy={7} r={6} fill={BLUE} stroke={NAVY} strokeWidth={1.4} />
        <text x={184} y={11} fontSize={11} fill={INK}>FK · clave foránea</text>
      </g>
    </svg>
  );
}

// A "concept" card: a distinct navy-tinted panel with a small lightbulb badge,
// used to explain a MostlyAI modelling concept that isn't a step or an option
// (so it reads differently from the StepTable / OptionCallout / Example blocks).
function ConceptCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#cdd9ec] bg-[#f5f8fd] dark:border-[#26375f] dark:bg-[#0e1b36]">
      <div className="flex items-center gap-1.5 bg-[#16386f] px-2.5 py-1.5">
        <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" aria-hidden>
          <path
            d="M8 1.5a4.5 4.5 0 0 0-2.7 8.1c.4.3.7.8.7 1.3v.6h4v-.6c0-.5.3-1 .7-1.3A4.5 4.5 0 0 0 8 1.5Z"
            fill="#FFDB00"
          />
          <rect x={6} y={12.5} width={4} height={1.6} rx={0.8} fill="#FFDB00" />
          <rect x={6.6} y={14.6} width={2.8} height={1.3} rx={0.65} fill="#FFDB00" />
        </svg>
        <span className="text-[10.5px] font-bold uppercase tracking-wide text-white">
          Concepto · {title}
        </span>
      </div>
      <div className="space-y-2 px-3 py-2.5 text-[12px] leading-relaxed text-[#3a4a63] dark:text-[#aebdd9]">
        {children}
      </div>
    </div>
  );
}

// Context-relationship schematic: a parent table whose row defines the
// "context" in which the child table's related rows are generated together.
function ContextDiagram() {
  return (
    <svg {...svgBase} width="340" height="150" viewBox="0 0 340 150" role="img"
      aria-label="Una fila de la tabla padre define el contexto en el que se generan juntas sus filas hijas">
      {/* parent row (context anchor) */}
      <rect x={8} y={20} width={104} height={34} rx={7} fill="#fff"
        stroke={NAVY} strokeWidth={2.5} />
      <text x={60} y={35} fontSize={11} fontWeight={700} fill={INK} textAnchor="middle">
        paciente #42
      </text>
      <text x={60} y={48} fontSize={9} fill={INK} textAnchor="middle">
        (contexto)
      </text>
      <text x={60} y={13} fontSize={9.5} fontWeight={700} fill={NAVY} textAnchor="middle">
        TABLA PADRE
      </text>

      {/* child rows generated within that context */}
      {[0, 1, 2].map((i) => {
        const y = 6 + i * 34;
        return (
          <g key={i}>
            <rect x={188} y={y} width={104} height={28} rx={6} fill="#eef3ff"
              stroke={NAVY} strokeWidth={1.6} />
            <text x={240} y={y + 18} fontSize={10.5} fill={INK} textAnchor="middle">
              episodio {i + 1}
            </text>
            {/* link from the parent context to each child row */}
            <path
              d={`M112 37 C 150 37, 150 ${y + 14}, 188 ${y + 14}`}
              stroke={NAVY}
              strokeWidth={1.8}
              fill="none"
              strokeLinecap="round"
            />
          </g>
        );
      })}
      <text x={240} y={123} fontSize={9.5} fontWeight={700} fill={NAVY} textAnchor="middle">
        TABLA HIJA
      </text>
      <text x={240} y={136} fontSize={9} fill={INK} textAnchor="middle">
        generadas juntas, en contexto
      </text>
    </svg>
  );
}

// Legend of the "potentially problematic" column flags the inspection can
// raise. Mirrors the icons/colors of the Tipos de codificación card's legend
// (see types-card.tsx WARNING_META) so the rail and the page read the same.
type WarningDoc = {
  Icon: LucideIcon;
  label: string;
  /** Icon badge color — matches the card's badgeClass. */
  badgeClass: string;
  /** Left-accent + tint of the row — matches the card's chipClass. */
  rowClass: string;
  what: string;
  /** Whether the column is excluded from training automatically. */
  autoExcluded: boolean;
  action: string;
};

const WARNING_DOCS: WarningDoc[] = [
  {
    Icon: AlertOctagon,
    label: "Tipo incompatible",
    badgeClass: "bg-red-600 text-white",
    rowClass: "border-red-500 bg-red-50 dark:bg-red-950/40",
    what: "La columna mezcla números y texto sin un tipo de codificación seguro que los represente a la vez (p. ej. una columna con «12», «N/D» y «pendiente»).",
    autoExcluded: true,
    action: "Se excluye del entrenamiento por defecto. Para conservarla, separa o limpia los datos (deja un único tipo de valor) y vuelve a incluirla.",
  },
  {
    Icon: Droplet,
    label: "Alta proporción de nulos",
    badgeClass: "bg-amber-500 text-white",
    rowClass: "border-amber-500 bg-amber-50 dark:bg-amber-950/40",
    what: "Un porcentaje alto de los valores está vacío. Con tan pocos datos reales, el tipo autodetectado puede ser erróneo y la columna sintética de baja calidad.",
    autoExcluded: false,
    action: "No se excluye automáticamente. Revisa el tipo detectado y decide si continuar, excluir la columna o tratar los huecos tú mismo.",
  },
  {
    Icon: CalendarClock,
    label: "Posible fecha compuesta",
    badgeClass: "bg-sky-600 text-white",
    rowClass: "border-sky-500 bg-sky-50 dark:bg-sky-950/40",
    what: "Una fecha parece estar repetida en columnas separadas: una columna con la fecha completa y otras con el día, el mes o el año por separado. Generarlas por separado puede producir combinaciones incoherentes.",
    autoExcluded: false,
    action: "No se excluye automáticamente. Si quieres que las partes se deriven de la fecha completa, añade una regla «date_composition» en la página «Reglas de negocio»; déjalo así si la divergencia es intencionada.",
  },
];

function WarningsLegend() {
  return (
    <div className="space-y-2.5">
      {WARNING_DOCS.map(({ Icon, label, badgeClass, rowClass, what, autoExcluded, action }) => (
        <div
          key={label}
          className={"rounded-md border border-l-4 p-2.5 " + rowClass}
        >
          <div className="flex items-center gap-2">
            <span className={"flex h-5 w-5 shrink-0 items-center justify-center rounded " + badgeClass}>
              <Icon className="h-3.5 w-3.5" />
            </span>
            <span className="text-[13px] font-bold text-[#16386f] dark:text-[#dce8ff]">
              {label}
            </span>
            <span
              className={
                "ml-auto rounded-full px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wide " +
                (autoExcluded
                  ? "bg-red-600 text-white"
                  : "bg-[#16386f] text-white dark:bg-[#2a4a85]")
              }
            >
              {autoExcluded ? "Excluida por defecto" : "Se conserva"}
            </span>
          </div>
          <p className="mt-1.5">{what}</p>
          <p className="mt-1 text-[#16386f] dark:text-[#aebdd9]">
            <span className="font-semibold">Qué hacer: </span>
            {action}
          </p>
        </div>
      ))}
    </div>
  );
}

// Each column is assigned an encoding type.
// Health-domain example for each MostlyAI encoding type.
const ENCODING_TYPE_EXAMPLES: Record<string, string> = {
  AUTO: "Una columna recién añadida cuyo tipo aún no conoces: deja que el sistema lo decida.",
  TABULAR_CATEGORICAL: "servicio = {urgencias, cardiología, pediatría}: un conjunto fijo de unidades hospitalarias.",
  TABULAR_NUMERIC_AUTO: "peso_kg de los pacientes: valores continuos sin un formato fijo.",
  TABULAR_NUMERIC_DISCRETE: "numero_ingresos_previos: un entero pequeño con pocos valores distintos.",
  TABULAR_NUMERIC_BINNED: "dosis_mg con muchos valores dispersos que conviene suavizar en intervalos.",
  TABULAR_NUMERIC_DIGIT: "numero_historia_clinica: un identificador numérico de longitud fija.",
  TABULAR_CHARACTER: "codigo_cita con un formato fijo de letras y números, p. ej. «A-2048».",
  TABULAR_DATETIME: "fecha_ingreso: una marca temporal absoluta del episodio.",
  TABULAR_DATETIME_RELATIVE: "en la secuencia de episodios de un paciente, la fecha de cada episodio como días transcurridos desde el episodio anterior.",
  TABULAR_LAT_LONG: "ubicacion del centro de salud como par latitud/longitud.",
  LANGUAGE_TEXT: "observaciones_clinicas: texto libre redactado por el personal sanitario.",
  LANGUAGE_CATEGORICAL: "motivo_consulta con categorías de texto largas y muy variadas.",
  LANGUAGE_NUMERIC: "una columna numérica (p. ej. dosis_mg) generada por el motor de lenguaje, normalmente porque su tabla también tiene columnas de texto libre.",
  LANGUAGE_DATETIME: "una columna de fecha (p. ej. fecha_informe) generada por el motor de lenguaje, normalmente porque su tabla también tiene columnas de texto libre.",
};

// What an actual value of each type looks like — a literal sample shown next to
// the description so se ve de un vistazo el formato que produce cada tipo.
const ENCODING_TYPE_FORMATS: Record<string, string> = {
  AUTO: "(según lo que detecte: 42 · «urgencias» · «2024-03-11»…)",
  TABULAR_CATEGORICAL: "urgencias · cardiología · pediatría",
  TABULAR_NUMERIC_AUTO: "72.4 · 8.1 · 103.7",
  TABULAR_NUMERIC_DISCRETE: "0 · 1 · 2 · 3",
  TABULAR_NUMERIC_BINNED: "3.2 · 7.8 · 12.1 (muestreado dentro de su intervalo)",
  TABULAR_NUMERIC_DIGIT: "00472 · 01938 · 12005",
  TABULAR_CHARACTER: "A-2048 · B-0071 · C-3312",
  TABULAR_DATETIME: "2024-03-11 09:42:00",
  TABULAR_DATETIME_RELATIVE: "2024-03-14 09:30:00 (fecha normal; modelada como intervalo dentro de la secuencia)",
  TABULAR_LAT_LONG: "40.4168, -3.7038",
  LANGUAGE_TEXT: "«Paciente refiere dolor torácico de 2 h de evolución…»",
  LANGUAGE_CATEGORICAL: "«Revisión post-operatoria de prótesis de cadera»",
  LANGUAGE_NUMERIC: "12.5 · 8.0 · 250",
  LANGUAGE_DATETIME: "2024-03-11 · 2024-04-02",
};

// Which engine models each encoding type — used to group the explorer's
// dropdown and to show an engine badge, so the 14 types read as "a few choices
// per engine" instead of one flat list.
function encodingEngine(type: string): "Automático" | "Tabular" | "Lenguaje" {
  if (type === "AUTO") return "Automático";
  return type.startsWith("LANGUAGE_") ? "Lenguaje" : "Tabular";
}

// A small pill marking which engine an encoding type belongs to.
function EngineBadge({ engine }: { engine: ReturnType<typeof encodingEngine> }) {
  return (
    <span className="inline-flex items-center rounded-full bg-[#16386f] px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white dark:bg-[#2a4a85]">
      {engine}
    </span>
  );
}

// Interactive encoding-type explorer for the manual: a dropdown of every
// MostlyAI encoding type, grouped by engine, with its Spanish description, the
// engine it belongs to, and a health example.
function EncodingTypeExplorer() {
  const [value, setValue] = useState<string>("TABULAR_CATEGORICAL");
  // Group the types by engine so the <select> shows labelled sections.
  const groups = (
    [
      ["Automático", "Automático"],
      ["Tabular", "Tabular"],
      ["Lenguaje", "Lenguaje"],
    ] as const
  ).map(([label, engine]) => ({
    label,
    options: ENCODING_TYPES.filter((t) => encodingEngine(t) === engine).map(
      (t) => ({ value: t, label: ENCODING_TYPE_LABELS[t] ?? t }),
    ),
  }));
  return (
    <div className="space-y-2.5">
      <div>
        <label className="mb-1 block text-[12px] font-bold uppercase tracking-wide text-[#26467a] dark:text-[#9db4dc]">
          Tipo de codificación
        </label>
        <SelectMenu value={value} onChange={setValue} groups={groups} />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-[#5f83be] dark:text-[#9db4dc]">
          Motor
        </span>
        <EngineBadge engine={encodingEngine(value)} />
      </div>
      <p>{ENCODING_TYPE_DESCRIPTIONS[value]}</p>
      <Example>
        <p>{ENCODING_TYPE_EXAMPLES[value]}</p>
        <div className="mt-2">
          <span className="mb-1 block text-[10.5px] font-bold uppercase tracking-wide text-[#8a7a1e] dark:text-[#bca85a]">
            Formato
          </span>
          <code className="block rounded-md border border-[#e6d98f] bg-white/70 px-2 py-1 font-mono text-[12px] text-[#4a4214] dark:border-[#5a4e16] dark:bg-black/20 dark:text-[#d8c98a]">
            {ENCODING_TYPE_FORMATS[value]}
          </code>
        </div>
      </Example>
    </div>
  );
}

function HistorialDiagram() {
  return (
    <svg {...svgBase} width="320" height="120" viewBox="0 0 320 120" role="img"
      aria-label="Historial de cargas de datos con la activa resaltada">
      {[0, 1, 2].map((i) => {
        const y = 6 + i * 38;
        const active = i === 0;
        return (
          <g key={i}>
            <rect x={4} y={y} width={312} height={30} rx={7}
              fill={active ? "#eef3ff" : "#fff"} stroke={active ? NAVY : SKY}
              strokeWidth={active ? 2.5 : 1.6} />
            <text x={18} y={y + 20} fontSize={13.5} fontWeight={active ? 700 : 400} fill={INK}>
              Carga de Datos {i + 1}{active ? "  ·  activa" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}


// ── Entries — an overview plus one per page section (WorkflowGroup) ─────────
export const INSPECCION_INSTRUCTIONS: readonly InstructionsEntry[] = [
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
    title: "Selección de ficheros",
    content: (
      <>
        <Lead>
          Elige los datos de partida y lanza la carga de datos, que detectará
          automáticamente tablas, columnas y relaciones. Sigue estos pasos:
        </Lead>
        <StepTable
          steps={[
            {
              name: "Subir ficheros",
              desc: "Carga archivos CSV, Parquet o JSON desde tu equipo. Cada fichero se interpretará como una tabla.",
            },
            {
              name: "Seleccionar tablas a inspeccionar",
              desc: "Marca las casillas de los ficheros que quieres incluir. Solo los seleccionados se analizan.",
            },
            {
              name: "Editar separador",
              desc: "Si seleccionas un CSV, indica cómo se separan sus columnas. Un separador incorrecto hace que toda la fila se lea como una sola columna.",
            },
            {
              name: "Revisar tablas seleccionadas",
              desc: "La vista previa muestra una muestra de cada tabla; confirma que las columnas y los datos son los esperados.",
            },
            {
              name: "Eliminar columnas no deseadas",
              desc: "Pulsa una columna en la vista previa para excluirla de la carga de datos — útil para datos personales o irrelevantes.",
            },
            {
              name: "Iniciar carga de datos",
              desc: "Lanza el análisis. Al terminar verás las tablas, relaciones y tipos detectados.",
            },
          ]}
        />
        <Subtitle>Visualización y ejecución de la carga</Subtitle>
        <p>
          Muestra una vista previa de cada tabla para que confirmes columnas y datos antes de lanzar. Cuando estés listo, pulsa <strong>Iniciar carga de datos</strong>: aparecerá un diálogo para darle un nombre funcional a esta carga. Dale un nombre descriptivo — si lo omites se asignará un ID automático basado en fecha y hora..
        </p>
        <OptionCallout
          name="Generar informes de profiling"
          state="Activada por defecto"
        >
          Genera un informe que describe las principales características de cada
          tabla (distribuciones, valores faltantes, correlaciones, etc.) usando
          la librería de Python <code>ydata-profiling</code>. Puedes
          desactivarla si prefieres una carga de datos más rápida.
        </OptionCallout>
        <Subtitle>Eliminación de columnas</Subtitle>
        <p>
          Usa el icono de papelera junto al nombre de una columna en la vista previa para excluirla de
          la carga de datos. Una columna excluida queda tachada y no se
          analizará ni formará parte del modelo ni de los datos sintéticos
          generados. La exclusión en esta fase es reversible, vuelve a pulsarla para incluirla de nuevo. Resulta útil
          para:
        </p>
        <OptionList
          items={[
            {
              name: "Datos personales",
              desc: "Identificadores directos (nombre, DNI, número de historia clínica) que no deben llegar al modelo.",
            },
            {
              name: "Columnas irrelevantes",
              desc: "Campos técnicos o de auditoría (timestamps internos, claves de importación) que no aportan al análisis.",
            },
            {
              name: "Columnas problemáticas",
              desc: "Columnas casi vacías o constantes que añaden ruido sin información útil.",
            },
          ]}
        />
        <Example>
          En la tabla <code>pacientes</code>, excluye <code>nombre</code> y{" "}
          <code>dni</code> antes de iniciar la carga: el modelo aprenderá los
          patrones del resto de columnas sin memorizar datos identificativos.
        </Example>
      </>
    ),
  },
  {
    id: "resultados",
    title: "Autodetección",
    content: (
      <>
        <Lead>
          Durante la carga de datos, la herramienta autodetecta relaciones entre tablas y el tipo de datos de cada columna. Esto es necesario para que el modelo que entrenaremos pueda generar datos sintéticos coherentes.
        </Lead>

        <p>
          <span className="font-semibold">Opcionalmente,</span> revisa y corrige lo que el sistema ha detectado.
        </p>

        <Subtitle>Relaciones detectadas</Subtitle>
        <p>
          Las tablas se enlazan mediante claves:
        </p>
        <ul className="space-y-1">
          <li className="flex gap-2">
            <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
            <span>
              <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
                PK (clave primaria)
              </span>{" "}
              — la columna que identifica de forma única cada fila de una
              tabla.
            </span>
          </li>
          <li className="flex gap-2">
            <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
            <span>
              <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
                FK (clave foránea)
              </span>{" "}
              — una columna que apunta a la PK de otra tabla, creando la
              relación entre ambas.
            </span>
          </li>
        </ul>
        <Diagram>
          <RelacionesDiagram />
        </Diagram>
        <p>
          Para configurar una relación, indica la tabla y columna FK de la
          tabla hija y la tabla y columna PK de la tabla padre a la que apunta.
          Revisa cada relación autodetectada: añade las que falten, elimina las
          incorrectas y corrige las columnas mal emparejadas.
        </p>
        <Example>
          <code>episodios.id_paciente</code> (FK) debe apuntar a{" "}
          <code>pacientes.id</code> (PK). Si la relación no se detecta, créala
          manualmente para que cada episodio sintético corresponda a un
          paciente existente.
        </Example>

        <ConceptCard title="Context relationship (MostlyAI)">
          <p>
            MostlyAI no trata las relaciones PK/FK como simples enlaces: las usa
            como <strong>relaciones de contexto</strong>. Cada tabla hija se
            genera <em>dentro del contexto</em> de la fila padre a la que
            pertenece, no de forma independiente. Una tabla puede tener tantas
            FKs como necesite, pero <strong>solo una puede ser contexto</strong>
            ; el resto se modelan como referencias.
          </p>
          <Diagram>
            <ContextDiagram />
          </Diagram>
          <p>
            Al generar un paciente sintético, todos sus episodios se generan
            <strong> juntos y condicionados</strong> a ese paciente. Así el
            modelo aprende patrones <em>dentro de cada grupo</em> —cuántos
            episodios suele tener un paciente, cómo evolucionan— y no solo las
            distribuciones globales.
          </p>
          <p>
            Por eso es clave revisar bien las relaciones detectadas: definen la
            jerarquía padre → hija que MostlyAI seguirá al generar.
          </p>
        </ConceptCard>

        <Subtitle>Tipos de codificación</Subtitle>
        <p>
          El <strong>tipo de codificación</strong> le dice al modelo cómo
          interpretar y reproducir cada columna. El sistema asigna un tipo
          automáticamente al inspeccionar, pero conviene revisarlo: una columna
          mal clasificada degrada los datos sintéticos. Aquí puedes fijar el
          tipo a mano cuando la detección no sea la correcta.
        </p>
        <ConceptCard title="Cómo está organizada la lista">
          <p>
            Los tipos no son 14 opciones sueltas: se agrupan según el{" "}
            <strong>motor</strong> que modela la columna. Piensa primero en el
            motor y la lista se reduce a unas pocas opciones.
          </p>
          <OptionList
            items={[
              {
                name: "Automático",
                desc: "Auto a nivel global: el sistema detecta el tipo de dato y elige automáticamente una codificación tabular (categórica, numérica o de fecha). Es el punto de partida de cada columna antes de tocar nada; los tipos de lenguaje no se eligen solos, hay que fijarlos a mano. No confundir con «Numérica automática», que solo elige el formato de un número ya fijado como tabular.",
              },
              {
                name: "Tabular",
                desc: "Datos estructurados normales: categorías, números, fechas, coordenadas e identificadores. Es lo que usarás casi siempre al ajustar a mano. Incluye «Numérica automática»: tú fijas que la columna es un número y el sistema solo elige cómo representarlo (discreta, agrupada o por dígitos), sin reconsiderar si en realidad es categoría, fecha o texto.",
              },
              {
                name: "Lenguaje",
                desc: "Texto libre o contenido complejo, modelado con un motor de lenguaje. Más potente pero mucho más lento; úsalo solo si la columna realmente lo necesita.",
              },
            ]}
          />
        </ConceptCard>
        <p className="mt-2">
          <strong>¿Cuándo cambiarlo?</strong> Solo si el tipo detectado es
          claramente incorrecto y degrada el resultado. Algunos casos
          frecuentes:
        </p>
        <OptionList
          items={[
            {
              name: "Identificador numérico clasificado como número",
              desc: "El nº de historia clínica «00472» es una etiqueta, no una cantidad: no se suma ni se promedia. Si se trata como número se pierden los ceros a la izquierda y se inventan valores intermedios. Cámbialo a «Numérica por dígitos» (conserva la longitud y el formato) o «Texto corto».",
            },
            {
              name: "Número con pocos valores clasificado como continuo",
              desc: "El nº de ingresos previos solo toma 0, 1, 2, 3… Como continuo, el modelo puede generar 1,7 ingresos. «Numérica discreta» mantiene los valores enteros reales que aparecen en los datos.",
            },
            {
              name: "Texto libre clasificado como categórica",
              desc: "Las observaciones clínicas son frases únicas, no un conjunto cerrado de opciones. Como categórica, el modelo solo repetiría textos vistos. «Texto libre» (motor de lenguaje) genera redacción nueva y coherente.",
            },
          ]}
        />
        <p className="mt-2">
          Explora cada tipo abajo: elige uno para ver qué hace, a qué motor
          pertenece y un ejemplo.
        </p>
        <EncodingTypeExplorer />

        <Subtitle>Eliminación de columnas desde la autodetección</Subtitle>
        <p>
          También puedes excluir columnas aquí, después de que la carga haya
          terminado. La diferencia con la exclusión previa (en{" "}
          <em>Selección de ficheros</em>) es que ahora ya ves el tipo detectado
          y los avisos de cada columna, lo que te permite tomar una decisión más
          informada.
        </p>
        <IconOptionList
          items={[
            {
              Icon: Trash2,
              name: "Papelera",
              desc: "excluye la columna de inmediato: desaparece del esquema y de los datos preprocesados al instante, sin necesidad de relanzar la carga.",
            },
          ]}
        />
        <p>
          <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
            ¿Cuándo se aplica?
          </span>{" "}
          Al instante — no es una exclusión diferida ni pasa por las Reglas de
          negocio. La columna queda fuera del esquema y de los datos
          preprocesados de forma permanente para esta carga. Ten en cuenta que
          esta acción{" "}
          <span className="font-semibold">
            no se revierte con «Restaurar autodetectado»
          </span>
          : si quieres recuperarla tendrás que relanzar la carga.
        </p>
        <Example>
          La columna <code>codigo_postal</code> tiene el aviso de{" "}
          «Tipo incompatible» porque mezcla números y texto. Una vez vista la
          autodetección, decides excluirla: desaparece del esquema al
          momento y no llegará al entrenamiento ni a los datos sintéticos.
        </Example>

        <Subtitle>Columnas marcadas (leyenda)</Subtitle>
        <p>
          Durante la autodetección, el sistema marca las columnas que podrían
          dar problemas con un icono de color. La leyenda bajo la tabla de tipos
          explica cada marca. Estos son todos los avisos posibles y qué hacer
          con cada uno:
        </p>
        <WarningsLegend />
        <p className="mt-2">
          Pasa el cursor por el icono de una columna marcada para ver el mensaje
          concreto (por ejemplo, el porcentaje exacto de nulos o las columnas de
          fecha implicadas).
        </p>
      </>
    ),
  },
  {
    id: "datos-preprocesados",
    title: "Datos preprocesados",
    content: (
      <>
        <Lead>
          Una vez completada la carga, aquí puedes ver el dataset{" "}
          <strong>preprocesado</strong>. No son tus ficheros originales, sino el
          resultado de aplicar una limpieza preliminar automática (eliminar columnas vacías, normalizar nombres de columna,
          convertir decimales sin parte fraccionaria a enteros, y eliminar filas duplicadas), la autodetección (tipos, relaciones), y las
          columnas excluidas. Te sirve para comprobar que la carga ha
          interpretado bien tus datos.
        </Lead>
        <p>
          Estos datos pueden usarse directamente para entrenar. Alternativamente, puedes
          aplicar una fase de <strong>reglas de negocio</strong> que transforme
          estos datos (columnas derivadas, fechas compuestas, relaciones semánticas etc.).
        </p>

        <Subtitle>Visualización de datos</Subtitle>
        <p>
          Muestra una vista previa de cada tabla preprocesada para que confirmes
          que las columnas, los tipos y los valores son los esperados.
        </p>
        <IconOptionList
          items={[
            {
              Icon: ChevronDown,
              name: "Ver muestra",
              desc: "despliega una muestra de filas de la tabla.",
            },
            {
              Icon: Maximize2,
              name: "Ver completa",
              desc: "abre un explorador paginado para recorrer todas las filas de la tabla.",
            },
            {
              Icon: Download,
              name: "Descargar ZIP",
              desc: "exporta el dataset preprocesado completo para revisarlo fuera de la herramienta.",
            },
          ]}
        />
      </>
    ),
  },
  {
    id: "profiling",
    title: "Profiling",
    content: (
      <>
        <Lead>
          El <strong>profiling</strong> es un informe automático que describe
          cada tabla con detalle: distribución de cada columna, valores
          faltantes, valores extremos, correlaciones, duplicados, etc. Te ayuda
          a entender tus datos antes de entrenar.
        </Lead>
        <p>
          Se genera con la librería <code>ydata-profiling</code> y solo está
          disponible si lanzaste la carga con la casilla{" "}
          <span className="font-semibold">«Generar informes de profiling»</span>{" "}
          activada. Hay un informe por tabla.
        </p>
        <IconOptionList
          items={[
            {
              Icon: BarChart3,
              name: "Pestañas por tabla",
              desc: "cambia entre los informes de cada tabla detectada en la carga.",
            },
            {
              Icon: ExternalLink,
              name: "Abrir en pestaña nueva",
              desc: "abre el informe completo de la tabla activa en otra pestaña del navegador.",
            },
            {
              Icon: Download,
              name: "Descargar todos (zip)",
              desc: "exporta los informes HTML de todas las tablas en un único archivo.",
            },
          ]}
        />
        <Example>
          Una columna con un{" "}
          <span className="font-semibold">90% de valores faltantes</span> o una
          correlación muy alta entre dos columnas saltan a la vista en el
          informe: son señales de que conviene revisar el tipo detectado o
          excluir la columna antes de entrenar.
        </Example>
      </>
    ),
  },
  {
    id: "historial",
    title: "Historial",
    content: (
      <>
        <Lead>
          Todas las cargas de datos de la sesión. Permite retomar trabajo previo
          sin repetir la configuración.
        </Lead>
        <Diagram>
          <HistorialDiagram />
        </Diagram>
        <IconOptionList
          items={[
            {
              Icon: MousePointerClick,
              name: "Seleccionar",
              desc: "haz clic en una fila para recargar los resultados de esa carga de datos.",
            },
            {
              Icon: Pencil,
              name: "Renombrar",
              desc: "asigna un nombre funcional para identificar la carga más fácilmente.",
            },
            {
              Icon: BarChart3,
              name: "Ver profiling",
              desc: "abre el informe de profiling de la carga (si se generó).",
            },
            {
              Icon: Download,
              name: "Descargar",
              desc: "exporta el dataset preprocesado o la carpeta completa de la carga.",
            },
            {
              Icon: XCircle,
              name: "Cancelar",
              desc: "detiene una carga que aún está en curso.",
            },
            {
              Icon: Trash2,
              name: "Eliminar",
              desc: "borra esa carga y sus artefactos. No se puede deshacer.",
            },
            {
              Icon: Trash2,
              name: "Limpiar sesiones incompletas",
              desc: "elimina carpetas vacías, ejecuciones huérfanas y duplicados.",
            },
            {
              Icon: Trash2,
              name: "Limpiar todas las sesiones",
              desc: "borra TODAS las cargas de datos — úsalo con cuidado.",
            },
          ]}
        />
      </>
    ),
  },
];
