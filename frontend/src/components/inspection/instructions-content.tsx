// Help content for the Inspección instructions manual.
//
// One entry per page section (WorkflowGroup); the `id` matches the section's
// DOM id. Each entry combines concise prose, the meaning of the available
// options, a small inline schematic, and a concrete usage example.

"use client";

import { useState } from "react";

import {
  ENCODING_TYPES,
  ENCODING_TYPE_DESCRIPTIONS,
  ENCODING_TYPE_LABELS,
} from "@/lib/api";
import type { InstructionsEntry } from "@/components/layout/instructions-panel";

// ── Brand palette ───────────────────────────────────────────────────────────
const NAVY = "#00215C";
const BLUE = "#114da6";
const SKY = "#c9d4ea";
// Darker amber for the PK key marker — the brand yellow is too light to read.
const AMBER = "#C79200";
const INK = "#2b3a52";

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

// A heading for a section nested inside a Subtitle — a tinted pill so it
// stands out, while staying clearly subordinate to the full Subtitle.
function InnerSubtitle({ children }: { children: React.ReactNode }) {
  return (
    <h5 className="mt-2.5 inline-flex items-center gap-1.5 rounded-md bg-[#eef3ff] py-1 pl-1.5 pr-2.5 text-[12px] font-bold uppercase tracking-wide text-[#16386f] dark:bg-[#16284d] dark:text-[#dce8ff]">
      <span className="h-3.5 w-1 rounded-full bg-[#FFDB00]" />
      {children}
    </h5>
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
}: {
  value: string;
  onChange: (v: string) => void;
  options: Array<{ value: string; label: string }>;
}) {
  return (
    <div className="relative">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-9 w-full appearance-none rounded-lg border-2 border-[#16386f] bg-[#eef3ff] pl-3 pr-9 text-[13px] font-semibold text-[#16386f] shadow-sm transition-colors hover:bg-[#e2eaff] focus:outline-none focus:ring-2 focus:ring-[#5f83be] dark:border-[#5f83be] dark:bg-[#16284d] dark:text-[#dce8ff]"
      >
        {options.map((o) => (
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
};

// Horizontal numbered stepper: numbered nodes on a connecting track, with a
// short label beneath each. Clean and compact — used for the Resumen overview.
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
      {/* connecting track */}
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
            {/* soft halo */}
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
        ["Carga de", "ficheros"],
        ["Inspección autom.", "de tablas"],
        ["Vista previa", "de tablas"],
        ["Revisión de", "relaciones"],
        ["Revisión de", "tipos"],
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
        keys={[{ col: "id", color: AMBER, tag: "PK" }]}
        rows={["nombre", "fecha_nac.", "sexo"]}
      />
      <RelTable
        x={198}
        name="episodios"
        role="Tabla hija"
        keys={[
          { col: "id", color: AMBER, tag: "PK" },
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
  TABULAR_DATETIME_RELATIVE: "fecha_alta modelada como días transcurridos desde fecha_ingreso.",
  TABULAR_LAT_LONG: "ubicacion del centro de salud como par latitud/longitud.",
  LANGUAGE_TEXT: "observaciones_clinicas: texto libre redactado por el personal sanitario.",
  LANGUAGE_CATEGORICAL: "motivo_consulta con categorías de texto largas y muy variadas.",
  LANGUAGE_NUMERIC: "valores numéricos incrustados en texto clínico no estructurado.",
  LANGUAGE_DATETIME: "fechas mencionadas dentro de un informe clínico en texto libre.",
};

// Interactive encoding-type explorer for the manual: a dropdown of every
// MostlyAI encoding type with its Spanish description and a health example.
function EncodingTypeExplorer() {
  const [value, setValue] = useState<string>("TABULAR_CATEGORICAL");
  return (
    <div className="space-y-2.5">
      <div>
        <label className="mb-1 block text-[12px] font-bold uppercase tracking-wide text-[#26467a] dark:text-[#9db4dc]">
          Tipo de codificación
        </label>
        <SelectMenu
          value={value}
          onChange={setValue}
          options={ENCODING_TYPES.map((t) => ({
            value: t,
            label: ENCODING_TYPE_LABELS[t] ?? t,
          }))}
        />
      </div>
      <p>{ENCODING_TYPE_DESCRIPTIONS[value]}</p>
      <Example>{ENCODING_TYPE_EXAMPLES[value]}</Example>
    </div>
  );
}

function HistorialDiagram() {
  return (
    <svg {...svgBase} width="320" height="120" viewBox="0 0 320 120" role="img"
      aria-label="Historial de inspecciones con la activa resaltada">
      {[0, 1, 2].map((i) => {
        const y = 6 + i * 38;
        const active = i === 0;
        return (
          <g key={i}>
            <rect x={4} y={y} width={312} height={30} rx={7}
              fill={active ? "#eef3ff" : "#fff"} stroke={active ? NAVY : SKY}
              strokeWidth={active ? 2.5 : 1.6} />
            <text x={18} y={y + 20} fontSize={13.5} fontWeight={active ? 700 : 400} fill={INK}>
              Inspección {i + 1}{active ? "  ·  activa" : ""}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

// ── Rule-type reference ─────────────────────────────────────────────────────
// Mirrors the rule types offered by the rules editor on the page. Each entry
// describes how the rule is configured (its parameters) and a health-domain
// example.
type RuleTypeInfo = {
  value: string;
  label: string;
  desc: string;
  /** Configurable parameters and what each one means. */
  params: Array<{ name: string; meaning: string }>;
  /** Opt-in / opt-out toggle options of this rule, shown as callouts. */
  toggles?: Array<{ name: string; state: string; desc: string }>;
  example: React.ReactNode;
};

const RULE_TYPES: readonly RuleTypeInfo[] = [
  {
    value: "date_inequality",
    label: "Desigualdad de fechas",
    desc: "Garantiza que una fecha objetivo cumpla un orden respecto a una fecha origen o a una fecha constante.",
    params: [
      { name: "Tabla / columna objetivo", meaning: "la fecha que debe respetar la restricción." },
      { name: "Tabla / columna origen", meaning: "la fecha de referencia con la que se compara." },
      { name: "Constante (opcional)", meaning: "una fecha fija (p. ej. 2020-01-01) que sustituye a la columna origen." },
      { name: "Operador (≥ / ≤)", meaning: "indica si la objetivo debe ser posterior o anterior al origen." },
      { name: "Columna auxiliar (opcional)", meaning: "nombre de la columna de duración que se genera; se autogenera si se deja vacío." },
    ],
    toggles: [
      {
        name: "Forzar duraciones no negativas",
        state: "Activada por defecto",
        desc: "Limita la duración resultante a valores ≥ 0. Desactívala si los datos reales contienen inconsistencias temporales que quieras replicar fielmente en los datos sintéticos. En ambos casos, configurar esta regla es útil porque transforma el par de fechas en una duración —un valor numérico directamente interpretable— que el modelo puede aprender con mucha más facilidad que dos fechas absolutas mezcladas entre decenas de columnas del dataset.",
      },
    ],
    example:
      "fecha_alta_hospitalaria ≥ fecha_ingreso: ningún paciente puede recibir el alta antes de haber ingresado.",
  },
  {
    value: "numeric_inequality",
    label: "Desigualdad numérica",
    desc: "Garantiza que un valor numérico objetivo cumpla un orden respecto a un valor origen o a una constante.",
    params: [
      { name: "Tabla / columna objetivo", meaning: "el valor numérico que debe respetar la restricción." },
      { name: "Tabla / columna origen", meaning: "el valor numérico de referencia." },
      { name: "Constante (opcional)", meaning: "un número fijo que sustituye a la columna origen." },
      { name: "Operador (≥ / ≤)", meaning: "indica si la objetivo debe ser mayor o menor que el origen." },
      { name: "Columna auxiliar (opcional)", meaning: "nombre de la columna de diferencia generada; se autogenera si se deja vacío." },
    ],
    example:
      "tension_sistolica ≥ tension_diastolica: la presión sistólica nunca es inferior a la diastólica.",
  },
  {
    value: "semantic_ranking_consistency",
    label: "Consistencia semántica (ranking)",
    desc: "Restringe qué combinaciones de dos columnas categóricas son válidas, asumiendo que ambas tienen un orden de niveles equiespaciados.",
    params: [
      { name: "Tabla / columna origen", meaning: "la categórica que actúa como condición." },
      { name: "Tabla / columna objetivo", meaning: "la categórica cuyos valores se restringen según el origen." },
    ],
    example:
      "Un paciente clasificado como triaje «leve» no puede tener a la vez nivel de gravedad «crítico».",
  },
  {
    value: "semantic_proportional_consistency",
    label: "Consistencia semántica (proporcional)",
    desc: "Como la consistencia de ranking, pero los intervalos válidos respetan la frecuencia real de cada categoría en los datos.",
    params: [
      { name: "Tabla / columna origen", meaning: "la categórica que actúa como condición." },
      { name: "Tabla / columna objetivo", meaning: "la categórica cuyos valores se restringen, ponderada por su frecuencia real." },
    ],
    example:
      "Relaciona el servicio hospitalario con el tipo de ingreso respetando cuántos ingresos reales tiene cada servicio.",
  },
  {
    value: "foreign_keys_consistency_rule",
    label: "Consistencia de claves foráneas",
    desc: "Reconstruye una clave foránea redundante copiando su valor desde la tabla padre marcada como contexto, evitando referencias inválidas.",
    params: [
      { name: "Tabla origen", meaning: "la tabla padre que aporta el valor de referencia (contexto)." },
      { name: "Tabla / columna objetivo", meaning: "la tabla hija y la columna FK que se reconstruye." },
      { name: "Columna fuente (opcional)", meaning: "columna de la tabla padre de la que se copia; por defecto, la misma que la objetivo." },
      { name: "Tabla referenciada (opcional)", meaning: "tabla a la que apunta la FK, si difiere de la de origen." },
    ],
    example:
      "episodios.id_paciente se rellena desde la tabla pacientes para que todo episodio apunte a un paciente existente.",
  },
  {
    value: "date_to_age",
    label: "Columna derivada: edad a partir de fecha",
    desc: "Crea una columna de edad (en años) a partir de una columna de fecha y una fecha de referencia.",
    params: [
      { name: "Tabla / columna origen", meaning: "la columna de fecha de la que se calcula la edad." },
      { name: "Columna derivada (aux_col)", meaning: "nombre de la nueva columna de edad que se crea." },
      { name: "Fecha de referencia (constante)", meaning: "fecha fija respecto a la que se calcula la edad." },
      { name: "o columna de referencia", meaning: "otra columna de fecha como referencia (alternativa a la constante)." },
      { name: "Eliminar columna origen", meaning: "descarta la fecha original tras derivar la edad." },
      { name: "Reconstruir en POST", meaning: "vuelve a generar la fecha original tras la generación, si se eliminó." },
    ],
    example:
      "Genera pacientes.edad a partir de fecha_nacimiento y la fecha de ingreso, para modelar la edad al ingresar.",
  },
  {
    value: "numeric_threshold",
    label: "Columna derivada: umbral numérico",
    desc: "Crea una columna booleana comparando una columna numérica con un umbral.",
    params: [
      { name: "Tabla / columna origen", meaning: "la columna numérica que se compara." },
      { name: "Columna derivada (aux_col)", meaning: "nombre de la nueva columna booleana." },
      { name: "Operador (≥ > ≤ <)", meaning: "la comparación que se aplica frente al umbral." },
      { name: "Umbral", meaning: "el valor numérico contra el que se compara." },
      { name: "Valor si verdadero / falso", meaning: "valores personalizados para cada resultado de la comparación." },
      { name: "Eliminar / reconstruir origen", meaning: "descarta la columna numérica original y, opcionalmente, la recupera tras la generación." },
    ],
    example:
      "Crea fiebre = (temperatura ≥ 38) para marcar qué pacientes presentan fiebre.",
  },
  {
    value: "numeric_bucket",
    label: "Columna estratificada: buckets numéricos",
    desc: "Crea una columna categórica agrupando una columna numérica en intervalos (bins). Útil para generalizar el modelo.",
    params: [
      { name: "Tabla / columna origen", meaning: "la columna numérica que se agrupa por intervalos." },
      { name: "Columna derivada (aux_col)", meaning: "nombre de la nueva columna categórica." },
      { name: "Bordes de bins", meaning: "los límites de los intervalos (se necesitan al menos 2; admite «Infinity»)." },
      { name: "Etiquetas (opcional)", meaning: "nombre de cada intervalo; deben ser N−1 para N bordes." },
      { name: "include_lowest / right", meaning: "controlan si el borde inferior se incluye y si los intervalos son cerrados por la derecha." },
      { name: "Eliminar / reconstruir origen", meaning: "descarta la columna numérica original y, opcionalmente, la recupera tras la generación." },
    ],
    example:
      "Agrupa edad en [0, 18, 65, ∞) con etiquetas «pediátrico», «adulto», «geriátrico».",
  },
];

// Interactive rule-type explorer for the manual: an always-available selector
// (independent from the page's transient Add/Edit form) that shows, for the
// chosen rule type, how it is configured (each parameter) and an example.
function RuleTypeExplorer() {
  const [value, setValue] = useState(RULE_TYPES[0].value);
  const info = RULE_TYPES.find((r) => r.value === value) ?? RULE_TYPES[0];
  return (
    <div className="space-y-2.5">
      <div>
        <label className="mb-1 block text-[12px] font-bold uppercase tracking-wide text-[#26467a] dark:text-[#9db4dc]">
          Tipo de regla
        </label>
        <SelectMenu
          value={value}
          onChange={setValue}
          options={RULE_TYPES.map((r) => ({ value: r.value, label: r.label }))}
        />
      </div>
      <p>{info.desc}</p>
      <div>
        <InnerSubtitle>Cómo se configura</InnerSubtitle>
        <ul className="mt-1.5 space-y-1">
          {info.params.map((p) => (
            <li key={p.name} className="flex gap-2">
              <span className="mt-[5px] h-1.5 w-1.5 shrink-0 rounded-sm bg-[#5f83be]" />
              <span>
                <span className="font-semibold text-[#16386f] dark:text-[#dce8ff]">
                  {p.name}
                </span>{" "}
                — {p.meaning}
              </span>
            </li>
          ))}
        </ul>
      </div>
      {info.toggles?.map((t) => (
        <OptionCallout key={t.name} name={t.name} state={t.state}>
          {t.desc}
        </OptionCallout>
      ))}
      <Example>{info.example}</Example>
    </div>
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
    title: "Preparación",
    content: (
      <>
        <Lead>
          Elige los datos de partida y lanza la inspección, que detectará
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
              desc: "Pulsa una columna en la vista previa para excluirla de la inspección — útil para datos personales o irrelevantes.",
            },
            {
              name: "Iniciar inspección",
              desc: "Lanza el análisis. Al terminar verás las tablas, relaciones y tipos detectados.",
            },
          ]}
        />
        <OptionCallout
          name="Generar informes de profiling"
          state="Activada por defecto"
        >
          Genera un informe que describe las principales características de cada
          tabla (distribuciones, valores faltantes, correlaciones, etc.) usando
          la librería de Python <code>ydata-profiling</code>. Puedes
          desactivarla si prefieres una inspección más rápida.
        </OptionCallout>
      </>
    ),
  },
  {
    id: "reglas-negocio",
    title: "Reglas de negocio",
    content: (
      <>
        <Lead>
          Restricciones propias de tu dominio que los datos deben cumplir. Se
          aplican antes de entrenar para que el modelo aprenda solo de datos
          coherentes, y se reutilizan en los pasos posteriores.
        </Lead>
        <p>
          Pulsa <span className="font-semibold">«Añadir regla»</span>, elige el
          tipo de regla, indica las tablas y columnas a las que se aplica,
          ajusta sus parámetros y guarda. Puedes definir varias reglas; se
          aplican todas en orden de dependencia.
        </p>
        <Subtitle>Tipos de regla y su configuración</Subtitle>
        <p>
          Selecciona un tipo para ver qué hace, qué significa cada parámetro
          configurable y un ejemplo de uso:
        </p>
        <RuleTypeExplorer />
      </>
    ),
  },
  {
    id: "resultados",
    title: "Resultados",
    content: (
      <>
        <Lead>
          Tras la inspección, revisa y corrige lo que el sistema ha detectado:
          las relaciones entre tablas y el tipo de cada columna.
        </Lead>

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

        <Subtitle>Tipos de codificación</Subtitle>
        <p>
          A cada columna se le asigna un tipo de codificación que determina
          cómo se modela. Una clasificación incorrecta degrada la calidad de
          los datos sintéticos; corrígela si es necesario. Selecciona un tipo
          para ver qué significa y un ejemplo:
        </p>
        <EncodingTypeExplorer />
      </>
    ),
  },
  {
    id: "historial",
    title: "Historial",
    content: (
      <>
        <Lead>
          Todas las inspecciones de la sesión. Permite retomar trabajo previo
          sin repetir la configuración.
        </Lead>
        <Diagram>
          <HistorialDiagram />
        </Diagram>
        <OptionList
          items={[
            { name: "Seleccionar", desc: "recarga los resultados de una inspección anterior." },
            { name: "Renombrar", desc: "asigna un nombre funcional para identificarla." },
            { name: "Limpiar", desc: "elimina carpetas vacías, huérfanas y duplicados." },
            { name: "Purgar", desc: "borra TODAS las inspecciones — úsalo con cuidado." },
          ]}
        />
      </>
    ),
  },
];
