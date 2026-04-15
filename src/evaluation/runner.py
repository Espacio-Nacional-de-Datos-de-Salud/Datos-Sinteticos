"""End-to-end evaluation runner.

``EvaluationRunner.run`` is the single entry point for evaluating a real /
synthetic data pair. It executes synthcity's built-in metrics and the
project's custom metrics, returning a unified report DataFrame. Persisting
results (locally and to MLflow) is the responsibility of
``EvaluationTracker`` — this class is purely about computing the report.
"""

import os

import config.general_config as general_config
import pandas as pd
import synthcity.logger as synthcity_log
from config.evaluation.evaluation_config import DROP_ID_COLUMNS_FROM_METRICS, EVAL_DEFAULT_METRICS

from src.core.logging_config import get_logger
from src.evaluation._custom_metrics import run_custom_metrics
from src.evaluation._synthcity_metrics import build_data_loaders, evaluate_synthcity_metrics
from src.evaluation.utils import filter_id_columns

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
            report = run_custom_metrics(real_data, synthetic_data, report, custom_metric_names)

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
        """Pick the single table evaluated and optionally strip ID columns."""
        real_data = next(iter(real_data_dict.values()))
        synthetic_data = next(iter(synthetic_data_dict.values()))

        if DROP_ID_COLUMNS_FROM_METRICS:
            real_data = filter_id_columns(real_data, metadata_path)
            synthetic_data = filter_id_columns(synthetic_data, metadata_path)

        return real_data, synthetic_data

    def _partition_requested_metrics(
        self, target_column: str | None
    ) -> tuple[dict[str, list[str]], list[str]]:
        """Split configured metrics into a synthcity dict and a custom-name list.

        Also handles two project-specific overrides:

        - ``performance`` is dropped when no target column is provided.
        - ``k-anonymization`` (synthcity's built-in) is replaced by our
          subset-aware ``k_anonymity`` custom metric.
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
            custom_metric_names.append("k_anonymity")

        return synthcity_metrics, custom_metric_names
