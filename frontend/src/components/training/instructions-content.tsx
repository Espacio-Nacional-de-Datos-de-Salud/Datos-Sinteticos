// Help content for the Entrenamiento instructions manual.
//
// One entry per top-level page section (WorkflowGroup); the `id` matches the
// section's DOM id. Each entry combines concise prose, the meaning of the
// available options, a small inline schematic, and a concrete usage example.
//
// Structurally a sibling of @/components/inspection/instructions-content.tsx;
// the presentational helpers (Lead, Subtitle, StepTable, Example, ...) are
// duplicated here on purpose so this module stays self-contained.

"use client";

import { useState } from "react";
import {
  ChevronDown,
  ChevronUp,
  Brain,
  Info,
  Lock,
  Sparkles,
  ExternalLink,
  MousePointerClick,
  Pencil,
  Download,
  XCircle,
  Trash2,
  AlertTriangle,
  type LucideIcon,
} from "lucide-react";
import { AdvancedBadge } from "@/components/ui/advanced-section";
import type { InstructionsEntry } from "@/components/layout/instructions-panel";

// ── Brand palette ───────────────────────────────────────────────────────────
const NAVY = "#00215C";
const SKY = "#c9d4ea";
const INK = "#2b3a52";
// Violet of the "advanced / optional" sparkle (matches the sidebar nav marker
// and AdvancedBadge) — used to flag advanced steps in the overview stepper.
const VIOLET = "#a78bfa";

// ── Presentational helpers (mirror of inspection/instructions-content.tsx) ──
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

// A nested heading one level below Subtitle — for sub-sections that belong to a
// Subtitle (e.g. Modos de configuración / Parámetros / Ajustes por tabla under
// "Configuración del modelo"). Stands out with a sky-blue accent bar + a thin
// underline, but stays clearly below the yellow-underlined Subtitle.
function SubSubtitle({ children }: { children: React.ReactNode }) {
  return (
    <h5 className="mt-3 mb-1 flex items-center gap-1.5 text-[12.5px] font-bold uppercase tracking-wide text-[#16386f] underline decoration-[#5f83be]/60 decoration-2 underline-offset-4 dark:text-[#9db4dc]">
      <span className="h-3.5 w-1 rounded-full bg-[#5f83be]" />
      {children}
    </h5>
  );
}

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

function OptionList({ items }: { items: Array<{ name: React.ReactNode; desc: string }> }) {
  return (
    <ul className="space-y-1">
      {items.map((it, i) => (
        <li key={i} className="flex gap-2">
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

// A note describing an activatable (opt-in / opt-out) option — same look used
// across the manuals: navy-tinted card, yellow accent edge, sliders icon and a
// yellow state badge in the top-right corner.
function OptionCallout({
  name,
  state,
  children,
  extra,
}: {
  name: string;
  state: string;
  children: React.ReactNode;
  /** Optional block content rendered inside the box, below the description
      (e.g. the list of sub-parameters that depend on this option). */
  extra?: React.ReactNode;
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
      {extra && (
        <div className="mt-2 border-t border-[#5f83be]/25 pt-2">{extra}</div>
      )}
    </div>
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

function DpChainWarning() {
  return (
    <div className="overflow-hidden rounded-lg border border-amber-300/70 bg-amber-50/60 dark:border-amber-700/40 dark:bg-amber-950/20">
      <div className="flex items-center gap-1.5 bg-amber-400/80 px-2.5 py-1 dark:bg-amber-700/60">
        <AlertTriangle className="h-3.5 w-3.5 shrink-0 text-amber-900 dark:text-amber-200" aria-hidden />
        <span className="text-[10.5px] font-bold uppercase tracking-wide text-amber-900 dark:text-amber-200">
          Aviso
        </span>
      </div>
      <div className="px-2.5 py-2 space-y-2 text-[12px] text-[#5a3a00] dark:text-[#f5d38a]">
        <p>
          <strong>MostlyAI crashea si 3 o más tablas encadenadas por FK contextual tienen Privacidad Diferencial (DP) activa al mismo tiempo.</strong>{" "}
          La limitación es interna de PyTorch.
        </p>
        <p>
          <strong className="text-amber-800 dark:text-amber-300">Cómo corregirlo desde aquí:</strong>{" "}
          Usa «Ajustes por tabla» para deshabilitar DP en una o más tablas de la cadena (establece{" "}
          <code className="rounded bg-amber-100 px-1 text-[10.5px] dark:bg-amber-900/50">privacidad diferencial: desactivada</code>{" "}
          en la tabla que quieras excluir). Dejando un máximo de 2 tablas con DP activa basta para que el entrenamiento no crashee sin tener que eliminar las relaciones.
        </p>
        <p>
          <strong className="text-amber-800 dark:text-amber-300">Cómo cortar la cadena de FK:</strong>{" "}
          Si prefieres eliminar la relación, ve a{" "}
          <strong>Carga de Datos</strong> y modifica las relaciones entre tablas para romper la cadena de tres o más niveles contextuales. Ten en cuenta que cualquier cambio en Carga de Datos invalida las configuraciones de Reglas de negocio (BRC) existentes:{" "}
          <strong>tendrás que volver a ejecutar el paso de BRC</strong> antes de poder entrenar.
        </p>
      </div>
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

// Horizontal numbered stepper: numbered nodes on a connecting track, with a
// short label beneath each. Used for the Resumen overview at the top of the
// panel. Steps flagged `optional` carry a violet sparkle above their node.
// Unlike the other figures, this one carries its own surface classes so it can
// blend into the dark rail (the brand-colored schematics keep the shared light
// "paper" of `svgBase`).
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
        { lines: ["Selección de", "datos (y reglas)"] },
        { lines: ["Configuración", "del modelo"] },
        { lines: ["Ejecución del", "entrenamiento"] },
        { lines: ["Revisión del", "entrenamiento"] },
        { lines: ["Revisión del", "historial"] },
      ]}
    />
  );
}

// ── Mostly AI Model & Architecture Information (Collapsible) ───────────────
function MostlyAiModelInfo() {
  const [expanded, setExpanded] = useState(false);

  // The instructions panel positions each section's help block absolutely and
  // reserves page space from its measured height. Toggling this nested block
  // changes that height, so notify the panel (it re-measures on window resize)
  // after the new content has laid out — otherwise the expanded text overflows
  // onto the next section ("Resultados").
  const toggle = () => {
    setExpanded((v) => !v);
    requestAnimationFrame(() =>
      requestAnimationFrame(() => window.dispatchEvent(new Event("resize"))),
    );
  };

  return (
    <div className="mt-4 overflow-hidden rounded-lg border border-blue-100 bg-blue-50/20 p-3.5 dark:border-blue-950/30 dark:bg-blue-950/5">
      <div className="flex items-start gap-2.5">
        <div className="mt-0.5 rounded-md bg-blue-500/10 p-1 text-blue-600 dark:text-blue-400">
          <Brain className="h-4 w-4" />
        </div>
        <div className="flex-1 space-y-1.5">
          <h5 className="text-[13px] font-bold text-blue-950 dark:text-blue-200">
            Arquitectura del Generador: TabularARGN
          </h5>
          <p className="text-[12px] leading-relaxed text-[#3a4a63] dark:text-[#aebdd9]">
            El motor de síntesis de este sistema utiliza **TabularARGN** (Any-order Auto-Regressive Generative Network), un framework avanzado y flexible de redes neuronales autorregresivas desarrollado y publicado por **Mostly AI**.
          </p>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-[11px] font-medium text-[#16386f] dark:text-[#8ea9db]">
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
              Variantes: Flat y Sequential
            </span>
            <span className="flex items-center gap-1">
              <span className="h-1.5 w-1.5 rounded-full bg-blue-500" />
              Tamaño por defecto: Medium
            </span>
          </div>
          <p className="text-[11px] text-[#3a4a63] dark:text-[#aebdd9] mt-1">
            Referencia:{" "}
            <a
              href="https://arxiv.org/pdf/2501.12012"
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-0.5 text-blue-600 hover:underline dark:text-blue-400 font-semibold"
            >
              Paper de TabularARGN (arXiv:2501.12012)
              <ExternalLink className="h-3 w-3" />
            </a>
          </p>
        </div>
      </div>

      {/* Toggle Button */}
      <button
        type="button"
        onClick={toggle}
        className="mt-3.5 flex w-full items-center justify-between rounded-md bg-blue-500/10 px-3 py-2 text-[11px] font-bold uppercase tracking-wider text-blue-700 hover:bg-blue-500/20 dark:text-blue-300 dark:hover:bg-blue-500/15 transition-all"
      >
        <span className="flex items-center gap-1.5">
          <Info className="h-3.5 w-3.5" />
          {expanded ? "Ocultar detalles técnicos avanzados" : "Ver detalles técnicos y funcionamiento"}
        </span>
        {expanded ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
      </button>

      {/* Collapsible Content */}
      {expanded && (
        <div className="mt-3.5 space-y-3.5 border-t border-blue-100/60 pt-3 text-[12px] text-[#3a4a63] dark:border-blue-950/30 dark:text-[#aebdd9]">
          {/* Arquitectura en profundidad */}
          <div>
            <div className="flex items-center gap-1 text-[12.5px] font-bold text-blue-950 dark:text-blue-200 mb-1">
              <span className="h-1 w-2 rounded-full bg-blue-600 dark:bg-blue-400" />
              Arquitectura de Red Neuronal
            </div>
            <p className="leading-relaxed pl-3">
              A diferencia de las arquitecturas GAN clásicas, **TabularARGN** es un modelo autorregresivo flexible. Trata cada columna como un paso en una secuencia de predicción condicional, modelando la distribución conjunta de la fila de forma ordenada o aleatoria:
            </p>
            <ul className="mt-1.5 list-disc pl-7 space-y-1 text-[11.5px]">
              <li>
                <strong className="text-blue-955 dark:text-blue-200">FlatModel:</strong> Diseñado para datos tabulares no secuenciales simples (procesa una fila a la vez de forma independiente).
              </li>
              <li>
                <strong className="text-blue-955 dark:text-blue-200">SequentialModel:</strong> Para series temporales u ordenadas, incorporando capas **LSTM** (Long Short-Term Memory) para aprender dependencias de historial.
              </li>
              <li>
                <strong className="text-blue-955 dark:text-blue-200">Dimensionamiento Dinámico:</strong> Los embeddings de columnas y las dimensiones del regresor feed-forward se escalan según el tamaño configurado (<code className="rounded bg-slate-100 px-1 dark:bg-slate-800 text-[10.5px]">Small</code>, <code className="rounded bg-slate-100 px-1 dark:bg-slate-800 text-[10.5px]">Medium</code> o <code className="rounded bg-slate-100 px-1 dark:bg-slate-800 text-[10.5px]">Large</code>), optimizando el mapeo de relaciones complejas de alta dimensión.
              </li>
            </ul>
          </div>

          {/* Cómo Funciona: Loss, LR, Batch size, Early stopping */}
          <div>
            <div className="flex items-center gap-1 text-[12.5px] font-bold text-blue-955 dark:text-blue-200 mb-1">
              <span className="h-1 w-2 rounded-full bg-blue-600 dark:bg-blue-400" />
              Cómo funciona (Optimización y Loss)
            </div>
            <div className="space-y-2 pl-3">
              <p className="leading-relaxed">
                <strong className="text-blue-955 dark:text-blue-200">Todo es Clasificación (Cross-Entropy Loss):</strong> Para dar soporte robusto a columnas categóricas, texto y valores numéricos continuos, el motor **discretiza automáticamente los números** en intervalos o categorías virtuales. Así, el modelo trata la predicción de cada columna como una tarea de clasificación múltiple y optimiza mediante <code className="rounded bg-slate-100 px-1 dark:bg-slate-800 text-[10.5px]">CrossEntropyLoss</code>. La pérdida total es la suma de pérdidas de todas las columnas.
              </p>
              <p className="leading-relaxed">
                <strong className="text-blue-955 dark:text-blue-200">Optimización y LR Schedule:</strong> Utiliza el optimizador **AdamW**. La tasa de aprendizaje inicial se calcula con la heurística <code className="rounded bg-slate-100 px-1 dark:bg-slate-800 text-[10.5px]">0.001 * sqrt(batch_size / 32)</code>. A través de un programador <code className="rounded bg-slate-100 px-1 dark:bg-slate-800 text-[10.5px]">ReduceLROnPlateau</code>, la tasa de aprendizaje se reduce a la mitad (factor 0.5x) si no hay mejora en la pérdida de validación durante 2 épocas.
              </p>
              <p className="leading-relaxed">
                <strong className="text-blue-955 dark:text-blue-200">Parada Temprana Inteligente:</strong> El bucle de entrenamiento ejecuta la parada de forma automática y rígida (4 épocas sin mejora de la pérdida de validación) para evitar el sobreajuste. Al finalizar, restaura automáticamente el mejor checkpoint obtenido.
              </p>
              <p className="leading-relaxed">
                <strong className="text-blue-955 dark:text-blue-200">Heurística de Batch Size:</strong> Si se deja en automático, el motor calcula el tamaño de lote físico óptimo (entre 8 y 4096) basándose en la RAM del hardware, el recuento de registros, el número de columnas y los parámetros para evitar errores de falta de memoria.
              </p>
            </div>
          </div>

          {/* Configuración de Privacidad */}
          <div className="rounded border border-yellow-100 bg-yellow-50/20 p-2.5 dark:border-yellow-950/20 dark:bg-yellow-950/5">
            <div className="flex items-center gap-1.5 text-[12px] font-bold text-yellow-900 dark:text-yellow-300 mb-1.5">
              <Lock className="h-3.5 w-3.5 text-yellow-600 dark:text-yellow-400" />
              Arquitectura de Privacidad de Doble Capa
            </div>
            <div className="space-y-2 text-[11.5px] leading-relaxed text-[#5a4e14] dark:text-[#d8c98a]">
              <p>
                El motor de Mostly AI opera mediante dos capas independientes y complementarias para resguardar la identidad de los datos reales:
              </p>
              <div className="pl-1 space-y-1.5">
                <p>
                  <strong className="font-semibold text-yellow-950 dark:text-yellow-200">1. Value Protection (Capa de Datos - Pre/Post):</strong> Activa por defecto. Evita que el modelo memorice categorías extremadamente raras (las reemplaza por un token especial <code className="rounded bg-yellow-100 px-1 dark:bg-yellow-900/40 text-[10px]">_RARE_</code>) o valores numéricos extremos fuera de los percentiles habituales.
                </p>
                <p>
                  <strong className="font-semibold text-yellow-950 dark:text-yellow-200">2. Privacidad Diferencial - DP (Capa del Modelo - En entrenamiento):</strong> Garantía formal matemática (ε, δ)-DP. Al activarla, se recorta la norma de los gradientes de cada muestra (<code className="rounded bg-yellow-100 px-1 dark:bg-yellow-900/40 text-[10px]">max_grad_norm</code>) e inyecta ruido gaussiano calibrado (<code className="rounded bg-yellow-100 px-1 dark:bg-yellow-900/40 text-[10px]">noise_multiplier</code>) al optimizador. Si el presupuesto consumido alcanza el límite <code className="rounded bg-yellow-100 px-1 dark:bg-yellow-900/40 text-[10px]">max_epsilon</code>, el entrenamiento se detiene de forma segura.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── Entries — an overview plus one per top-level page section ───────────────
export function getEntrenamientoInstructions(): readonly InstructionsEntry[] {
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
      title: "Configuración",
      content: (
        <>
          <Lead>
            Elige los datos a partir de los cuales entrenar, ajusta el modelo y
            lanza el entrenamiento. Esta sección tiene tres pasos:
          </Lead>
          <StepTable
            steps={[
              {
                name: "Selector de fuente de datos",
                desc: "Elige la fuente de datos: una configuración con reglas aplicadas o los datos preprocesados de la carga, y selecciona el conjunto concreto en el desplegable.",
              },
              {
                name: "Configuración del modelo",
                desc: "Parte de un modo de configuración y, si lo necesitas, ajusta los parámetros a mano. Los valores por defecto son razonables para empezar.",
              },
              {
                name: "Ejecución del entrenamiento",
                desc: "Lanza el proceso con «Iniciar entrenamiento» y asigna un nombre al modelo. El sistema generará el modelo entrenado.",
              },
            ]}
          />
          <Subtitle>Selector de fuente de datos</Subtitle>
          <p>
            Aquí eliges sobre qué datos se entrenará el modelo. Hay dos fuentes:
          </p>
          <OptionList
            items={[
              {
                name: "Datos preprocesados",
                desc: "los datos preprocesados de la carga, sin reglas de negocio. Úsalo si quieres entrenar sin restricciones o si aún no has creado ninguna configuración de reglas.",
              },
              {
                name: (
                  <span className="inline-flex items-center gap-1">
                    Datos preprocesados + Reglas aplicadas
                    <AdvancedBadge tooltip="Avanzado · usa una configuración de reglas de negocio aplicadas" />
                  </span>
                ),
                desc: "una configuración del paso de Reglas de negocio (BRC) cuyo dataset ya tiene las reglas aplicadas. Es la opción por defecto: el modelo aprende respetando las restricciones que definiste. Elige la configuración concreta en el desplegable.",
              },
            ]}
          />
          <p>
            Tras elegir la fuente, selecciona en el desplegable el conjunto
            concreto (configuración de reglas o carga de datos) sobre el que
            entrenar.
          </p>

          <Subtitle>Configuración del modelo</Subtitle>
          <p>
            Define cómo se entrena el modelo. Puedes partir de un{" "}
            <strong>modo de configuración</strong> y, si lo necesitas, ajustar
            cada parámetro a mano.
          </p>

          <SubSubtitle>Modos de configuración</SubSubtitle>
          <p>
            Un modo rellena de golpe los parámetros según el equilibrio que
            busques entre privacidad y calidad. Cuando eliges un modo distinto de{" "}
            <strong>Libre</strong>, los campos que ese modo fija aparecen{" "}
            <strong>bloqueados</strong> (en gris, con un candado), mientras que los
            que deja sin configurar siguen siendo editables. Para editarlo todo a
            mano, vuelve a <strong>Libre</strong>.
          </p>
          <OptionList
            items={[
              {
                name: "✏️ Libre (por defecto)",
                desc: "configuración personalizada sin restricciones: todos los campos editables. Es el modo seleccionado de inicio.",
              },
              {
                name: "🔒 Privacidad",
                desc: "máxima protección: modelo pequeño y privacidad diferencial robusta (ε≈1.0). Menor fidelidad. Úsalo con datos sensibles donde la protección prima.",
              },
              {
                name: "⚖️ Equilibrado",
                desc: "modelo mediano con generación flexible, sin privacidad diferencial. Buen balance calidad/privacidad para la mayoría de los casos.",
              },
              {
                name: "✨ Utilidad",
                desc: "máxima calidad sintética: modelo grande sin restricciones de privacidad. Para datos no sensibles donde la fidelidad es lo importante.",
              },
            ]}
          />

          <SubSubtitle>Precisión y velocidad del entrenamiento</SubSubtitle>
          <p>
            Con un modo activo, el <strong>tamaño de batch</strong> (cuántas filas
            procesa el modelo en cada paso) se calcula automáticamente según el
            número de filas de tus datos, por lo que aparece bloqueado. Junto al
            selector de modo puedes elegir cómo equilibrar{" "}
            <strong>precisión</strong> y <strong>tiempo</strong>: con el mismo
            volumen de datos, un batch menor hace que el modelo se ajuste más
            veces (aprende mejor pero tarda más) y uno mayor menos veces (entrena
            antes pero aprende menos).
          </p>
          <OptionList
            items={[
              {
                name: "🐢 Más preciso",
                desc: "batches menores: el modelo ajusta más veces sobre los mismos datos, así que aprende mejor (mayor fidelidad), a costa de un entrenamiento más lento.",
              },
              {
                name: "⚖️ Equilibrado",
                desc: "tamaño de batch intermedio: buen compromiso entre precisión y tiempo. Es la opción por defecto.",
              },
              {
                name: "🐇 Más rápido",
                desc: "batches mayores: el modelo ajusta menos veces, así que entrena antes a cambio de algo menos de aprendizaje. Útil para pruebas o datasets muy grandes.",
              },
            ]}
          />
          <p>
            En casos extremos el batch puede <strong>no cambiar</strong> entre las
            tres opciones: con <strong>muy pocas filas</strong> se queda siempre en
            el batch mínimo, y con <strong>muchísimas</strong> se satura en el
            máximo. Es normal: el tamaño se acota a un rango seguro para no romper
            el entrenamiento ni agotar la memoria.
          </p>

          <SubSubtitle>Parámetros configurables</SubSubtitle>
          <p>
            En modo <strong>Libre</strong> puedes ajustar a mano estos parámetros
            principales:
          </p>
          <OptionList
            items={[
              {
                name: "Épocas máximas",
                desc: "Número máximo de pasadas completas sobre los datos. Más épocas suelen mejorar la fidelidad, pero alargan el entrenamiento y pueden sobreajustar. Vacío = sin límite.",
              },
              {
                name: "Tamaño de batch",
                desc: "Filas por paso de entrenamiento (mínimo 2). Batches grandes van más rápido por época pero usan más memoria. Déjalo vacío para cálculo automático.",
              },
              {
                name: "Tiempo máximo (min)",
                desc: "Detiene el entrenamiento al alcanzar ese tiempo. Útil para acotar pruebas. Ej.: 30 min para un primer ensayo. Vacío = sin límite.",
              },
              {
                name: "Tamaño máximo de muestra",
                desc: "Limita cuántas filas se usan para entrenar. Útil con datasets enormes para entrenar más rápido. Vacío = usar todas.",
              },
              {
                name: "Tamaño del modelo (S / M / L)",
                desc: "Pequeño, Mediano o Grande. Modelos mayores aprenden patrones más complejos a costa de más tiempo y memoria. Ej.: empieza con Mediano y sube a Grande si la precisión se queda corta.",
              },
              {
                name: "Habilitar generación flexible",
                desc: "Permite rebalanceo e imputación al generar, pero puede reducir algo la precisión. Actívala si luego querrás generar bajo condiciones.",
              },
            ]}
          />

          <OptionCallout
            name="Privacidad diferencial"
            state="Desactivada por defecto"
            extra={
              <>
                <p className="mb-1.5 text-[12px] font-semibold text-[#16386f] dark:text-[#dce8ff]">
                  Al activarla, se configuran estos parámetros:
                </p>
                <OptionList
                  items={[
                    {
                      name: "Epsilon máximo (ε)",
                      desc: "Presupuesto de privacidad: más bajo = más privacidad y menos fidelidad. Ej.: ε≈1 es estricto; valores mayores relajan la protección. Vacío = sin tope.",
                    },
                    {
                      name: "Delta (δ)",
                      desc: "Probabilidad de fallo del mecanismo. Valores típicos muy pequeños (p. ej. 1e-5).",
                    },
                    {
                      name: "Multiplicador de ruido",
                      desc: "Cuánto ruido se añade a los gradientes. Más ruido = más privacidad, menor utilidad.",
                    },
                    {
                      name: "Norma máxima del gradiente",
                      desc: "Umbral de recorte (clipping) de gradientes antes de añadir el ruido.",
                    },
                  ]}
                />
              </>
            }
          >
            Añade ruido controlado durante el entrenamiento para acotar lo que el
            modelo memoriza, con una garantía formal (ε, δ). Reduce algo la
            fidelidad a cambio de protección.
          </OptionCallout>

          <div className="relative mt-3 rounded-lg border border-violet-200/60 bg-violet-50/30 p-3 pl-4 shadow-sm before:absolute before:inset-y-3 before:left-0 before:w-1 before:rounded-r-full before:bg-violet-300/70 dark:border-violet-900/40 dark:bg-violet-950/10 dark:before:bg-violet-500/50">
            <div className="flex items-center gap-1.5">
              <Sparkles className="h-3.5 w-3.5 shrink-0 text-violet-400 dark:text-violet-300" aria-hidden />
              <span className="text-[13px] font-bold tracking-tight text-[#16386f] dark:text-[#dce8ff]">
                Ajustes por tabla
              </span>
            </div>
            <p className="mt-1.5">
              Opcional y solo útil con <strong>varias tablas</strong>. Por defecto
              todas las tablas usan la configuración global de arriba; aquí puedes
              sobrescribir parámetros para una tabla concreta y el resto sigue
              heredando lo global.
            </p>
            <p className="mt-1.5 font-semibold text-[#16386f] dark:text-[#dce8ff]">
              Cómo usarlo:
            </p>
            <OptionList
              items={[
                {
                  name: "Añadir tabla",
                  desc: "elige la tabla que quieres personalizar de la lista.",
                },
                {
                  name: "Sobrescribir parámetros",
                  desc: "ajusta solo los campos que quieras cambiar para esa tabla (tamaño del modelo, épocas, batch…); los que no toques heredan la configuración global.",
                },
                {
                  name: "Quitar",
                  desc: "elimina la personalización de una tabla para que vuelva a heredar lo global.",
                },
              ]}
            />
            <Example>
              Usa un modelo <strong>Grande</strong> solo en la tabla principal
              (la más compleja) y deja las tablas auxiliares en{" "}
              <strong>Mediano</strong> para ahorrar tiempo y memoria.
            </Example>
            <DpChainWarning />
          </div>

          <SubSubtitle>¿Se guarda mi configuración?</SubSubtitle>
          <p>
            Sí. La configuración se guarda en el servidor de forma continua, así
            que el entrenamiento <strong>siempre usa lo que ves en pantalla</strong>:
          </p>
          <OptionList
            items={[
              {
                name: "Al elegir un modo",
                desc: "se aplica y guarda al instante (verás un aviso «Configuración actualizada»). No hace falta pulsar «Guardar».",
              },
              {
                name: "Al editar un campo a mano",
                desc: "el cambio queda pendiente y el botón «Guardar» se activa. El indicador muestra «Cambios sin guardar» hasta que pulsas Guardar.",
              },
              {
                name: "Indicador de estado",
                desc: "junto al botón «Guardar», en verde «Configuración guardada» significa que no hay nada pendiente; en ámbar «Cambios sin guardar» significa que debes guardar para aplicarlos.",
              },
            ]}
          />
          <Example>
            Si el botón «Guardar» está en gris y el indicador dice{" "}
            <strong>«Configuración guardada»</strong>, es que ya está todo
            guardado: puedes iniciar el entrenamiento con esa configuración.
          </Example>

          <SubSubtitle>Editar como YAML</SubSubtitle>
          <p>
            El botón <strong>«Editar como YAML»</strong> (arriba a la izquierda del
            panel) cambia del formulario guiado al texto en crudo de la
            configuración. Útil para usuarios avanzados que quieran ver o ajustar
            todos los parámetros a la vez, copiar/pegar una configuración completa
            o tocar campos que el formulario no expone.
          </p>
          <OptionList
            items={[
              {
                name: "Editar como YAML",
                desc: "muestra el archivo de configuración como texto editable. Si el YAML es inválido, se avisa y «Guardar» se bloquea hasta corregirlo.",
              },
              {
                name: "Volver al formulario",
                desc: "regresa a la vista guiada; los cambios válidos hechos en YAML se conservan y se reflejan en los campos.",
              },
            ]}
          />

          <MostlyAiModelInfo />

          <Subtitle>Ejecución del entrenamiento</Subtitle>
          <p>
            Antes de lanzar, el recuadro{" "}
            <span className="font-medium text-foreground">«Configuración que se usará»</span>{" "}
            resume con nombres claros los parámetros guardados que se aplicarán
            (tamaño del modelo, épocas, batch, privacidad diferencial si está
            activa…). Es un reflejo de lo que configuraste arriba, para que
            confirmes de un vistazo con qué ajustes vas a entrenar.
          </p>
          <p>
            Cuando la configuración esté lista, pulsa{" "}
            <span className="font-medium text-foreground">«Iniciar entrenamiento»</span>{" "}
            para lanzarlo. Antes de empezar, una comprobación previa avisa si la
            configuración haría fallar el entrenamiento (en ese caso, el botón se
            deshabilita hasta que la corrijas).
          </p>
          <p>
            Al iniciar se abre una ventana para asignar un{" "}
            <strong>nombre funcional</strong> al modelo (opcional; puedes dejarlo
            en blanco). Ese nombre identifica el modelo y podrás editarlo después
            desde el propio recuadro de ejecución, desde la cabecera de la página
            y desde el <span className="font-medium text-foreground">Historial</span>;
            además aparece al seleccionar el modelo en el paso de Generación.
          </p>
          <Example>
            Nómbralo según lo que lo distingue, p. ej.{" "}
            <code>modelo_DP_epsilon1</code> o <code>modelo_grande_sin_reglas</code>,
            para reconocerlo entre varios entrenamientos.
          </Example>
        </>
      ),
    },
    {
      id: "resultados",
      title: "Resultados",
      content: (
        <>
          <Lead>
            Mientras el entrenamiento corre verás su progreso aquí.
          </Lead>

          <Subtitle>Entrenamiento actual</Subtitle>
          <p>
            Muestra el estado del entrenamiento en curso (o del último iniciado
            en esta sesión): la fase actual, las tablas implicadas y el número de
            filas.
          </p>
          <OptionList
            items={[
              {
                name: "Cancelar entrenamiento",
                desc: "Detiene un entrenamiento en curso. Los artefactos parciales se conservan en el catálogo, marcados como cancelados.",
              },
              {
                name: "Tiempos de ejecución",
                desc: "Una vez completado, despliega los tiempos por fase para entender en qué se ha invertido el cómputo.",
              },
            ]}
          />

        </>
      ),
    },
    {
      id: "historial",
      title: "Historial",
      content: (
        <>
          <Lead>
            Catálogo completo de modelos disponibles en el servidor. Permite
            retomar modelos pasados sin tener que reentrenarlos.
          </Lead>
          <IconOptionList
            items={[
              {
                Icon: MousePointerClick,
                name: "Seleccionar",
                desc: "haz clic en una fila para cargar ese modelo como entrenamiento actual; su información vuelve a aparecer arriba.",
              },
              {
                Icon: Pencil,
                name: "Renombrar",
                desc: "asigna un nombre funcional para identificar el modelo más fácilmente.",
              },
              {
                Icon: Download,
                name: "Descargar",
                desc: "exporta el modelo generador o la carpeta completa con todos sus artefactos.",
              },
              {
                Icon: XCircle,
                name: "Cancelar",
                desc: "detiene un entrenamiento en curso desde el propio catálogo.",
              },
              {
                Icon: Trash2,
                name: "Eliminar",
                desc: "borra el modelo y sus artefactos. No se puede deshacer.",
              },
              {
                Icon: Trash2,
                name: "Limpiar sesiones incompletas",
                desc: "elimina carpetas vacías y ejecuciones huérfanas — útil tras varias cancelaciones.",
              },
              {
                Icon: Trash2,
                name: "Limpiar todas las sesiones",
                desc: "elimina TODOS los modelos — úsalo con cuidado.",
              },
            ]}
          />
        </>
      ),
    },
  ];
}
