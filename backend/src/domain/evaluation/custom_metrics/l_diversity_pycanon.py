"""PyCanon-backed l-diversity over configured quasi-identifier subsets.

This metric intentionally does not fall back to all pairwise column
combinations. l-diversity needs human-selected quasi-identifiers and sensitive
attributes to be meaningful and tractable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from backend.src.config import evaluation as evaluation_config
from backend.src.domain.evaluation.custom_metrics.base import MetricEvaluator
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


_FIELD_DESCRIPTIONS: dict[str, str] = {
    "real_l": (
        "Distinct l-diversity computed by PyCanon on the real dataset for this "
        "quasi-identifier subset."
    ),
    "syn_l": (
        "Distinct l-diversity computed by PyCanon on the synthetic dataset for "
        "this quasi-identifier subset."
    ),
    "columns": "Quasi-identifier columns used to define equivalence classes.",
    "sensitive_columns": "Sensitive columns whose diversity is measured inside each class.",
    "sensitive_column_scores": (
        "Per-sensitive-column l-diversity values. The subset score is the minimum "
        "across configured sensitive columns."
    ),
}

_SUMMARY_ROWS: dict[str, str] = {
    "l_diversity.real": "Minimum l-diversity observed across configured subsets in real data.",
    "l_diversity.syn": "Minimum l-diversity observed across configured subsets in synthetic data.",
}


def _normalize_column_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple, set)):
        return [column for column in value if isinstance(column, str)]
    return []


class LDiversityPyCanon(MetricEvaluator):
    """Compute exact distinct l-diversity with PyCanon.

    The metric is skipped when either ``metrics.quasi_identifier_subsets`` or
    ``metrics.sensitive_columns`` is missing. That keeps evaluation bounded and
    avoids producing misleading values from guessed privacy columns.
    """

    def __init__(
        self,
        quasi_identifier_subsets: dict[str, list[str]] | None = None,
        sensitive_columns: list[str] | None = None,
        **kwargs,
    ) -> None:
        """Initialize the metric evaluator.

        Args:
            quasi_identifier_subsets: Per-run QI subsets overriding the global
                config (e.g. table-specific). ``None`` ⇒ use global config.
            sensitive_columns: Per-run sensitive columns overriding the global
                config. ``None`` ⇒ use global config.
        """
        super().__init__(**kwargs)
        self._quasi_identifier_subsets = quasi_identifier_subsets
        self._sensitive_columns = sensitive_columns

    @staticmethod
    def name() -> str:
        """Return the canonical metric name used by the custom runner."""
        return "l_diversity_pycanon"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute l-diversity for configured QI subsets and sensitive columns."""
        if len(real_data) == 0 or len(synthetic_data) == 0:
            return self._skipped_result("empty_dataset")

        qi_subsets = (
            self._quasi_identifier_subsets
            if self._quasi_identifier_subsets is not None
            else evaluation_config.QUASI_IDENTIFIER_SUBSETS
        )
        if not qi_subsets:
            return self._skipped_result("missing_quasi_identifier_subsets")

        sensitive_columns = _normalize_column_list(
            self._sensitive_columns
            if self._sensitive_columns is not None
            else evaluation_config.SENSITIVE_COLUMNS
        )
        if not sensitive_columns:
            return self._skipped_result("missing_sensitive_columns")

        valid_sensitive_columns = self._valid_columns(
            sensitive_columns, real_data, synthetic_data, "sensitive column"
        )
        if not valid_sensitive_columns:
            return self._skipped_result("no_valid_sensitive_columns")

        subset_results = self._compute_subset_results(
            real_data,
            synthetic_data,
            qi_subsets,
            valid_sensitive_columns,
        )
        additional = {
            "report_metadata": {
                "metric_name": "l_diversity_pycanon",
                "activation_key": "distinct l-diversity",
                "library": "pycanon.anonymity.l_diversity",
                "subset_source": "config.metrics.quasi_identifier_subsets",
                "summary_rows": _SUMMARY_ROWS,
            },
            "field_descriptions": _FIELD_DESCRIPTIONS,
            "subsets": subset_results,
        }

        if not subset_results:
            return self._skipped_result("no_valid_quasi_identifier_subsets", additional)

        return {
            "scores": self._aggregate_scores(subset_results),
            "additional": additional,
        }

    def _compute_subset_results(
        self,
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        qi_subsets: dict[str, list[str]],
        sensitive_columns: list[str],
    ) -> dict[str, dict]:
        subset_results: dict[str, dict] = {}
        for subset_name, configured_columns in qi_subsets.items():
            columns = self._valid_qi_columns(
                configured_columns,
                sensitive_columns,
                real_data,
                synthetic_data,
                subset_name,
            )
            if not columns:
                continue
            entry = self._compute_subset_entry(
                real_data,
                synthetic_data,
                subset_name,
                columns,
                sensitive_columns,
            )
            if entry is not None:
                subset_results[subset_name] = entry
        return subset_results

    def _compute_subset_entry(
        self,
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        subset_name: str,
        columns: list[str],
        sensitive_columns: list[str],
    ) -> dict | None:
        from pycanon import anonymity

        try:
            real_l = int(anonymity.l_diversity(real_data, columns, sensitive_columns))
            syn_l = int(anonymity.l_diversity(synthetic_data, columns, sensitive_columns))
            if len(sensitive_columns) == 1:
                sensitive_scores = {sensitive_columns[0]: {"real_l": real_l, "syn_l": syn_l}}
            else:
                sensitive_scores = self._compute_sensitive_column_scores(
                    real_data, synthetic_data, columns, sensitive_columns
                )
        except Exception as exc:
            logger.warning("Could not compute l-diversity for subset '%s': %s", subset_name, exc)
            return None

        logger.debug("Subset '%s': real_l=%s, syn_l=%s", subset_name, real_l, syn_l)
        return {
            "real_l": real_l,
            "syn_l": syn_l,
            "columns": columns,
            "sensitive_columns": sensitive_columns,
            "sensitive_column_scores": sensitive_scores,
        }

    @staticmethod
    def _compute_sensitive_column_scores(
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        columns: list[str],
        sensitive_columns: list[str],
    ) -> dict[str, dict[str, int]]:
        from pycanon import anonymity

        scores: dict[str, dict[str, int]] = {}
        for sensitive_column in sensitive_columns:
            scores[sensitive_column] = {
                "real_l": int(anonymity.l_diversity(real_data, columns, [sensitive_column])),
                "syn_l": int(anonymity.l_diversity(synthetic_data, columns, [sensitive_column])),
            }
        return scores

    @staticmethod
    def _valid_columns(
        columns: list[str],
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        label: str,
    ) -> list[str]:
        valid_columns: list[str] = []
        for column in columns:
            if column in real_data.columns and column in synthetic_data.columns:
                valid_columns.append(column)
            else:
                logger.warning("Skipping unknown %s '%s' for l-diversity", label, column)
        return valid_columns

    def _valid_qi_columns(
        self,
        configured_columns: list[str],
        sensitive_columns: list[str],
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        subset_name: str,
    ) -> list[str]:
        columns = self._valid_columns(
            configured_columns,
            real_data,
            synthetic_data,
            f"quasi-identifier in subset {subset_name}",
        )
        columns = [column for column in columns if column not in sensitive_columns]
        if not columns:
            logger.warning("Skipping l-diversity subset '%s': no valid QI columns", subset_name)
        return columns

    @staticmethod
    def _aggregate_scores(subset_results: dict[str, dict]) -> dict[str, dict]:
        real_ls = [entry["real_l"] for entry in subset_results.values()]
        syn_ls = [entry["syn_l"] for entry in subset_results.values()]
        return {
            "l_diversity.real": {
                "mean": float(np.min(real_ls)),
                "min": float(np.min(real_ls)),
                "max": float(np.max(real_ls)),
            },
            "l_diversity.syn": {
                "mean": float(np.min(syn_ls)),
                "min": float(np.min(syn_ls)),
                "max": float(np.max(syn_ls)),
            },
        }

    @staticmethod
    def _skipped_result(reason: str, additional: dict | None = None) -> dict:
        logger.info("Skipping l-diversity: %s", reason)
        payload = additional or {}
        payload["skipped"] = True
        payload["skip_reason"] = reason
        return {"score": None, "additional": payload}
