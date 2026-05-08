"""l-diversity metric over user-defined quasi-identifier subsets.

For each QI subset, verifies that every equivalence class contains at least
``l`` distinct values of the sensitive columns. The final score is the
minimum ``syn_l`` across all subsets (lower = more vulnerable).
"""

import numpy as np
import pandas as pd
from backend.src.config.evaluation import SENSITIVE_COLUMNS
from backend.src.core.logging_config import get_logger
from backend.src.evaluation.custom_metrics.base import MetricEvaluator
from backend.src.evaluation.custom_metrics.helpers import resolve_quasi_identifier_subsets
from backend.src.evaluation.utils import get_id_columns

logger = get_logger(__name__)


class LDiversityPyCanon(MetricEvaluator):
    """Compute l-diversity for specific column subsets.

    l-diversity measures whether each group of records sharing
    quasi-identifiers has at least l "well-represented" sensitive values.

    Higher l-values indicate better privacy. Returns 999 on fail
    """

    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "l_diversity_pycanon"

    @staticmethod
    def _resolve_sensitive_columns(real_data: pd.DataFrame) -> list[str]:
        """Return configured sensitive columns or fall back to detected id columns.

        Args:
            real_data (pd.DataFrame): Reference dataset used for detection fallback.

        Returns:
            list[str]: Sensitive columns to pass to ``pycanon.anonymity.l_diversity``.
        """
        if SENSITIVE_COLUMNS is not None:
            return SENSITIVE_COLUMNS
        logger.debug("No sensitive columns defined. Performing automatic detection of id columns")
        return get_id_columns(real_data)

    @staticmethod
    def _compute_subset_l(
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        subset_name: str,
        columns: list[str],
        sensitive_columns: list[str],
    ) -> dict | None:
        """Compute real and synthetic l-diversity for a single QI subset.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.
            subset_name (str): Label used in logs.
            columns (list[str]): Quasi-identifier columns for this subset.
            sensitive_columns (list[str]): Columns treated as sensitive.

        Returns:
            dict | None: ``{real_l, syn_l, columns}`` or ``None`` on failure.
        """
        from pycanon import anonymity

        try:
            l_real = anonymity.l_diversity(real_data, columns, sensitive_columns)
            l_syn = anonymity.l_diversity(synthetic_data, columns, sensitive_columns)
            logger.debug(f"Subset '{subset_name}': real_l={l_real}, syn_l={l_syn}")
            return {"real_l": l_real, "syn_l": l_syn, "columns": columns}
        except Exception as e:
            logger.error(f"Failed to compute l-diversity for subset '{subset_name}': {e}")
            return None

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute l-diversity for multiple column subsets.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with per-subset scores, additional metadata, and comparison.
        """
        if len(real_data) == 0 or len(synthetic_data) == 0:
            logger.warning("Cannot compute l-diversity: empty dataset(s)")
            return {"score": 999, "additional": {}}

        quasi_identifier_subsets, _ = resolve_quasi_identifier_subsets(real_data)
        sensitive_columns = self._resolve_sensitive_columns(real_data)

        subset_results: dict[str, dict] = {}
        for subset_name, columns in quasi_identifier_subsets.items():
            if not columns:
                logger.warning(f"Skipping subset '{subset_name}': no valid columns found")
                continue
            entry = self._compute_subset_l(
                real_data, synthetic_data, subset_name, columns, sensitive_columns
            )
            if entry is not None:
                subset_results[subset_name] = entry

        if subset_results:
            main_score = np.min([v["syn_l"] for v in subset_results.values()])
            max_score = float(np.max([v["syn_l"] for v in subset_results.values()]))
        else:
            main_score = 999
            max_score = 999

        return {
            "score": float(main_score),
            "min": float(main_score),
            "max": max_score,
            "additional": subset_results,
        }
