"""End-to-end evaluation runner.

``EvaluationRunner.run`` is the single entry point for evaluating a real /
synthetic data pair. It executes synthcity's built-in metrics and the
project's custom metrics, returning a unified report DataFrame. Persisting
results locally is the responsibility of ``EvaluationTracker`` — this
class is purely about computing the report.
"""

import os

import pandas as pd
import synthcity.logger as synthcity_log

import backend.src.config.general as general_config
from backend.src.config.evaluation import (
    DROP_ID_COLUMNS_FROM_METRICS,
    EVAL_DEFAULT_METRICS,
)
from backend.src.domain.evaluation._custom_metrics import run_custom_metrics
from backend.src.domain.evaluation._synthcity_metrics import (
    build_data_loaders,
    evaluate_synthcity_metrics,
)
from backend.src.domain.evaluation.dtype_alignment import align_dtypes
from backend.src.domain.evaluation.utils import filter_id_columns
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import ProfilerPhase
from backend.src.infrastructure.time_profiling import profiler

logger = get_logger(__name__)


class EvaluationRunner:
    """Compute fidelity/privacy/detection metrics for a real/synthetic data pair.

    Args:
        eval_results_dir (str): Directory used to host the synthcity log file
            and the synthcity workspace cache. Output reports are written by
            ``EvaluationTracker``, not by this class.
        metrics (dict[str, list[str]] | None): Metric groups to run. Defaults
            to ``EVAL_DEFAULT_METRICS``.
    """

    def __init__(self, eval_results_dir: str, metrics: dict[str, list[str]] | None = None) -> None:
        self.eval_results_dir = eval_results_dir
        self.metrics = metrics or EVAL_DEFAULT_METRICS

        synthcity_log_path = os.path.join(
            eval_results_dir, f"synthcity_{general_config.get_run_timestamp()}.log"
        )
        synthcity_log.add(sink=synthcity_log_path, level="INFO")
        self.synthcity_workspace = os.path.join(eval_results_dir, "workspace")

    def run(
        self,
        real_data_dict: dict[str, pd.DataFrame],
        synthetic_data_dict: dict[str, pd.DataFrame],
        target_column: str | None = None,
        task_type: str = "classification",
        metadata_path: str | None = None,
    ) -> pd.DataFrame:
        """Run all configured metrics against the first table in each dict.

        Args:
            real_data_dict (dict[str, pd.DataFrame]): Mapping of table name to real data.
            synthetic_data_dict (dict[str, pd.DataFrame]): Mapping of table name to synthetic data.
            target_column (str | None): Optional target column for performance metrics.
            task_type (str): Task type for performance metrics
                (``classification`` / ``regression`` / ``survival_analysis``).
            metadata_path (str | None): Path to ``metadata.json`` used to drop
                ID columns when ``DROP_ID_COLUMNS_FROM_METRICS`` is enabled.

        Returns:
            pd.DataFrame: Report with one row per metric.
        """
        real_data, synthetic_data = self._select_first_table(
            real_data_dict, synthetic_data_dict, metadata_path
        )

        synthcity_metrics, custom_metric_names = self._partition_requested_metrics(target_column)

        loader_real, loader_syn = build_data_loaders(real_data, synthetic_data, target_column)

        logger.info("Running metrics: %s", list(synthcity_metrics.keys()))
        try:
            with profiler.phase(ProfilerPhase.SYNTHCITY_METRICS):
                report = evaluate_synthcity_metrics(
                    loader_real,
                    loader_syn,
                    metrics=synthcity_metrics,
                    task_type=task_type,
                    workspace_path=self.synthcity_workspace,
                )
        except Exception:
            logger.error("Error during synthcity metrics evaluation.", exc_info=True)
            raise

        if custom_metric_names:
            report = run_custom_metrics(
                real_data,
                synthetic_data,
                report,
                custom_metric_names,
                real_data_dict=real_data_dict,
                synthetic_data_dict=synthetic_data_dict,
            )

        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _select_first_table(
        self,
        real_data_dict: dict[str, pd.DataFrame],
        synthetic_data_dict: dict[str, pd.DataFrame],
        metadata_path: str | None,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Pick the single table evaluated, strip ID columns, and align dtypes."""
        real_data = next(iter(real_data_dict.values()))
        synthetic_data = next(iter(synthetic_data_dict.values()))

        if DROP_ID_COLUMNS_FROM_METRICS:
            real_data = filter_id_columns(real_data, metadata_path)
            synthetic_data = filter_id_columns(synthetic_data, metadata_path)

        real_data, synthetic_data = align_dtypes(real_data, synthetic_data)
        return real_data, synthetic_data

    def _partition_requested_metrics(
        self, target_column: str | None
    ) -> tuple[dict[str, list[str]], list[str]]:
        """Split configured metrics into a synthcity dict and a custom-name list.

        Also handles two project-specific overrides:

        - ``performance`` is dropped when no target column is provided.
        - ``k-anonymization`` and ``distinct l-diversity`` are replaced by
          project custom metrics that use configured quasi-identifier subsets.
        """
        synthcity_metrics = {k: list(v) for k, v in self.metrics.items()}
        custom_metric_names = list(synthcity_metrics.pop("custom", []))

        if not target_column and "performance" in synthcity_metrics:
            if synthcity_metrics["performance"]:
                logger.info("No 'target_column' provided. Skipping 'performance' metrics.")
            del synthcity_metrics["performance"]

        privacy_metrics = synthcity_metrics.get("privacy", [])
        if "k-anonymization" in privacy_metrics:
            logger.info(
                "Replacing synthcity 'k-anonymization' with custom subset-aware k_anonymity."
            )
            privacy_metrics.remove("k-anonymization")
            if "k_anonymity" not in custom_metric_names:
                custom_metric_names.append("k_anonymity")

        if "distinct l-diversity" in privacy_metrics:
            logger.info("Running 'distinct l-diversity' with custom PyCanon l_diversity.")
            privacy_metrics.remove("distinct l-diversity")
            if "l_diversity_pycanon" not in custom_metric_names:
                custom_metric_names.append("l_diversity_pycanon")

        sanity_metrics = synthcity_metrics.get("sanity", [])
        if "exact_match_rows" in sanity_metrics:
            logger.info("Replacing synthcity 'exact_match_rows' with custom ExactMatchRows.")
            sanity_metrics.remove("exact_match_rows")
            if "exact_match_rows" not in custom_metric_names:
                custom_metric_names.append("exact_match_rows")

        return synthcity_metrics, custom_metric_names
