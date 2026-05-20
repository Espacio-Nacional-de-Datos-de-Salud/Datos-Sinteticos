from abc import ABC, abstractmethod
from collections.abc import Callable
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats

from backend.src.config.evaluation import NUM_BOOTSTRAP_SAMPLES
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


# Bootstrap is run in chunks so the transient (chunk, n) index matrix stays
# bounded regardless of dataset size: at chunk_size=256 and n=100_000 this
# is ~205 MB (int64). Tune downward if memory pressure surfaces in practice.
_BOOTSTRAP_CHUNK_SIZE: int = 256


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

    def bootstrap_signature(self) -> tuple | None:
        """Identify the data series this statistic bootstraps over.

        Returns a hashable signature when the statistic operates on a single
        column drawn from ``self.column`` — used by ``ConfidenceIntervalOverlap``
        to share resampling work across statistics that target the same series.
        Returning ``None`` opts the statistic out of sharing (multi-column or
        custom-data statistics).
        """
        if self.column is None:
            return None
        return (self.table, self.column, self.convert_to_categorical)

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

    def _percentile_ci(self, bootstrap_values: np.ndarray) -> tuple[float, float]:
        """Reduce a 1D array of bootstrap statistics to a percentile CI."""
        alpha = 1 - self.confidence_level
        lower_percentile = (alpha / 2) * 100
        upper_percentile = (1 - alpha / 2) * 100
        bootstrap_values = bootstrap_values[~np.isnan(bootstrap_values)]
        if bootstrap_values.size == 0:
            return (float("nan"), float("nan"))
        return (
            float(np.percentile(bootstrap_values, lower_percentile)),
            float(np.percentile(bootstrap_values, upper_percentile)),
        )

    def _vectorized_bootstrap_ci(
        self,
        values: np.ndarray,
        vec_stat_func: Callable[[np.ndarray], np.ndarray],
        bootstrap_rng_seed: int | None = None,
        num_samples: int | None = None,
        chunk_size: int = _BOOTSTRAP_CHUNK_SIZE,
    ) -> tuple[float, float]:
        """Vectorised percentile bootstrap CI.

        Resamples ``values`` in chunks of ``chunk_size`` bootstraps at a time
        and applies ``vec_stat_func`` to each chunked ``(chunk, n)`` matrix
        along ``axis=1``. Chunking caps the transient memory footprint while
        keeping the inner loop fully vectorised.

        Args:
            values: 1D array of the underlying series.
            vec_stat_func: Callable mapping a ``(chunk, n)`` array to a
                ``(chunk,)`` array of bootstrap statistics.
            bootstrap_rng_seed: Optional seed. When two statistics on the
                same series share a seed they draw identical resamples,
                which is how :class:`ConfidenceIntervalOverlap` shares work.
            num_samples: Override for ``NUM_BOOTSTRAP_SAMPLES``.
            chunk_size: Bootstraps per chunk; tune for memory.
        """
        n = len(values)
        if n < 2:
            return (float("nan"), float("nan"))

        B = num_samples if num_samples is not None else NUM_BOOTSTRAP_SAMPLES
        rng = np.random.default_rng(bootstrap_rng_seed)

        bootstrap_stats: list[np.ndarray] = []
        for start in range(0, B, chunk_size):
            stop = min(start + chunk_size, B)
            idx_chunk = rng.integers(0, n, size=(stop - start, n), dtype=np.int64)
            samples_2d = values[idx_chunk]
            stat_chunk = np.asarray(vec_stat_func(samples_2d), dtype=np.float64).ravel()
            bootstrap_stats.append(stat_chunk)

        return self._percentile_ci(np.concatenate(bootstrap_stats))

    def _bootstrap_confidence_interval(
        self,
        data: pd.Series,
        statistic_value: float,
        statistic_func,
    ) -> tuple[float, float]:
        """Legacy bootstrap CI helper kept for user-defined custom statistics.

        Replaced internally by :meth:`_vectorized_bootstrap_ci`. This wrapper
        survives so existing custom statistics that pass a ``pd.Series``-taking
        callable continue to work, but each draw still incurs Python-level
        overhead — prefer the vectorised path for new statistics.

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

        values = data.to_numpy()
        rng = np.random.default_rng()
        bootstrap_statistics: list[float] = []

        for start in range(0, NUM_BOOTSTRAP_SAMPLES, _BOOTSTRAP_CHUNK_SIZE):
            stop = min(start + _BOOTSTRAP_CHUNK_SIZE, NUM_BOOTSTRAP_SAMPLES)
            idx_chunk = rng.integers(0, n, size=(stop - start, n), dtype=np.int64)
            for row in idx_chunk:
                sample = pd.Series(values[row])
                bootstrap_statistics.append(statistic_func(sample))

        return self._percentile_ci(np.asarray(bootstrap_statistics, dtype=np.float64))

    # ------------------------------------------------------------------
    # Shared-bootstrap protocol
    #
    # Statistics that implement ``_scalar_stat`` and ``_vec_stat`` opt in to
    # the shared chunked bootstrap path driven by
    # :meth:`ConfidenceIntervalOverlap.evaluate`. The orchestrator generates
    # ``(chunk, n)`` resamples once per chunk and feeds the same matrix to
    # every statistic in the group, so the dominant cost — materialising
    # ``values[indices]`` — is paid once instead of once per statistic.
    #
    # Statistics that do not implement these (mode, formula, age) fall back
    # to per-stat ``calculate(data, bootstrap_rng_seed=...)``.
    # ------------------------------------------------------------------

    def _scalar_stat(self, values: np.ndarray) -> float:
        """Central estimate from the full 1D values array (no resampling)."""
        raise NotImplementedError

    def _vec_stat(self, samples_2d: np.ndarray) -> np.ndarray:
        """Statistic applied across ``axis=1`` of a ``(chunk, n)`` matrix."""
        raise NotImplementedError

    def supports_shared_bootstrap(self) -> bool:
        """Whether this statistic implements the shared-bootstrap protocol.

        Subclasses opting in should override both ``_scalar_stat`` and
        ``_vec_stat`` and return ``True`` here.
        """
        return False

    @abstractmethod
    def calculate(
        self,
        data: pd.DataFrame,
        bootstrap_rng_seed: int | None = None,
    ) -> dict[str, Any]:
        """Calculate statistic and confidence interval.

        Args:
            data (pd.DataFrame): Input data.
            bootstrap_rng_seed (int | None): When provided, seeds the bootstrap
                RNG so multiple statistics on the same series share resamples.

        Returns:
            Dict[str, Any]: Dictionary with 'value' and 'ci' keys.
        """
        pass


def _vectorized_mode(samples_2d: np.ndarray) -> np.ndarray:
    """Per-row mode of a (B, n) matrix, picking the smallest value on ties."""
    result, _ = stats.mode(samples_2d, axis=1, keepdims=False)
    return result.astype(np.float64, copy=False)


def _default_calculate(
    self: Statistic,
    data: pd.DataFrame,
    bootstrap_rng_seed: int | None = None,
) -> dict[str, Any]:
    """Shared ``calculate`` for stats that implement the shared-bootstrap protocol."""
    series = self._preprocess_series(data)
    if series is None:
        return {"value": np.nan, "ci": (np.nan, np.nan)}
    values = series.to_numpy()
    return {
        "value": self._scalar_stat(values),
        "ci": self._vectorized_bootstrap_ci(values, self._vec_stat, bootstrap_rng_seed),
    }


class MeanStatistic(Statistic):
    """Calculate mean and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "mean"

    def supports_shared_bootstrap(self) -> bool:
        return True

    def _scalar_stat(self, values: np.ndarray) -> float:
        return float(values.mean())

    def _vec_stat(self, samples_2d: np.ndarray) -> np.ndarray:
        return samples_2d.mean(axis=1)

    calculate = _default_calculate


class MedianStatistic(Statistic):
    """Calculate median and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "median"

    def supports_shared_bootstrap(self) -> bool:
        return True

    def _scalar_stat(self, values: np.ndarray) -> float:
        return float(np.median(values))

    def _vec_stat(self, samples_2d: np.ndarray) -> np.ndarray:
        return np.median(samples_2d, axis=1)

    calculate = _default_calculate


class ModeStatistic(Statistic):
    """Calculate mode and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "mode"

    def supports_shared_bootstrap(self) -> bool:
        return True

    def _scalar_stat(self, values: np.ndarray) -> float:
        mode_result, _ = stats.mode(values, keepdims=False)
        return float(mode_result)

    def _vec_stat(self, samples_2d: np.ndarray) -> np.ndarray:
        return _vectorized_mode(samples_2d)

    def calculate(
        self,
        data: pd.DataFrame,
        bootstrap_rng_seed: int | None = None,
    ) -> dict[str, Any]:
        """Calculate mode and confidence interval."""
        series = self._preprocess_series(data)
        if series is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        # Preserve the original "smallest-on-ties" semantics from pandas mode().
        mode_result = series.mode()
        if len(mode_result) == 0:
            logger.debug(f"No mode found for column '{self.column}' in table '{self.table}'")
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        values = series.to_numpy()
        mode_val = float(mode_result.iloc[0])
        ci = self._vectorized_bootstrap_ci(values, self._vec_stat, bootstrap_rng_seed)
        return {"value": mode_val, "ci": ci}


class VarianceStatistic(Statistic):
    """Calculate variance and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "variance"

    def supports_shared_bootstrap(self) -> bool:
        return True

    def _scalar_stat(self, values: np.ndarray) -> float:
        # ddof=1 matches pandas' default `Series.var()`.
        return float(np.var(values, ddof=1))

    def _vec_stat(self, samples_2d: np.ndarray) -> np.ndarray:
        return np.var(samples_2d, axis=1, ddof=1)

    calculate = _default_calculate


class SkewnessStatistic(Statistic):
    """Calculate skewness and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "skewness"

    def supports_shared_bootstrap(self) -> bool:
        return True

    def _scalar_stat(self, values: np.ndarray) -> float:
        return float(stats.skew(values))

    def _vec_stat(self, samples_2d: np.ndarray) -> np.ndarray:
        return stats.skew(samples_2d, axis=1)

    calculate = _default_calculate


class KurtosisStatistic(Statistic):
    """Calculate excess kurtosis and confidence interval."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "kurtosis"

    def supports_shared_bootstrap(self) -> bool:
        return True

    def _scalar_stat(self, values: np.ndarray) -> float:
        return float(stats.kurtosis(values, fisher=True))

    def _vec_stat(self, samples_2d: np.ndarray) -> np.ndarray:
        return stats.kurtosis(samples_2d, axis=1, fisher=True)

    calculate = _default_calculate


class RangeStatistic(Statistic):
    """Calculate range (min, max)."""

    @staticmethod
    def name() -> str:
        """Return the canonical statistic name."""
        return "range"

    def calculate(
        self,
        data: pd.DataFrame,
        bootstrap_rng_seed: int | None = None,
    ) -> dict[str, Any]:
        """Calculate range (min and max values).

        Note: deterministic on the input — no bootstrap.
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

    def supports_shared_bootstrap(self) -> bool:
        return True

    def _scalar_stat(self, values: np.ndarray) -> float:
        return float(np.quantile(values, self.quantile))

    def _vec_stat(self, samples_2d: np.ndarray) -> np.ndarray:
        return np.quantile(samples_2d, self.quantile, axis=1)

    # ``bootstrap_signature`` (table, column, convert_to_categorical) is inherited:
    # two quantile stats on the same column with different ``quantile`` values
    # still resample the same series, so they belong in the same shared group.

    calculate = _default_calculate


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

    def bootstrap_signature(self) -> tuple | None:
        """Formula statistics span multiple columns and opt out of sharing."""
        return None

    def calculate(
        self,
        data: pd.DataFrame,
        bootstrap_rng_seed: int | None = None,
    ) -> dict[str, Any]:
        """Calculate formula-based statistic with confidence interval."""
        series_dict = self._preprocess_series_dict(data)
        if series_dict is None:
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        # Calculate value with full dataset
        value = self._evaluate_formula(series_dict)
        if np.isnan(value):
            return {"value": np.nan, "ci": (np.nan, np.nan)}

        # Bootstrap confidence interval. The formula evaluator works on
        # pd.Series instances (its ALLOWED_FUNCTIONS call ``x.mean()`` etc.),
        # so we resample with numpy indices but materialise one Series per
        # placeholder per draw. Indices are batched in chunks via a shared
        # RNG for memory bounds and reproducibility.
        primary_series = series_dict[list(self.columns.keys())[0]]
        n = len(primary_series)
        if n < 2:
            return {"value": value, "ci": (value, value)}

        np_dict = {ph: s.to_numpy() for ph, s in series_dict.items()}
        rng = np.random.default_rng(bootstrap_rng_seed)
        bootstrap_values: list[float] = []

        for start in range(0, NUM_BOOTSTRAP_SAMPLES, _BOOTSTRAP_CHUNK_SIZE):
            stop = min(start + _BOOTSTRAP_CHUNK_SIZE, NUM_BOOTSTRAP_SAMPLES)
            idx_chunk = rng.integers(0, n, size=(stop - start, n), dtype=np.int64)
            for row in idx_chunk:
                resampled = {ph: pd.Series(arr[row]) for ph, arr in np_dict.items()}
                val = self._evaluate_formula(resampled)
                if not np.isnan(val):
                    bootstrap_values.append(val)

        if not bootstrap_values:
            return {"value": value, "ci": (value, value)}

        return {
            "value": value,
            "ci": self._percentile_ci(np.asarray(bootstrap_values, dtype=np.float64)),
        }


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
