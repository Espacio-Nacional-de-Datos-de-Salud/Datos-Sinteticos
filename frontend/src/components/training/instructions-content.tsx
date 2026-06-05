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
import { ChevronDown, ChevronUp, Brain, Info, Lock, ExternalLink } from "lucide-react";
import type { InstructionsEntry } from "@/components/layout/instructions-panel";

// ── Brand palette ───────────────────────────────────────────────────────────
const NAVY = "#00215C";
const SKY = "#c9d4ea";
const INK = "#2b3a52";

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

const svgBase = {
  preserveAspectRatio: "xMidYMid meet" as const,
  fontFamily: "inherit",
};

// Horizontal numbered stepper: numbered nodes on a connecting track, with a
// short label beneath each. Used for the Resumen overview at the top of the
// panel.
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
        ["Selección", "de carga de datos"],
        ["Configuración", "del modelo"],
        ["Ejecución", "del entrenamiento"],
        ["Revisión", "del modelo"],
      ]}
    />
  );
}

// ── Mostly AI Model & Architecture Information (Collapsible) ───────────────
function MostlyAiModelInfo() {
  const [expanded, setExpanded] = useState(false);

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
        onClick={() => setExpanded(!expanded)}
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
export const ENTRENAMIENTO_INSTRUCTIONS: readonly InstructionsEntry[] = [
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
          Elige la carga de datos a partir de la cual entrenar, ajusta los
          parámetros del modelo y lanza el entrenamiento. Sigue estos pasos:
        </Lead>
        <StepTable
          steps={[
            {
              name: "Revisar reglas de preprocesamiento",
              desc: "Las reglas definidas en la carga de datos se aplican automáticamente al entrenamiento. Confirma que son las que esperas antes de continuar.",
            },
            {
              name: "Seleccionar la carga de datos",
              desc: "Elige una carga de datos completada del desplegable. El modelo aprenderá los patrones de las tablas que esa carga de datos detectó.",
            },
            {
              name: "Configurar el modelo",
              desc: "Ajusta los parámetros del entrenamiento (épocas, tamaño de batch, etc.). Los valores por defecto son razonables para empezar.",
            },
            {
              name: "Iniciar entrenamiento",
              desc: "Lanza el proceso. El sistema generará el modelo entrenado.",
            },
          ]}
        />
        <Subtitle>Reglas de preprocesamiento</Subtitle>
        <p>
          Provienen del paso de <span className="font-semibold">Carga de Datos</span>:
          son restricciones de dominio (rangos válidos, formatos, dependencias
          entre columnas, etc.) que el modelo respetará al aprender. Si
          necesitas cambiarlas, vuelve a la pantalla de Carga de Datos.
        </p>
        <Subtitle>Configuración del modelo</Subtitle>
        <p>
          Abre el panel de configuración para ajustar los parámetros que
          controlan el entrenamiento. Los más relevantes:
        </p>
        <OptionList
          items={[
            {
              name: "Épocas (epochs)",
              desc: "Número de pasadas completas sobre los datos. Más épocas suelen mejorar la fidelidad, pero alargan el tiempo de entrenamiento y pueden sobreajustar.",
            },
            {
              name: "Tamaño de batch",
              desc: "Cuántas filas procesa el modelo en cada paso. Batches grandes son más rápidos por época pero requieren más memoria.",
            },
            {
              name: "Tasa de aprendizaje",
              desc: "Cuánto se ajusta el modelo en cada paso. Valores muy altos pueden hacer que no converja; muy bajos, que tarde demasiado.",
            },
            {
              name: "Privacidad diferencial",
              desc: "Añade ruido controlado durante el entrenamiento para reforzar la privacidad. Reduce ligeramente la fidelidad a cambio de garantías formales.",
            },
          ]}
        />
        <MostlyAiModelInfo />
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
          en esta sesión): la fase actual, las tablas implicadas, el número de
          filas y la precisión final cuando termina.
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
        <Example>
          Una <span className="font-semibold">precisión</span> alta indica que
          las distribuciones marginales y las correlaciones del modelo se
          aproximan a las del dataset original. Una precisión baja sugiere
          revisar los tipos de codificación detectados en la carga de datos o
          aumentar el número de épocas.
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
          Catálogo completo de modelos disponibles en el servidor. Permite
          retomar modelos pasados sin tener que reentrenarlos.
        </Lead>
        <OptionList
          items={[
            {
              name: "Seleccionar",
              desc: "Carga un modelo del catálogo como entrenamiento actual; sus métricas e informe vuelven a aparecer arriba.",
            },
            {
              name: "Renombrar",
              desc: "Asigna un nombre funcional para identificar el modelo más fácilmente.",
            },
            {
              name: "Descargar",
              desc: "Exporta el modelo generador o la carpeta completa con todos sus artefactos.",
            },

            {
              name: "Cancelar",
              desc: "Detiene un entrenamiento en curso desde el propio catálogo.",
            },
            {
              name: "Eliminar",
              desc: "Borra el modelo y sus artefactos. La acción no se puede deshacer.",
            },
            {
              name: "Limpiar",
              desc: "Borra carpetas vacías y ejecuciones huérfanas — útil tras varias cancelaciones.",
            },
            {
              name: "Purgar",
              desc: "Elimina TODOS los modelos. Úsalo con cuidado.",
            },
          ]}
        />
      </>
    ),
  },
];
