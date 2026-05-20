"""Confidence Interval Overlap metric.

For each configured statistic (mean, median, variance, etc.), computes a
confidence interval on both the real and synthetic data and reports the
overlap ratio. The final score is the mean overlap across all statistics.
"""

import importlib
from collections import defaultdict

import numpy as np
import pandas as pd
import yaml

from backend.src.config.evaluation import (
    CONFIDENCE_INTERVAL_LEVEL,
    CUSTOM_STATISTICS_MODULE,
    NUM_BOOTSTRAP_SAMPLES,
)
from backend.src.domain.evaluation.custom_metrics.base import MetricEvaluator
from backend.src.domain.evaluation.statistics import (
    _BOOTSTRAP_CHUNK_SIZE,
    Statistic,
    create_statistic,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.sessions.configs import resolve_config_path

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

        statistics_config_path = resolve_config_path("statistics")
        try:
            with open(statistics_config_path) as f:
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
            logger.error(f"Could not find statistics config at path {statistics_config_path}")
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
        seed_real: int | None = None,
        seed_syn: int | None = None,
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
            seed_real (int | None): Bootstrap RNG seed for the real-data CI.
                Statistics sharing the same seed draw identical resamples.
            seed_syn (int | None): Bootstrap RNG seed for the synthetic-data CI.

        Returns:
            tuple[float, dict] | None: ``(overlap, detail_entry)`` or ``None``
            if the statistic failed to run.
        """
        try:
            logger.debug(f"Running statistic {statistic.name()}")
            if statistic.valueConvertCategorical():
                real_result = statistic.calculate(real_processed, bootstrap_rng_seed=seed_real)
                synthetic_result = statistic.calculate(
                    synthetic_processed, bootstrap_rng_seed=seed_syn
                )
            else:
                real_result = statistic.calculate(real_data, bootstrap_rng_seed=seed_real)
                synthetic_result = statistic.calculate(synthetic_data, bootstrap_rng_seed=seed_syn)

            overlap = self._calculate_overlap(real_result["ci"], synthetic_result["ci"])
            detail_entry = {
                "overlap": overlap,
                "real_ci_lower": real_result["ci"][0],
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

        Statistics that share a :meth:`Statistic.bootstrap_signature` (same
        column with the same encoding) AND implement the shared-bootstrap
        protocol are run through a single chunked-pipeline pass: each
        ``(chunk, n)`` resample matrix is materialised once and consumed by
        every statistic in the group, instead of each statistic allocating
        its own. This is what eliminates the dominant cost at large ``n``.

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

        shared_groups, unshared = self._partition_for_shared_bootstrap()

        for group in shared_groups:
            group_results = self._run_shared_group(
                group, real_data, synthetic_data, real_processed, synthetic_processed
            )
            for statistic, detail_entry in group_results:
                overlaps.append(detail_entry["overlap"])
                key = f"{statistic.table}_{statistic.column}_{type(statistic).__name__}"
                details[key] = detail_entry

        for statistic in unshared:
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

    # ------------------------------------------------------------------
    # Shared chunked-bootstrap path
    # ------------------------------------------------------------------

    def _partition_for_shared_bootstrap(
        self,
    ) -> tuple[list[list[Statistic]], list[Statistic]]:
        """Bucket statistics into shared-bootstrap groups and the unshared rest.

        A statistic joins a group when both ``supports_shared_bootstrap`` is
        true and its ``bootstrap_signature`` is non-None. Groups of size 1
        still go through the shared path — the cost is the same as the
        legacy per-stat path and the code is simpler.
        """
        groups: dict[tuple, list[Statistic]] = defaultdict(list)
        unshared: list[Statistic] = []
        for statistic in self.statistics:
            signature = statistic.bootstrap_signature()
            if signature is None or not statistic.supports_shared_bootstrap():
                unshared.append(statistic)
                continue
            groups[signature].append(statistic)
        return list(groups.values()), unshared

    def _run_shared_group(
        self,
        group: list[Statistic],
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        real_processed: pd.DataFrame,
        synthetic_processed: pd.DataFrame,
    ) -> list[tuple[Statistic, dict]]:
        """Run one chunked-pipeline bootstrap for every statistic in a group."""
        head = group[0]
        # All statistics in the group share signature so the picked frame and
        # preprocessing match for every member.
        if head.valueConvertCategorical():
            real_frame, syn_frame = real_processed, synthetic_processed
        else:
            real_frame, syn_frame = real_data, synthetic_data

        real_series = head._preprocess_series(real_frame)
        syn_series = head._preprocess_series(syn_frame)
        if real_series is None or syn_series is None:
            # Defer to the per-stat path so each one logs its own failure.
            results: list[tuple[Statistic, dict]] = []
            for statistic in group:
                outcome = self._compute_statistic_overlap(
                    statistic, real_data, synthetic_data, real_processed, synthetic_processed
                )
                if outcome is not None:
                    _, detail = outcome
                    results.append((statistic, detail))
            return results

        real_values = real_series.to_numpy()
        syn_values = syn_series.to_numpy()
        n_real, n_syn = real_values.size, syn_values.size

        rng = np.random.default_rng()
        real_boot, syn_boot = self._run_chunked_pipeline(
            group, real_values, syn_values, n_real, n_syn, rng
        )

        results = []
        for statistic in group:
            try:
                real_value = statistic._scalar_stat(real_values)
                syn_value = statistic._scalar_stat(syn_values)
                real_ci = statistic._percentile_ci(np.concatenate(real_boot[id(statistic)]))
                syn_ci = statistic._percentile_ci(np.concatenate(syn_boot[id(statistic)]))
            except Exception as exc:
                logger.error(
                    "Failed to run statistic %s in shared group: %s",
                    statistic.name(),
                    exc,
                )
                continue

            overlap = self._calculate_overlap(real_ci, syn_ci)
            detail_entry = {
                "overlap": overlap,
                "real_ci_lower": real_ci[0],
                "real_ci_upper": real_ci[1],
                "synthetic_ci_lower": syn_ci[0],
                "synthetic_ci_upper": syn_ci[1],
                "real_value": real_value,
                "synthetic_value": syn_value,
            }
            results.append((statistic, detail_entry))
        return results

    @staticmethod
    def _run_chunked_pipeline(
        group: list[Statistic],
        real_values: np.ndarray,
        syn_values: np.ndarray,
        n_real: int,
        n_syn: int,
        rng: np.random.Generator,
        chunk_size: int = _BOOTSTRAP_CHUNK_SIZE,
    ) -> tuple[dict[int, list[np.ndarray]], dict[int, list[np.ndarray]]]:
        """Materialise each ``(chunk, n)`` sample matrix once and fan it out
        to every statistic in the group on both the real and synthetic side.
        """
        real_boot: dict[int, list[np.ndarray]] = {id(s): [] for s in group}
        syn_boot: dict[int, list[np.ndarray]] = {id(s): [] for s in group}

        for start in range(0, NUM_BOOTSTRAP_SAMPLES, chunk_size):
            chunk = min(chunk_size, NUM_BOOTSTRAP_SAMPLES - start)

            idx_real = rng.integers(0, n_real, size=(chunk, n_real), dtype=np.int64)
            samples_real = real_values[idx_real]
            for statistic in group:
                real_boot[id(statistic)].append(
                    np.asarray(statistic._vec_stat(samples_real), dtype=np.float64).ravel()
                )
            del samples_real, idx_real

            idx_syn = rng.integers(0, n_syn, size=(chunk, n_syn), dtype=np.int64)
            samples_syn = syn_values[idx_syn]
            for statistic in group:
                syn_boot[id(statistic)].append(
                    np.asarray(statistic._vec_stat(samples_syn), dtype=np.float64).ravel()
                )
            del samples_syn, idx_syn

        return real_boot, syn_boot
