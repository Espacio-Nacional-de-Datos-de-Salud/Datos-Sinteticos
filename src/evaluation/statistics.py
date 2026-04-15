from abc import ABC, abstractmethod
from typing import Any

import numpy as np
import pandas as pd
from config.evaluation.evaluation_config import NUM_BOOTSTRAP_SAMPLES
from scipy import stats

from src.core.logging_config import get_logger

logger = get_logger(__name__)


class Statistic(ABC):
    """Base class for statistical measures."""

    def __init__(
        self,
        table: str,
        column: str | None,
        confidence_level: float,
        convert_to_categorical: bool = True,
    ):
        """Initialize statistic.

        Args:
            table (str): Table name.
            column (str | None): Column name.
            confidence_level (float): Confidence level for intervals.
            convert_to_categorical (bool): Whether to convert to categorical if non-numeric. Default True.
        """
        self.table = table
        self.column = column
        self.confidence_level = confidence_level
        self.convert_to_categorical = convert_to_categorical

    def valueConvertCategorical(self) -> bool:
        """Return whether categorical values should be converted before computing statistics.

        Returns:
            bool: True when categorical-to-numeric conversion is enabled.
        """
        return self.convert_to_categorical

    def _preprocess_series(self, data: pd.DataFrame) -> pd.Series | None:
        """Preprocess and validate data series for statistical calculation.

        Validates column existence, removes NaN values, converts datetime to numeric,
        and checks numeric type. Logs debug messages for validation failures.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            pd.Series | None: Cleaned numeric series if validation succeeds, None otherwise.
        """
        if self.column not in data.columns:
            logger.debug(f"Column '{self.column}' not found in table '{self.table}'")
            return None

        series = data[self.column].dropna()
        if len(series) == 0:
            logger.debug(
                f"No valid data for column '{self.column}' in table '{self.table}' after removing NaN values"
            )
            return None

        # Convert datetime to numerical if needed
        if pd.api.types.is_datetime64_any_dtype(series):
            series = pd.to_numeric(series)

        if not pd.api.types.is_numeric_dtype(series):
            logger.debug(f"Column '{self.column}' in table '{self.table}' is not numeric")
            return None

        return series

    def _bootstrap_confidence_interval(
        self,
        data: pd.Series,
        statistic_value: float,
        statistic_func,
    ) -> tuple[float, float]:
        """Calculate confidence interval using bootstrap resampling.

        Args:
            data (pd.Series): Data series.
            statistic_value (float): Calculated statistic value.
            statistic_func: Callable that computes the statistic on a sample.

        Returns:
            tuple[float, float]: Lower and upper bounds of confidence interval.
        """
        n = len(data)
        if n < 2:
            return (statistic_value, statistic_value)

        # Bootstrap confidence interval
        bootstrap_statistics = []

        for _ in range(NUM_BOOTSTRAP_SAMPLES):
            bootstrap_sample = data.sample(n=n, replace=True)
            bootstrap_statistics.append(statistic_func(bootstrap_sample))

        alpha = 1 - self.confidence_level
        lower_percentile = (alpha / 2) * 100
        upper_percentile = (1 - alpha / 2) * 100

        ci_lower = np.percentile(bootstrap_statistics, lower_percentile)
        ci_upper = np.percentile(bootstrap_statistics, upper_percentile)

        return (ci_lower, ci_upper)

    @abstractmethod
    def calculate(self, data: pd.DataFrame) -> dict[str, Any]:
        """Calculate statistic and confidence interval.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            Dict[str, Any]: Dictionary with 'value' and 'ci' keys.
        """
        pass


class MeanStatistic(Statistic):
    """Calculate mean and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name.

        Returns:
            str: Statistic identifier used in reports.
        """
        return "mean"

    def calculate(self, data: pd.DataFrame) -> dict[str, Any]:
        """Calculate mean and confidence interval.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            dict[str, Any]: Dictionary with 'value' and 'ci' keys.
        """
        series = self._preprocess_series(data)
        if series is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        mean_val = float(series.mean())
        ci = self._bootstrap_confidence_interval(series, mean_val, lambda x: x.mean())

        return {"value": mean_val, "ci": ci}


class MedianStatistic(Statistic):
    """Calculate median and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name.

        Returns:
            str: Statistic identifier used in reports.
        """
        return "median"

    def calculate(self, data: pd.DataFrame) -> dict[str, Any]:
        """Calculate median and confidence interval.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            dict[str, Any]: Dictionary with 'value' and 'ci' keys.
        """
        series = self._preprocess_series(data)
        if series is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        median_val = float(series.median())
        ci = self._bootstrap_confidence_interval(series, median_val, lambda x: x.median())

        return {"value": median_val, "ci": ci}


class ModeStatistic(Statistic):
    """Calculate mode and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name.

        Returns:
            str: Statistic identifier used in reports.
        """
        return "mode"

    def calculate(self, data: pd.DataFrame) -> dict[str, Any]:
        """Calculate mode and confidence interval.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            dict[str, Any]: Dictionary with 'value' and 'ci' keys.
        """
        series = self._preprocess_series(data)
        if series is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        mode_result = series.mode()
        if len(mode_result) == 0:
            logger.debug(f"No mode found for column '{self.column}' in table '{self.table}'")
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        mode_val = float(mode_result.iloc[0])
        ci = self._bootstrap_confidence_interval(
            series, mode_val, lambda x: float(x.mode().iloc[0]) if len(x.mode()) > 0 else np.nan
        )

        return {"value": mode_val, "ci": ci}


class VarianceStatistic(Statistic):
    """Calculate variance and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name.

        Returns:
            str: Statistic identifier used in reports.
        """
        return "variance"

    def calculate(self, data: pd.DataFrame) -> dict[str, Any]:
        """Calculate variance and confidence interval.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            dict[str, Any]: Dictionary with 'value' and 'ci' keys.
        """
        series = self._preprocess_series(data)
        if series is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        variance_val = float(series.var())
        ci = self._bootstrap_confidence_interval(series, variance_val, lambda x: x.var())

        return {"value": variance_val, "ci": ci}


class SkewnessStatistic(Statistic):
    """Calculate skewness and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name.

        Returns:
            str: Statistic identifier used in reports.
        """
        return "skewness"

    def calculate(self, data: pd.DataFrame) -> dict[str, Any]:
        """Calculate skewness and confidence interval.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            dict[str, Any]: Dictionary with 'value' and 'ci' keys.
        """
        series = self._preprocess_series(data)
        if series is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        skewness_val = float(stats.skew(series))
        ci = self._bootstrap_confidence_interval(series, skewness_val, lambda x: stats.skew(x))

        return {"value": skewness_val, "ci": ci}


class KurtosisStatistic(Statistic):
    """Calculate excess kurtosis and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name.

        Returns:
            str: Statistic identifier used in reports.
        """
        return "kurtosis"

    def calculate(self, data: pd.DataFrame) -> dict[str, Any]:
        """Calculate excess kurtosis and confidence interval.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            dict[str, Any]: Dictionary with 'value' and 'ci' keys.
        """
        series = self._preprocess_series(data)
        if series is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        kurtosis_val = float(stats.kurtosis(series, fisher=True))
        ci = self._bootstrap_confidence_interval(
            series, kurtosis_val, lambda x: stats.kurtosis(x, fisher=True)
        )

        return {"value": kurtosis_val, "ci": ci}


class RangeStatistic(Statistic):
    """Calculate range (min, max)."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name.

        Returns:
            str: Statistic identifier used in reports.
        """
        return "range"

    def calculate(self, data: pd.DataFrame) -> dict[str, Any]:
        """Calculate range (min and max values).

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            dict[str, Any]: Dictionary with 'value' as (min, max) tuple and 'ci' as same tuple.
        """
        series = self._preprocess_series(data)
        if series is None:
            return {"value": (np.nan, np.nan), "ci": (np.nan, np.nan)}

        min_val = float(series.min())
        max_val = float(series.max())
        range_tuple = (min_val, max_val)

        return {"value": range_tuple, "ci": range_tuple}


class QuantileStatistic(Statistic):
    """Calculate quantile and confidence interval."""

    def __init__(
        self,
        table: str,
        column: str,
        confidence_level: float,
        convert_to_categorical: bool = True,
        quantile: float = 0.5,
    ):
        """Initialize quantile statistic.

        Args:
            table (str): Table name.
            column (str): Column name.
            confidence_level (float): Confidence level for intervals.
            quantile (float): Quantile to compute (0.0 to 1.0). Default 0.5 (median).
        """
        super().__init__(table, column, confidence_level, convert_to_categorical)
        self.quantile = quantile

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name.

        Returns:
            str: Statistic identifier used in reports.
        """
        return "quantile"

    def calculate(self, data: pd.DataFrame) -> dict[str, Any]:
        """Calculate quantile and confidence interval.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            dict[str, Any]: Dictionary with 'value' and 'ci' keys.
        """
        series = self._preprocess_series(data)
        if series is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        quantile_val = float(series.quantile(self.quantile))
        ci = self._bootstrap_confidence_interval(
            series, quantile_val, lambda x: x.quantile(self.quantile)
        )

        return {"value": quantile_val, "ci": ci}


class FormulaStatistic(Statistic):
    """Calculate statistic from user-defined formula with bootstrap confidence interval."""

    # Whitelist of allowed functions for formula evaluation
    ALLOWED_FUNCTIONS = {
        "np": np,
        "pd": pd,
        "min": min,
        "max": max,
        "sum": sum,
        "mean": lambda x: x.mean(),
        "std": lambda x: x.std(),
        "var": lambda x: x.var(),
    }

    def __init__(
        self,
        table: str,
        column: str | None,
        confidence_level: float,
        formula: str,
        columns: dict[str, str] | None = None,
        convert_datetime: bool = True,
        convert_to_categorical: bool = True,
    ):
        """Initialize formula-based statistic.

        Args:
            table (str): Table name.
            column (str | None): Primary column name (for backward compatibility).
            confidence_level (float): Confidence level for intervals.
            formula (str): Formula string with {col_name} placeholders.
            columns (dict[str, str] | None): Mapping of placeholder names to actual column names.
                                             If None, uses 'col' as default placeholder for primary column.

        Raises:
            ValueError: If formula contains disallowed function names or syntax errors.
        """
        super().__init__(table, column, confidence_level, convert_to_categorical)
        self.formula = formula
        self.columns = columns or {"col": column}
        self.convert_datetime = convert_datetime
        self._validate_formula()

    def _validate_formula(self) -> None:
        """Validate formula syntax and detect disallowed functions.

        Raises:
            ValueError: If formula contains __import__, exec, eval, or other unsafe patterns.
        """
        forbidden_patterns = [
            "__import__",
            "exec",
            "eval",
            "__",
            "getattr",
            "setattr",
            "globals",
            "locals",
            "open",
            "compile",
            "input",
            "os",
            "sys",
            "subprocess",
        ]
        for pattern in forbidden_patterns:
            if pattern in self.formula:
                logger.error(f"Formula contains forbidden pattern: {pattern}")
                raise ValueError(f"Formula contains forbidden pattern: {pattern}")

        # Try to parse formula to catch syntax errors early
        try:
            compile(self.formula, "<formula>", "eval")
        except SyntaxError as e:
            logger.error(f"Formula syntax error: {e}")
            raise ValueError(f"Formula syntax error: {e}")

    def _preprocess_series_dict(self, data: pd.DataFrame) -> dict[str, pd.Series] | None:
        """Preprocess and validate multiple data series for formula substitution.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            dict[str, pd.Series] | None: Dict mapping placeholder names to cleaned series, or None if validation fails.
        """
        series_dict = {}

        for placeholder, col_name in self.columns.items():
            if col_name not in data.columns:
                logger.debug(
                    f"Column '{col_name}' (placeholder '{placeholder}') not found in table '{self.table}'"
                )
                return None

            series = data[col_name].dropna()
            if len(series) == 0:
                logger.debug(
                    f"No valid data for column '{col_name}' (placeholder '{placeholder}') in table '{self.table}' after removing NaN values"
                )
                return None

            # Convert datetime to numerical if needed
            if pd.api.types.is_datetime64_any_dtype(series) and self.convert_datetime:
                series = pd.to_numeric(series)

            if not pd.api.types.is_numeric_dtype(
                series
            ) and not pd.api.types.is_datetime64_any_dtype(series):
                logger.debug(
                    f"Column '{col_name}' (placeholder '{placeholder}') in table '{self.table}' is not numeric or datetime"
                )
                return None

            series_dict[placeholder] = series

        # also replace placeholders in formula with actual column names for evaluation
        for placeholder in series_dict.keys():
            self.formula = self.formula.replace(f"{{{placeholder}}}", placeholder)

        return series_dict

    def _evaluate_formula(self, series_dict: dict[str, pd.Series]) -> float:
        """Evaluate formula with series values.

        Args:
            series_dict (dict[str, pd.Series]): Mapping of placeholder names to series.

        Returns:
            float: Result of formula evaluation. Returns np.nan if evaluation fails.
        """
        try:
            safe_dict = self.ALLOWED_FUNCTIONS.copy()
            safe_dict.update(series_dict)

            result = eval(self.formula, {"__builtins__": {}}, safe_dict)

            # Handle Series results (convert to scalar)
            if isinstance(result, pd.Series):
                result = float(result.iloc[0]) if len(result) > 0 else np.nan
            else:
                result = float(result)

            return result

        except Exception as e:
            logger.warning(f"Formula evaluation failed: {e}. Formula: {self.formula}")
            return np.nan

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name.

        Returns:
            str: Statistic identifier used in reports.
        """
        return "custom_formula"

    def calculate(self, data: pd.DataFrame) -> dict[str, Any]:
        """Calculate formula-based statistic with confidence interval.

        Args:
            data (pd.DataFrame): Input data.

        Returns:
            dict[str, Any]: Dictionary with 'value' and 'ci' keys.
        """
        series_dict = self._preprocess_series_dict(data)
        if series_dict is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        # Calculate value with full dataset
        value = self._evaluate_formula(series_dict)
        if np.isnan(value):
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        # Bootstrap confidence interval
        primary_series = series_dict[list(self.columns.keys())[0]]
        n = len(primary_series)

        def bootstrap_formula_func(indices):
            """Apply formula to bootstrap-resampled data."""
            bootstrap_dict = {}
            for placeholder, series in series_dict.items():
                bootstrap_dict[placeholder] = series.iloc[indices].reset_index(drop=True)
            return self._evaluate_formula(bootstrap_dict)

        # Generate bootstrap samples
        bootstrap_values = []

        for _ in range(NUM_BOOTSTRAP_SAMPLES):
            indices = np.random.choice(n, size=n, replace=True)
            bootstrap_val = bootstrap_formula_func(indices)
            if not np.isnan(bootstrap_val):
                bootstrap_values.append(bootstrap_val)

        if len(bootstrap_values) == 0:
            return {"value": value, "ci": (value, value)}

        # Calculate confidence interval from bootstrap samples
        alpha = 1 - self.confidence_level
        lower_percentile = (alpha / 2) * 100
        upper_percentile = (1 - alpha / 2) * 100

        ci_lower = np.percentile(bootstrap_values, lower_percentile)
        ci_upper = np.percentile(bootstrap_values, upper_percentile)

        return {"value": value, "ci": (ci_lower, ci_upper)}


statistic_map = {
    "mean": MeanStatistic,
    "median": MedianStatistic,
    "mode": ModeStatistic,
    "variance": VarianceStatistic,
    "skewness": SkewnessStatistic,
    "kurtosis": KurtosisStatistic,
    # "range": RangeStatistic,
    "quantile": QuantileStatistic,
    "custom_formula": FormulaStatistic,
}


def create_statistic(
    confidence_level: float, config: dict[str, Any], custom_statistic_map: dict | None = None
) -> Statistic:
    """Factory function to create statistics from configuration.

    Args:
        confidence_level (float): Confidence level for intervals.
        config (Dict[str, Any]): Configuration dictionary with ``operation``, ``table``, and
            optional ``col`` keys. Additional keys are passed as kwargs to the
            statistic constructor when applicable.
        custom_statistic_map (dict | None): Optional mapping of custom operation names to Statistic classes.

    Returns:
        Statistic: Appropriate statistic instance.

    Raises:
        ValueError: If operation not found or instantiation fails.
    """
    operation = config["operation"]
    table = config["table"]
    column = config.get("col", None)
    convert_to_categorical = config.get("convert_to_categorical", True)

    # Combine built-in and custom statistic maps
    combined_map = {**statistic_map}
    if custom_statistic_map:
        combined_map.update(custom_statistic_map)

    if operation not in combined_map:
        raise ValueError(f"Unknown statistic operation: {operation}")

    statistic_class = combined_map[operation]

    # Extract extra params, excluding those we handle specially
    extra_params = {
        k: v
        for k, v in config.items()
        if k not in ["operation", "table", "col", "convert_to_categorical", "convert_datetime"]
    }

    try:
        if operation == "quantile":
            quantile = config.get("quantile", 0.5)
            return statistic_class(
                table,
                column,
                confidence_level,
                convert_to_categorical=convert_to_categorical,
                quantile=quantile,
            )
        elif operation == "custom_formula":
            formula = config.get("formula")
            if not formula:
                raise ValueError("custom_formula operation requires 'formula' parameter")
            # Support both single column (formula uses {col}) or multiple columns
            columns = config.get("columns")  # Optional: {'col': 'col_name', 'col2': 'other_col'}
            convert_datetime = config.get("convert_datetime", True)
            return statistic_class(
                table,
                column,
                confidence_level,
                formula=formula,
                columns=columns,
                convert_datetime=convert_datetime,
            )
        else:
            # Generic handler for other custom statistics with extra params
            return statistic_class(
                table,
                column,
                confidence_level,
                convert_to_categorical=convert_to_categorical,
                **extra_params,
            )
    except TypeError as e:
        raise ValueError(f"Failed to instantiate {operation} statistic: {e}")
