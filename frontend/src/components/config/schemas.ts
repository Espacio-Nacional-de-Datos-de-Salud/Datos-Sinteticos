// Per-config field metadata. Drives <ConfigDrawer> form rendering.
//
// Adding a new config means adding an entry to CONFIG_SCHEMAS keyed by the
// backend config id (see _ID_ALIASES in backend/src/services/configs.py).

export type FieldKind = "boolean" | "number" | "text" | "select" | "list" | "json" | "checklist";

export type SelectOption = { value: string; label: string };

export type FieldSchema = {
  // Dotted path inside the parsed YAML, e.g. "settings.default_csv_delimiter".
  path: string;
  label: string;
  help?: string;
  kind: FieldKind;
  // Used only when kind === "select".
  options?: SelectOption[];
  // When set, options are populated dynamically from the current context (e.g. simulation).
  dynamicOptions?: "tables" | "columns";
  // When true, an empty string in the form maps to YAML null.
  nullable?: boolean;
};

// Optional on/off toggle for an entire group. When off, the whole `path`
// (typically a nested object key in the YAML) is removed from the draft;
// when on, it is inserted with `defaults`. Lets us model conditional blocks
// like `model_settings.differential_privacy` that should be absent unless
// explicitly enabled.
export type GroupToggle = {
  path: string;
  label: string;
  help?: string;
  defaults: Record<string, unknown>;
};

export type FieldGroup = {
  title: string;
  description?: string;
  fields: FieldSchema[];
  toggle?: GroupToggle;
};

export type ConfigSchema = {
  title: string;
  description: string;
  groups: FieldGroup[];
};

export const CONFIG_SCHEMAS: Record<string, ConfigSchema> = {
  mostly_ai: {
    title: "Configuración del modelo (Mostly AI)",
    description:
      "Parámetros del generador y del entrenamiento. Aplican tanto al entrenamiento como a la generación.",
    groups: [
      {
        title: "Generador",
        fields: [
          {
            path: "generator.name",
            label: "Nombre",
            help: "Prefijo usado al nombrar los modelos creados.",
            kind: "text",
          },
          {
            path: "generator.description",
            label: "Descripción",
            kind: "text",
          },
          {
            path: "generator.random_state",
            label: "Random state",
            help: "Semilla para reproducibilidad. Mismo valor → mismos resultados.",
            kind: "number",
          },
        ],
      },
      {
        title: "Entrenamiento",
        description:
          "Limita tamaño/tiempo del entrenamiento. Vacío = sin límite.",
        fields: [
          {
            path: "model_settings.max_epochs",
            label: "Épocas máximas",
            kind: "number",
          },
          {
            path: "model_settings.batch_size",
            label: "Tamaño de batch",
            kind: "number",
          },
          {
            path: "model_settings.max_training_time",
            label: "Tiempo máximo (min)",
            help: "Detiene el entrenamiento al alcanzar este tiempo.",
            kind: "number",
            nullable: true,
          },
          {
            path: "model_settings.max_sample_size",
            label: "Tamaño máximo de muestra",
            help: "Filas máximas usadas para entrenar.",
            kind: "number",
            nullable: true,
          },
          {
            path: "model_settings.enable_model_report",
            label: "Generar informe del modelo",
            kind: "boolean",
          },
          {
            path: "model_settings.model",
            label: "Tamaño del modelo",
            kind: "select",
            options: [
              { value: "MOSTLY_AI/Small", label: "Pequeño (S)" },
              { value: "MOSTLY_AI/Medium", label: "Mediano (M)" },
              { value: "MOSTLY_AI/Large", label: "Grande (L)" },
            ],
          },
          {
            path: "model_settings.enable_flexible_generation",
            label: "Habilitar generación flexible",
            help: "Permite rebalanceo e imputación, pero puede reducir la precisión en tablas anchas.",
            kind: "boolean",
          },
        ],
      },
      {
        title: "Privacidad diferencial",
        description:
          "Añade ruido durante el entrenamiento para acotar la información que el modelo memoriza de cada fila.",
        toggle: {
          path: "model_settings.differential_privacy",
          label: "Activar privacidad diferencial",
          help: "Si está desactivada, el bloque se omite de la configuración.",
          defaults: {
            max_epsilon: null,
            delta: 0.00001,
            noise_multiplier: 1.5,
            max_grad_norm: 1.0,
            value_protection_epsilon: 1.0,
          },
        },
        fields: [
          {
            path: "model_settings.differential_privacy.max_epsilon",
            label: "Epsilon máximo",
            help: "Presupuesto de privacidad. Vacío = sin tope.",
            kind: "number",
            nullable: true,
          },
          {
            path: "model_settings.differential_privacy.delta",
            label: "Delta",
            kind: "number",
          },
          {
            path: "model_settings.differential_privacy.noise_multiplier",
            label: "Multiplicador de ruido",
            kind: "number",
          },
          {
            path: "model_settings.differential_privacy.max_grad_norm",
            label: "Norma máxima del gradiente",
            kind: "number",
          },
          {
            path: "model_settings.differential_privacy.value_protection_epsilon",
            label: "Epsilon de protección de valores",
            kind: "number",
          },
        ],
      },
    ],
  },
  evaluation: {
    title: "Configuración de evaluación",
    description:
      "Parámetros de ejecución, métricas de utilidad (Synthcity), privacidad y estadísticos personalizados.",
    groups: [
      {
        title: "Ejecución",
        fields: [
          {
            path: "execution.drop_id_columns_from_metrics",
            label: "Excluir columnas ID en métricas",
            help: "Detecta y descarta claves primarias / foráneas al calcular métricas.",
            kind: "boolean",
          },
        ],
      },
      {
        title: "Métricas de Utilidad (Synthcity)",
        description: "Activa o desactiva las métricas por categoría.",
        fields: [
          {
            path: "metrics.default.sanity",
            label: "Sanity Checks",
            kind: "checklist",
            options: [
              { value: "common_rows_proportion", label: "Common Rows Proportion" },
            ],
          },
          {
            path: "metrics.default.stats",
            label: "Estadísticas",
            kind: "checklist",
            options: [
              { value: "jensenshannon_dist", label: "Jensen-Shannon Distance" },
              { value: "inv_kl_divergence", label: "Inverse KL Divergence" },
            ],
          },
          {
            path: "metrics.default.performance",
            label: "Rendimiento (ML)",
            kind: "checklist",
            options: [
              { value: "linear_model", label: "Linear Model" },
              { value: "mlp", label: "MLP" },
            ],
          },
          {
            path: "metrics.default.detection",
            label: "Detección",
            kind: "checklist",
            options: [
              { value: "detection_mlp", label: "Detection MLP" },
            ],
          },
          {
            path: "metrics.default.custom",
            label: "Personalizadas",
            kind: "checklist",
            options: [
              { value: "dcr", label: "DCR (Distance to Closest Record)" },
              { value: "nndr", label: "NNDR (Nearest Neighbor Distance Ratio)" },
              { value: "correlation_matrix_distance", label: "Correlation Matrix Distance" },
              { value: "confidence_interval_overlap", label: "Confidence Interval Overlap" },
              { value: "average_complementary_tvd", label: "Avg Complementary TVD" },
            ],
          },
        ],
      },
      {
        title: "Privacidad",
        description: "Métricas y parámetros de privacidad.",
        fields: [
          {
            path: "metrics.default.privacy",
            label: "Métricas de Privacidad",
            kind: "checklist",
            options: [
              { value: "k-anonymization", label: "k-anonymization" },
              { value: "distinct l-diversity", label: "distinct l-diversity" },
              { value: "DomiasMIA_BNAF", label: "DomiasMIA_BNAF" },
            ],
          },
          {
            path: "metrics.sensitive_columns",
            label: "Columnas Sensibles",
            help: "Columnas a proteger (usadas en l-diversity).",
            kind: "checklist",
            dynamicOptions: "columns",
            nullable: true,
          },
        ],
      },
      {
        title: "Parámetros estadísticos",
        fields: [
          {
            path: "metrics.confidence_interval_level",
            label: "Nivel de confianza",
            help: "Por ejemplo 0.95 para intervalos al 95%.",
            kind: "number",
          },
          {
            path: "metrics.num_bootstrap_samples",
            label: "Muestras de bootstrap",
            kind: "number",
          },
          {
            path: "metrics.average_complementary_tvd_n_bins",
            label: "Bins (TVD complementaria)",
            kind: "number",
          },
        ],
      },
      {
        title: "TSTR (Train Synthetic, Test Real)",
        description: "Predicción supervisada para evaluar utilidad.",
        fields: [
          {
            path: "metrics.tstr.target_column",
            label: "Columna objetivo",
            kind: "select",
            dynamicOptions: "columns",
          },
          {
            path: "metrics.tstr.task_type",
            label: "Tipo de tarea",
            kind: "select",
            options: [
              { value: "classification", label: "Clasificación" },
              { value: "regression", label: "Regresión" },
            ],
          },
        ],
      },
      {
        title: "Estadísticos de Columna",
        description: "Operaciones específicas por tabla/columna.",
        fields: [
          {
            path: "statistics",
            label: "Definición de estadísticos",
            help: "Lista de objetos con: operation, table, col. Ej: mean, median, mode, variance, quantile, age.",
            kind: "json",
          },
        ],
      },
      {
        title: "Subconjuntos de Quasi-identificadores",
        description: "Para el cálculo de k-anonimato.",
        fields: [
          {
            path: "metrics.quasi_identifier_subsets",
            label: "Subconjuntos",
            help: "Lista de listas de columnas. Si es nulo, usa todas las combinaciones pares.",
            kind: "json",
            nullable: true,
          },
        ],
      },
    ],
  },
  general: {
    title: "Configuración general",
    description:
      "Ajustes globales que afectan a todas las ejecuciones del pipeline.",
    groups: [
      {
        title: "Ajustes",
        fields: [
          {
            path: "settings.enable_data_profiling",
            label: "Generar informes de profiling",
            help: "Si está activado, cada inspección produce un informe ydata-profiling por tabla.",
            kind: "boolean",
          },
          {
            path: "settings.default_csv_delimiter",
            label: "Delimitador CSV por defecto",
            kind: "select",
            options: [
              { value: ",", label: "coma (,)" },
              { value: ";", label: "punto y coma (;)" },
              { value: "\t", label: "tabulador (\\t)" },
              { value: "|", label: "barra vertical (|)" },
            ],
          },
          {
            path: "settings.default_sample_size",
            label: "Tamaño de muestra por defecto",
            help: "Número de filas usadas cuando no se especifica explícitamente.",
            kind: "number",
          },
          {
            path: "settings.synthetic_data_file_format",
            label: "Formato de archivo del dataset sintético",
            help: "Controla la extensión con la que se guardan las tablas sintéticas para que evaluación las lea directamente.",
            kind: "select",
            options: [
              { value: "csv", label: "CSV" },
              { value: "parquet", label: "Parquet" },
            ],
          },
          {
            path: "settings.data_subpath",
            label: "Subcarpeta de datos",
            help: 'Subcarpeta dentro de "data/" para resolver DEFAULT_DATA_PATH. Vacío = raíz.',
            kind: "text",
          },
        ],
      },
      {
        title: "Ejecución por defecto",
        description:
          "Parámetros usados cuando la CLI del backend se invoca sin argumentos.",
        fields: [
          {
            path: "execution.mode",
            label: "Modo",
            kind: "select",
            options: [
              { value: "i", label: "Inspeccionar (i)" },
              { value: "t", label: "Entrenar (t)" },
              { value: "s", label: "Simular (s)" },
              { value: "e", label: "Evaluar (e)" },
            ],
          },
          {
            path: "execution.sample_size",
            label: "Tamaño de muestra",
            kind: "number",
            nullable: true,
          },
          {
            path: "execution.model_id",
            label: "ID de modelo",
            kind: "text",
            nullable: true,
          },
          {
            path: "execution.simulation_id",
            label: "ID de simulación",
            kind: "text",
            nullable: true,
          },
          {
            path: "execution.inspection_id",
            label: "ID de inspección",
            kind: "text",
            nullable: true,
          },
        ],
      },
    ],
  },
};
