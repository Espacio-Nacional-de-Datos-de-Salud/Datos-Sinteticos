"""Shared base class for every custom metric evaluator.

``MetricEvaluator`` offers a single convenience: a deterministic label-encoder
over categorical columns so downstream metrics can operate on purely numeric
arrays (needed by k-NN and correlation-based metrics).
"""

import pandas as pd
from sklearn.preprocessing import LabelEncoder

from backend.src.config.evaluation import (
    EXPENSIVE_METRICS_RANDOM_STATE,
    MAX_ROWS_PER_TABLE_FOR_EXPENSIVE_METRICS,
)


class MetricEvaluator:
    """Base class for all custom metric evaluators."""

    def _sample_for_expensive_metric(
        self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Optionally cap rows for metrics with superlinear runtime.

        DCR/NNDR and bootstrap-based metrics are useful diagnostics, but on
        multi-million-row tables their cost can dominate a run. This helper
        keeps the cap local to those metrics so aggregate utility tests still
        see the full dataset.
        """
        max_rows = MAX_ROWS_PER_TABLE_FOR_EXPENSIVE_METRICS
        if max_rows is None or max_rows <= 0:
            return real_data, synthetic_data

        return (
            self._sample_frame(real_data, max_rows),
            self._sample_frame(synthetic_data, max_rows),
        )

    @staticmethod
    def _sample_frame(data: pd.DataFrame, max_rows: int) -> pd.DataFrame:
        """Return a deterministic row sample when ``data`` exceeds ``max_rows``."""
        if len(data) <= max_rows:
            return data
        return data.sample(
            n=max_rows,
            random_state=EXPENSIVE_METRICS_RANDOM_STATE,
        ).reset_index(drop=True)

    def _encode_categorical_columns(
        self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Encode categorical columns using LabelEncoder.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            tuple[pd.DataFrame, pd.DataFrame]: Encoded real and synthetic data.
        """
        real_processed = real_data.copy()
        synthetic_processed = synthetic_data.copy()

        for col in real_data.columns:
            if real_data[col].dtype == "object":
                le = LabelEncoder()
                combined_values = pd.concat([real_data[col], synthetic_data[col]]).astype(str)
                le.fit(combined_values)
                real_processed[col] = le.transform(real_data[col].astype(str))
                synthetic_processed[col] = le.transform(synthetic_data[col].astype(str))

        return real_processed, synthetic_processed
