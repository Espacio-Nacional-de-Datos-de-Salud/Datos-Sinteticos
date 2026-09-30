"""Correlation matrix distance metric.

Compares the real vs synthetic correlation matrices using a scaled RMSE
(SRMSE) over their off-diagonal entries and emits heatmaps of both matrices
as an artefact for the evaluation report.
"""

import numpy as np
import pandas as pd

from backend.src.domain.evaluation.custom_metrics.base import MetricEvaluator
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


class CorrelationMatrixDistance(MetricEvaluator):
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
        return "correlation_matrix_distance"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute SRMSE between correlation matrices of real and synthetic data.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with a "score" key and numeric value.
        """
        if len(real_data) == 0 or len(synthetic_data) == 0:
            logger.debug("Cannot calculate correlation matrix distance, not enough data.")
            return {"score": float("inf")}

        real_processed, synthetic_processed = self._encode_categorical_columns(
            real_data, synthetic_data
        )

        real_processed = real_processed.dropna()
        synthetic_processed = synthetic_processed.dropna()

        if len(real_processed) == 0 or len(synthetic_processed) == 0:
            logger.debug("Cannot calculate correlation matrix distance, not enough non-NaN data.")
            return {"score": float("inf")}

        real_corr = real_processed.corr()
        synthetic_corr = synthetic_processed.corr()

        # Remove diagonal (always 1.0) and check if matrix is not empty
        mask = ~np.eye(real_corr.shape[0], dtype=bool)
        real_corr_no_diag = real_corr.values[mask]
        synthetic_corr_no_diag = synthetic_corr.values[mask]

        if len(real_corr_no_diag) == 0:
            logger.debug("Cannot calculate correlation matrix distance, 1x1 matrix")
            return {"score": 0.0}

        # Generate correlation matrix figures
        import matplotlib.pyplot as plt
        import seaborn as sns

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 5))

        sns.heatmap(real_corr, annot=True, cmap="coolwarm", center=0, ax=ax1, fmt=".2f")
        ax1.set_title("Real Data Correlation Matrix")

        sns.heatmap(synthetic_corr, annot=True, cmap="coolwarm", center=0, ax=ax2, fmt=".2f")
        ax2.set_title("Synthetic Data Correlation Matrix")

        fig.tight_layout()

        # Calculate SRMSE using off-diagonal values
        diff = real_corr_no_diag - synthetic_corr_no_diag
        mse = np.mean(diff**2)
        rmse = np.sqrt(mse)

        # Scale by standard deviation of real correlation matrix
        real_corr_std = np.std(real_corr_no_diag)
        srmse = rmse / real_corr_std if real_corr_std > 0 else rmse

        # Calculate L1 and Frobenius (L2) distances as well
        l1_distance = np.sum(np.abs(diff))
        frobenius_distance = np.sqrt(np.sum(diff**2))

        return {
            "score": float(srmse),
            "figure": fig,
            "additional": {
                "l1_distance": float(l1_distance),
                "frobenius_distance": float(frobenius_distance),
            },
        }
