"""Confidence Interval Overlap metric.

For each configured statistic (mean, median, variance, etc.), computes a
confidence interval on both the real and synthetic data and reports the
overlap ratio. The final score is the mean overlap across all statistics.
"""

import importlib

import numpy as np
import pandas as pd
import yaml
from config.evaluation.evaluation_config import (
    CONFIDENCE_INTERVAL_LEVEL,
    CUSTOM_STATISTICS_MODULE,
    STATISTICS_CONFIG_PATH,
)

from src.core.logging_config import get_logger
from src.evaluation.custom_metrics.base import MetricEvaluator
from src.evaluation.statistics import Statistic, create_statistic

logger = get_logger(__name__)


class ConfidenceIntervalOverlap(MetricEvaluator):
    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            statistics_config_path (str): Path to statistics configuration file (optional).
            custom_statistics_module (str): Path to custom statistics module (optional).
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)
        self.custom_statistics_module = kwargs.get("custom_statistics_module")
        self.statistics = self._load_statistics()

    def _load_custom_statistics(self) -> dict | None:
        """Load custom statistics from configured module.

        Returns:
            dict | None: Mapping of operation names to Statistic classes, or None if not configured.
        """
        module_path = self.custom_statistics_module or CUSTOM_STATISTICS_MODULE

        if not module_path:
            return None

        try:
            module = importlib.import_module(module_path)

            if hasattr(module, "CUSTOM_STATISTIC_MAP"):
                custom_map = module.CUSTOM_STATISTIC_MAP
                logger.debug(f"Loaded {len(custom_map)} custom statistics from {module_path}")
                return custom_map
            else:
                logger.warning(f"Module {module_path} does not contain CUSTOM_STATISTIC_MAP")
                return None
        except ImportError as e:
            logger.error(f"Could not import custom statistics module {module_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading custom statistics from {module_path}: {e}")
            return None

    def _load_statistics(self) -> list[Statistic]:
        """Load statistics from configuration file and optionally custom statistics.

        Returns:
            List[Statistic]: List of configured statistics.
        """
        custom_stats = self._load_custom_statistics()

        try:
            with open(STATISTICS_CONFIG_PATH) as f:
                config = yaml.safe_load(f)

            statistics = []
            for stat_config in config.get("statistics", []):
                try:
                    stat = create_statistic(
                        CONFIDENCE_INTERVAL_LEVEL, stat_config, custom_statistic_map=custom_stats
                    )
                    statistics.append(stat)
                except ValueError as e:
                    logger.error(f"Failed to create statistic from config {stat_config}: {e}")
                    continue

            return statistics
        except FileNotFoundError:
            logger.error(f"Could not find statistics config at path {STATISTICS_CONFIG_PATH}")
            return []
        except Exception as e:
            logger.error(f"Error loading statistics configuration: {e}")
            return []

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "confidence_interval_overlap"

    def _calculate_overlap(self, ci1: tuple, ci2: tuple) -> float:
        """Calculate overlap between two confidence intervals.

        Args:
            ci1 (tuple): First confidence interval (lower, upper).
            ci2 (tuple): Second confidence interval (lower, upper).

        Returns:
            float: Overlap ratio (0 to 1).
        """
        if any(np.isnan([ci1[0], ci1[1], ci2[0], ci2[1]])):
            logger.debug("Could not calculate confidence level: NaN")
            return 0.0

        overlap_start = max(ci1[0], ci2[0])
        overlap_end = min(ci1[1], ci2[1])

        if overlap_start >= overlap_end:
            return 0.0

        overlap_length = overlap_end - overlap_start
        total_length = max(ci1[1], ci2[1]) - min(ci1[0], ci2[0])

        return overlap_length / total_length if total_length > 0 else 0.0

    def _compute_statistic_overlap(
        self,
        statistic: Statistic,
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        real_processed: pd.DataFrame,
        synthetic_processed: pd.DataFrame,
    ) -> tuple[float, dict] | None:
        """Compute the CI overlap for a single statistic.

        Picks encoded or raw data depending on whether the statistic requires
        categorical conversion, then builds the detail record used in reports.

        Args:
            statistic (Statistic): Statistic to evaluate.
            real_data (pd.DataFrame): Raw reference dataset.
            synthetic_data (pd.DataFrame): Raw synthetic dataset.
            real_processed (pd.DataFrame): Label-encoded reference dataset.
            synthetic_processed (pd.DataFrame): Label-encoded synthetic dataset.

        Returns:
            tuple[float, dict] | None: ``(overlap, detail_entry)`` or ``None``
            if the statistic failed to run.
        """
        try:
            logger.debug(f"Running statistic {statistic.name()}")
            if statistic.valueConvertCategorical():
                real_result = statistic.calculate(real_processed)
                synthetic_result = statistic.calculate(synthetic_processed)
            else:
                real_result = statistic.calculate(real_data)
                synthetic_result = statistic.calculate(synthetic_data)

            overlap = self._calculate_overlap(real_result["ci"], synthetic_result["ci"])
            detail_entry = {
                "overlap": overlap,
                "real_ci_lower": real_result["ci"][0],  # split for mlflow
                "real_ci_upper": real_result["ci"][1],
                "synthetic_ci_lower": synthetic_result["ci"][0],
                "synthetic_ci_upper": synthetic_result["ci"][1],
                "real_value": real_result["value"],
                "synthetic_value": synthetic_result["value"],
            }
            return overlap, detail_entry
        except Exception as e:
            logger.error(f"Failed to run statistic metric {statistic.name()}, error: {e}")
            return None

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute confidence interval overlap for configured statistics.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with overall score and detailed results per statistic.
        """
        if len(self.statistics) == 0:
            logger.debug("No statistics configured.")
            return {"score": 0.0}

        real_processed, synthetic_processed = self._encode_categorical_columns(
            real_data, synthetic_data
        )

        overlaps: list[float] = []
        details: dict[str, dict] = {}

        for statistic in self.statistics:
            result = self._compute_statistic_overlap(
                statistic, real_data, synthetic_data, real_processed, synthetic_processed
            )
            if result is None:
                continue
            overlap, detail_entry = result
            overlaps.append(overlap)
            key = f"{statistic.table}_{statistic.column}_{type(statistic).__name__}"
            details[key] = detail_entry

        overall_score = np.mean(overlaps) if overlaps else 0.0

        return {"score": float(overall_score), "additional": details, "direction": "maximize"}
