"""Single source of truth for all editable config field schemas.

Both the CLI (config_editor.py) and the REST API (/configs/schemas) derive
their UI from this module — the frontend fetches the JSON-serialised version
so it never has to duplicate field names, types, or option lists.

Data model mirrors the TypeScript counterpart in
    frontend/src/components/config/schemas.ts
which is expected to consume data from GET /configs/schemas rather than
maintaining its own hardcoded constants.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

# ── primitive building blocks ─────────────────────────────────────────────────


@dataclass
class FieldOption:
    value: str
    label: str


@dataclass
class GroupToggle:
    path: str
    label: str
    help: str
    defaults: dict[str, Any]


@dataclass
class FieldSchema:
    path: str
    label: str
    kind: str  # "text" | "number" | "boolean" | "select" | "checklist" | "json"
    help: str = ""
    options: list[FieldOption] = field(default_factory=list)
    nullable: bool = False
    dynamic_options: str | None = None  # e.g. "columns" – resolved at render time


@dataclass
class FieldGroup:
    title: str
    fields: list[FieldSchema]
    description: str = ""
    toggle: GroupToggle | None = None


@dataclass
class ConfigSchema:
    title: str
    description: str
    groups: list[FieldGroup]


# ── helpers ───────────────────────────────────────────────────────────────────


def _opt(value: str, label: str) -> FieldOption:
    return FieldOption(value=value, label=label)


# Schema field names that need snake_case → camelCase for the frontend.
# We rename selectively (not a blanket camelize) because GroupToggle.defaults
# carries user YAML keys that must stay snake_case.
_API_KEY_RENAMES = {"dynamic_options": "dynamicOptions"}


def _rename_api_keys(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {_API_KEY_RENAMES.get(k, k): _rename_api_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_rename_api_keys(v) for v in obj]
    return obj


def to_dict(schema: ConfigSchema) -> dict:
    """Recursively convert a ConfigSchema to a JSON-serialisable dict.

    Renames ``dynamic_options`` → ``dynamicOptions`` so the payload matches
    the TypeScript ``FieldSchema`` type in
    ``frontend/src/components/config/schemas.ts``.
    """
    return _rename_api_keys(asdict(schema))


# ── general.yaml ─────────────────────────────────────────────────────────────

GENERAL_SCHEMA = ConfigSchema(
    title="Configuración general",
    description="Ajustes globales que afectan a todas las ejecuciones del pipeline.",
    groups=[
        FieldGroup(
            title="Ajustes",
            fields=[
                FieldSchema(
                    path="settings.enable_data_profiling",
                    label="Generar informes de profiling",
                    kind="boolean",
                    help="Si está activado, cada inspección produce un informe ydata-profiling por tabla.",
                ),
                FieldSchema(
                    path="settings.default_csv_delimiter",
                    label="Delimitador CSV por defecto",
                    kind="select",
                    help="Carácter usado para separar columnas al leer CSVs sin delimitador detectable.",
                    options=[
                        _opt(",", "coma (,)"),
                        _opt(";", "punto y coma (;)"),
                        _opt("\t", "tabulador (\\t)"),
                        _opt("|", "barra vertical (|)"),
                    ],
                ),
                FieldSchema(
                    path="settings.default_sample_size",
                    label="Tamaño de muestra por defecto",
                    kind="number",
                    help="Número de filas usadas cuando no se especifica explícitamente.",
                ),
                FieldSchema(
                    path="settings.synthetic_data_file_format",
                    label="Formato de archivo del dataset sintético",
                    kind="select",
                    help="Controla la extensión con la que se guardan las tablas sintéticas.",
                    options=[
                        _opt("csv", "CSV"),
                        _opt("parquet", "Parquet"),
                    ],
                ),
                FieldSchema(
                    path="settings.data_subpath",
                    label="Subcarpeta de datos",
                    kind="text",
                    help='Subcarpeta dentro de "data/" para resolver DEFAULT_DATA_PATH. Vacío = raíz.',
                ),
            ],
        ),
        FieldGroup(
            title="Ejecución por defecto",
            description="Parámetros usados cuando la CLI se invoca sin argumentos.",
            fields=[
                FieldSchema(
                    path="execution.mode",
                    label="Modo",
                    kind="select",
                    help="Fase del pipeline a ejecutar cuando se llama a la CLI sin argumentos.",
                    options=[
                        _opt("i", "Inspeccionar (i)"),
                        _opt("t", "Entrenar (t)"),
                        _opt("s", "Simular (s)"),
                        _opt("e", "Evaluar (e)"),
                    ],
                ),
                FieldSchema(
                    path="execution.sample_size",
                    label="Tamaño de muestra",
                    kind="number",
                    nullable=True,
                    help="Filas a generar en simulación cuando no se pasa por línea de comandos. Vacío = valor por defecto.",
                ),
                FieldSchema(
                    path="execution.model_id",
                    label="ID de modelo",
                    kind="text",
                    nullable=True,
                    help="Identificador del modelo entrenado a usar en simulación/evaluación. Vacío = el más reciente.",
                ),
            ],
        ),
    ],
)


# ── mostly_ai.yaml ────────────────────────────────────────────────────────────

MOSTLY_AI_SCHEMA = ConfigSchema(
    title="Configuración del modelo",
    description="Parámetros del modelo y del entrenamiento. Aplican tanto al entrenamiento como a la generación.",
    groups=[
        FieldGroup(
            title="Entrenamiento",
            description="Limita tamaño/tiempo del entrenamiento. Vacío = sin límite.",
            fields=[
                FieldSchema(
                    path="model_settings.max_epochs",
                    label="Épocas máximas",
                    kind="number",
                    help="Número máximo de pasadas completas sobre los datos durante el entrenamiento.",
                ),
                FieldSchema(
                    path="model_settings.batch_size",
                    label="Tamaño de batch",
                    kind="number",
                    help="Filas por lote en cada paso de entrenamiento. Valores mayores aceleran pero requieren más memoria.",
                ),
                FieldSchema(
                    path="model_settings.max_training_time",
                    label="Tiempo máximo (min)",
                    kind="number",
                    nullable=True,
                    help="Detiene el entrenamiento al alcanzar este tiempo.",
                ),
                FieldSchema(
                    path="model_settings.max_sample_size",
                    label="Tamaño máximo de muestra",
                    kind="number",
                    nullable=True,
                    help="Filas máximas usadas para entrenar.",
                ),
                FieldSchema(
                    path="model_settings.enable_model_report",
                    label="Generar informe del modelo",
                    kind="boolean",
                    help="Si está activado, Mostly AI produce un informe HTML con métricas del entrenamiento.",
                ),
                FieldSchema(
                    path="model_settings.model",
                    label="Tamaño del modelo",
                    kind="select",
                    help="Tamaño del modelo Mostly AI. Modelos mayores aprenden mejor a costa de tiempo y memoria.",
                    options=[
                        _opt("MOSTLY_AI/Small", "Pequeño (S)"),
                        _opt("MOSTLY_AI/Medium", "Mediano (M)"),
                        _opt("MOSTLY_AI/Large", "Grande (L)"),
                    ],
                ),
                FieldSchema(
                    path="model_settings.enable_flexible_generation",
                    label="Habilitar generación flexible",
                    kind="boolean",
                    help="Permite rebalanceo e imputación, pero puede reducir la precisión.",
                ),
            ],
        ),
        FieldGroup(
            title="Privacidad diferencial",
            description="Añade ruido durante el entrenamiento para acotar la información memorizada.",
            toggle=GroupToggle(
                path="model_settings.differential_privacy",
                label="Activar privacidad diferencial",
                help="Si está desactivada, el bloque se omite de la configuración.",
                defaults={
                    "max_epsilon": None,
                    "delta": 0.00001,
                    "noise_multiplier": 1.5,
                    "max_grad_norm": 1.0,
                    "value_protection_epsilon": 1.0,
                },
            ),
            fields=[
                FieldSchema(
                    path="model_settings.differential_privacy.max_epsilon",
                    label="Epsilon máximo",
                    kind="number",
                    nullable=True,
                    help="Presupuesto de privacidad. Vacío = sin tope.",
                ),
                FieldSchema(
                    path="model_settings.differential_privacy.delta",
                    label="Delta",
                    kind="number",
                    help="Probabilidad de fallo del mecanismo DP. Valores típicos: 1e-5 o menores.",
                ),
                FieldSchema(
                    path="model_settings.differential_privacy.noise_multiplier",
                    label="Multiplicador de ruido",
                    kind="number",
                    help="Cantidad de ruido añadido a los gradientes. Más ruido = más privacidad, menor utilidad.",
                ),
                FieldSchema(
                    path="model_settings.differential_privacy.max_grad_norm",
                    label="Norma máxima del gradiente",
                    kind="number",
                    help="Umbral para recortar gradientes antes de añadir ruido (clipping).",
                ),
                FieldSchema(
                    path="model_settings.differential_privacy.value_protection_epsilon",
                    label="Epsilon de protección de valores",
                    kind="number",
                    help="Presupuesto de privacidad reservado a proteger valores raros del dominio.",
                ),
            ],
        ),
    ],
)


# ── evaluation.yaml ───────────────────────────────────────────────────────────

EVALUATION_SCHEMA = ConfigSchema(
    title="Configuración de evaluación",
    description="Métricas agrupadas por eje: privacidad, fidelidad y utilidad.",
    groups=[
        FieldGroup(
            title="Ajustes generales",
            fields=[
                FieldSchema(
                    path="execution.drop_id_columns_from_metrics",
                    label="Excluir columnas ID en métricas",
                    kind="boolean",
                    help="Detecta y descarta claves primarias / foráneas al calcular métricas.",
                ),
            ],
        ),
        FieldGroup(
            title="Privacidad",
            description="¿Los datos sintéticos protegen frente a re-identificación e inferencia?",
            fields=[
                FieldSchema(
                    path="metrics.default.privacy",
                    label="k-anonimato y derivados",
                    kind="checklist",
                    help="Métricas de anonimato y ataques de inferencia de membresía. L-diversity requiere columnas sensibles y subconjuntos QI explícitos.",
                    options=[
                        _opt("k-anonymization", "k-anonymization"),
                        _opt("distinct l-diversity", "distinct l-diversity"),
                        _opt(
                            "DomiasMIA_BNAF", "DomiasMIA_BNAF (Membership inference — muy pesado)"
                        ),
                    ],
                ),
                FieldSchema(
                    path="metrics.default.custom",
                    label="Distancia a registros reales",
                    kind="checklist",
                    help="DCR y NNDR: miden cuán cerca quedan las filas sintéticas de filas reales.",
                    options=[
                        _opt("dcr", "DCR (Distance to Closest Record)"),
                        _opt("nndr", "NNDR (Nearest Neighbor Distance Ratio)"),
                    ],
                ),
                FieldSchema(
                    path="metrics.default.sanity",
                    label="Filas exactas (EMR)",
                    kind="checklist",
                    help="Proporción de filas sintéticas idénticas a alguna fila real. Debe ser 0.",
                    options=[
                        _opt("common_rows_proportion", "Common Rows Proportion"),
                        _opt("exact_match_rows", "Exact Match Rows (detallado)"),
                    ],
                ),
                FieldSchema(
                    path="metrics.default.detection",
                    label="Detectabilidad",
                    kind="checklist",
                    help="Clasificador que intenta distinguir filas reales de sintéticas. Cerca de 0.5 = indistinguibles.",
                    options=[_opt("detection_mlp", "Detection MLP")],
                ),
                FieldSchema(
                    path="metrics.sensitive_columns",
                    label="Columnas sensibles",
                    kind="checklist",
                    nullable=True,
                    dynamic_options="columns",
                    help="Columnas a proteger (usadas en l-diversity).",
                ),
                FieldSchema(
                    path="metrics.quasi_identifier_subsets",
                    label="Subconjuntos de quasi-identificadores",
                    kind="json",
                    nullable=True,
                    help="Grupos de columnas QI usados por k-anonimato y l-diversity. L-diversity se omite si no hay grupos explícitos.",
                ),
            ],
        ),
        FieldGroup(
            title="Fidelidad",
            description="¿Las distribuciones y correlaciones sintéticas se parecen a las reales?",
            fields=[
                FieldSchema(
                    path="metrics.default.stats",
                    label="Distancias entre distribuciones",
                    kind="checklist",
                    help="Comparan distribuciones marginales reales vs sintéticas.",
                    options=[
                        _opt("jensenshannon_dist", "Jensen-Shannon Distance"),
                        _opt("inv_kl_divergence", "Inverse KL Divergence"),
                    ],
                ),
                FieldSchema(
                    path="metrics.default.custom",
                    label="Correlaciones e intervalos",
                    kind="checklist",
                    help="Preservación de correlaciones y de intervalos de confianza de estadísticos clave.",
                    options=[
                        _opt("correlation_matrix_distance", "Correlation Matrix Distance"),
                        _opt("confidence_interval_overlap", "Confidence Interval Overlap"),
                        _opt(
                            "distribution_comparison_report",
                            "Distribution Comparison (1-TVD uni/bi/tri)",
                        ),
                    ],
                ),
                FieldSchema(
                    path="metrics.confidence_interval_level",
                    label="Nivel de confianza",
                    kind="number",
                    help="Por ejemplo 0.95 para intervalos al 95%.",
                ),
                FieldSchema(
                    path="metrics.num_bootstrap_samples",
                    label="Muestras de bootstrap",
                    kind="number",
                    help="Número de remuestreos usados para estimar intervalos de confianza.",
                ),
                FieldSchema(
                    path="metrics.tvd_n_bins",
                    label="Bins (TVD)",
                    kind="number",
                    help="Número de bins para discretizar variables continuas al calcular Total Variation Distance.",
                ),
                FieldSchema(
                    path="statistics",
                    label="Estadísticos de columna",
                    kind="json",
                    help="Lista de objetos con: operation, table, col. Ej: mean, median, mode.",
                ),
            ],
        ),
        FieldGroup(
            title="Utilidad",
            description="¿Sirven los datos sintéticos para entrenar modelos predictivos?",
            fields=[
                FieldSchema(
                    path="metrics.default.performance",
                    label="Modelos ML (TSTR)",
                    kind="checklist",
                    help="Modelos entrenados con sintéticos y evaluados en reales para medir utilidad predictiva.",
                    options=[
                        _opt("linear_model", "Linear Model"),
                        _opt("mlp", "MLP"),
                    ],
                ),
                FieldSchema(
                    path="metrics.tstr.target_column",
                    label="Columna objetivo",
                    kind="select",
                    dynamic_options="columns",
                    help="Columna a predecir al entrenar con sintético y testear con real.",
                ),
                FieldSchema(
                    path="metrics.tstr.task_type",
                    label="Tipo de tarea",
                    kind="select",
                    help="Naturaleza del problema supervisado en TSTR.",
                    options=[
                        _opt("classification", "Clasificación"),
                        _opt("regression", "Regresión"),
                    ],
                ),
            ],
        ),
    ],
)


# ── public registry ───────────────────────────────────────────────────────────

CONFIG_SCHEMAS: dict[str, ConfigSchema] = {
    "general": GENERAL_SCHEMA,
    "mostly_ai": MOSTLY_AI_SCHEMA,
    "evaluation": EVALUATION_SCHEMA,
}

# Subset shown before each workflow in the CLI pre-execution review
PRE_EXECUTION_SCHEMAS: dict[str, list[str]] = {
    # mode → list of config_ids to offer review for
    "i": ["general"],
    "t": ["mostly_ai"],
    "s": ["mostly_ai", "general"],  # general for output format
    "e": ["evaluation"],
}
