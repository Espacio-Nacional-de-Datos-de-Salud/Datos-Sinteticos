import os
from pathlib import Path

import config.general_config as general_config
import pandas as pd
import synthcity.logger as log
from config.evaluation.evaluation_config import DROP_ID_COLUMNS_FROM_METRICS, EVAL_DEFAULT_METRICS
from synthcity.metrics import Metrics
from synthcity.plugins.core.dataloader import GenericDataLoader

from src.core.logging_config import get_logger
from src.evaluation.abstract_evaluation_engine import AbstractEvaluationEngine
from src.evaluation.metrics import (
    DCR,
    NNDR,
    AverageComplementaryTVD,
    ConfidenceIntervalOverlap,
    CorrelationMatrixDistance,
    KAnonymity,
    LDiversityPyCanon,
)
from src.evaluation.utils import filter_id_columns

custom_metrics = [
    DCR,
    NNDR,
    CorrelationMatrixDistance,
    ConfidenceIntervalOverlap,
    AverageComplementaryTVD,
    KAnonymity,
    LDiversityPyCanon,
]

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
            eval_results_dir, f"synthcity_{general_config.get_run_timestamp()}.log"
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
        model_id: str | None = None,
        simulation_id: str | None = None,
        metadata_path: str | None = None,
    ) -> pd.DataFrame:
        """Run SynthCity evaluation metrics for real and synthetic data.

        Args:
            real_data_dict (dict[str, pd.DataFrame]): Mapping of table name to real data.
            synthetic_data_dict (dict[str, pd.DataFrame]): Mapping of table name to synthetic data.
            target_column (str | None): Optional target column for performance metrics.
            task_type (str): Task type for performance metrics.
            model_id (str | None): Optional model ID for lineage tracking.
            simulation_id (str | None): Optional simulation ID for result association.
            metadata_path (str | None): Path to metadata.json for identifying ID columns to exclude.

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
            ...     task_type='classification',
            ...     metadata_path='path/to/metadata.json'
            ... )
        """
        # 1. Data Loading (SynthCity specific)
        real_data = next(iter(real_data_dict.values()))
        synthetic_data = next(iter(synthetic_data_dict.values()))

        if DROP_ID_COLUMNS_FROM_METRICS:
            real_data = filter_id_columns(real_data, metadata_path)
            synthetic_data = filter_id_columns(synthetic_data, metadata_path)

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

            privacy_metrics = current_metrics.get("privacy", [])
            if privacy_metrics is not None:
                if "k-anonymization" in privacy_metrics:
                    logger.info(
                        "User requested k-anonymization metric, using custom implementation with subsets instead"
                    )
                    privacy_metrics.remove("k-anonymization")
                    requested_custom_metrics.append("k_anonymity")
                # if "distinct l-diversity" in privacy_metrics:
                #    logger.info("User requested distinct l-diversity metric, using custom implementation with subsets instead")
                #    privacy_metrics.remove("distinct l-diversity")
                #    requested_custom_metrics.append("l_diversity_pycanon")

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
                report = self._run_custom_metrics(
                    real_data, synthetic_data, report, requested_custom_metrics
                )

            return report

        except Exception as e:
            logger.error("Error during SynthCity metrics evaluation: %s", e)
            raise

    def _run_custom_metrics(self, real, syn, report, requested_metrics):
        """Run custom metrics and inject results into the report.

        Metrics may return either a single-row result (``score`` key) or a
        multi-row result (``scores`` key mapping row names to dicts with
        ``mean``/``min``/``max``).  The ``additional`` dict is attached to
        the *first* row only.

        Args:
            real (pd.DataFrame): Real dataset.
            syn (pd.DataFrame): Synthetic dataset.
            report (pd.DataFrame): Report DataFrame to update.
            requested_metrics (list[str]): Custom metric names requested.

        Returns:
            pd.DataFrame: Updated report with custom metrics.
        """
        logger.info("Running custom metrics: %s", requested_metrics)
        for MetricClass in custom_metrics:
            metric_name = MetricClass.name()
            if metric_name in requested_metrics:
                try:
                    evaluator = MetricClass()
                    results = evaluator.evaluate(real, syn)
                    logger.debug(f"Successfully executed custom metric {metric_name}")

                    figure = results.get("figure", None)
                    additional = results.get("additional", None)

                    # Multi-row metrics (e.g. k_anonymity → k_anonymity.real + k_anonymity.syn)
                    if "scores" in results:
                        first = True
                        for row_name, row_scores in results["scores"].items():
                            row_data = dict(row_scores)
                            row_data["figure"] = figure if first else None
                            row_data["additional"] = additional if first else None
                            first = False
                            report = pd.concat([report, pd.DataFrame([row_data], index=[row_name])])
                    else:
                        new_row_data = {}
                        score = results.get("score", None)
                        if score is not None:
                            new_row_data["mean"] = score
                            new_row_data["min"] = results.get("min")
                            new_row_data["max"] = results.get("max")
                        new_row_data["figure"] = figure
                        new_row_data["additional"] = additional
                        report = pd.concat(
                            [report, pd.DataFrame([new_row_data], index=[metric_name])]
                        )

                except Exception as e:
                    logger.error("Failed to run custom metric %s: %s", metric_name, e)

        return report
