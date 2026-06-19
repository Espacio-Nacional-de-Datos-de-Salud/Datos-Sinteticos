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

try:
    _EVAL = _load_config_yaml("evaluation.yaml")
except ConfigFileMissingError:
    _EVAL = {}
_METRICS = _EVAL.get("metrics", {})
_EXEC = _EVAL.get("execution", {})
_TSTR = _METRICS.get("tstr", {})

DROP_ID_COLUMNS_FROM_METRICS: bool = _EXEC.get("drop_id_columns_from_metrics", True)
MAX_ROWS_PER_TABLE_FOR_EXPENSIVE_METRICS: int | None = _EXEC.get(
    "max_rows_per_table_for_expensive_metrics"
)
EXPENSIVE_METRICS_RANDOM_STATE: int = _EXEC.get("expensive_metrics_random_state", 1)

EVAL_DEFAULT_METRICS: dict = _METRICS.get("default", {})
QUASI_IDENTIFIER_SUBSETS: dict[str, list[str]] | None = _METRICS.get("quasi_identifier_subsets")
SENSITIVE_COLUMNS: list[str] | None = _METRICS.get("sensitive_columns")

TVD_N_BINS: int = _METRICS.get("tvd_n_bins", 10)

TSTR_TARGET_COLUMN: str = _TSTR.get("target_column", "expire_flag")
TSTR_TASK_TYPE: str = _TSTR.get("task_type", "classification")

UTILITY_TESTS_CONFIG: dict = _METRICS.get("utility_tests", {})

# When True, ExactMatchRows includes the actual matching (real) rows in its
# report so they can be displayed; off by default since those are verbatim
# real-data records.
EXACT_MATCH_SHOW_FILTERED_ROWS: bool = bool(
    _METRICS.get("exact_match", {}).get("show_filtered_rows", False)
)
