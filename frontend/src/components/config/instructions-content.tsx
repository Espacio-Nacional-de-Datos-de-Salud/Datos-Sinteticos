// Help content for the Reglas de negocio (Configuración) instructions manual.
//
// Mirrors @/components/inspection/instructions-content: one entry per page
// section, combining concise prose, the meaning of the available options, a
// small inline schematic and a concrete usage example. Rendered by WizardShell's
// <InstructionsPanel /> in the page's right-hand column — the same collapsible,
// section-aligned manual used on Carga de Datos — taking over the side rail's
// slot while the manual is open.

"use client";

import { useLayoutEffect, useState } from "react";
import {
  BarChart3,
  ChevronDown,
  Download,
  FileText,
  FolderOpen,
  Lock,
  LockOpen,
  Maximize2,
  MousePointerClick,
  Pencil,
  RotateCcw,
  Save,
  Trash2,
  type LucideIcon,
} from "lucide-react";

import { NativeSelect } from "@/components/ui/native-select";
import { AdvancedBadge } from "@/components/ui/advanced-section";
import type { InstructionsEntry } from "@/components/layout/instructions-panel";

// ── Brand palette ───────────────────────────────────────────────────────────
const NAVY = "#00215C";
const BLUE = "#114da6";
const SKY = "#c9d4ea";
const AMBER = "#C79200";
const INK = "#2b3a52";
// Violet of the "advanced / optional" sparkle (matches the sidebar nav marker
// and AdvancedBadge) — used to flag advanced steps in the overview stepper.
const VIOLET = "#a78bfa";

// ── Presentational helpers (kept local, as in instructions-content) ─────────
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

// A collapsible subsection whose header reuses the Subtitle look. Collapsed by
// default so dense sections (e.g. Panel de reglas) don't take up so much
// vertical space until the user expands the part they care about.
//
// The instructions panel positions each section's help block absolutely and
// reserves page space from the block's measured height (via a ResizeObserver +
// a window-resize listener). Toggling this changes the block height after the
// initial layout, so we nudge a `resize` across the next couple frames to make
// the panel re-measure and push the following sections down — exactly like the
// top-level sections behave.
function CollapsibleSubsection({
  title,
  defaultOpen = false,
  children,
}: {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  useLayoutEffect(() => {
    if (typeof window === "undefined") return;
    let raf2 = 0;
    const raf1 = window.requestAnimationFrame(() => {
      window.dispatchEvent(new Event("resize"));
      raf2 = window.requestAnimationFrame(() =>
        window.dispatchEvent(new Event("resize")),
      );
    });
    return () => {
      window.cancelAnimationFrame(raf1);
      if (raf2) window.cancelAnimationFrame(raf2);
    };
  }, [open]);
  return (
    <div className="mt-3.5 first:mt-0">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 text-left"
      >
        <svg
          viewBox="0 0 12 12"
          className={
            "h-3 w-3 shrink-0 text-[#16386f] transition-transform dark:text-[#dce8ff] " +
            (open ? "rotate-90" : "")
          }
          aria-hidden
        >
          <path
            d="M4 2l4 4-4 4"
            stroke="currentColor"
            strokeWidth={2}
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="text-[13.5px] font-bold uppercase tracking-wide text-[#16386f] underline decoration-[#FFDB00] decoration-2 underline-offset-4 dark:text-[#dce8ff]">
          {title}
        </span>
      </button>
      {open && <div className="mt-2 space-y-2">{children}</div>}
    </div>
  );
}

function OptionList({
  items,
}: {
  items: Array<{ name: string; desc: string }>;
}) {
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
// for that
// action, so the help mirrors the buttons the user actually sees (matches the
// IconOptionList used in the Carga de Datos manual).
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
          <rect
            x={6.6}
            y={14.6}
            width={2.8}
            height={1.3}
            rx={0.65}
            fill="#00215C"
          />
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

function OptionCallout({
  name,
  state,
  children,
}: {
  name: string;
  /** Short tag shown in the top-right corner, e.g. "Desactivada por defecto". */
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
      <p className="mt-1">
        <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
          {name}
        </span>{" "}
        — {children}
      </p>
    </div>
  );
}

// A caution note: warm amber accent + ⚠ marker, visually distinct from the
// yellow "Opción activable" callouts so it reads as a warning, not an option.
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

// A collapsible "application mode" card. Keeps the OptionCallout look (yellow
// left accent + state badge in the corner) but its body expands/collapses, so
// the two modes can hold a diagram + detailed prose without flooding the panel.
function CollapsibleMode({
  name,
  state,
  defaultOpen = false,
  children,
}: {
  name: string;
  state: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="relative overflow-hidden rounded-md border-l-4 border-[#FFDB00] bg-[#eef3ff] dark:bg-[#16284d]">
      <span className="absolute right-0 top-0 rounded-bl-md bg-[#FFDB00] px-2 py-0.5 text-[9.5px] font-bold uppercase tracking-wide text-[#00215C]">
        {state}
      </span>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full py-2 pl-2.5 pr-24 text-left"
      >
        {/* "Opción activable" header — same marker used by OptionCallout. */}
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
        <div className="mt-1 flex items-center gap-2">
          <svg
            viewBox="0 0 12 12"
            className={
              "h-3.5 w-3.5 shrink-0 text-[#16386f] transition-transform dark:text-[#9db4dc] " +
              (open ? "rotate-90" : "")
            }
            aria-hidden
          >
            <path
              d="M4 2l4 4-4 4"
              stroke="currentColor"
              strokeWidth={2}
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span className="text-[13px] font-bold text-[#16386f] dark:text-[#dce8ff]">
            {name}
          </span>
        </div>
      </button>
      {open && (
        <div className="space-y-2 px-3 pb-3 pl-9 pt-0.5">{children}</div>
      )}
    </div>
  );
}

function SelectMenu({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <NativeSelect
      value={value}
      onValueChange={onChange}
      className="h-9 rounded-lg border-2 border-[#16386f] bg-[#eef3ff] pl-3 text-[13px] font-semibold text-[#16386f] shadow-sm transition-colors hover:bg-[#e2eaff] focus:ring-2 focus:ring-[#5f83be] dark:border-[#5f83be] dark:bg-[#16284d] dark:text-[#dce8ff]"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </NativeSelect>
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

// Horizontal numbered stepper — reused for the Resumen overview. Steps flagged
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
            <text
              x={cx}
              y={cy + 4.5}
              fontSize={12.5}
              fontWeight={700}
              fill="#fff"
              textAnchor="middle"
            >
              {i + 1}
            </text>
            {/* advanced marker — lucide sparkle just above the node, nudged out
                so it clears the number */}
            {step.optional && <SparkleMark cx={cx + 17} cy={cy - 15} size={12} />}
            {step.lines.map((ln, j) => (
              <text
                key={j}
                x={cx}
                y={cy + 28 + j * 10}
                fontSize={9}
                fontWeight={600}
                fill="var(--ink)"
                textAnchor="middle"
              >
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
        { lines: ["Cargar / guardar", "reglas"], optional: true },
        { lines: ["Crear / eliminar", "columnas"], optional: true },
        { lines: ["Editar reglas", "lógicas"], optional: true },
        { lines: ["Ejecutar", "preprocesamiento"], optional: true },
        { lines: ["Revisión", "de datos"], optional: true },
        { lines: ["Revisión del", "historial"], optional: true },
      ]}
    />
  );
}

// Schematic of a derived column: an existing column feeds a rule box that
// emits a brand-new column appended to the same table.
function DerivedColumnDiagram() {
  return (
    <svg
      {...svgBase}
      width="330"
      height="96"
      viewBox="0 0 330 96"
      role="img"
      aria-label="Una columna de origen atraviesa una regla de derivación y produce una columna nueva"
    >
      {/* source column */}
      <rect
        x={2}
        y={30}
        width={104}
        height={34}
        rx={7}
        fill="#fff"
        stroke={NAVY}
        strokeWidth={1.8}
      />
      <text
        x={54}
        y={46}
        fontSize={11.5}
        fontWeight={600}
        fill={INK}
        textAnchor="middle"
      >
        fecha_nac.
      </text>
      <text x={54} y={59} fontSize={9} fill="#5f83be" textAnchor="middle">
        columna origen
      </text>
      {/* rule box */}
      <rect x={130} y={26} width={70} height={42} rx={9} fill={NAVY} />
      <text
        x={165}
        y={44}
        fontSize={10.5}
        fontWeight={700}
        fill="#fff"
        textAnchor="middle"
      >
        regla
      </text>
      <text x={165} y={57} fontSize={8.5} fill={SKY} textAnchor="middle">
        derivada
      </text>
      {/* derived column */}
      <rect
        x={224}
        y={30}
        width={104}
        height={34}
        rx={7}
        fill="#fffaf0"
        stroke={AMBER}
        strokeWidth={2}
      />
      <text
        x={276}
        y={46}
        fontSize={11.5}
        fontWeight={700}
        fill={INK}
        textAnchor="middle"
      >
        edad
      </text>
      <text x={276} y={59} fontSize={9} fill={AMBER} textAnchor="middle">
        columna nueva
      </text>
      {/* arrows */}
      <path
        d="M106 47 L128 47 m-7 -5 l7 5 l-7 5"
        stroke={BLUE}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M200 47 L222 47 m-7 -5 l7 5 l-7 5"
        stroke={BLUE}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

// Schematic of a logical/business rule constraining two columns of a row.
function LogicalRuleDiagram() {
  return (
    <svg
      {...svgBase}
      width="330"
      height="110"
      viewBox="0 0 330 110"
      role="img"
      aria-label="Una regla lógica impone que la fecha de alta sea posterior a la de ingreso"
    >
      {/* row */}
      <rect
        x={2}
        y={20}
        width={140}
        height={70}
        rx={8}
        fill="#fff"
        stroke={NAVY}
        strokeWidth={1.8}
      />
      <text
        x={72}
        y={37}
        fontSize={10.5}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        episodio (fila)
      </text>
      <rect
        x={10}
        y={45}
        width={124}
        height={18}
        rx={4}
        fill={BLUE}
        fillOpacity={0.12}
      />
      <text x={16} y={58} fontSize={10.5} fill={INK}>
        fecha_ingreso
      </text>
      <rect
        x={10}
        y={66}
        width={124}
        height={18}
        rx={4}
        fill={AMBER}
        fillOpacity={0.16}
      />
      <text x={16} y={79} fontSize={10.5} fill={INK}>
        fecha_alta
      </text>
      {/* constraint */}
      <path
        d="M142 74 C 176 74, 176 54, 210 54"
        stroke={BLUE}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
      />
      <rect x={210} y={38} width={116} height={34} rx={9} fill={NAVY} />
      <text
        x={268}
        y={53}
        fontSize={10.5}
        fontWeight={700}
        fill="#fff"
        textAnchor="middle"
      >
        regla lógica
      </text>
      <text x={268} y={66} fontSize={9} fill={SKY} textAnchor="middle">
        alta ≥ ingreso
      </text>
    </svg>
  );
}

// ── Per-rule-type diagrams ──────────────────────────────────────────────────
// One small schematic per logical-rule type, shown at the top of that type's
// explanation in the RuleTypeExplorer so the user sees the situation the rule
// addresses before reading the prose.

// Two stacked value cells linked by an operator badge — used for the
// fecha/número ordering rules.
function OrderRuleDiagram({
  caption,
  rowA,
  rowB,
  op,
  label,
}: {
  caption: string;
  rowA: string;
  rowB: string;
  op: string;
  label: string;
}) {
  return (
    <svg
      {...svgBase}
      width="320"
      height="104"
      viewBox="0 0 320 104"
      role="img"
      aria-label={`${rowB} ${op} ${rowA}`}
    >
      <rect
        x={2}
        y={14}
        width={150}
        height={76}
        rx={8}
        fill="#fff"
        stroke={NAVY}
        strokeWidth={1.8}
      />
      <text
        x={77}
        y={30}
        fontSize={10.5}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        {caption}
      </text>
      <rect
        x={10}
        y={38}
        width={134}
        height={20}
        rx={4}
        fill={BLUE}
        fillOpacity={0.12}
      />
      <text x={17} y={52} fontSize={10.5} fill={INK}>
        {rowA}
      </text>
      <rect
        x={10}
        y={62}
        width={134}
        height={20}
        rx={4}
        fill={AMBER}
        fillOpacity={0.16}
      />
      <text x={17} y={76} fontSize={10.5} fill={INK}>
        {rowB}
      </text>
      <path
        d="M152 60 C 184 60, 184 52, 214 52"
        stroke={BLUE}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
      />
      <rect x={214} y={36} width={104} height={34} rx={9} fill={NAVY} />
      <text
        x={266}
        y={50}
        fontSize={11}
        fontWeight={700}
        fill="#fff"
        textAnchor="middle"
      >
        regla
      </text>
      <text x={266} y={63} fontSize={9.5} fill={SKY} textAnchor="middle">
        {label}
      </text>
    </svg>
  );
}

function DateRelationDiagram() {
  return (
    <OrderRuleDiagram
      caption="episodio (fila)"
      rowA="fecha_ingreso"
      rowB="fecha_alta"
      op="≥"
      label="alta ≥ ingreso"
    />
  );
}

function NumberRelationDiagram() {
  return (
    <OrderRuleDiagram
      caption="constantes (fila)"
      rowA="t_sistólica"
      rowB="t_diastólica"
      op="≤"
      label="diastólica ≤ sistólica"
    />
  );
}

// Two categorical columns with allowed/forbidden value pairings.
function SemanticConsistencyDiagram() {
  return (
    <svg
      {...svgBase}
      width="320"
      height="118"
      viewBox="0 0 320 118"
      role="img"
      aria-label="Solo se permiten combinaciones coherentes entre dos columnas categóricas"
    >
      <text
        x={70}
        y={14}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        diagnóstico
      </text>
      <text
        x={210}
        y={14}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        tratamiento
      </text>
      {[
        { a: "diabetes", b: "insulina", ok: true, y: 24 },
        { a: "fractura", b: "escayola", ok: true, y: 56 },
        { a: "gripe", b: "quimioterapia", ok: false, y: 88 },
      ].map((r) => (
        <g key={r.a}>
          <rect
            x={6}
            y={r.y}
            width={128}
            height={24}
            rx={5}
            fill={BLUE}
            fillOpacity={0.1}
            stroke={NAVY}
            strokeWidth={1}
          />
          <text
            x={70}
            y={r.y + 16}
            fontSize={10.5}
            fill={INK}
            textAnchor="middle"
          >
            {r.a}
          </text>
          <rect
            x={186}
            y={r.y}
            width={128}
            height={24}
            rx={5}
            fill={r.ok ? BLUE : AMBER}
            fillOpacity={r.ok ? 0.1 : 0.16}
            stroke={r.ok ? NAVY : AMBER}
            strokeWidth={1}
          />
          <text
            x={250}
            y={r.y + 16}
            fontSize={10.5}
            fill={INK}
            textAnchor="middle"
          >
            {r.b}
          </text>
          <path
            d={`M134 ${r.y + 12} L186 ${r.y + 12}`}
            stroke={r.ok ? NAVY : AMBER}
            strokeWidth={1.8}
            strokeDasharray={r.ok ? "0" : "4 3"}
            fill="none"
          />
          <text
            x={160}
            y={r.y + 8}
            fontSize={11}
            fontWeight={700}
            fill={r.ok ? "#1a7a3a" : AMBER}
            textAnchor="middle"
          >
            {r.ok ? "✓" : "✗"}
          </text>
        </g>
      ))}
    </svg>
  );
}

// A child row's FK must point to an existing parent key.
function ForeignKeyDiagram() {
  return (
    <svg
      {...svgBase}
      width="320"
      height="138"
      viewBox="0 0 320 138"
      role="img"
      aria-label="La clave foránea de la tabla hija debe apuntar a una fila existente de la tabla padre"
    >
      {/* parent table (left) */}
      <text
        x={62}
        y={14}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        pacientes (padre)
      </text>
      <rect
        x={4}
        y={20}
        width={116}
        height={64}
        rx={8}
        fill="#fff"
        stroke={NAVY}
        strokeWidth={1.8}
      />
      <rect
        x={12}
        y={30}
        width={100}
        height={22}
        rx={4}
        fill={AMBER}
        fillOpacity={0.16}
      />
      <text x={18} y={45} fontSize={10} fill={INK}>
        id = 42 (PK)
      </text>
      <rect
        x={12}
        y={56}
        width={100}
        height={20}
        rx={4}
        fill="#fff"
        stroke={SKY}
        strokeWidth={1}
      />
      <text x={18} y={70} fontSize={10} fill={INK}>
        nombre…
      </text>

      {/* child table (right) */}
      <text
        x={258}
        y={14}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        episodios (hija)
      </text>
      <rect
        x={200}
        y={20}
        width={116}
        height={64}
        rx={8}
        fill="#fff"
        stroke={NAVY}
        strokeWidth={1.8}
      />
      <rect
        x={208}
        y={30}
        width={100}
        height={22}
        rx={4}
        fill={BLUE}
        fillOpacity={0.14}
      />
      <text x={214} y={45} fontSize={9.5} fill={INK}>
        id_paciente=42
      </text>
      <rect
        x={208}
        y={56}
        width={100}
        height={20}
        rx={4}
        fill="#fff"
        stroke={SKY}
        strokeWidth={1}
      />
      <text x={214} y={70} fontSize={10} fill={INK}>
        diagnóstico…
      </text>

      {/* connector dips below the tables so the label has clear space */}
      <path
        d="M120 41 C 160 41, 160 112, 208 41"
        stroke={NAVY}
        strokeWidth={2}
        fill="none"
        strokeLinecap="round"
        markerEnd="url(#fkArrow)"
      />
      <text
        x={160}
        y={128}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        la FK debe existir en el padre
      </text>
      <defs>
        <marker
          id="fkArrow"
          markerWidth={7}
          markerHeight={7}
          refX={5}
          refY={3}
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0 0 L6 3 L0 6 z" fill={NAVY} />
        </marker>
      </defs>
    </svg>
  );
}

// Year/month/day part columns composing into one date column.
function DateCompositionDiagram() {
  return (
    <svg
      {...svgBase}
      width="320"
      height="96"
      viewBox="0 0 320 96"
      role="img"
      aria-label="Tres columnas año, mes y día se combinan en una única columna de fecha"
    >
      {[
        { t: "año", v: "2024", y: 10 },
        { t: "mes", v: "03", y: 38 },
        { t: "día", v: "11", y: 66 },
      ].map((r) => (
        <g key={r.t}>
          <rect
            x={4}
            y={r.y}
            width={118}
            height={22}
            rx={5}
            fill={BLUE}
            fillOpacity={0.1}
            stroke={NAVY}
            strokeWidth={1}
          />
          <text x={14} y={r.y + 15} fontSize={10.5} fill={INK}>
            {r.t}: {r.v}
          </text>
          <path
            d={`M122 ${r.y + 11} C 150 ${r.y + 11}, 160 48, 188 48`}
            stroke={SKY}
            strokeWidth={2}
            fill="none"
            strokeLinecap="round"
          />
        </g>
      ))}
      <rect x={188} y={32} width={128} height={32} rx={9} fill={NAVY} />
      <text
        x={252}
        y={47}
        fontSize={10.5}
        fontWeight={700}
        fill="#fff"
        textAnchor="middle"
      >
        fecha
      </text>
      <text x={252} y={59} fontSize={9.5} fill={SKY} textAnchor="middle">
        2024-03-11
      </text>
    </svg>
  );
}

// ── Derived-column explorer ─────────────────────────────────────────────────
// Each type has a description, per-type option callouts, and a health example.
// The options shown change depending on the selected type, mirroring the actual
// form fields available in the rules editor for that type.

const DERIVED_COLUMN_LABELS = [
  "Derivar edad o lapso desde fecha",
  "Umbral numérico",
  "Intervalos numéricos",
] as const;
type DerivedLabel = (typeof DERIVED_COLUMN_LABELS)[number];

// Type-specific content: description + type-specific options only.
// The two shared options (Eliminar / Reconstruir) are rendered outside the
// inset box, after the example, since they apply to every derived-column type.
const DERIVED_DESCRIPTIONS: Record<DerivedLabel, React.ReactNode> = {
  "Derivar edad o lapso desde fecha": (
    <>
      <p>
        Genera una columna numérica que contiene el tiempo transcurrido entre
        una columna de fecha origen y una referencia temporal (una constante o
        una segunda columna de fecha). La unidad se selecciona entre{" "}
        <strong>años</strong>, <strong>meses</strong> o <strong>días</strong>;
        conviene utilizar días o meses para duraciones cortas como estancias
        hospitalarias, donde redondear a años produciría valores de cero.
      </p>
      <div className="mt-1.5 flex gap-2">
        <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
        <div>
          <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
            ¿Cuándo usar?
          </span>
          <p className="mt-1 pl-3">
            1) Si se desea simular una columna de duración que no existe en el
            conjunto de datos.
          </p>
          <p className="mt-1 pl-3">
            2){" "}
            <span className="inline-flex items-center gap-1 align-middle">
              <AdvancedBadge tooltip="Caso de uso avanzado: encadenar esta regla con un Umbral numérico o Intervalos numéricos para condicionar la generación." />
            </span>{" "}
            Si se desea <strong>condicionar la generación a un grupo</strong>{" "}
            (por ejemplo, generar solo pacientes mayores de edad) pero esa
            columna de agrupación{" "}
            <strong>no existe en los datos originales</strong>. En ese caso hay
            que construirla primero en dos pasos: <strong>(a)</strong> crear la
            columna numérica de duración (p. ej., <em>edad al ingreso</em> a
            partir de fecha de nacimiento y fecha de ingreso) y{" "}
            <strong>(b)</strong> derivar después la columna categórica mediante
            un <strong>Umbral numérico</strong> o{" "}
            <strong>Intervalos numéricos</strong> (p. ej.,{" "}
            <em>mayor / menor de edad</em> con corte en 18). Si se omite el paso
            (a), el modelo no habrá aprendido esa columna y no será posible
            condicionar la síntesis a "<em>mayor / menor de edad</em>".
          </p>
        </div>
      </div>
      <div className="mt-2 space-y-2">
        <OptionCallout
          name="Forzar lapso no negativo"
          state="Activada por defecto"
        >
          Trunca a cero las duraciones / edades negativas. Desactívese
          únicamente si la fecha de origen puede ser posterior a la de
          referencia y se desea conservar el signo (por ejemplo, fechas futuras
          respecto a una referencia pasada).
        </OptionCallout>
      </div>
    </>
  ),
  "Umbral numérico": (
    <>
      <p>
        Genera una columna booleana comparando una columna numérica origen con
        un umbral constante mediante un operador de comparación (≥, {">"}, ≤,{" "}
        {"<"}). El resultado es <code>True</code> o <code>False</code> (o los
        valores personalizados que se indiquen en los campos opcionales). Sirve
        para representar explícitamente una condición clínica o de negocio, de
        modo que el modelo la trate como una categoría en lugar de tener que
        inferirla a partir del valor continuo.
      </p>
      <div className="mt-1.5 flex gap-2">
        <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
        <div>
          <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
            ¿Cuándo usar?
          </span>
          <p className="mt-1 pl-3">
            1) Si se desea generar una variable dicotómica a partir de una
            columna numérica que no existe en el conjunto de datos.
          </p>
          <p className="mt-1 pl-3">
            2){" "}
            <span className="inline-flex items-center gap-1 align-middle">
              <AdvancedBadge tooltip="Caso de uso avanzado: encadenar esta regla tras un Derivar edad o lapso para condicionar la generación a un grupo binario." />
            </span>{" "}
            Si se desea{" "}
            <strong>condicionar la generación a un grupo binario</strong> (por
            ejemplo, generar solo pacientes mayores de edad) pero esa columna de
            agrupación <strong>no existe en los datos originales</strong>.{" "}
            Primero hay que crear la columna numérica con{" "}
            <strong>Derivar edad o lapso desde fecha</strong> y después aplicar
            este umbral sobre ella (p. ej., <em>mayor_de_edad</em> = edad ≥ 18).
          </p>
        </div>
      </div>
      <div className="mt-2 space-y-2">
        <OptionCallout
          name="Valor si verdadero / Valor si falso"
          state="Opcional"
        >
          Sustituye los literales <em>True</em> / <em>False</em> por etiquetas
          personalizadas (por ejemplo, <code>hipertenso</code> /{" "}
          <code>normotenso</code>). Si se omiten, la columna contiene valores
          booleanos estándar.
        </OptionCallout>
      </div>
    </>
  ),
  "Intervalos numéricos": (
    <>
      <p>
        Genera una columna categórica estratificando una columna numérica en
        intervalos definidos por el usuario. Cada fila queda asignada al tramo
        correspondiente en lugar de conservar el valor exacto. Esta
        transformación generaliza el modelo, reduce el riesgo de
        reidentificación y mejora la calidad sintética cuando el valor preciso
        no aporta señal estadística adicional.
      </p>
      <p className="mt-1.5">
        Los bordes de los intervalos se especifican como una lista de valores
        numéricos (por ejemplo, <code>0, 18, 65, inf</code>). Se pueden
        proporcionar etiquetas opcionales para los tramos resultantes; si se
        indican, deben ser exactamente <em>N − 1</em> etiquetas para <em>N</em>{" "}
        bordes.
      </p>
      <div className="mt-1.5 flex gap-2">
        <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
        <div>
          <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
            ¿Cuándo usar?
          </span>
          <p className="mt-1 pl-3">
            1) Si se desea generar una variable categórica a partir de una
            columna numérica que no existe en el conjunto de datos.
          </p>
          <p className="mt-1 pl-3">
            2){" "}
            <span className="inline-flex items-center gap-1 align-middle">
              <AdvancedBadge tooltip="Caso de uso avanzado: encadenar esta regla tras un Derivar edad o lapso para condicionar la generación a un grupo de múltiples tramos." />
            </span>{" "}
            Si se desea{" "}
            <strong>
              condicionar la generación a un grupo de múltiples tramos
            </strong>{" "}
            (por ejemplo, generar solo pacientes de entre 35 y 65 años) pero esa
            columna de agrupación{" "}
            <strong>no existe en los datos originales</strong>. Primero hay que
            crear la columna numérica con{" "}
            <strong>Derivar edad o lapso desde fecha</strong> y después aplicar
            los intervalos sobre ella (p. ej., <em>grupo_edad</em> con cortes en
            0 / 18 / 65 / inf y etiquetas <em>menor, adulto, mayor</em>).
          </p>
        </div>
      </div>
      <div className="mt-2 space-y-2">
        <OptionCallout
          name="Incluir el borde inferior en el primer intervalo"
          state="Activada por defecto"
        >
          Hace que el primer tramo sea cerrado por la izquierda, de forma que
          ningún valor quede fuera del rango al extremo inferior. Desactívese
          únicamente si se requiere un comportamiento estrictamente abierto en
          ese extremo.
        </OptionCallout>
        <OptionCallout
          name="Intervalos cerrados por la derecha"
          state="Desactivada por defecto"
        >
          Cuando está activa, cada tramo incluye su borde derecho (intervalo de
          la forma <em>(a, b]</em>). Por defecto los intervalos son abiertos por
          la derecha (<em>[a, b)</em>). La elección afecta a qué tramo recibe
          los valores exactamente iguales al borde.
        </OptionCallout>
      </div>
    </>
  ),
};

const DERIVED_EXAMPLES: Record<DerivedLabel, React.ReactNode> = {
  "Derivar edad o lapso desde fecha": (
    <>
      <code>edad</code> = años entre <code>fecha_nac.</code> y la fecha del
      episodio. O bien <code>estancia_dias</code> = días entre{" "}
      <code>fecha_ingreso</code> y <code>fecha_alta</code>.
    </>
  ),
  "Umbral numérico": (
    <>
      <code>hipertenso</code> = <code>tension_sistolica</code> ≥ 140, con
      valores personalizados <code>Sí</code> / <code>No</code> en lugar de
      booleanos.
    </>
  ),
  "Intervalos numéricos": (
    <>
      <code>grupo_edad</code> a partir de <code>edad</code> con bordes{" "}
      <code>0, 18, 65, inf</code> y etiquetas <code>menor, adulto, mayor</code>,
      de modo que el modelo no memorice edades exactas.
    </>
  ),
};

function DerivedColumnExplorer() {
  const [value, setValue] = useState<DerivedLabel>(DERIVED_COLUMN_LABELS[0]);
  return (
    <div className="space-y-2">
      <div>
        <label className="mb-1 block text-[12px] font-bold uppercase tracking-wide text-[#26467a] dark:text-[#9db4dc]">
          Tipo de columna derivada
        </label>
        <SelectMenu
          value={value}
          onChange={(v) => setValue(v as DerivedLabel)}
          options={DERIVED_COLUMN_LABELS.map((l) => ({ value: l, label: l }))}
        />
      </div>
      {/* Inset panel — groups the type-specific description, its options and
          the example as belonging to the selected dropdown entry. No background
          fill; the border alone is sufficient to demarcate the boundary. */}
      <div className="space-y-2 rounded-md border border-[#cdd9ec] px-3 py-2.5 dark:border-[#26375f]">
        {DERIVED_DESCRIPTIONS[value]}
        <Example>{DERIVED_EXAMPLES[value]}</Example>
      </div>
      {/* Shared options — present for every derived-column type. */}
      <OptionCallout
        name="Eliminar columna origen tras la derivación"
        state="Desactivada por defecto"
      >
        Descarta la columna origen del conjunto de entrenamiento una vez
        calculada la columna derivada, de modo que el modelo aprenda únicamente
        la representación derivada. Actívese cuando esta recoge toda la
        información relevante de la original y se desea evitar redundancia o
        colinealidad.
      </OptionCallout>
      <OptionCallout
        name="Reconstruir la columna origen en la fase POST"
        state="Desactivada por defecto"
      >
        Solo disponible si se ha activado la opción anterior. Recompone la
        columna origen a partir de la columna derivada sintetizada (la operación
        puede ser exacta o aproximada según el tipo de derivación). Actívese si
        se requiere que la columna origen figure también en los datos sintéticos
        finales sin que el modelo la haya aprendido directamente.
      </OptionCallout>
    </div>
  );
}

// ── Business-rule type explorer ─────────────────────────────────────────────
// Each type shows its description, type-specific fields/options, and an
// example. The "Modo de aplicación" toggle (Determinista / Muestreo por
// rechazo) is shared by all inequality and semantic types and rendered outside
// the inset box. date_composition and foreign_keys_consistency_rule do not
// support it.

const LOGICAL_RULE_LABELS = [
  "Relación entre fechas",
  "Relación entre números",
  "Consistencia semántica",
  "Consistencia de claves foráneas",
  "Composición de fecha desde columnas año/mes/día",
] as const;
type LogicalLabel = (typeof LOGICAL_RULE_LABELS)[number];

// Labels hidden from the manual's dropdown without deleting their content.
// "Consistencia de claves foráneas" is an auto-generated, non-configurable
// rule, so it does not warrant a user-facing manual entry; its definitions are
// kept below in case it needs to be surfaced again.
const LOGICAL_RULE_HIDDEN = new Set<LogicalLabel>([
  "Consistencia de claves foráneas",
]);
const LOGICAL_RULE_VISIBLE_LABELS = LOGICAL_RULE_LABELS.filter(
  (l) => !LOGICAL_RULE_HIDDEN.has(l),
);

// One illustrative schematic per rule type, shown at the top of its
// explanation in the RuleTypeExplorer.
const LOGICAL_DIAGRAMS: Record<LogicalLabel, React.ReactNode> = {
  "Relación entre fechas": <DateRelationDiagram />,
  "Relación entre números": <NumberRelationDiagram />,
  "Consistencia semántica": <SemanticConsistencyDiagram />,
  "Consistencia de claves foráneas": <ForeignKeyDiagram />,
  "Composición de fecha desde columnas año/mes/día": <DateCompositionDiagram />,
};

const LOGICAL_DESCRIPTIONS: Record<LogicalLabel, React.ReactNode> = {
  "Relación entre fechas": (
    <>
      <p>
        Impone que una columna de fecha objetivo sea mayor o igual (≥) o menor o
        igual (≤) que una columna de fecha origen o que una constante de fecha.
        Se especifican la tabla y columna objetivo, el operador (≥ o ≤) y la
        tabla y columna origen, o bien una fecha constante como alternativa a la
        columna origen. Ambas columnas deben pertenecer al mismo registro o
        estar relacionadas mediante claves foráneas.
      </p>
      <div className="mt-1.5 flex gap-2">
        <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
        <div>
          <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
            ¿Cuándo usar?
          </span>
          <p className="mt-1 pl-3">
            1) Cuando exista una relación temporal obligatoria entre dos
            columnas de fecha del mismo registro (por ejemplo, la fecha de alta
            debe ser posterior o igual a la de ingreso).
          </p>
          <p className="mt-1 pl-3">
            2) Cuando se desee acotar una fecha respecto a un límite absoluto
            conocido (por ejemplo, la fecha de diagnóstico no puede ser anterior
            al año de apertura del centro).
          </p>
        </div>
      </div>
      <div className="mt-2 space-y-2">
        <OptionCallout name="Columna auxiliar" state="Opcional">
          Nombre de la columna intermedia que el sistema crea internamente para
          codificar la restricción durante el entrenamiento. Si se deja vacío,
          se genera automáticamente. Solo es necesario especificarla si se desea
          controlar el nombre de esa columna interna.
        </OptionCallout>
        <OptionCallout
          name="Forzar duraciones no negativas"
          state="Activada por defecto"
        >
          Trunca a cero las diferencias negativas que pudieran surgir durante la
          reconstrucción en modo determinista. Desactívese únicamente si se
          desea permitir duraciones negativas (por ejemplo, si la columna origen
          puede ser posterior a la columna objetivo por diseño). Esta opción no
          aplica en modo de muestreo por rechaz (explicado más abajo), ya que en
          ese modo las filas que incumplen la regla se descartan y se resimulan
          en su totalidad.
        </OptionCallout>
      </div>
    </>
  ),

  "Relación entre números": (
    <>
      <p>
        Impone que una columna numérica objetivo sea mayor o igual (≥) o menor o
        igual (≤) que una columna numérica origen o que una constante numérica.
        Se especifican la tabla y columna objetivo, el operador y la tabla y
        columna origen, o bien un valor numérico constante como alternativa.
      </p>
      <div className="mt-1.5 flex gap-2">
        <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
        <div>
          <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
            ¿Cuándo usar?
          </span>
          <p className="mt-1 pl-3">
            1) Cuando exista una relación de orden obligatoria entre dos
            columnas numéricas del mismo registro (por ejemplo, la tensión
            diastólica debe ser siempre menor o igual que la sistólica).
          </p>
          <p className="mt-1 pl-3">
            2) Cuando se desee acotar una columna numérica respecto a un límite
            absoluto conocido (por ejemplo, el número de días de estancia no
            puede ser negativo).
          </p>
        </div>
      </div>
      <div className="mt-2 space-y-2">
        <OptionCallout name="Columna auxiliar" state="Opcional">
          Nombre de la columna intermedia creada internamente para codificar la
          restricción durante el entrenamiento. Si se deja vacío, se genera
          automáticamente.
        </OptionCallout>
      </div>
    </>
  ),

  "Consistencia semántica": (
    <>
      <p>
        Restringe las combinaciones válidas entre dos columnas categóricas de la
        misma tabla. El sistema aprende qué valores de la columna origen son
        compatibles con qué valores de la columna objetivo, de modo que los
        datos sintéticos no generen combinaciones semánticamente incoherentes
        (por ejemplo, un diagnóstico secundario que contradiga el principal).
      </p>
      <p className="mt-1.5">
        Se selecciona un subtipo que determina cuánta libertad tiene el modelo
        sobre las proporciones de cada categoría:
      </p>
      <div className="mt-2 space-y-2">
        <OptionCallout name="Fijo" state="Activada por defecto">
          Fuerza las proporciones observadas en los datos reales. El modelo
          reproduce la frecuencia con que aparece cada categoría tal como está
          en el original: si «urgencias» representa el 70 % de los casos, en los
          datos sintéticos se mantendrá esa proporción. Recomendada cuando se
          desea preservar la distribución real de las categorías.
        </OptionCallout>
        <OptionCallout name="Flexible" state="Opcional">
          Da libertad al modelo para aprender y simular las proporciones que
          considere. Solo se garantiza que las combinaciones sean semánticamente
          válidas; las frecuencias de cada categoría no quedan ancladas a las
          reales. Adecuada cuando las proporciones reales no son representativas
          o se desea mayor libertad al modelo.
        </OptionCallout>
      </div>
      <div className="mt-1.5 flex gap-2">
        <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
        <div>
          <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
            ¿Cuándo usar?
          </span>
          <p className="mt-1 pl-3">
            1) Cuando dos columnas categóricas del mismo registro tengan una
            relación semántica que el modelo debe respetar (por ejemplo, el
            servicio asignado debe ser coherente con el tipo de episodio).
          </p>
          <p className="mt-1 pl-3">
            2) Cuando se desee preservar la distribución real de combinaciones
            entre categorías (subtipo fijo), o únicamente la coherencia
            semántica sin restricción de proporciones (subtipo flexible).
          </p>
        </div>
      </div>
    </>
  ),

  "Consistencia de claves foráneas": (
    <>
      <p>
        Reconstruye una clave foránea redundante copiando el valor correcto
        desde la tabla padre. Es una regla que el sistema genera y aplica de
        forma automática: no requiere configuración por parte del usuario. No
        solo evita que el modelo tenga que aprender esa relación por sí mismo,
        sino que es necesaria para garantizar una modelización correcta: al
        intentar mantener una FK de un «abuelo» —que para la tabla padre ya es a
        su vez una FK— se producen incoherencias que esta regla resuelve.
      </p>
      <div className="mt-1.5 flex gap-2">
        <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
        <div>
          <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
            ¿Cuándo usar?
          </span>
          <p className="mt-1 pl-3">
            Cuando una columna de la tabla hija es una copia de una columna de
            la tabla padre (por ejemplo, <code>id_paciente</code> en la tabla de
            episodios debe coincidir siempre con un <code>id</code> real de la
            tabla de pacientes). Sin esta regla, el modelo podría generar
            identificadores que no corresponden a ningún paciente existente en
            los datos sintéticos.
          </p>
        </div>
      </div>
      <div className="mt-2 space-y-2">
        <OptionCallout name="Columna fuente" state="Opcional">
          Columna de la tabla padre desde la que se copia el valor. Si se deja
          vacía, se asume que la columna fuente tiene el mismo nombre que la
          columna objetivo de la tabla hija.
        </OptionCallout>
        <OptionCallout name="Tabla referenciada" state="Opcional">
          Tabla padre que contiene el valor que se desea copiar. Si se deja
          vacía, el sistema infiere la tabla padre a partir de las relaciones
          detectadas en la Carga de Datos.
        </OptionCallout>
      </div>
    </>
  ),

  "Composición de fecha desde columnas año/mes/día": (
    <>
      <p>
        Declara que un conjunto de columnas (año, mes, día, hora, minuto,
        segundo) son componentes derivados de una única columna de fecha
        canónica. Durante el entrenamiento, las columnas componentes se eliminan
        para evitar que el modelo aprenda redundancias; tras la generación, se
        reconstruyen de forma determinista a partir de la fecha canónica
        sintetizada. De este modo se garantiza que las columnas componentes sean
        siempre coherentes entre sí y con la fecha canónica.
      </p>
      <div className="mt-1.5 flex gap-2">
        <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
        <div>
          <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
            ¿Cuándo usar?
          </span>
          <p className="mt-1 pl-3">
            Cuando el conjunto de datos contiene tanto una columna de fecha
            completa como columnas separadas para sus componentes (por ejemplo,
            <code> fecha_nac.</code>, <code>año_nac.</code>,{" "}
            <code>mes_nac.</code> y <code>día_nac.</code> en la misma tabla).
            Sin esta regla, el modelo podría generar valores inconsistentes
            entre la fecha completa y sus componentes.
          </p>
        </div>
      </div>
      <div className="mt-2 space-y-2">
        <OptionCallout name="Fecha canónica" state="Obligatorio">
          La columna que contiene la fecha o fecha-hora completa. Es la fuente
          de verdad a partir de la cual se reconstruirán las columnas componente
          tras la generación.
        </OptionCallout>
        <OptionCallout
          name="Columnas parte (Año / Mes / Día / Hora / Minuto / Segundo)"
          state="Al menos una"
        >
          Para cada componente que exista como columna separada en los datos, se
          indica el nombre de esa columna. Solo es necesario mapear los
          componentes que estén presentes; los que no se indiquen no se
          modifican. Deben ser al menos uno.
        </OptionCallout>
      </div>

      <Subtitle>Sugerencias detectadas durante la inspección</Subtitle>
      <p>
        Esta es la única regla que el sistema puede proponer automáticamente.
        Durante la Carga de Datos busca columnas de año, mes y día que parezcan
        derivar de una misma fecha y, cuando las encuentra, muestra un recuadro{" "}
        <span className="font-medium text-foreground">
          «Sugerencias detectadas durante la inspección»
        </span>{" "}
        con la composición propuesta, para que la añadas con un clic en vez de
        configurarla a mano. Cada sugerencia muestra la fecha canónica, las
        columnas parte de las que provendría y un porcentaje de coincidencia; un
        contador en la cabecera del panel indica cuántas hay pendientes.
      </p>
      {/* Mini mock of the amber suggestion box the user sees on the page. */}
      <div className="rounded-md border border-amber-300/60 bg-amber-50/60 p-2.5 dark:border-amber-700/40 dark:bg-amber-950/20">
        <p className="text-[11.5px] font-semibold text-amber-900 dark:text-amber-200">
          Sugerencias detectadas durante la inspección
        </p>
        <div className="mt-1.5 flex items-center justify-between gap-2 rounded border border-amber-200/70 bg-background/60 p-1.5 dark:border-amber-800/40">
          <span className="min-w-0 text-[11px]">
            <span className="font-mono">episodios.fecha_ingreso</span>
            <span className="ml-1 text-muted-foreground">
              ← año, mes, día (95% coincidencia)
            </span>
          </span>
          <span className="shrink-0 rounded border border-[#cdd9ec] px-1.5 py-0.5 text-[10px] font-semibold text-[#16386f] dark:border-[#26375f] dark:text-[#dce8ff]">
            + Añadir regla
          </span>
        </div>
      </div>
      <OptionList
        items={[
          {
            name: "Añadir regla",
            desc: "registra la regla sugerida con un clic; la sugerencia desaparece y la regla pasa a la lista, donde puedes editarla como cualquier otra.",
          },
          {
            name: "Ignorar",
            desc: "si la divergencia entre las columnas es intencionada, no añadas la regla: la sugerencia es solo informativa.",
          },
        ]}
      />
    </>
  ),
};

const LOGICAL_EXAMPLES: Record<LogicalLabel, React.ReactNode> = {
  "Relación entre fechas": (
    <>
      <code>fecha_alta</code> ≥ <code>fecha_ingreso</code>: ningún episodio
      sintético puede recibir el alta con anterioridad a la fecha de ingreso.
    </>
  ),
  "Relación entre números": (
    <>
      <code>tension_diastolica</code> ≤ <code>tension_sistolica</code>: en
      ningún registro sintético la tensión diastólica puede superar a la
      sistólica.
    </>
  ),
  "Consistencia semántica": (
    <>
      El <code>servicio</code> asignado al episodio debe ser coherente con el{" "}
      <code>tipo_episodio</code>: urgencias no puede combinarse con un tipo de
      episodio programado. Con subtipo fijo, además se preserva que urgencias
      represente aproximadamente el 70 % de los episodios.
    </>
  ),
  "Consistencia de claves foráneas": (
    <>
      <code>id_paciente</code> en la tabla <code>episodios</code> se copia desde
      la columna <code>id</code> de la tabla <code>pacientes</code> marcada como
      contexto, garantizando que cada episodio sintético referencie un paciente
      existente.
    </>
  ),
  "Composición de fecha desde columnas año/mes/día": (
    <>
      <code>año_nac.</code>, <code>mes_nac.</code> y <code>día_nac.</code> se
      declaran como componentes de <code>fecha_nac.</code>: el modelo solo
      aprende la fecha completa y los componentes se reconstruyen
      automáticamente, evitando inconsistencias como mes 13 o día 31 en un mes
      de 30 días.
    </>
  ),
};

// Whether the rule type supports the "Modo de aplicación" toggle.
const LOGICAL_HAS_MODE = new Set<LogicalLabel>([
  "Relación entre fechas",
  "Relación entre números",
  "Consistencia semántica",
]);

function RuleTypeExplorer() {
  const [value, setValue] = useState<LogicalLabel>(
    LOGICAL_RULE_VISIBLE_LABELS[0],
  );
  return (
    <div className="space-y-2">
      <div>
        <label className="mb-1 block text-[12px] font-bold uppercase tracking-wide text-[#26467a] dark:text-[#9db4dc]">
          Tipo de regla de negocio
        </label>
        <SelectMenu
          value={value}
          onChange={(v) => setValue(v as LogicalLabel)}
          options={LOGICAL_RULE_VISIBLE_LABELS.map((l) => ({
            value: l,
            label: l,
          }))}
        />
      </div>
      {/* Inset panel — groups the type-specific content as belonging to the
          selected dropdown entry, mirroring the DerivedColumnExplorer style.
          A schematic at the top illustrates the situation each rule addresses. */}
      <div className="space-y-2 rounded-md border border-[#cdd9ec] px-3 py-2.5 dark:border-[#26375f]">
        <Diagram>{LOGICAL_DIAGRAMS[value]}</Diagram>
        {LOGICAL_DESCRIPTIONS[value]}
        <Example>{LOGICAL_EXAMPLES[value]}</Example>
      </div>
      {/* Modo de aplicación — present for inequality and semantic types only.
          Each mode is collapsible because both carry a diagram + detail. */}
      {LOGICAL_HAS_MODE.has(value) && (
        <div className="space-y-2">
          <p className="text-[12px] font-semibold uppercase tracking-wide text-[#26467a] dark:text-[#9db4dc]">
            Modo de aplicación
          </p>
          <CollapsibleMode
            name="Modo determinista"
            state="Activada por defecto"
            defaultOpen
          >
            <Diagram>
              <DeterministicModeDiagram />
            </Diagram>
            <p>
              Este modo impone la regla{" "}
              <strong>reformulando el problema</strong> para que al modelo le
              resulte más fácil aprenderlo: en lugar de que aprenda dos columnas
              y que «por su cuenta» respeten la relación, crea de forma
              automática una <strong>columna auxiliar</strong> que codifica la
              restricción y cuyo rango de valores es más acotado. Tú solo
              defines la regla; el software se encarga del resto internamente.
            </p>
            <p>
              Por ejemplo, para «fecha_alta ≥ fecha_ingreso» no modela las dos
              fechas por separado: modela <code>fecha_ingreso</code> y una
              <strong> duración de estancia (≥ 0)</strong> como columna
              auxiliar. Como esa duración teóricamente nunca podrá ser negativa
              (a excepción de que haya errores en el dataset o de que el modelo
              cometa errores), al reconstruir
              <code> fecha_alta = fecha_ingreso + duración</code> la regla se
              cumple siempre. Esta columna auxiliar la genera y elimina el
              sistema solo: tú no la creas ni la ves en el resultado.
            </p>
            <CautionNote title="Úsalo solo si la regla se cumple en los datos reales">
              <p>
                Este modo{" "}
                <strong>garantiza la regla, pero no corrige la magnitud</strong>
                . Como trunca la duración auxiliar a ≥ 0, los registros que en
                la realidad <em>incumplen</em> la relación no se descartan: se
                aplastan contra el límite. Si en tus datos no hay un
                cumplimiento del 100 % (o muy cercano), eso desplaza la
                distribución e introduce un <strong>sesgo estadístico</strong>.
              </p>
              <p>
                Por ejemplo, al exigir <code>edad ≥ 18</code> derivada de la
                fecha de nacimiento, un registro que en realidad es de un menor
                se fuerza justo a 18: la <strong>edad reconstruida</strong>{" "}
                figura como adulta, pero la <strong>resta de valores</strong>{" "}
                sigue siendo las de un niño. La regla «cuadra», pero los datos
                dejan de ser representativos.
              </p>
              <p>
                <span className="inline-flex items-center gap-1 align-middle">
                  <AdvancedBadge tooltip="Caso de uso avanzado: elegir entre corregir el incumplimiento (muestreo por rechazo) u orientar al modelo sin forzar la relación (determinista permitiendo duraciones negativas)." />
                </span>{" "}
                Cuando la regla no se cumple de forma (casi) universal, tienes
                dos salidas según tu objetivo (a parte de descartar la regla):
              </p>
              <p className="pl-3">
                <strong>(a) Corregirlo</strong> para que la regla sí se respete
                usando el <strong>modo de muestreo por rechazo</strong>, que
                descarta las filas incoherentes en vez de truncarlas durante la
                simulación.
              </p>
              <p className="pl-3">
                <strong>(b) No corregirlo</strong>, si el incumplimiento no te
                importa y solo quieres <strong>ayudar al modelo</strong> a
                entender que las dos fechas están relacionadas sin imponer la
                relación: usa el modo determinista pero{" "}
                <strong>desactiva «Forzar duraciones no negativas»</strong>. Así
                se permiten duraciones/lapsos negativos y no se introduce el
                sesgo.
              </p>
            </CautionNote>
            <OptionList
              items={[
                {
                  name: "Ventaja",
                  desc: "al aprender una columna auxiliar más restringida, el modelo capta la regla con más facilidad y fidelidad; es eficiente y siempre devuelve el número de filas pedido.",
                },
                {
                  name: "Límite",
                  desc: "la regla debe cumplirse (o casi) en los datos reales: si no, fuerza el cumplimiento truncando y sesga la distribución. Además está pensado para una relación entre dos columnas; si encadenas muchas reglas que dependen unas de otras, sus reformulaciones internas pueden entrar en conflicto. La herramienta lo detecta y se detiene antes de generar un resultado erróneo, pidiéndote que simplifiques las reglas.",
                },
              ]}
            />
          </CollapsibleMode>

          <CollapsibleMode
            name="Modo muestreo por rechazo"
            state="Desactivada por defecto"
          >
            <Diagram>
              <RejectionSamplingDiagram />
            </Diagram>
            <p>
              No reformula el problema ni crea ninguna columna auxiliar: deja
              que el modelo genere con libertad,{" "}
              <strong>genera filas de más, descarta las que incumplen</strong>{" "}
              la regla y conserva las válidas, repitiendo hasta alcanzar el
              total pedido. La fila resultante es coherente{" "}
              <strong>en su conjunto</strong> —todo el registro, no solo dos
              columnas.
            </p>
            <OptionList
              items={[
                {
                  name: "Ventaja",
                  desc: "no impone una reformulación: comprueba la fila completa, así que respeta restricciones entre muchas columnas que el modo determinista no puede expresar.",
                },
                {
                  name: "Límite",
                  desc: "es más costoso (genera y descarta de más) y, si se agotan los intentos, puede no alcanzar el total de filas solicitado.",
                },
              ]}
            />
            <CautionNote
              title="El total de filas solo se respeta en la tabla cuyo tamaño hayas fijado"
              badge={
                <AdvancedBadge tooltip="Uso avanzado: la garantía del número de filas depende de qué tabla fijes en Volumen de datos (página de Generación)." />
              }
            >
              <p>
                El muestreo por rechazo <strong>siempre elimina</strong> las
                filas que incumplen la regla, así que puedes estar seguro de que
                el resultado solo contendrá filas válidas. Lo que no siempre se
                garantiza es el <strong>número de filas</strong>: el motor solo
                resimula intentando acercarse al objetivo cuando la tabla a la
                que has fijado un tamaño (<em>Volumen de datos</em>, en la página
                de Generación) <strong>coincide</strong> con la tabla sobre la
                que se aplica la regla.
              </p>
              <p>
                Si la tabla con tamaño fijado es la <strong>maestra</strong> y la
                regla afecta a una <strong>hija</strong>, el esquema se simula
                una sola vez (la maestra impone su número de filas y las hijas
                caen en cascada): tras descartar las filas de la hija que
                incumplen <strong>no se resimula</strong> para reponerlas. Tendrás
                la certeza de que las filas de la hija cumplen la regla, pueden ser <strong>menos de las esperadas</strong>.
              </p>
              <p>
                Para que el total de filas se respete sobre la tabla de
                la regla, fija el tamaño de <em>esa</em> tabla (modo «Objetivo
                fijo» en Volumen de datos). Este conflicto se extiende a cuando existen varias reglas con muestreo por rechazo en diferentes tablas. En ese caso solo se podría llegar a garantizar el total de filas en una de las tablas.
              </p>
            </CautionNote>
          </CollapsibleMode>
        </div>
      )}
    </div>
  );
}

// Deterministic mode, as a left→right flow:
//  [ lo que aprende el modelo: fecha_ingreso + duración≥0 (auxiliar) ]
//      → reconstruye (suma) → [ fecha_alta ]  ⇒ regla ✓
// The auxiliary column is highlighted in amber to show it's the constrained,
// system-generated piece that makes the rule hold.
function DeterministicModeDiagram() {
  const X_ING = 60; // fecha_ingreso position on the axis
  const X_ALTA = 244; // fecha_alta position on the axis
  const AXIS_Y = 78;
  return (
    <svg
      {...svgBase}
      width="300"
      height="150"
      viewBox="0 0 300 150"
      role="img"
      aria-label="Línea temporal: fecha_ingreso a la izquierda, fecha_alta a la derecha, separadas por la duración (columna auxiliar no negativa); por eso fecha_alta nunca es anterior a fecha_ingreso."
    >
      {/* timeline axis with an arrowhead (time flows →) */}
      <line
        x1={20}
        y1={AXIS_Y}
        x2={284}
        y2={AXIS_Y}
        stroke={SKY}
        strokeWidth={2}
        strokeLinecap="round"
        markerEnd="url(#timeArrow)"
      />
      <text x={288} y={AXIS_Y + 16} fontSize={8.5} fill={INK} textAnchor="end">
        tiempo
      </text>

      {/* duration span between the two dates — the auxiliary column */}
      <line
        x1={X_ING}
        y1={AXIS_Y}
        x2={X_ALTA}
        y2={AXIS_Y}
        stroke={AMBER}
        strokeWidth={5}
        strokeLinecap="round"
        opacity={0.55}
      />

      {/* fecha_ingreso point */}
      <line
        x1={X_ING}
        y1={AXIS_Y - 9}
        x2={X_ING}
        y2={AXIS_Y + 9}
        stroke={NAVY}
        strokeWidth={2}
      />
      <circle cx={X_ING} cy={AXIS_Y} r={5} fill={BLUE} />
      <text
        x={X_ING}
        y={AXIS_Y - 16}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        fecha_ingreso
      </text>

      {/* fecha_alta point */}
      <line
        x1={X_ALTA}
        y1={AXIS_Y - 9}
        x2={X_ALTA}
        y2={AXIS_Y + 9}
        stroke={NAVY}
        strokeWidth={2}
      />
      <circle cx={X_ALTA} cy={AXIS_Y} r={5} fill={NAVY} />
      <text
        x={X_ALTA}
        y={AXIS_Y - 16}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        fecha_alta
      </text>

      {/* duration label below the span */}
      <text
        x={(X_ING + X_ALTA) / 2}
        y={AXIS_Y + 24}
        fontSize={10}
        fontWeight={700}
        fill={AMBER}
        textAnchor="middle"
      >
        duración ≥ 0
      </text>
      <text
        x={(X_ING + X_ALTA) / 2}
        y={AXIS_Y + 36}
        fontSize={8.5}
        fill={INK}
        textAnchor="middle"
      >
        (columna auxiliar interna)
      </text>

      {/* rule badge */}
      <rect
        x={64}
        y={126}
        width={172}
        height={20}
        rx={8}
        fill="#fff"
        stroke={NAVY}
        strokeWidth={1.3}
      />
      <text
        x={150}
        y={140}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        fecha_alta ≥ fecha_ingreso ✓
      </text>

      <defs>
        <marker
          id="timeArrow"
          markerWidth={7}
          markerHeight={7}
          refX={5}
          refY={3}
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0 0 L6 3 L0 6 z" fill={SKY} />
        </marker>
      </defs>
    </svg>
  );
}

// Rejection sampling shown as a 3-stage flow: overgenerate → filter (keep ✓,
// drop ✗) → reach the target, with a retry loop back if rows are still short.
// Boxes are spaced with labels above/below so no text overlaps.
function RejectionSamplingDiagram() {
  return (
    <svg
      {...svgBase}
      width="320"
      height="182"
      viewBox="0 0 320 182"
      role="img"
      aria-label="Se generan filas de más, se filtran descartando las que incumplen la regla, y se conservan las válidas hasta el objetivo; si faltan, se reintenta"
    >
      {/* Stage 1: overgenerate */}
      <text
        x={48}
        y={16}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        1 · Genera de más
      </text>
      {[0, 1, 2, 3].map((i) => (
        <rect
          key={i}
          x={20}
          y={26 + i * 18}
          width={56}
          height={13}
          rx={3}
          fill={BLUE}
          fillOpacity={0.14}
          stroke={NAVY}
          strokeWidth={0.8}
        />
      ))}

      {/* arrow 1 → 2 */}
      <path
        d="M80 55 L 110 55"
        stroke={NAVY}
        strokeWidth={1.8}
        fill="none"
        markerEnd="url(#arrowN)"
      />

      {/* Stage 2: filter */}
      <text
        x={160}
        y={16}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        2 · Filtra por la regla
      </text>
      {[
        { ok: true, y: 26 },
        { ok: false, y: 44 },
        { ok: true, y: 62 },
        { ok: false, y: 80 },
      ].map((r, i) => (
        <g key={i}>
          <rect
            x={120}
            y={r.y}
            width={56}
            height={13}
            rx={3}
            fill={r.ok ? BLUE : AMBER}
            fillOpacity={r.ok ? 0.16 : 0.2}
            stroke={r.ok ? NAVY : AMBER}
            strokeWidth={0.9}
          />
          <text
            x={182}
            y={r.y + 10}
            fontSize={10}
            fontWeight={700}
            fill={r.ok ? "#1a7a3a" : AMBER}
          >
            {r.ok ? "✓" : "✗"}
          </text>
        </g>
      ))}
      <text x={148} y={108} fontSize={8.5} fill={AMBER} textAnchor="middle">
        descarta ✗
      </text>

      {/* arrow 2 → 3 (only valids) */}
      <path
        d="M196 55 L 226 55"
        stroke={NAVY}
        strokeWidth={1.8}
        fill="none"
        markerEnd="url(#arrowN)"
      />

      {/* Stage 3: target — a goal container that fills with the valid rows from
          this iteration; the empty slots show what's still missing (and drives
          the retry). 5 slots: 2 already had, +2 from this round, 1 missing. */}
      <text
        x={277}
        y={16}
        fontSize={10}
        fontWeight={700}
        fill={NAVY}
        textAnchor="middle"
      >
        3 · Objetivo
      </text>
      <rect
        x={240}
        y={22}
        width={72}
        height={74}
        rx={6}
        fill="none"
        stroke={NAVY}
        strokeWidth={1.5}
      />
      {[
        { kind: "prev", label: "" },
        { kind: "prev", label: "" },
        { kind: "new", label: "+1" },
        { kind: "new", label: "+1" },
        { kind: "missing", label: "" },
      ].map((s, i) => {
        const y = 27 + i * 13.5;
        if (s.kind === "missing") {
          return (
            <rect
              key={i}
              x={246}
              y={y}
              width={60}
              height={11}
              rx={2}
              fill="none"
              stroke={SKY}
              strokeWidth={1}
              strokeDasharray="3 2"
            />
          );
        }
        const isNew = s.kind === "new";
        return (
          <g key={i}>
            <rect
              x={246}
              y={y}
              width={60}
              height={11}
              rx={2}
              fill={NAVY}
              fillOpacity={isNew ? 1 : 0.35}
            />
            {isNew && (
              <text
                x={276}
                y={y + 9}
                fontSize={8}
                fontWeight={700}
                fill="#fff"
                textAnchor="middle"
              >
                +1 ✓
              </text>
            )}
          </g>
        );
      })}
      <text x={277} y={108} fontSize={8} fill={NAVY} textAnchor="middle">
        esta ronda suma 2
      </text>

      {/* arrow 2 → 3 lands at the "new" rows of the target */}

      {/* retry loop — triggered by the missing (dashed) slot */}
      <path
        d="M277 118 C 277 146, 48 146, 48 96"
        stroke={SKY}
        strokeWidth={2}
        fill="none"
        strokeDasharray="5 4"
        markerEnd="url(#arrowS)"
      />
      <text
        x={160}
        y={170}
        fontSize={9.5}
        fill={NAVY}
        textAnchor="middle"
        fontWeight={700}
      >
        si aún faltan, reintenta (máx. N intentos)
      </text>

      <defs>
        <marker
          id="arrowN"
          markerWidth={7}
          markerHeight={7}
          refX={5}
          refY={3}
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0 0 L6 3 L0 6 z" fill={NAVY} />
        </marker>
        <marker
          id="arrowS"
          markerWidth={7}
          markerHeight={7}
          refX={5}
          refY={3}
          orient="auto"
          markerUnits="strokeWidth"
        >
          <path d="M0 0 L6 3 L0 6 z" fill={SKY} />
        </marker>
      </defs>
    </svg>
  );
}

function HistorialDiagram() {
  return (
    <svg
      {...svgBase}
      width="320"
      height="120"
      viewBox="0 0 320 120"
      role="img"
      aria-label="Historial de ejecuciones de reglas con la activa resaltada"
    >
      {[0, 1, 2].map((i) => {
        const y = 6 + i * 38;
        const active = i === 0;
        return (
          <g key={i}>
            <rect
              x={4}
              y={y}
              width={312}
              height={30}
              rx={7}
              fill={active ? "#eef3ff" : "#fff"}
              stroke={active ? NAVY : SKY}
              strokeWidth={active ? 2.5 : 1.6}
            />
            <text
              x={18}
              y={y + 20}
              fontSize={13.5}
              fontWeight={active ? 700 : 400}
              fill={INK}
            >
              Ejecución {i + 1}
              {active ? "  ·  activa" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// Horizontal bar split into three colored segments showing the three compliance
// buckets: compliant (green), null (gray), non-compliant (red/amber). Labels
// annotate each segment below the bar.
function ComplianceBarDiagram() {
  // Example split: 94 % compliant, 3 % null, 3 % non-compliant.
  const W = 300;
  const BAR_H = 22;
  const BAR_Y = 22;
  const pctOk = 63;
  const pctNull = 20;
  const pctFail = 17;
  const wOk = Math.round((pctOk / 100) * W);
  const wNull = Math.round((pctNull / 100) * W);
  const wFail = W - wOk - wNull;
  const xNull = wOk;
  const xFail = wOk + wNull;
  const midOk = wOk / 2;
  const midNull = xNull + wNull / 2;
  const midFail = xFail + wFail / 2;
  return (
    <svg
      {...svgBase}
      width={W}
      height={96}
      viewBox={`0 0 ${W} 96`}
      role="img"
      aria-label="Barra de cumplimiento dividida en tres segmentos: 94 % cumplen, 3 % nulas, 3 % no cumplen"
    >
      {/* segments */}
      <rect
        x={0}
        y={BAR_Y}
        width={wOk}
        height={BAR_H}
        rx={0}
        fill="#16a34a"
        opacity={0.85}
      />
      <rect
        x={xNull}
        y={BAR_Y}
        width={wNull}
        height={BAR_H}
        fill="#94a3b8"
        opacity={0.7}
      />
      <rect
        x={xFail}
        y={BAR_Y}
        width={wFail}
        height={BAR_H}
        rx={0}
        fill="#dc2626"
        opacity={0.8}
      />
      {/* rounded caps on the outer edges */}
      <rect
        x={0}
        y={BAR_Y}
        width={8}
        height={BAR_H}
        rx={4}
        fill="#16a34a"
        opacity={0.85}
      />
      <rect
        x={W - 8}
        y={BAR_Y}
        width={8}
        height={BAR_H}
        rx={4}
        fill="#dc2626"
        opacity={0.8}
      />

      {/* pct labels inside the bar (only ok is wide enough) */}
      <text
        x={midOk}
        y={BAR_Y + 15}
        fontSize={11.5}
        fontWeight={700}
        fill="#fff"
        textAnchor="middle"
      >
        {pctOk}%
      </text>

      {/* tick lines + labels below */}
      {[
        { x: midOk, label: "% cumplen", color: "#15803d" },
        { x: midNull, label: "% nulas", color: "#64748b" },
        { x: midFail, label: "% no cumplen", color: "#b91c1c" },
      ].map(({ x, label, color }) => (
        <g key={label}>
          <line
            x1={x}
            y1={BAR_Y + BAR_H + 2}
            x2={x}
            y2={BAR_Y + BAR_H + 9}
            stroke={color}
            strokeWidth={1.5}
          />
          <text
            x={x}
            y={BAR_Y + BAR_H + 20}
            fontSize={9.5}
            fontWeight={600}
            fill={color}
            textAnchor="middle"
          >
            {label}
          </text>
        </g>
      ))}
    </svg>
  );
}

// ── Entries — an overview plus one per page section (WorkflowGroup) ─────────
export const CONFIGURACION_INSTRUCTIONS: readonly InstructionsEntry[] = [
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
    id: "reglas-banner",
    title: "Panel de reglas",
    content: (
      <>
        <Lead>
          El panel de <strong>«Reglas de negocio»</strong> en la parte superior
          de esta página resume, en tiempo real, las reglas y transformaciones
          configuradas en ese momento. Es el único panel <em>en vivo</em> de la
          herramienta: refleja el estado actual del editor y se actualiza
          automáticamente cada vez que añades, modificas o eliminas una regla.
        </Lead>

        {/* ── Live vs snapshot ── */}
        <CollapsibleSubsection title="En vivo vs. snapshot">
          <p>
            El mismo panel aparece más abajo al seleccionar una ejecución
            pasada, o en las páginas de Entrenamiento, Generación y Auditoría,
            pero en esas páginas muestra un <strong>snapshot</strong>: las
            reglas que se aplicaron en la ejecución concreta que tienes
            seleccionada, no las reglas actualmente configuradas. Esto permite
            revisar exactamente qué restricciones estaban activas en cada
            ejecución pasada sin que los cambios posteriores alteren la lectura.
          </p>
          {/* Mini mock showing the two badge variants */}
          <div className="space-y-1.5 rounded-md border border-[#cdd9ec] px-3 py-2 dark:border-[#26375f]">
            <div className="flex items-center gap-2">
              <span className="rounded-full border border-emerald-500/60 px-2 py-0.5 text-[10px] font-semibold text-emerald-700 dark:text-emerald-400">
                en vivo · próxima ejecución
              </span>
              <span className="text-[11px] text-muted-foreground">
                — esta página (Reglas de negocio)
              </span>
            </div>
            <div className="flex items-center gap-2">
              <span className="rounded-full border border-muted-foreground/40 px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                snapshot BRC
              </span>
              <span className="text-[11px] text-muted-foreground">
                — Entrenamiento, Generación, Auditoría
              </span>
            </div>
          </div>
        </CollapsibleSubsection>

        {/* ── Per-rule badges / icons legend ── */}
        <CollapsibleSubsection title="Etiquetas e iconos de cada regla">
          <p>
            Cada regla del panel se acompaña de unas etiquetas que resumen su
            tipo y su configuración de un vistazo. Aquí solo se describen
            brevemente; el significado de fondo de cada una se explica en las
            secciones indicadas más abajo en este mismo manual.
          </p>
          <ul className="space-y-2">
            <li className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-blue-400/50 bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-800 dark:bg-blue-900/40 dark:text-blue-300">
                tipo (azul)
              </span>
              <span className="rounded-full border border-transparent bg-[#FFDB00] px-2 py-0.5 text-[10px] font-semibold text-[#00215C]">
                tipo (amarillo)
              </span>
              <span className="min-w-0 flex-1 text-[12px]">
                El color del tipo distingue las{" "}
                <strong>columnas derivadas o eliminadas</strong> (azul) de las{" "}
                <strong>reglas lógicas</strong> (amarillo). Es la misma{" "}
                <em>«Leyenda»</em> que aparece al pie del panel. Más detalle en{" "}
                <em>Crear / eliminar columnas</em> y{" "}
                <em>Reglas lógicas / de negocio</em>.
              </span>
            </li>
            <li className="flex flex-wrap items-center gap-2">
              <span className="rounded-full border border-muted-foreground/30 px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                Determinista
              </span>
              <span className="rounded-full border border-amber-500/70 px-2 py-0.5 text-[10px] font-semibold text-amber-700 dark:text-amber-400">
                Muestreo por rechazo
              </span>
              <span className="min-w-0 flex-1 text-[12px]">
                Indica el <strong>modo de aplicación</strong> con el que se
                impondrá la regla. Más detalle en{" "}
                <em>Reglas lógicas / de negocio → Modo de aplicación</em>.
              </span>
            </li>
            <li className="flex flex-wrap items-center gap-2">
              <span className="inline-flex items-center gap-1 rounded-full border border-sky-500/60 px-2 py-0.5 text-[10px] font-semibold text-sky-700 dark:text-sky-400">
                <Lock className="h-2.5 w-2.5" />
                Lapso ≥ 0
              </span>
              <span className="inline-flex items-center gap-1 rounded-full border border-muted-foreground/30 px-2 py-0.5 text-[10px] font-semibold text-muted-foreground">
                <LockOpen className="h-2.5 w-2.5" />
                Lapso libre
              </span>
              <span className="min-w-0 flex-1 text-[12px]">
                El candado señala si la regla{" "}
                <strong>fuerza duraciones / lapsos no negativos</strong>{" "}
                (cerrado) o los deja libres (abierto). Más detalle en{" "}
                <em>
                  Reglas lógicas / de negocio → «Forzar duraciones no negativas»
                </em>
                .
              </span>
            </li>
          </ul>
        </CollapsibleSubsection>

        {/* ── Compliance percentages ── */}
        <CollapsibleSubsection title="Porcentajes de cumplimiento">
          <p>
            En el banner en vivo, cuando hay una{" "}
            <span className="font-medium text-foreground">Carga de Datos</span>{" "}
            seleccionada y la regla es de tipo lógico (relación entre fechas,
            entre números, semántica, etc.), cada regla muestra tres cifras
            calculadas sobre una muestra de hasta{" "}
            <strong>10 000 filas sacadas de los datos reales</strong>:
          </p>
          {/* Compliance bar diagram */}
          <Diagram>
            <ComplianceBarDiagram />
          </Diagram>
          <OptionList
            items={[
              {
                name: "% cumplen",
                desc: "filas cuyas columnas involucradas tienen valor (no son nulas) Y satisfacen la regla. Es el indicador principal.",
              },
              {
                name: "% nulas",
                desc: "filas donde alguna de las columnas de la regla no tiene valor. Estas filas no se cuentan como incumplimientos: el sistema no puede verificar la regla si faltan datos.",
              },
              {
                name: "% no cumplen",
                desc: "filas con valor en todas las columnas involucradas pero que violan la restricción. Cualquier valor mayor que 0 % aquí indica que los datos de entrenamiento ya contienen excepciones a la regla.",
              },
            ]}
          />
          <p>
            El color del porcentaje principal varía según el nivel de
            cumplimiento:{" "}
            <span className="font-semibold text-emerald-700 dark:text-emerald-400">
              verde (100 %)
            </span>
            ,{" "}
            <span className="font-semibold text-amber-700 dark:text-amber-400">
              ámbar (≥ 90 %)
            </span>{" "}
            o{" "}
            <span className="font-semibold text-red-600 dark:text-red-400">
              rojo (&lt; 90 %)
            </span>
            . Un porcentaje rojo no impide ejecutar la regla, pero sí señala que
            una parte significativa de los datos reales ya incumple la
            restricción que el modelo tendrá que aprender.
          </p>
          <p>
            Las <strong>columnas derivadas y eliminadas</strong> (etiquetas en
            azul) no muestran porcentajes: no son restricciones verificables en
            los datos, sino transformaciones aplicadas antes del entrenamiento.
          </p>
          <Example>
            Una regla <code>fecha_alta ≥ fecha_ingreso</code> muestra{" "}
            <span className="font-semibold text-emerald-700 dark:text-emerald-400">
              100 % cumplen
            </span>{" "}
            → el dataset real es consistente, el modelo aprenderá la relación
            sin excepciones. Si aparece un{" "}
            <span className="font-semibold text-red-600 dark:text-red-400">
              3 % no cumplen
            </span>
            , hay episodios con fechas invertidas en los datos de entrenamiento;
            conviene revisar si son errores o casos válidos antes de proceder.
          </Example>
        </CollapsibleSubsection>
      </>
    ),
  },
  {
    id: "biblioteca-reglas",
    title: "Biblioteca de reglas",
    content: (
      <>
        <Lead>
          Este recuadro permite guardar, reutilizar y reiniciar el{" "}
          <strong>conjunto de reglas</strong> al completo. Un conjunto agrupa
          las <strong>reglas lógicas</strong>, las{" "}
          <strong>columnas derivadas</strong> y las{" "}
          <strong>columnas marcadas para eliminar</strong>.
        </Lead>
        <IconOptionList
          items={[
            {
              Icon: RotateCcw,
              name: "Reinicio automático al entrar",
              desc: "cada vez que abres esta página, el editor de reglas y las columnas marcadas para eliminar arrancan vacíos.",
            },
            {
              Icon: Save,
              name: "Guardar conjunto actual",
              desc: "guarda en la biblioteca el conjunto actual completo (reglas lógicas, columnas derivadas y columnas a eliminar) sin ejecutar nada.",
            },
            {
              Icon: FolderOpen,
              name: "Cargar conjunto de reglas",
              desc: "carga en el editor un conjunto guardado en la biblioteca o el de una ejecución anterior (del historial), incluidas sus columnas a eliminar, para iterar desde ahí sin reconfigurar nada.",
            },
          ]}
        />
      </>
    ),
  },
  {
    id: "columnas",
    title: "Crear / eliminar columnas",
    content: (
      <>
        <Lead>
          Antes de iniciar el entrenamiento es posible ajustar el conjunto de
          columnas que recibirá el modelo: añadir columnas calculadas a partir
          de las existentes y excluir aquellas que no deban modelarse.
        </Lead>

        <Subtitle>Columnas derivadas</Subtitle>
        <p>
          Una columna derivada se calcula a partir de una columna origen
          existente y se añade a la tabla antes del entrenamiento. Su uso
          principal es transformar valores brutos en representaciones más
          estables o interpretables para el modelo (por ejemplo, convertir una
          fecha de nacimiento en edad, o agrupar valores continuos en tramos).
        </p>
        <Diagram>
          <DerivedColumnDiagram />
        </Diagram>
        <p>
          Seleccione un tipo de columna derivada para consultar su descripción,
          las opciones disponibles y un ejemplo:
        </p>
        <DerivedColumnExplorer />

        <Subtitle>Eliminar columnas</Subtitle>
        <p>
          Las columnas marcadas para exclusión se eliminan de los datos que
          recibe el modelo, así como de todas las fases posteriores
          (entrenamiento, generación y auditoría). La exclusión es{" "}
          <span className="font-medium text-foreground">no destructiva</span>:
          los datos originales no se modifican, las columnas siguen disponibles
          para ser referenciadas por las reglas de derivación o de negocio, y la
          exclusión puede revertirse en cualquier momento sin necesidad de
          volver a ejecutar la Carga de Datos.
        </p>
        <p>
          Las columnas marcadas para eliminar forman parte del{" "}
          <strong>conjunto de reglas</strong>: se reinician al entrar a la
          página y se guardan y cargan junto con las reglas desde la{" "}
          <span className="font-medium text-foreground">
            «Biblioteca de reglas»
          </span>{" "}
          (ver la sección <em>Reglas lógicas / de negocio</em>).
        </p>
        <Example>
          La columna <code>numero_historia_clinica</code> es un identificador
          único sin valor estadístico para el modelo; excluirla evita que el
          modelo memorice patrones de identificación irrelevantes.
        </Example>
      </>
    ),
  },
  {
    id: "reglas-logicas",
    title: "Reglas lógicas / de negocio",
    content: (
      <>
        <Lead>
          Las reglas de negocio definen restricciones que los datos sintéticos
          deben respetar para mantener su coherencia interna. Sin ellas, el
          modelo puede generar filas individualmente plausibles pero imposibles
          como conjunto (por ejemplo, una fecha de alta anterior al ingreso o
          una tensión diastólica superior a la sistólica).
        </Lead>
        <Diagram>
          <LogicalRuleDiagram />
        </Diagram>
        <p>
          Seleccione un tipo de regla para consultar su descripción, las
          opciones disponibles y un ejemplo:
        </p>
        <RuleTypeExplorer />
      </>
    ),
  },
  {
    id: "resultados",
    title: "Preprocesamiento de datos",
    content: (
      <>
        <Lead>
          Una vez configuradas las columnas y las reglas, esta sección ejecuta
          el preprocesamiento y muestra su resultado: el estado de la ejecución,
          un resumen de los cambios aplicados y una vista previa del dataset
          preprocesado que se enviará al entrenamiento.
        </Lead>

        <Subtitle>Ejecución de preprocesamiento</Subtitle>
        <p>
          El botón{" "}
          <span className="font-medium text-foreground">
            «Aplicar cambios configurados»
          </span>{" "}
          aplica todo lo configurado (columnas derivadas, exclusiones y reglas
          lógicas) sobre la Carga de Datos seleccionada en la cabecera y genera
          un nuevo dataset preprocesado. Mientras la ejecución está en curso, el
          botón se deshabilita y el progreso se muestra justo debajo. Al
          terminar, la ejecución pasa a ser la activa y alimenta las dos
          subsecciones siguientes.
        </p>

        <Subtitle>Visualización de datos</Subtitle>
        <p>
          Aquí puedes revisar el dataset ya preprocesado, el que verá el modelo.
          El selector{" "}
          <span className="font-medium text-foreground">«Vista»</span> controla
          qué columnas se muestran:
        </p>
        <OptionList
          items={[
            {
              name: "Tabla completa",
              desc: "muestra todas las columnas de cada tabla tal y como las recibirá el modelo.",
            },
            {
              name: "Solo columnas nuevas",
              desc: "muestra únicamente las columnas nuevas creadas a lo largo de esta página de configuración, para comprobar su efecto de un vistazo.",
            },
          ]}
        />
        <p>Y, para cada tabla, dispones de estas acciones:</p>
        <IconOptionList
          items={[
            {
              Icon: ChevronDown,
              name: "Ver muestra",
              desc: "despliega una muestra de filas de la tabla en la misma página.",
            },
            {
              Icon: Maximize2,
              name: "Ver completa",
              desc: "abre la tabla completa en una ventana emergente para recorrerla con detalle.",
            },
            {
              Icon: BarChart3,
              name: "Ver perfilado de columnas nuevas",
              desc: "abre en una pestaña nueva un informe de profiling de las columnas generadas para esa tabla concreta.",
            },
          ]}
        />
        <Example>
          Tras añadir la regla <code>fecha_alta ≥ fecha_ingreso</code>, aplica
          los cambios y verifica en los datos preprocesados que no existe ningún
          episodio con fecha de alta anterior a la de ingreso.
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
          El historial recoge todas las ejecuciones de reglas realizadas durante
          la sesión. Permite comparar distintas configuraciones y retomar una
          ejecución anterior como la activa sin necesidad de repetir el proceso
          de configuración.
        </Lead>
        <Diagram>
          <HistorialDiagram />
        </Diagram>
        <IconOptionList
          items={[
            {
              Icon: MousePointerClick,
              name: "Seleccionar como activa",
              desc: "haz clic en una fila para usar esa ejecución como referencia en los resultados y en los pasos posteriores del flujo.",
            },
            {
              Icon: Pencil,
              name: "Renombrar",
              desc: "asigna un nombre funcional a la configuración para identificarla más fácilmente; el nombre se mantiene en los pasos siguientes.",
            },
            {
              Icon: FileText,
              name: "Ver snapshot de rules.yaml",
              desc: "abre el snapshot de las reglas tal y como se aplicaron en esa ejecución.",
            },
            {
              Icon: Download,
              name: "Descargar",
              desc: "exporta los artefactos de la ejecución.",
            },
            {
              Icon: Trash2,
              name: "Eliminar ejecución",
              desc: "borra esa ejecución del historial. No se puede deshacer.",
            },
          ]}
        />
      </>
    ),
  },
];
