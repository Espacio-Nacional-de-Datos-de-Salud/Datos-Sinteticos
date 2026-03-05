import os
from pathlib import Path

import pandas as pd
import synthcity.logger as log
from config.general_config import EVAL_DEFAULT_METRICS, RUN_TIMESTAMP
from synthcity.metrics import Metrics
from synthcity.plugins.core.dataloader import GenericDataLoader

from src.core.logging_config import get_logger
from src.evaluation.abstract_evaluation_engine import AbstractEvaluationEngine
from src.evaluation.metrics import (
    ConfidenceIntervalOverlap,
    CorrelationMatrixDistance,
    NearestNeighborDistance,
)

custom_metrics = [NearestNeighborDistance, CorrelationMatrixDistance, ConfidenceIntervalOverlap]

logger = get_logger(__name__)


class SynthCityEvaluationEngine(AbstractEvaluationEngine):
    def __init__(self, eval_results_dir: str | None, metrics: dict[str, list[str]] | None = None):
        """Initialize the SynthCity evaluation engine.

        Args:
            eval_results_dir (str | None): Directory where evaluation outputs are stored.
            metrics (dict[str, list[str]] | None): Metric groups to run; defaults to config.
        """
        super().__init__(eval_results_dir)

        # SynthCity specific logging setup
        self.evaluation_logger_path = os.path.join(
            eval_results_dir, f"synthcity_{RUN_TIMESTAMP}.log"
        )
        self.evaluation_workspace_path = os.path.join(eval_results_dir, "workspace")

        log.add(sink=self.evaluation_logger_path, level="INFO")
        self.metrics = metrics or EVAL_DEFAULT_METRICS

    def run(
        self,
        real_data_dict: dict[str, pd.DataFrame],
        synthetic_data_dict: dict[str, pd.DataFrame],
        target_column: str | None = None,
        task_type: str = "classification",  # Options: 'classification', 'regression', 'survival_analysis'
    ) -> pd.DataFrame:
        """Run SynthCity evaluation metrics for real and synthetic data.

        Args:
            real_data_dict (dict[str, pd.DataFrame]): Mapping of table name to real data.
            synthetic_data_dict (dict[str, pd.DataFrame]): Mapping of table name to synthetic data.
            target_column (str | None): Optional target column for performance metrics.
            task_type (str): Task type for performance metrics.

        Returns:
            pd.DataFrame: Evaluation report with metric scores.

        Raises:
            Exception: If data loaders or metric evaluation fail.

        Example:
            >>> eval_engine = SynthCityEvaluationEngine(eval_results_dir='eval_results/')
            >>> report = eval_engine.run(
            ...     real_data_dict=real_data,
            ...     synthetic_data_dict=synthetic_data,
            ...     target_column='target',
            ...     task_type='classification'
            ... )
            >>> print(report)
        """
        # 1. Data Loading (SynthCity specific)
        real_data = next(iter(real_data_dict.values()))
        synthetic_data = next(iter(synthetic_data_dict.values()))

        try:
            loader_real = GenericDataLoader(
                real_data, target_column=target_column, sensitive_features=[]
            )
            loader_syn = GenericDataLoader(
                synthetic_data, target_column=target_column, sensitive_features=[]
            )
        except Exception as e:
            logger.error("Failed to create DataLoaders: %s", e)
            raise

        # 2. Config Logic
        current_metrics = self.metrics.copy()
        requested_custom_metrics = current_metrics.pop("custom", [])

        if not target_column and "performance" in current_metrics:
            if current_metrics["performance"]:
                logger.info("No 'target_column' provided. Skipping 'performance' metrics.")
            del current_metrics["performance"]

        # 3. Execution
        try:
            logger.info("Running metrics: %s", list(current_metrics.keys()))
            report = Metrics.evaluate(
                loader_real,
                loader_syn,
                metrics=current_metrics,
                task_type=task_type,
                workspace=Path(self.evaluation_workspace_path),
                X_train=loader_real,
                X_ref_syn=loader_syn,
            )

            # 4. Custom Metrics
            if requested_custom_metrics:
                self._run_custom_metrics(
                    real_data, synthetic_data, report, requested_custom_metrics
                )

            return report

        except Exception as e:
            logger.error("Error during SynthCity metrics evaluation: %s", e)
            raise

    def _run_custom_metrics(self, real, syn, report, requested_metrics):
        """Run custom metrics and inject results into the report.

        Args:
            real (pd.DataFrame): Real dataset.
            syn (pd.DataFrame): Synthetic dataset.
            report (pd.DataFrame): Report DataFrame to update.
            requested_metrics (list[str]): Custom metric names requested.
        """
        logger.info("Running custom metrics: %s", requested_metrics)
        for MetricClass in custom_metrics:
            metric_name = MetricClass.name()
            if metric_name in requested_metrics:
                try:
                    evaluator = MetricClass()
                    results = evaluator.evaluate(real, syn)
                    score = results.get("score", None)

                    if score is not None:
                        if "mean" not in report.columns:
                            report["mean"] = float("nan")
                        report.loc[metric_name, "mean"] = score
                except Exception as e:
                    logger.error("Failed to run custom metric %s: %s", metric_name, e)
