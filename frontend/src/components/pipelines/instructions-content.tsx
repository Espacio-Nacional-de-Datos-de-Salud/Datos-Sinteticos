// Help content for the Pipelines workbench manual.
//
// Unlike the guided wizard steps (Carga de Datos, Configuración, Entrenamiento,
// Generación, Auditoría), the Pipelines page is a free-form, dev-only workbench
// with a two-column layout — not a vertical stack of WorkflowGroups. So this
// manual is NOT section-aligned: instead of binding each block to a DOM section
// id, `PipelinesInstructionsPanel` renders every entry sequentially inside a
// self-contained, scrollable right-hand drawer.
//
// Presentational helpers are duplicated here (rather than shared) so the module
// stays self-contained, mirroring the other instructions-content files.

"use client";

import { BookOpen, X } from "lucide-react";

// ── Brand palette ───────────────────────────────────────────────────────────
const NAVY = "#00215C";
const BLUE = "#114da6";
const SKY = "#c9d4ea";
const AMBER = "#C79200";
const INK = "#2b3a52";

// ── Presentational helpers ──────────────────────────────────────────────────
function Lead({ children }: { children: React.ReactNode }) {
  return <p>{children}</p>;
}

function Diagram({ children }: { children: React.ReactNode }) {
  return <div className="my-1 flex justify-center">{children}</div>;
}

function OptionList({ items }: { items: Array<{ name: string; desc: React.ReactNode }> }) {
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
      <div className="px-2.5 py-1.5 text-[12px] text-[#4a4214] dark:text-[#d8c98a]">
        {children}
      </div>
    </div>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-md border-l-4 border-[#5f83be] bg-[#eef3ff] py-2 pl-2.5 pr-3 text-[12px] dark:bg-[#16284d]">
      {children}
    </div>
  );
}

function StepTable({ steps }: { steps: Array<{ name: string; desc: React.ReactNode }> }) {
  return (
    <div className="overflow-hidden rounded-lg border border-[#cdd9ec] shadow-[0_1px_3px_rgba(16,40,80,0.06)] dark:border-[#26375f]">
      <div className="grid grid-cols-[34%_66%] bg-[#16386f] text-[10px] font-bold uppercase tracking-[0.06em] text-white">
        <div className="px-3 py-2">Paso</div>
        <div className="border-l border-white/15 px-3 py-2">Qué hace</div>
      </div>
      {steps.map((s, i) => (
        <div
          key={s.name}
          className={
            "grid grid-cols-[34%_66%] border-t border-[#e5ebf6] dark:border-[#26375f] " +
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

const svgBase = {
  preserveAspectRatio: "xMidYMid meet" as const,
  fontFamily: "inherit",
  // Figures are drawn with light-theme brand colors, so they always sit on a
  // light "paper" surface — keeps contrast correct in dark mode too.
  className: "rounded-lg border border-[#e3e9f4] bg-[#f7f9fd] p-2 dark:border-[#2a3a5e]",
};

// Top-level overview: the four things you do on this page.
function OverviewDiagram() {
  const steps = [
    ["Crear o", "abrir config"],
    ["Definir jobs", "y pasos"],
    ["Combinar /", "variar"],
    ["Guardar", "YAML"],
    ["Lanzar y", "seguir runs"],
  ];
  const colW = 96;
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
            <text x={cx} y={cy + 4.5} fontSize={12.5} fontWeight={700} fill="#fff" textAnchor="middle">
              {i + 1}
            </text>
            {lines.map((ln, j) => (
              <text key={j} x={cx} y={40 + j * 10} fontSize={9} fontWeight={600} fill={INK} textAnchor="middle">
                {ln}
              </text>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

// A pipeline = config → N jobs → each job a chain of up to 3 steps.
function StructureDiagram() {
  return (
    <svg {...svgBase} width="320" height="178" viewBox="0 0 320 178" role="img"
      aria-label="Un pipeline contiene varios jobs; cada job encadena los pasos entrenar, simular y evaluar">
      {/* config envelope */}
      <rect x={4} y={4} width={312} height={170} rx={8} fill="#f5f8fd" stroke={NAVY}
        strokeWidth={1.4} strokeDasharray="5 3" />
      <text x={14} y={20} fontSize={10} fontWeight={700} fill={NAVY}>pipeline.yaml</text>

      {[0, 1].map((row) => {
        const y = 30 + row * 70;
        return (
          <g key={row}>
            {/* job box */}
            <rect x={14} y={y} width={292} height={60} rx={7} fill="#fff" stroke={SKY} strokeWidth={1.4} />
            <text x={24} y={y + 16} fontSize={9.5} fontWeight={700} fill={BLUE}>
              job_{row + 1}
            </text>
            {/* three step pills, chained */}
            {[
              { lbl: "entrenar", x: 24 },
              { lbl: "simular", x: 120 },
              { lbl: "evaluar", x: 216 },
            ].map((s, i) => (
              <g key={s.lbl}>
                <rect x={s.x} y={y + 24} width={80} height={26} rx={6}
                  fill={NAVY} opacity={0.92} />
                <text x={s.x + 40} y={y + 41} fontSize={10} fontWeight={600}
                  fill="#fff" textAnchor="middle">{s.lbl}</text>
                {i < 2 && (
                  <path d={`M${s.x + 82} ${y + 37} l10 0`} stroke={AMBER}
                    strokeWidth={2} markerEnd="" />
                )}
                {i < 2 && (
                  <path d={`M${s.x + 88} ${y + 33} l5 4 l-5 4`} stroke={AMBER}
                    strokeWidth={2} fill="none" strokeLinecap="round" strokeLinejoin="round" />
                )}
              </g>
            ))}
          </g>
        );
      })}
    </svg>
  );
}

// Combinations = cartesian product of axes; variants = sparse hand-picked list.
function ExpansionDiagram() {
  return (
    <svg {...svgBase} width="320" height="150" viewBox="0 0 320 150" role="img"
      aria-label="Combinaciones generan el producto cartesiano de ejes; variantes una lista escogida a mano">
      {/* Left: combinations grid */}
      <text x={78} y={12} fontSize={10} fontWeight={700} fill={NAVY} textAnchor="middle">Combinaciones</text>
      <text x={78} y={24} fontSize={8.5} fill="#5f83be" textAnchor="middle">2 modelos × 3 tamaños = 6</text>
      {[0, 1].map((r) =>
        [0, 1, 2].map((c) => (
          <rect key={`${r}-${c}`} x={20 + c * 40} y={32 + r * 34} width={34} height={28} rx={4}
            fill={NAVY} opacity={r === 0 ? 0.85 : 0.5} />
        )),
      )}
      <text x={37} y={120} fontSize={8.5} fill={INK}>Small</text>
      <text x={107} y={120} fontSize={8.5} fill={INK}>Large</text>

      {/* divider */}
      <line x1={160} y1={30} x2={160} y2={130} stroke={SKY} strokeWidth={1.2} strokeDasharray="3 3" />

      {/* Right: variants list */}
      <text x={244} y={12} fontSize={10} fontWeight={700} fill={NAVY} textAnchor="middle">Variantes</text>
      <text x={244} y={24} fontSize={8.5} fill="#5f83be" textAnchor="middle">lista escogida a mano</text>
      {[
        "1k filas",
        "5k filas",
        "10k filas + DP",
      ].map((lbl, i) => (
        <g key={lbl}>
          <rect x={180} y={34 + i * 30} width={128} height={24} rx={5}
            fill="#eef3ff" stroke={BLUE} strokeWidth={1.3} />
          <text x={244} y={50 + i * 30} fontSize={9.5} fill={INK} textAnchor="middle">{lbl}</text>
        </g>
      ))}
    </svg>
  );
}

// ── Manual entries ──────────────────────────────────────────────────────────
type Entry = { id: string; title: string; content: React.ReactNode };

export const PIPELINES_INSTRUCTIONS: readonly Entry[] = [
  {
    id: "resumen",
    title: "Resumen",
    content: (
      <>
        <Lead>
          El <strong>Diseñador de Pipelines</strong> automatiza, en una sola
          ejecución desatendida, el mismo flujo que harías a mano paso a paso en
          el asistente guiado (Carga de Datos → Configuración → Entrenamiento →
          Generación → Auditoría). En lugar de hacer clic por cada pantalla,
          describes el trabajo una vez como una lista de <em>jobs</em> y lo
          lanzas.
        </Lead>
        <Diagram>
          <OverviewDiagram />
        </Diagram>
        <Note>
          Es una herramienta <strong>avanzada</strong>, disponible en la sección{" "}
          <strong>Avanzado</strong> del menú lateral. Cada cambio se guarda como
          un archivo <code>.yaml</code> reutilizable; lanzar un pipeline es
          exactamente el mismo flujo que usa la CLI.
        </Note>
      </>
    ),
  },
  {
    id: "para-que-sirve",
    title: "¿Para qué sirve?",
    content: (
      <>
        <Lead>
          El asistente guiado es ideal para una ejecución única y supervisada.
          El pipeline es la herramienta cuando necesitas{" "}
          <strong>repetir, comparar o escalar</strong>:
        </Lead>
        <OptionList
          items={[
            {
              name: "Reproducibilidad",
              desc: "El YAML deja constancia exacta de qué datos, modelo, reglas y parámetros se usaron. Vuelve a lanzarlo meses después y obtienes el mismo proceso.",
            },
            {
              name: "Automatización",
              desc: "Entrena, genera y evalúa de extremo a extremo sin intervención. Útil para tandas nocturnas o conjuntos grandes que tardan.",
            },
            {
              name: "Experimentación (barridos)",
              desc: "Lanza decenas de variantes a la vez — distintos modelos, tamaños de muestra, épocas o niveles de privacidad — para comparar resultados.",
            },
            {
              name: "Encadenado",
              desc: "La salida de un paso alimenta automáticamente al siguiente, sin pasar artefactos a mano entre pantallas.",
            },
          ]}
        />
        <Example>
          «Quiero comparar el modelo <code>Small</code> frente al{" "}
          <code>Large</code>, cada uno generando 1k, 5k y 10k filas, y evaluar
          los seis». Eso son seis jobs que defines en segundos con{" "}
          <strong>Combinaciones</strong> y lanzas de una vez.
        </Example>
      </>
    ),
  },
  {
    id: "anatomia",
    title: "Anatomía de un pipeline",
    content: (
      <>
        <Lead>
          Un pipeline es un archivo de configuración que contiene una lista de{" "}
          <strong>jobs</strong>. Cada job es una unidad de trabajo independiente
          que encadena hasta tres pasos. Puedes activar solo los que necesites.
        </Lead>
        <Diagram>
          <StructureDiagram />
        </Diagram>
        <p>
          Los pasos se ejecutan en orden y se <strong>auto-enlazan</strong>: el
          primero (la «cabeza» de la cadena) toma su entrada de una fuente
          externa — archivos crudos, una inspección, un modelo o una simulación
          ya existentes — y cada paso posterior consume la salida del anterior.
          No tienes que copiar identificadores entre pasos a mano.
        </p>
        <Note>
          Puedes empezar la cadena por donde quieras. Un job de{" "}
          <em>solo simular</em> que parte de un modelo ya entrenado, o uno de{" "}
          <em>solo evaluar</em> sobre una simulación existente, son configuraciones
          válidas y habituales.
        </Note>
      </>
    ),
  },
  {
    id: "pasos",
    title: "Los tres pasos de un job",
    content: (
      <>
        <Lead>
          En cada tarjeta de job activas los pasos con sus desplegables. Esto es
          lo que hace cada uno:
        </Lead>
        <StepTable
          steps={[
            {
              name: "Entrenar (train)",
              desc: (
                <>
                  Preprocesa los datos y entrena un modelo. Acepta dos modos
                  de entrada mutuamente excluyentes:{" "}
                  <strong>archivos crudos</strong> (se inspeccionan al vuelo) o{" "}
                  <strong>reanudar desde una inspección</strong> ya guardada
                  (tiene prioridad si indicas ambos).
                </>
              ),
            },
            {
              name: "Simular (simulate)",
              desc: (
                <>
                  Genera datos sintéticos a partir de un modelo. Configuras el{" "}
                  <strong>tamaño de muestra</strong>, el formato de salida (CSV o
                  Parquet) y, opcionalmente, condiciones de generación. Si el
                  job entrena antes, el modelo se enlaza solo.
                </>
              ),
            },
            {
              name: "Evaluar (evaluate)",
              desc: (
                <>
                  Compara los datos sintéticos con los reales y produce el
                  informe de calidad. Los datos reales se{" "}
                  <strong>vinculan automáticamente</strong> a los de
                  entrenamiento del modelo, para que columnas derivadas y
                  descartadas coincidan en ambos lados.
                </>
              ),
            },
          ]}
        />
      </>
    ),
  },
  {
    id: "overrides",
    title: "Ajustes por job",
    content: (
      <>
        <Lead>
          Cada job admite <strong>sobre-escrituras</strong> opcionales que
          modifican la configuración base solo para ese job. Lo que dejes en
          blanco mantiene el valor por defecto (no se escribe en el YAML), así
          que la fusión profunda de la configuración global se conserva.
        </Lead>
        <OptionList
          items={[
            { name: "Reglas (rules_config)", desc: "Aplica un archivo de reglas de negocio concreto a este job. Puedes editarlo en el momento sin salir de la página." },
            { name: "Modelo / épocas / batch", desc: "Elige el preset del motor (Small / Medium / Large) y ajusta épocas máximas y tamaño de lote del entrenamiento." },
            { name: "Generación flexible e informe", desc: "Activa o desactiva la generación flexible y el informe del modelo de Mostly AI." },
            { name: "Privacidad diferencial (DP)", desc: "Fija el épsilon máximo y el multiplicador de ruido para entrenar con garantías de privacidad diferencial." },
            { name: "General", desc: "Perfilado de datos y delimitador CSV por defecto." },
          ]}
        />
      </>
    ),
  },
  {
    id: "expansion",
    title: "Combinaciones y variantes",
    content: (
      <>
        <Lead>
          Para barridos no defines los jobs uno a uno: los generas. Hay dos
          herramientas según la forma del barrido.
        </Lead>
        <Diagram>
          <ExpansionDiagram />
        </Diagram>
        <OptionList
          items={[
            {
              name: "Combinaciones",
              desc: (
                <>
                  Botón <strong>Combinaciones</strong> de la barra superior.
                  Eliges una cadena de pasos y, para cada parámetro, das uno o
                  varios valores. Cada parámetro con varios valores se convierte
                  en un <em>eje</em>; el resultado es el{" "}
                  <strong>producto cartesiano</strong> de todos los ejes. Ideal
                  para rejillas densas.
                </>
              ),
            },
            {
              name: "Variantes",
              desc: (
                <>
                  Botón <strong>Expandir</strong> dentro de una tarjeta de job.
                  Partes de un job base y defines a mano una lista de variantes
                  (cada una un pequeño retoque sobre la base). Ideal para
                  barridos <strong>dispersos</strong>, no toda la rejilla.
                </>
              ),
            },
          ]}
        />
        <p>
          Al aplicar, eliges si los jobs generados{" "}
          <strong>reemplazan</strong> al job base o se{" "}
          <strong>insertan después</strong> de él.
        </p>
      </>
    ),
  },
  {
    id: "guardar-lanzar",
    title: "Guardar, revisar y lanzar",
    content: (
      <>
        <Lead>
          Cuando el diseño esté listo, estos son los controles de la barra
          superior y el carril izquierdo:
        </Lead>
        <OptionList
          items={[
            {
              name: "Nombre del pipeline",
              desc: (
                <>
                  Se usa como nombre del archivo YAML. Solo letras, números,
                  guiones y guiones bajos. Guardar con un nombre distinto crea
                  una <strong>copia</strong>.
                </>
              ),
            },
            { name: "Ver YAML", desc: "Previsualiza —y puedes editar a mano— el YAML generado. Al guardar, se valida en el servidor y se recarga en el editor visual, manteniendo ambas vistas sincronizadas." },
            { name: "Restablecer", desc: "Descarta los cambios locales y recarga la última versión guardada (o vacía el editor si es nuevo)." },
            { name: "Guardar", desc: "Escribe el archivo .yaml. Debe haber al menos un job." },
            { name: "Lanzar", desc: "Ejecuta el pipeline guardado. Lanza el flujo completo de extremo a extremo en segundo plano." },
            { name: "Carril izquierdo", desc: "Lista los pipelines guardados (seleccionar para editar, ▶ para lanzar, 🗑 para eliminar) y las ejecuciones recientes." },
          ]}
        />
        <Note>
          El botón <strong>Lanzar</strong> de la barra superior exige guardar
          antes; el icono ▶ del carril izquierdo lanza directamente una config
          ya guardada.
        </Note>
      </>
    ),
  },
  {
    id: "ejecuciones",
    title: "Ejecuciones",
    content: (
      <>
        <Lead>
          Bajo <strong>Ejecuciones recientes</strong> (carril izquierdo) aparece
          el historial de lanzamientos, que se refresca automáticamente cada
          pocos segundos.
        </Lead>
        <OptionList
          items={[
            { name: "Seguimiento en vivo", desc: "Haz clic en una ejecución para abrir su detalle: estado y progreso por job y por paso, en tiempo real mientras corre." },
            { name: "Re-lanzar", desc: "Como cada pipeline es un archivo, basta volver a pulsar ▶ sobre la config para repetir la misma ejecución." },
            { name: "Independencia", desc: "Eliminar una config no afecta a las ejecuciones pasadas: sus artefactos quedan registrados aparte." },
          ]}
        />
      </>
    ),
  },
];

// ── Self-contained panel ────────────────────────────────────────────────────
// Renders the whole manual sequentially in a scrollable right-hand drawer.
// Deliberately NOT section-aligned (the page has no WorkflowGroups), so it
// owns its own header, scroll area and palette — no host measurement needed.
export function PipelinesInstructionsPanel({ onClose }: { onClose: () => void }) {
  return (
    <aside className="flex w-[380px] shrink-0 flex-col overflow-hidden border-l border-[#cdd9ec] bg-white dark:border-[#26375f] dark:bg-[#0a142b]">
      <div className="flex items-center justify-between gap-2 bg-[#00215C] px-4 py-3 text-white">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-[#FFDB00]" />
          <span className="text-sm font-bold">Manual de instrucciones</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar manual"
          className="rounded p-1 text-white/80 transition-colors hover:bg-white/10 hover:text-white"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="flex-1 space-y-6 overflow-y-auto px-4 py-4 text-[12.5px] leading-relaxed text-[#3a4a63] dark:text-[#aebdd9]">
        {PIPELINES_INSTRUCTIONS.map((entry) => (
          <section key={entry.id} className="space-y-2">
            <h3 className="text-[15px] font-bold text-[#00215C] dark:text-[#dce8ff]">
              {entry.title}
            </h3>
            {entry.content}
          </section>
        ))}
      </div>
    </aside>
  );
}
