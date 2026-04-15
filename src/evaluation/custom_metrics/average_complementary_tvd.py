"""Average Complementary Total Variation Distance (TVD) metric.

For every column, compares the real and synthetic value distributions using
TVD (numeric columns are quantile-binned first). The per-column score is
``1 - TVD`` (higher is better); the overall score is the mean across columns.
"""

import numpy as np
import pandas as pd
from config.evaluation.evaluation_config import AVERAGE_COMPLEMENTARY_TVD_N_BINS

from src.core.logging_config import get_logger
from src.evaluation.custom_metrics.base import MetricEvaluator

logger = get_logger(__name__)


class AverageComplementaryTVD(MetricEvaluator):
    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)
        self.n_bins = AVERAGE_COMPLEMENTARY_TVD_N_BINS

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "average_complementary_tvd"

    def _calculate_tvd(self, real_dist: dict, synthetic_dist: dict) -> float:
        """Calculate Total Variation Distance between two distributions.

        TVD = 0.5 * Σ |P(x) - Q(x)|

        Args:
            real_dist (dict): Distribution of real data (category -> frequency).
            synthetic_dist (dict): Distribution of synthetic data (category -> frequency).

        Returns:
            float: Total Variation Distance value between 0 and 1.
        """
        all_categories = set(real_dist.keys()) | set(synthetic_dist.keys())

        tvd = 0.0
        for category in all_categories:
            real_prob = real_dist.get(category, 0)
            synthetic_prob = synthetic_dist.get(category, 0)
            tvd += abs(real_prob - synthetic_prob)

        return tvd / 2.0

    def _bin_numeric_feature(self, feature_values: pd.Series) -> pd.Series:
        """Bin a numeric feature into categorical bins.

        Args:
            feature_values (pd.Series): Numeric values to bin.

        Returns:
            pd.Series: Binned categorical values.
        """
        return pd.cut(feature_values, bins=self.n_bins, labels=False, duplicates="drop")

    def _get_distribution(self, feature_values: pd.Series) -> dict:
        """Get the distribution (frequency) of values in a feature.

        Args:
            feature_values (pd.Series): Feature values (already categorical or binned).

        Returns:
            dict: Distribution with normalized frequencies (sum to 1).
        """
        value_counts = feature_values.value_counts()
        total = len(feature_values)
        return {category: count / total for category, count in value_counts.items()}

    def _bin_shared_range(
        self, real_feature: pd.Series, synthetic_feature: pd.Series
    ) -> tuple[pd.Series, pd.Series]:
        """Apply numeric binning using a common range derived from both datasets.

        Args:
            real_feature (pd.Series): Real column values (numeric, NaNs dropped).
            synthetic_feature (pd.Series): Synthetic column values.

        Returns:
            tuple[pd.Series, pd.Series]: Binned real and synthetic series.
        """
        combined_data = pd.concat([real_feature, synthetic_feature])
        bins = np.linspace(combined_data.min(), combined_data.max(), self.n_bins + 1)
        real_binned = pd.cut(real_feature, bins=bins, labels=False, duplicates="drop")
        synthetic_binned = pd.cut(synthetic_feature, bins=bins, labels=False, duplicates="drop")
        return real_binned, synthetic_binned

    def _complementary_tvd_for_column(
        self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame, column: str
    ) -> float | None:
        """Compute ``1 - TVD`` for a single column, or ``None`` when not computable.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.
            column (str): Column name to evaluate.

        Returns:
            float | None: Complementary TVD in [0, 1], or ``None`` if the column
            has no overlapping non-NaN values or raised during processing.
        """
        try:
            real_feature = real_data[column].dropna()
            synthetic_feature = synthetic_data[column].dropna()

            if len(real_feature) == 0 or len(synthetic_feature) == 0:
                return None

            if pd.api.types.is_numeric_dtype(real_feature):
                real_binned, synthetic_binned = self._bin_shared_range(
                    real_feature, synthetic_feature
                )
            else:
                real_binned = real_feature
                synthetic_binned = synthetic_feature

            real_dist = self._get_distribution(real_binned)
            synthetic_dist = self._get_distribution(synthetic_binned)

            tvd = self._calculate_tvd(real_dist, synthetic_dist)
            return 1.0 - tvd
        except Exception as e:
            logger.warning(f"Error processing feature '{column}' for AverageComplementaryTVD: {e}")
            return None

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute the average complementary TVD across all features.

        For each feature:
        1. Bin numeric features to treat them as categorical
        2. Calculate the Total Variation Distance
        3. Compute 1 - TVD (complementary TVD)
        4. Average across all features

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with "score" (average complementary TVD), per-feature scores,
                and direction.
        """
        if len(real_data) == 0 or len(synthetic_data) == 0:
            logger.debug("Complementary TVD: Empty dataset(s)")
            return {"score": 0.0, "per_feature_scores": {}, "errors": 1}

        complementary_tvd_scores: dict[str, float] = {}
        for column in real_data.columns:
            score = self._complementary_tvd_for_column(real_data, synthetic_data, column)
            if score is not None:
                complementary_tvd_scores[column] = score

        if not complementary_tvd_scores:
            logger.debug("Inverse TVD: No valid features to compare")
            return {"score": 0.0, "per_feature_scores": {}, "errors": 1}

        average_complementary_tvd = np.mean(list(complementary_tvd_scores.values()))

        return {
            "score": float(average_complementary_tvd),
            "additional": {k: float(v) for k, v in complementary_tvd_scores.items()},
        }
