"""
Custom statistics template for user-defined statistical measures.

This module provides a template for defining custom statistics that extend the built-in
statistical capabilities. Users can inherit from the Statistic base class and define
custom calculation logic, then register these statistics in CUSTOM_STATISTIC_MAP.

Example:
    Define a custom statistic class:

    >>> class CoefficientOfVariationStatistic(Statistic):
    ...     @staticmethod
    ...     def name():
    ...         return "coefficient_of_variation"
    ...
    ...     def calculate(self, data: pd.DataFrame) -> dict:
    ...         series = self._preprocess_series(data)
    ...         if series is None:
    ...             return {'value': np.nan, 'ci': (np.nan, np.nan)}
    ...
    ...         mean = series.mean()
    ...         if mean == 0:
    ...             return {'value': np.nan, 'ci': (np.nan, np.nan)}
    ...
    ...         std = series.std()
    ...         cv = (std / mean) * 100
    ...         ci = self._bootstrap_confidence_interval(
    ...             series, cv,
    ...             lambda x: (x.std() / x.mean() * 100) if x.mean() != 0 else np.nan
    ...         )
    ...         return {'value': cv, 'ci': ci}

    Then register it in CUSTOM_STATISTIC_MAP:

    >>> CUSTOM_STATISTIC_MAP = {
    ...     "coefficient_of_variation": CoefficientOfVariationStatistic,
    ... }
"""

from typing import Any

import numpy as np
import pandas as pd

from backend.src.domain.evaluation.statistics import Statistic
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


# ============================================================================
# EXAMPLE 1: Coefficient of Variation (relative variability)
# ============================================================================


class CoefficientOfVariationStatistic(Statistic):
    """Calculate coefficient of variation (CV = std/mean × 100) and confidence interval.

    CV is a scale-independent measure of variability, useful for comparing
    spread across columns with different units.
    """

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "coefficient_of_variation"

    def supports_shared_bootstrap(self) -> bool:
        return True

    def _scalar_stat(self, values: np.ndarray) -> float:
        mean_val = values.mean()
        if mean_val == 0:
            logger.debug(
                f"Mean of column '{self.column}' in table '{self.table}' is zero; cannot compute CV"
            )
            return float("nan")
        return float((values.std(ddof=1) / mean_val) * 100)

    def _vec_stat(self, samples_2d: np.ndarray) -> np.ndarray:
        m = samples_2d.mean(axis=1)
        with np.errstate(divide="ignore", invalid="ignore"):
            cv = (samples_2d.std(axis=1, ddof=1) / m) * 100
        cv[m == 0] = np.nan
        return cv

    def calculate(
        self,
        data: pd.DataFrame,
        bootstrap_rng_seed: int | None = None,
    ) -> dict[str, Any]:
        """Calculate coefficient of variation and confidence interval."""
        series = self._preprocess_series(data)
        if series is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        values = series.to_numpy()
        cv_val = self._scalar_stat(values)
        if np.isnan(cv_val):
            return {"value": np.nan, "ci": (np.nan, np.nan)}
        ci = self._vectorized_bootstrap_ci(values, self._vec_stat, bootstrap_rng_seed)
        return {"value": cv_val, "ci": ci}


# ============================================================================
# EXAMPLE 2: Interquartile Range (Q3 - Q1)
# ============================================================================


class InterquartileRangeStatistic(Statistic):
    """Calculate interquartile range (IQR = Q3 - Q1) and confidence interval.

    IQR is a robust measure of spread that is unaffected by extreme outliers.
    """

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "interquartile_range"

    def supports_shared_bootstrap(self) -> bool:
        return True

    def _scalar_stat(self, values: np.ndarray) -> float:
        return float(np.quantile(values, 0.75) - np.quantile(values, 0.25))

    def _vec_stat(self, samples_2d: np.ndarray) -> np.ndarray:
        qs = np.quantile(samples_2d, [0.25, 0.75], axis=1)
        return qs[1] - qs[0]

    def calculate(
        self,
        data: pd.DataFrame,
        bootstrap_rng_seed: int | None = None,
    ) -> dict[str, Any]:
        """Calculate IQR and confidence interval."""
        series = self._preprocess_series(data)
        if series is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        values = series.to_numpy()
        iqr_val = self._scalar_stat(values)
        ci = self._vectorized_bootstrap_ci(values, self._vec_stat, bootstrap_rng_seed)
        return {"value": iqr_val, "ci": ci}


# ============================================================================
# EXAMPLE 3: Missing Data Proportion
# ============================================================================


class NullProportionStatistic(Statistic):
    """Calculate proportion of missing (null) values.

    Useful for validating that synthetic data has similar missingness patterns
    as the original data.
    """

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "null_proportion"

    def calculate(
        self,
        data: pd.DataFrame,
        bootstrap_rng_seed: int | None = None,
    ) -> dict[str, Any]:
        """Calculate proportion of null values.

        Note: This statistic does not apply bootstrap CI because null proportion
        is deterministic (no variability across resamples of same data).
        """
        if self.column not in data.columns:
            logger.debug(f"Column '{self.column}' not found in table '{self.table}'")
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        total = len(data)
        null_count = data[self.column].isna().sum()
        null_proportion = float(null_count / total) if total > 0 else 0.0

        # No CI for null proportion (deterministic on dataset)
        return {"value": null_proportion, "ci": (null_proportion, null_proportion)}


class AgeStatistic(Statistic):
    """Calculate mean age at admission from DOB and admission time columns.

    This statistic computes the age of patients in years at the time of admission,
    then calculates the mean age across all patients with a bootstrap confidence interval.

    Expected YAML config:
        - operation: "age"
          table: "dataset_prueba_tecnica_v2"
          col: "dob"
          col2: "admittime"
    """

    def __init__(
        self, table, column, confidence_level, columns=None, convert_to_categorical=True, **kwargs
    ):
        """Initialize AgeStatistic with DOB and admission time columns.

        Args:
            table: Table name
            column: Primary column (typically 'dob', used as col in YAML)
            confidence_level: Confidence level for bootstrap CI
            columns: Dict with 'col' (DOB) and 'col2' (admission time) keys
            **kwargs: Additional parameters from config
        """
        super().__init__(
            table, column, confidence_level, convert_to_categorical=convert_to_categorical
        )

        # Extract actual column names from the columns dict passed by factory
        # columns dict format: {'col': 'dob', 'col2': 'admittime'}
        self.dob_col = columns.get("col") if columns else None
        self.admit_col = columns.get("col2") if columns else None

        logger.debug(
            f"AgeStatistic initialized: table={table}, dob_col={self.dob_col}, "
            f"admit_col={self.admit_col}, columns_dict={columns}"
        )

        if not self.dob_col or not self.admit_col:
            logger.error(
                f"AgeStatistic configuration ERROR: requires both 'col' (DOB) and 'col2' (admission time). "
                f"Got: dob_col={self.dob_col}, admit_col={self.admit_col}. "
                f"Ensure YAML has top-level 'col' and 'col2' keys, not nested in 'columns' dict."
            )

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "age"

    def bootstrap_signature(self) -> tuple | None:
        """Age is derived from two columns; do not share resamples with single-column stats."""
        return None

    def calculate(
        self,
        data: pd.DataFrame,
        bootstrap_rng_seed: int | None = None,
    ) -> dict[str, Any]:
        """Calculate mean age at admission.

        Computes age in years for each patient as (admittime - dob) / 365.25,
        then returns the mean age with bootstrap confidence interval.

        Args:
            data (pd.DataFrame): Input data with DOB and admission time columns.

        Returns:
            dict[str, Any]: Dictionary with 'value' (mean age in years) and
                           'ci' (confidence interval tuple).
        """
        # Validate configuration
        if not self.dob_col or not self.admit_col:
            logger.error(
                f"AgeStatistic.calculate() called with invalid configuration: "
                f"dob_col={self.dob_col}, admit_col={self.admit_col}. "
                f"Check YAML configuration has top-level 'col' and 'col2' keys."
            )
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        # Validate columns exist
        if self.dob_col not in data.columns:
            logger.debug(f"Column '{self.dob_col}' not found in table '{self.table}'")
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        if self.admit_col not in data.columns:
            logger.debug(f"Column '{self.admit_col}' not found in table '{self.table}'")
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        # Convert both columns to datetime
        try:
            dob = pd.to_datetime(data[self.dob_col])
            admit_time = pd.to_datetime(data[self.admit_col])
        except Exception as e:
            logger.debug(f"Error converting columns to datetime: {e}")
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        # Calculate age in years (admittime - dob) / 365.25
        age_timedelta = admit_time - dob
        age_years = age_timedelta.dt.days / 365.25

        age_years = age_years.dropna()

        if len(age_years) == 0:
            logger.debug(
                f"No valid age data after removing NaN values for table '{self.table}' "
                f"(columns: {self.dob_col}, {self.admit_col})"
            )
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        # Calculate mean age
        values = age_years.to_numpy()
        mean_age = float(values.mean())

        logger.debug(f"Age calculation: mean={mean_age:.2f} years, n={len(values)} records")

        ci = self._vectorized_bootstrap_ci(values, lambda s2d: s2d.mean(axis=1), bootstrap_rng_seed)

        return {"value": mean_age, "ci": ci}


# ============================================================================
# CUSTOM STATISTIC MAP
# ============================================================================

CUSTOM_STATISTIC_MAP = {
    "coefficient_of_variation": CoefficientOfVariationStatistic,
    "interquartile_range": InterquartileRangeStatistic,
    "null_proportion": NullProportionStatistic,
    "age": AgeStatistic,
}


def load_custom_statistics() -> dict:
    """Load and return the custom statistics map.

    This function can be called by the metrics module to register custom statistics
    into the global statistic_map.

    Returns:
        dict: Mapping of operation names to Statistic classes.
    """
    return CUSTOM_STATISTIC_MAP
