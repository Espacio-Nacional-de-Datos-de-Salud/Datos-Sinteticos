"""Shared base class for every custom metric evaluator.

``MetricEvaluator`` offers a single convenience: a deterministic label-encoder
over categorical columns so downstream metrics can operate on purely numeric
arrays (needed by k-NN and correlation-based metrics).
"""

import pandas as pd
from sklearn.preprocessing import LabelEncoder


class MetricEvaluator:
    """Base class for all custom metric evaluators."""

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
