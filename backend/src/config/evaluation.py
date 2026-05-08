"""Evaluation configuration.

Values come from ``backend/config/evaluation.yaml`` (gitignored; bootstrap it
with ``make config`` from ``evaluation.example.yaml``). Env-driven resolvers
(interpreter path, custom statistics module) remain in Python.
"""

import os

from backend.src.config.general import PROJECT_ROOT, ConfigFileMissingError, _load_config_yaml


def _resolve_eval_python_path() -> str | None:
    """Resolve the Python interpreter for evaluation execution.

    Order: ``EVAL_PYTHON_PATH`` env → ``<project_root>/.venv_eval/bin/python`` → None.
    """
    if explicit := os.environ.get("EVAL_PYTHON_PATH"):
        return explicit
    candidate = PROJECT_ROOT / ".venv_eval" / "bin" / "python"
    return str(candidate) if candidate.exists() else None


EVAL_PYTHON_PATH: str | None = _resolve_eval_python_path()

# CUSTOM STATISTICS module (env-driven; not yaml)
CUSTOM_STATISTICS_MODULE: str | None = os.environ.get(
    "CUSTOM_STATISTICS_MODULE", "backend.src.evaluation.custom_metrics.custom_statistics"
)

try:
    _EVAL = _load_config_yaml("evaluation.yaml")
except ConfigFileMissingError:
    _EVAL = {}
_METRICS = _EVAL.get("metrics", {})
_EXEC = _EVAL.get("execution", {})
_TSTR = _METRICS.get("tstr", {})

DROP_ID_COLUMNS_FROM_METRICS: bool = _EXEC.get("drop_id_columns_from_metrics", True)

EVAL_DEFAULT_METRICS: dict = _METRICS.get("default", {})
QUASI_IDENTIFIER_SUBSETS: dict[str, list[str]] | None = _METRICS.get("quasi_identifier_subsets")
SENSITIVE_COLUMNS: list[str] | None = _METRICS.get("sensitive_columns")

CONFIDENCE_INTERVAL_LEVEL: float = _METRICS.get("confidence_interval_level", 0.95)
NUM_BOOTSTRAP_SAMPLES: int = _METRICS.get("num_bootstrap_samples", 10000)
AVERAGE_COMPLEMENTARY_TVD_N_BINS: int = _METRICS.get("average_complementary_tvd_n_bins", 10)

TSTR_TARGET_COLUMN: str = _TSTR.get("target_column", "expire_flag")
TSTR_TASK_TYPE: str = _TSTR.get("task_type", "classification")

STATISTICS: list[dict] = _EVAL.get("statistics", [])
