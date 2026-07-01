"""Resolved per-table evaluation settings.

The evaluation is single-table: each evaluated table is assessed independently
with its own config. The frontend sends, per table, a full evaluation-config
object (same shape as ``evaluation.yaml``) seeded from the global config and
then tweaked. ``build_table_settings`` parses that object the same way
``config.evaluation`` parses the global YAML, falling back to the global default
for any key the per-table config omits.
"""

from __future__ import annotations

from dataclasses import dataclass

from backend.src.config.evaluation import (
    DROP_ID_COLUMNS_FROM_METRICS,
    EVAL_DEFAULT_METRICS,
    EXACT_MATCH_SHOW_FILTERED_ROWS,
    QUASI_IDENTIFIER_SUBSETS,
    SENSITIVE_COLUMNS,
    TSTR_TARGET_COLUMN,
    TSTR_TASK_TYPE,
    TVD_N_BINS,
    UTILITY_TESTS_CONFIG,
)


@dataclass(frozen=True)
class TableEvalSettings:
    """Evaluation settings resolved for a single table."""

    table: str
    metrics: dict
    target_column: str | None
    task_type: str
    sensitive_columns: list[str] | None
    quasi_identifier_subsets: dict[str, list[str]] | None
    tvd_n_bins: int
    utility_tests: dict
    exact_match_show_filtered_rows: bool
    drop_id_columns: bool


def build_table_settings(table: str, config: dict | None) -> TableEvalSettings:
    """Resolve the effective settings for ``table`` from a per-table config object.

    Args:
        table: Name of the table to evaluate.
        config: Per-table evaluation config (``evaluation.yaml`` shape). ``None``
            or ``{}`` ⇒ every field falls back to the global default.
    """
    config = config or {}
    metrics = config.get("metrics", {}) if isinstance(config.get("metrics"), dict) else {}
    execution = config.get("execution", {}) if isinstance(config.get("execution"), dict) else {}
    tstr = metrics.get("tstr", {}) if isinstance(metrics.get("tstr"), dict) else {}
    exact_match = (
        metrics.get("exact_match", {}) if isinstance(metrics.get("exact_match"), dict) else {}
    )

    # An empty/blank target means "no predictive utility" for this table.
    target_column = (metrics.get("tstr") and tstr.get("target_column")) or None
    if "tstr" not in metrics:
        target_column = TSTR_TARGET_COLUMN or None

    return TableEvalSettings(
        table=table,
        metrics=metrics.get("default") or EVAL_DEFAULT_METRICS,
        target_column=target_column,
        task_type=tstr.get("task_type", TSTR_TASK_TYPE),
        sensitive_columns=(
            metrics["sensitive_columns"]
            if "sensitive_columns" in metrics
            else SENSITIVE_COLUMNS
        ),
        quasi_identifier_subsets=(
            metrics["quasi_identifier_subsets"]
            if "quasi_identifier_subsets" in metrics
            else QUASI_IDENTIFIER_SUBSETS
        ),
        tvd_n_bins=metrics.get("tvd_n_bins", TVD_N_BINS),
        utility_tests=(
            metrics["utility_tests"]
            if isinstance(metrics.get("utility_tests"), dict)
            else (UTILITY_TESTS_CONFIG or {})
        ),
        exact_match_show_filtered_rows=exact_match.get(
            "show_filtered_rows", EXACT_MATCH_SHOW_FILTERED_ROWS
        ),
        drop_id_columns=execution.get(
            "drop_id_columns_from_metrics", DROP_ID_COLUMNS_FROM_METRICS
        ),
    )
