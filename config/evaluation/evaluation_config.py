"""Evaluation configuration settings for the synthetic data project.

Centralizes all parameters and logic related to metrics, statistical evaluation,
and the execution environment for evaluation subprocesses.
"""

import os

from config.general_config import PROJECT_ROOT

# ============================================================================
# EVALUATION EXECUTION
# ============================================================================


def _resolve_eval_python_path() -> str | None:
    """Resolve the Python interpreter path for evaluation execution.

    Resolution order:
    1. ``EVAL_PYTHON_PATH`` environment variable.
    2. Conventional local path ``<project_root>/.venv_eval/bin/python``.
    3. ``None`` when no dedicated evaluation interpreter is available.

    Returns:
        str | None: Absolute interpreter path if found, otherwise ``None``.
    """
    if explicit := os.environ.get("EVAL_PYTHON_PATH"):
        return explicit
    candidate = PROJECT_ROOT / ".venv_eval" / "bin" / "python"
    return str(candidate) if candidate.exists() else None


EVAL_PYTHON_PATH: str | None = _resolve_eval_python_path()
DROP_ID_COLUMNS_FROM_METRICS = True  # if True detects and drops id columns and primary/foreign keys

# ============================================================================
# METRICS & STATISTICS
# ============================================================================

STATISTICS_CONFIG_PATH = os.path.join(PROJECT_ROOT, "config", "evaluation", "statistics.yaml")

EVAL_DEFAULT_METRICS = {
    "custom": [
        "dcr",
        "nndr",
        "correlation_matrix_distance",
        "confidence_interval_overlap",
        "average_complementary_tvd",
    ],
    "sanity": [
        "common_rows_proportion",
    ],
    "stats": [
        "jensenshannon_dist",
        "inv_kl_divergence",
    ],
    "performance": [
        "linear_model",
        "mlp",
    ],
    "detection": ["detection_mlp"],
    "privacy": [
        "k-anonymization",
        "distinct l-diversity",
        # "DomiasMIA_BNAF",  # Membership inference attack (MIA) - VERY HEAVY
    ],
}

# Defines subsets of quasi identifiers to use in k-anonymity evaluation metric
# If left undefined then metric will use all pairwise combinations
QUASI_IDENTIFIER_SUBSETS: dict[str, list[str]] | None = None
SENSITIVE_COLUMNS: list[str] | None = None

CONFIDENCE_INTERVAL_LEVEL = 0.95
TSTR_TARGET_COLUMN = "expire_flag"
TSTR_TASK_TYPE = "classification"
NUM_BOOTSTRAP_SAMPLES = 10000

# CUSTOM STATISTICS
CUSTOM_STATISTICS_MODULE: str | None = os.environ.get(
    "CUSTOM_STATISTICS_MODULE", "src.evaluation.custom_statistics"
)

# Metrics specifically configuration
AVERAGE_COMPLEMENTARY_TVD_N_BINS = 10
