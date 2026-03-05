"""
General configuration settings for the synthetic data project.

This file centralized all configuration values that are
shared across the entire project.
"""

import json
import logging
import os
from pathlib import Path

import pandas as pd

from src.core.preprocessing.logical_rules import (
    DateConsistencyRule,
    SemanticProportionalConsistencyRule,
    SemanticRankingConsistencyRule,
)

PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_DATA_PATH = os.path.join(PROJECT_ROOT, "data")

# Custom output directories
OUTPUTS_ROOT = os.path.join(PROJECT_ROOT, "outputs")
MODELS_FOLDER_PREFIX = "models"
MODEL_RUN_FOLDER_PREFIX = "model"
MODELS_DIR = os.path.join(OUTPUTS_ROOT, MODELS_FOLDER_PREFIX)
SIMULATIONS_FOLDER_PREFIX = "simulations"
SIMULATION_RUN_FOLDER_PREFIX = "simulation"
SIMULATIONS_DIR = os.path.join(OUTPUTS_ROOT, SIMULATIONS_FOLDER_PREFIX)

MOSTLYAI_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "mostly_ai_config.yaml")
RULES_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "rules.yaml")

# EVALUATION
# ============================================================================
EVAL_DEFAULT_METRICS = {
    "custom": [
        # custom metrics implemented ourselves
        "nearest_neighbor_distance_ratio",
        "correlation_matrix_distance",
        "confidence_interval_overlap",
    ],
    "sanity": [
        # "data_mismatch", # mismatched types, not included in doc
        "common_rows_proportion",  # exact match score (EMS) 0-1, 1= all leaked
        "nearest_syn_neighbor_distance",  # distance to closest record (DCR)
        # "close_values_probability"
    ],
    "stats": [
        "jensenshannon_dist",  # sqrt of Jensen-Shannon Divergence (JSD)
        "inv_kl_divergence",  # inverse KL divergence (proxy for distribution overlap)
    ],
    "performance": [
        "linear_model",  # TSTR with logistic/linear regression
        "mlp",  # TSTR with MLP
        #"xgb",  # TSTR with XGBoost
    ],
    "detection": ["detection_mlp"],  # synthetic vs real detection (AUC ~0.5 = good)
    "privacy": [
        "k-anonymization",  # in our report table at top of doc states k-map, while in text says k-anon
        #'k-map',
        "distinct l-diversity",
        #'identifiability_score',
        #"DomiasMIA_BNAF",  # Membership inference attack (MIA)
    ],
    # MISSING:
    # Nearest Neighbor Distance Ratio
    # Distancia de Matriz de Correlación (DMC)
    # Confidence interval Overlap (CIO)
}

TSTR_TARGET_COLUMN = "expire_flag"
TSTR_TASK_TYPE = "classification"  # or "regression"
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


RUN_TIMESTAMP = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")

RULE_MAP = {
    "date_consistency": DateConsistencyRule,
    "semantic_ranking_consistency": SemanticRankingConsistencyRule,
    "semantic_proportional_consistency": SemanticProportionalConsistencyRule,
}

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
