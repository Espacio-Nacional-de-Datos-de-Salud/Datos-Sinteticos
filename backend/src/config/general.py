"""General configuration: paths, runtime state, and yaml-backed settings.

Tunable values live in ``backend/config/<name>.yaml`` (gitignored). Committed
templates live alongside as ``backend/config/<name>.example.yaml`` — users
bootstrap their real files by running ``make config``, which copies every
``*.example.yaml`` to ``*.yaml``. Constants that are not user-tunable (paths,
filenames, SageMaker wiring, logging format) are defined directly in this
module.
"""

import contextvars
import json
import logging
import os
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

CONFIG_DIR = PROJECT_ROOT / "backend" / "config"


class ConfigFileMissingError(FileNotFoundError):
    """Raised when a required ``*.yaml`` file has not been created yet."""


def _load_config_yaml(relative_path: str) -> dict:
    """Load ``backend/config/<relative_path>``.

    The real file is the sole source of truth. If it is missing but a
    committed ``*.example.yaml`` template exists, raise a clear error telling
    the user to run ``make config``.
    """
    real_path = CONFIG_DIR / relative_path
    if real_path.is_file():
        with open(real_path, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    example_path = real_path.with_name(real_path.stem + ".example" + real_path.suffix)
    if example_path.is_file():
        raise ConfigFileMissingError(
            f"Config file missing: {real_path}. "
            f"Run `make config` to create it from {example_path.name}, "
            f"then edit {real_path.name} (not the .example template)."
        )
    raise ConfigFileMissingError(
        f"Config file missing: {real_path} (no template found at {example_path})."
    )


# ============================================================================
# OUTPUT DIRECTORIES AND FILENAMES
# ============================================================================
OUTPUTS_ROOT = os.path.join(PROJECT_ROOT, "backend", "outputs")
MOSTLYAI_DIR = os.path.join(OUTPUTS_ROOT, "mostlyai")
MODELS_FOLDER_PREFIX = "models"
MODEL_RUN_FOLDER_PREFIX = "model"
MODELS_DIR = os.path.join(OUTPUTS_ROOT, MODELS_FOLDER_PREFIX)
SIMULATIONS_FOLDER_PREFIX = "simulations"
SIMULATION_RUN_FOLDER_PREFIX = "simulation"
SIMULATIONS_DIR = os.path.join(OUTPUTS_ROOT, SIMULATIONS_FOLDER_PREFIX)
EVALUATIONS_FOLDER_PREFIX = "evaluations"
EVALUATION_RUN_FOLDER_PREFIX = "evaluation"
EVALUATIONS_DIR = os.path.join(OUTPUTS_ROOT, EVALUATIONS_FOLDER_PREFIX)

PIPELINES_FOLDER_PREFIX = "pipelines"
PIPELINE_RUN_FOLDER_PREFIX = "pipeline"
PIPELINES_DIR = os.path.join(OUTPUTS_ROOT, PIPELINES_FOLDER_PREFIX)
PIPELINE_CARD_FILENAME = "pipeline_card.json"
NO_PIPELINE_ID = "none"

INSPECTIONS_FOLDER_PREFIX = "inspections"
INSPECTION_RUN_FOLDER_PREFIX = "upload"
INSPECTIONS_DIR = os.path.join(OUTPUTS_ROOT, INSPECTIONS_FOLDER_PREFIX)
INSPECTION_CARD_FILENAME = "inspection_card.json"
INSPECTION_METADATA_FILENAME = "inspection_metadata.json"
AUTODETECTED_INSPECTION_METADATA_FILENAME = "autodetected_inspection_metadata.json"
PROCESSED_DATA_DIRNAME = "processed_data"
PROFILING_REPORTS_DIRNAME = "profiling_reports"

# Business-rules configurations: each run materialises an inspection's
# preprocessed data after applying the rules' PRE phase, so the user can
# preview / profile the dataset the model will see before training.
BRC_FOLDER_PREFIX = "brc"
BRC_RUN_FOLDER_PREFIX = "brc"
BRC_DIR = os.path.join(OUTPUTS_ROOT, BRC_FOLDER_PREFIX)
BRC_CARD_FILENAME = "brc_card.json"

# Rule library (presets): user-saved snapshots of rules.yaml kept for reuse,
# independent of any run. Each preset is its own folder holding the rules YAML
# plus a small descriptor card. Lives under OUTPUTS_ROOT (user data) rather than
# backend/config/ so `make clean-config` never wipes it and so it isn't gated by
# the *.example.yaml template requirement of the configs API.
RULES_LIBRARY_FOLDER_PREFIX = "rules_library"
RULES_PRESET_FOLDER_PREFIX = "preset"
RULES_LIBRARY_DIR = os.path.join(OUTPUTS_ROOT, RULES_LIBRARY_FOLDER_PREFIX)
RULES_PRESET_CARD_FILENAME = "preset_card.json"
RULES_PRESET_RULES_FILENAME = "rules.yaml"

MOSTLY_LOCAL_PORT = 8082
MOSTLY_LOCAL_TIMEOUT_SECONDS = float(os.getenv("MOSTLY_LOCAL_TIMEOUT", "1800"))

SUPPORTED_FILE_FORMATS = (".csv", ".parquet", ".xls", ".xlsx")

METADATA_FILENAME = "metadata.json"
PROFILING_REPORT_PATTERN = "{name}_profiling_report.html"
TIME_PROFILING_REPORT_FILENAME = "time_profiling_report.json"
GENERATOR_ZIP_NAME = "generator.zip"

MODEL_CARD_FILENAME = "model_card.json"
SIM_CARD_FILENAME = "sim_card.json"
EVAL_CARD_FILENAME = "eval_card.json"
SESSION_LOG_FILENAME = "session.log"
SIM_CONFIG_FILENAME = "sim_config.json"

# ============================================================================
# SAGEMAKER
# ============================================================================
_SAGEMAKER_METADATA_PATH = "/opt/ml/metadata/resource-metadata.json"
IS_SAGEMAKER = "SAGEMAKER_INTERNAL_IMAGE_URI" in os.environ

if IS_SAGEMAKER:
    with open(_SAGEMAKER_METADATA_PATH, encoding="utf-8") as _f:
        _sm_metadata = json.load(_f)

    USERPROFILENAME: str = _sm_metadata.get("UserProfileName", "")
else:
    USERPROFILENAME = "local"


_RUN_TIMESTAMP: contextvars.ContextVar[str] = contextvars.ContextVar(
    "RUN_TIMESTAMP", default=pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
)


def get_run_timestamp() -> str:
    """Get the ``RUN_TIMESTAMP`` for the current execution context."""
    return _RUN_TIMESTAMP.get()


def refresh_run_timestamp() -> str:
    """Refresh ``RUN_TIMESTAMP`` for this context and return it."""
    new_ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    _RUN_TIMESTAMP.set(new_ts)
    return new_ts


# ============================================================================
# YAML-BACKED SETTINGS
# ============================================================================
try:
    _GENERAL = _load_config_yaml("general.yaml")
except ConfigFileMissingError:
    _GENERAL = {}
_SETTINGS = _GENERAL.get("settings", {})

SYNTHETIC_DATA_FILE_FORMATS: tuple[str, ...] = ("csv", "parquet")


def normalize_table_name_list(value: object) -> tuple[str, ...]:
    """Normalize a table-name setting into a tuple of non-empty strings."""
    if value is None:
        return ()
    if isinstance(value, str):
        raw_values = [value]
    elif isinstance(value, (list, tuple, set)):
        raw_values = value
    else:
        return ()
    return tuple(str(item).strip() for item in raw_values if str(item).strip())


def normalize_synthetic_data_file_format(value: object) -> str:
    """Normalize the configured synthetic-data file format."""
    normalized = str(value or "csv").strip().lower()
    if normalized in {"", "none"}:
        return "csv"
    if normalized in SYNTHETIC_DATA_FILE_FORMATS:
        return normalized
    return "csv"


def synthetic_data_file_extension(file_format: str) -> str:
    """Return the file extension used for generated synthetic tables."""
    normalized = normalize_synthetic_data_file_format(file_format)
    return ".parquet" if normalized == "parquet" else ".csv"


ENABLE_DATA_PROFILING: bool = _SETTINGS.get("enable_data_profiling", True)
DEFAULT_CSV_DELIMITER: str = _SETTINGS.get("default_csv_delimiter", ",")
DEFAULT_SAMPLE_SIZE: int = _SETTINGS.get("default_sample_size", 1000)
SKIP_DATA_CLEANING_TABLES: tuple[str, ...] = normalize_table_name_list(
    _SETTINGS.get("skip_data_cleaning_tables")
)
SYNTHETIC_DATA_FILE_FORMAT: str = normalize_synthetic_data_file_format(
    _SETTINGS.get("synthetic_data_file_format", "csv")
)

UPLOAD_SIZE_LIMIT_GB: int = 1
UPLOAD_SIZE_LIMIT_BYTES: int = UPLOAD_SIZE_LIMIT_GB * 1024**3

# ``data_subpath`` is appended to ``<project_root>/data`` to produce
# ``DEFAULT_DATA_PATH``. Set it in ``general.yaml`` to keep your project data
# in a subfolder (e.g. ``"whatever/"`` → ``<project_root>/data/whatever``).
_DATA_SUBPATH: str = _SETTINGS.get("data_subpath", "") or ""
DEFAULT_DATA_PATH = os.path.join(PROJECT_ROOT, "data", _DATA_SUBPATH)

# Execution section is read by ``backend.src.config.execution`` — exposed here
# for callers that want the raw dict.
_EXECUTION: dict = _GENERAL.get("execution", {})

# ============================================================================
# LOGGING
# ============================================================================
LOG_LEVEL = logging.DEBUG
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# Process-wide rolling backend log (see ``logging_config.setup_global_file_log``).
# Lives under outputs/ (gitignored). Named ``runtime_logs`` rather than a generic
# ``logs`` so it's unambiguous this holds the backend process trail, not other
# kinds of logs. Size-based rotation: oldest backup is dropped automatically once
# the cap is hit, so the footprint is bounded (~MAX_BYTES * (BACKUP_COUNT + 1)).
GLOBAL_LOG_DIR = os.path.join(OUTPUTS_ROOT, "runtime_logs")
GLOBAL_LOG_FILENAME = "backend.log"
GLOBAL_LOG_MAX_BYTES = 10 * 1024 * 1024  # 10 MB per file
GLOBAL_LOG_BACKUP_COUNT = 10  # keep ~110 MB total before rotating out
