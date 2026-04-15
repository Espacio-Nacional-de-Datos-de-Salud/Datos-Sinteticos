"""
General configuration settings for the synthetic data project.

This file centralized all configuration values that are
shared across the entire project.
"""

import contextvars
import json
import logging
import os
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DATA_PATH = os.path.join(PROJECT_ROOT, "data")

# Custom output directories
OUTPUTS_ROOT = os.path.join(PROJECT_ROOT, "outputs")
MOSTLYAI_DIR = os.path.join(OUTPUTS_ROOT, "mostlyai")
MODELS_FOLDER_PREFIX = "models"
MODEL_RUN_FOLDER_PREFIX = "model"
MODELS_DIR = os.path.join(OUTPUTS_ROOT, MODELS_FOLDER_PREFIX)
SIMULATIONS_FOLDER_PREFIX = "simulations"
SIMULATION_RUN_FOLDER_PREFIX = "simulation"
SIMULATIONS_DIR = os.path.join(OUTPUTS_ROOT, SIMULATIONS_FOLDER_PREFIX)

PIPELINES_FOLDER_PREFIX = "pipelines"
PIPELINE_RUN_FOLDER_PREFIX = "pipeline"
PIPELINES_DIR = os.path.join(OUTPUTS_ROOT, PIPELINES_FOLDER_PREFIX)
NO_PIPELINE_ID = "none"

INSPECTIONS_FOLDER_PREFIX = "inspections"
INSPECTION_RUN_FOLDER_PREFIX = "inspection"
INSPECTIONS_DIR = os.path.join(OUTPUTS_ROOT, INSPECTIONS_FOLDER_PREFIX)
INSPECTION_CARD_FILENAME = "inspection_card.json"
AUTODETECT_FILENAME = "autodetect.json"
PROCESSED_DATA_DIRNAME = "processed_data"

MOSTLYAI_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "mostly_ai_config.yaml")
RULES_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "rules.yaml")
STATISTICS_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "evaluation", "statistics.yaml")

MOSTLY_LOCAL_PORT = 8082


# ============================================================================
# DEFAULT VALUES
# ============================================================================
# Default sample size for synthetic data generation
DEFAULT_SAMPLE_SIZE = 1000

SUPPORTED_FILE_FORMATS = (".csv", ".parquet", ".xls", ".xlsx")

METADATA_FILENAME = "metadata.json"
PROFILING_REPORT_PATTERN = "{name}_profiling_report.html"
GENERATOR_ZIP_NAME = "generator.zip"

# Tracking card and log filenames
MODEL_CARD_FILENAME = "model_card.json"
SIM_CARD_FILENAME = "sim_card.json"
SESSION_LOG_FILENAME = "session.log"
SIM_CONFIG_FILENAME = "sim_config.json"

# SageMaker detection: the resource-metadata file is only present inside a Studio environment.
_SAGEMAKER_METADATA_PATH = "/opt/ml/metadata/resource-metadata.json"
IS_SAGEMAKER = "SAGEMAKER_INTERNAL_IMAGE_URI" in os.environ

if IS_SAGEMAKER:
    with open(_SAGEMAKER_METADATA_PATH, encoding="utf-8") as _f:
        _sm_metadata = json.load(_f)

    USERPROFILENAME: str = _sm_metadata.get("UserProfileName", "")
    MLFLOW_TRACKING_URI = "arn:aws:sagemaker:eu-west-1:651068895157:mlflow-app/app-WOVA56CVVLL2"
else:
    USERPROFILENAME = "local"
    MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", str(PROJECT_ROOT / "mlruns"))

MLFLOW_EXPERIMENT_TRAINING = "SyntheticData-Training"
MLFLOW_EXPERIMENT_SIMULATION = "SyntheticData-Simulation"


_RUN_TIMESTAMP: contextvars.ContextVar[str] = contextvars.ContextVar(
    "RUN_TIMESTAMP", default=pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
)


def get_run_timestamp() -> str:
    """Get the ``RUN_TIMESTAMP`` for the current execution context.

    Returns:
        str: Timestamp string.
    """
    return _RUN_TIMESTAMP.get()


def refresh_run_timestamp() -> str:
    """Refresh ``RUN_TIMESTAMP`` to the current time for this context and return it.

    Returns:
        str: Updated timestamp with ``%Y%m%d_%H%M%S`` format.
    """
    new_ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    _RUN_TIMESTAMP.set(new_ts)
    return new_ts


# ============================================================================
# SETTINGS
# ============================================================================
ENABLE_DATA_PROFILING = False
DEFAULT_CSV_DELIMITER = ","

# ============================================================================
# LOGGING
# ============================================================================
LOG_LEVEL = logging.DEBUG
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
