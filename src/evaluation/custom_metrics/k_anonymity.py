"""k-anonymity metric over user-defined quasi-identifier subsets.

Computes real and synthetic k for each QI subset, along with equivalence-class
size statistics, marginal contributions (k obtained by removing one column at
a time from the subset on synthetic data), and single-column granularity for
every QI column.
"""

import numpy as np
import pandas as pd

from src.core.logging_config import get_logger
from src.evaluation.custom_metrics.base import MetricEvaluator
from src.evaluation.custom_metrics.helpers import resolve_quasi_identifier_subsets

logger = get_logger(__name__)


_FIELD_DESCRIPTIONS: dict[str, str] = {
    "real_k": (
        "k-anonymity computed on the real dataset for the subset. "
        "It is the size of the smallest equivalence class in the real data."
    ),
    "syn_k": (
        "k-anonymity computed on the synthetic dataset for the subset. "
        "It is the size of the smallest equivalence class in the synthetic data."
    ),
    "equivalence_class": (
        "A group of rows that share exactly the same values for the subset columns."
    ),
    "real_eq_class_stats": (
        "Distribution of equivalence-class sizes in the real dataset for the subset."
    ),
    "syn_eq_class_stats": (
        "Distribution of equivalence-class sizes in the synthetic dataset for the subset."
    ),
    "n_eq_classes": (
        "Number of distinct equivalence classes, i.e. unique value combinations in the subset."
    ),
    "size_min": ("Smallest equivalence-class size. In practice this matches the subset k value."),
    "size_p25": "25th percentile of equivalence-class sizes.",
    "size_median": "Median equivalence-class size.",
    "size_mean": "Mean equivalence-class size.",
    "size_p75": "75th percentile of equivalence-class sizes.",
    "size_max": "Largest equivalence-class size.",
    "column_granularity": (
        "Single-column view showing how identifying each quasi-identifier is on its own."
    ),
    "real_n_unique": "Number of distinct values in the real dataset for that column.",
    "syn_n_unique": "Number of distinct values in the synthetic dataset for that column.",
    "marginal_reference_dataset": (
        "Dataset used to compute marginal contributions. Currently always synthetic."
    ),
    "marginal_contributions": (
        "Impact of removing one column at a time from the subset when recomputing k "
        "on synthetic data."
    ),
    "marginal_contributions_syn": (
        "Same as marginal_contributions, kept with an explicit name to indicate the "
        "reference dataset."
    ),
    "k_without": "k obtained after removing the indicated column from the subset.",
    "k_delta": (
        "Difference between k_without and syn_k. "
        "Larger positive values mean the removed column was strongly identifying."
    ),
}

_SUMMARY_ROWS: dict[str, str] = {
    "k_anonymity.real": "Minimum k observed across all configured subsets in the real dataset.",
    "k_anonymity.syn": "Minimum k observed across all configured subsets in the synthetic dataset.",
}

_COMPARISON_GUIDANCE: str = (
    "Compare real_k and syn_k subset by subset. "
    "If syn_k is below real_k, the synthetic data is more unique on that subset. "
    "If syn_k is far above real_k, privacy is stronger but utility may be lower."
)


class KAnonymity(MetricEvaluator):
    """Compute k-anonymity for specific column subsets with granularity analysis.

    k-anonymity measures whether each record is indistinguishable from at least k-1
    others on quasi-identifying attributes.

    In addition to the k value per subset, this metric produces:
    - **Column granularity**: single-column k and number of unique values, showing
      which columns are inherently most identifying.
    - **Equivalence class distribution**: statistics on group sizes per subset,
      showing whether groups are uniformly large (safe) or skewed with tiny groups.
    - **Marginal contribution**: for each column in a subset, the synthetic-data
      k that would result from removing it. The delta shows how much that column
      drives the synthetic k down.

    Higher k-values indicate better privacy. Returns 999 on fail.
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
        return "k_anonymity"

    @staticmethod
    def _eq_class_stats(data: pd.DataFrame, columns: list[str]) -> dict:
        """Compute equivalence class size statistics for a set of quasi-identifiers.

        Args:
            data: Dataset to analyse.
            columns: Quasi-identifier columns that define the equivalence classes.

        Returns:
            dict with n_eq_classes and size distribution percentiles.
        """
        group_sizes = data.groupby(columns, observed=True).size()
        return {
            "n_eq_classes": int(len(group_sizes)),
            "size_min": int(group_sizes.min()),
            "size_p25": float(group_sizes.quantile(0.25)),
            "size_median": float(group_sizes.median()),
            "size_mean": float(group_sizes.mean()),
            "size_p75": float(group_sizes.quantile(0.75)),
            "size_max": int(group_sizes.max()),
        }

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute k-anonymity for multiple column subsets with granularity analysis.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with per-subset scores, granularity analysis, and comparison.
        """
        if len(real_data) == 0 or len(synthetic_data) == 0:
            logger.warning("Cannot compute k-anonymity: empty dataset(s)")
            return {"score": 999, "additional": {}}

        quasi_identifier_subsets, subset_source = resolve_quasi_identifier_subsets(real_data)

        subset_results = self._compute_all_subset_entries(
            real_data, synthetic_data, quasi_identifier_subsets
        )
        all_qi_columns = sorted({col for cols in quasi_identifier_subsets.values() for col in cols})
        column_granularity = self._compute_column_granularity(
            real_data, synthetic_data, all_qi_columns
        )

        additional = {
            "report_metadata": self._build_report_metadata(subset_source),
            "field_descriptions": _FIELD_DESCRIPTIONS,
            "subsets": subset_results,
            "column_granularity": column_granularity,
        }

        if not subset_results:
            return {"score": 999, "additional": additional}

        return {
            "scores": self._aggregate_scores(subset_results),
            "additional": additional,
        }

    def _compute_all_subset_entries(
        self,
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        quasi_identifier_subsets: dict[str, list[str]],
    ) -> dict[str, dict]:
        """Compute a k-anonymity entry for every configured QI subset.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.
            quasi_identifier_subsets (dict[str, list[str]]): Subsets to evaluate.

        Returns:
            dict[str, dict]: Mapping of subset name to its result entry. Subsets
            that fail or contain no columns are skipped with a log message.
        """
        subset_results: dict[str, dict] = {}
        for subset_name, columns in quasi_identifier_subsets.items():
            if not columns:
                logger.warning(f"Skipping subset '{subset_name}': no valid columns found")
                continue
            entry = self._compute_subset_entry(real_data, synthetic_data, subset_name, columns)
            if entry is not None:
                subset_results[subset_name] = entry
        return subset_results

    def _compute_subset_entry(
        self,
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        subset_name: str,
        columns: list[str],
    ) -> dict | None:
        """Compute real/synthetic k and equivalence-class stats for a single subset.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.
            subset_name (str): Label used in logs and results.
            columns (list[str]): Quasi-identifier columns for this subset.

        Returns:
            dict | None: Entry with real/syn k values, equivalence-class stats,
            and (when applicable) marginal contributions; ``None`` on failure.
        """
        from pycanon import anonymity

        try:
            k_real = anonymity.k_anonymity(real_data, columns)
            k_syn = anonymity.k_anonymity(synthetic_data, columns)
        except Exception as e:
            logger.error(f"Failed to compute k-anonymity for subset '{subset_name}': {e}")
            return None

        entry: dict = {
            "real_k": int(k_real),
            "syn_k": int(k_syn),
            "columns": columns,
            "real_eq_class_stats": self._eq_class_stats(real_data, columns),
            "syn_eq_class_stats": self._eq_class_stats(synthetic_data, columns),
        }
        if len(columns) > 1:
            entry["marginal_contributions_syn"] = self._compute_marginal_contributions_syn(
                synthetic_data, columns, int(k_syn), subset_name
            )
        logger.debug(f"Subset '{subset_name}': real_k={k_real}, syn_k={k_syn}")
        return entry

    @staticmethod
    def _compute_marginal_contributions_syn(
        synthetic_data: pd.DataFrame,
        columns: list[str],
        k_syn: int,
        subset_name: str,
    ) -> dict[str, dict]:
        """Compute the synthetic-data k obtained by removing each column from the subset.

        Args:
            synthetic_data (pd.DataFrame): Generated dataset.
            columns (list[str]): Full subset of quasi-identifiers.
            k_syn (int): Synthetic k for the full subset (baseline for deltas).
            subset_name (str): Label used in log messages on failure.

        Returns:
            dict[str, dict]: ``{column: {"k_without": int, "k_delta": int}}``.
        """
        from pycanon import anonymity

        marginal: dict[str, dict] = {}
        for col in columns:
            remaining = [c for c in columns if c != col]
            try:
                k_without = int(anonymity.k_anonymity(synthetic_data, remaining))
                marginal[col] = {"k_without": k_without, "k_delta": k_without - k_syn}
            except Exception as e:
                logger.warning(f"Could not compute marginal for '{col}' in '{subset_name}': {e}")
        return marginal

    @staticmethod
    def _compute_column_granularity(
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        qi_columns: list[str],
    ) -> dict[str, dict]:
        """Compute single-column k and unique-value counts for every QI column.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.
            qi_columns (list[str]): Columns to evaluate individually.

        Returns:
            dict[str, dict]: Per-column granularity stats.
        """
        from pycanon import anonymity

        column_granularity: dict[str, dict] = {}
        for col in qi_columns:
            try:
                column_granularity[col] = {
                    "real_k": int(anonymity.k_anonymity(real_data, [col])),
                    "syn_k": int(anonymity.k_anonymity(synthetic_data, [col])),
                    "real_n_unique": int(real_data[col].nunique()),
                    "syn_n_unique": int(synthetic_data[col].nunique()),
                }
            except Exception as e:
                logger.warning(f"Could not compute single-column granularity for '{col}': {e}")
        return column_granularity

    @staticmethod
    def _build_report_metadata(subset_source: str) -> dict:
        """Build the static report metadata block for k-anonymity results.

        Args:
            subset_source (str): Identifier describing where the QI subsets came from.

        Returns:
            dict: Report metadata payload.
        """
        return {
            "metric_name": "k_anonymity",
            "activation_key": "k-anonymization",
            "subset_source": subset_source,
            "summary_rows": _SUMMARY_ROWS,
            "comparison_guidance": _COMPARISON_GUIDANCE,
        }

    @staticmethod
    def _aggregate_scores(subset_results: dict[str, dict]) -> dict[str, dict]:
        """Reduce per-subset k values into the real/synthetic summary scores.

        Args:
            subset_results (dict[str, dict]): Per-subset k-anonymity entries.

        Returns:
            dict[str, dict]: Score rows ``k_anonymity.real`` and ``k_anonymity.syn``.
        """
        syn_ks = [v["syn_k"] for v in subset_results.values()]
        real_ks = [v["real_k"] for v in subset_results.values()]
        return {
            "k_anonymity.real": {
                "mean": float(np.min(real_ks)),
                "min": float(np.min(real_ks)),
                "max": float(np.max(real_ks)),
            },
            "k_anonymity.syn": {
                "mean": float(np.min(syn_ks)),
                "min": float(np.min(syn_ks)),
                "max": float(np.max(syn_ks)),
            },
        }
