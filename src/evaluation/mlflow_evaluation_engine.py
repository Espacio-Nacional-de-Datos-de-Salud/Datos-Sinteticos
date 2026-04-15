import json
import os

import config.general_config as general_config
import pandas as pd
from config.general_config import IS_SAGEMAKER, MLFLOW_EXPERIMENT_SIMULATION, MLFLOW_TRACKING_URI

from src.core.logging_config import get_logger
from src.evaluation.abstract_evaluation_engine import AbstractEvaluationEngine
from src.evaluation.synthcity_evaluation_engine import SynthCityEvaluationEngine

logger = get_logger(__name__)


try:
    import mlflow

    if IS_SAGEMAKER:
        import sagemaker_mlflow
except ImportError as e:
    raise ImportError("MLflow is a mandatory dependency for MLflowEvaluationEngine.") from e


class MLflowEvaluationEngine(AbstractEvaluationEngine):
    def __init__(self, eval_results_dir: str | None, metrics: dict[str, list[str]] | None = None):
        """Initialize MLflow-enabled evaluation engine.

        Args:
            eval_results_dir (str | None): Directory for evaluation outputs.
            metrics (dict[str, list[str]] | None): Metric groups to run.
        """
        super().__init__(eval_results_dir)
        self.synthcity_engine = SynthCityEvaluationEngine(eval_results_dir, metrics)

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT_SIMULATION)

    def run(
        self,
        real_data_dict: dict[str, pd.DataFrame],
        synthetic_data_dict: dict[str, pd.DataFrame],
        target_column: str | None = None,
        task_type: str = "classification",
        model_id: str | None = None,
        simulation_id: str | None = None,
        metadata_path: str | None = None,
    ) -> pd.DataFrame:
        """Run evaluation with MLflow tracking.

        Args:
            real_data_dict: Real data tables.
            synthetic_data_dict: Synthetic data tables.
            target_column: Target column for performance metrics.
            task_type: ML task type.
            model_id: ID of the model used for simulation.
            simulation_id: ID of the simulation being evaluated.
            metadata_path: Path to metadata.json for identifying ID columns.

        Returns:
            pd.DataFrame: Evaluation report.
        """
        # Find existing simulation run by simulation_id
        simulation_run_id = None
        if simulation_id:
            try:
                experiment = mlflow.get_experiment_by_name(MLFLOW_EXPERIMENT_SIMULATION)
                if experiment:
                    runs = mlflow.search_runs(
                        experiment_ids=[experiment.experiment_id],
                        filter_string=f"run_name = '{simulation_id}'",
                        max_results=1,
                    )
                    if not runs.empty:
                        simulation_run_id = runs.iloc[0]["run_id"]
            except Exception as e:
                logger.warning("Could not find simulation run %s: %s", simulation_id, e)

        # Run evaluation
        report = self.synthcity_engine.run(
            real_data_dict,
            synthetic_data_dict,
            target_column,
            task_type,
            model_id,
            simulation_id,
            metadata_path,
        )

        # Save detail JSON reports and clean CSV locally
        self._save_local_artifacts(report)

        # Log to MLflow if we found the simulation run
        if simulation_run_id:
            with mlflow.start_run(run_id=simulation_run_id):
                try:
                    if "mean" in report.columns:
                        for metric_name, row in report.iterrows():
                            if pd.notna(row.get("mean")):
                                mlflow.log_metric(f"eval_{metric_name}", float(row["mean"]))
                            if pd.notna(row.get("figure")):
                                mlflow.log_figure(row["figure"], f"eval_{metric_name}_fig.png")

                    # Upload all local artifacts to MLflow
                    for fname in os.listdir(self.eval_results_dir):
                        fpath = os.path.join(self.eval_results_dir, fname)
                        if os.path.isfile(fpath) and fname.endswith((".json", ".csv")):
                            mlflow.log_artifact(fpath, "evaluation")

                    mlflow.set_tag("evaluation_completed", "true")
                    logger.info("Evaluation metrics added to simulation run %s", simulation_id)
                except Exception as e:
                    mlflow.set_tag("evaluation_error", str(e))
                    logger.error("Evaluation failed during MLflow logging: %s", e)
                    raise
        else:
            logger.warning(
                "Could not find simulation run %s, evaluation saved locally only", simulation_id
            )

        return report

    def _save_local_artifacts(self, report: pd.DataFrame) -> None:
        """Save detail JSON reports and clean CSV to the evaluation directory.

        Metrics that carry an ``additional`` dict get their detail written to
        a ``<metric_name>_report.json`` file. The CSV is saved without the
        ``figure`` and ``additional`` columns.
        """
        os.makedirs(self.eval_results_dir, exist_ok=True)

        # Save per-metric detail JSON files
        if "additional" in report.columns:
            for metric_name, row in report.iterrows():
                additional = row.get("additional")
                if isinstance(additional, dict) and additional:
                    # Use base name (e.g. "k_anonymity" from "k_anonymity.real")
                    base_name = metric_name.split(".")[0] if "." in metric_name else metric_name
                    path = os.path.join(self.eval_results_dir, f"{base_name}_report.json")
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(additional, f, indent=2, ensure_ascii=False, default=str)
                    logger.info("Saved %s detail report to %s", base_name, path)

        # Save clean CSV
        drop_cols = [c for c in ("figure", "additional") if c in report.columns]
        report_for_csv = report.drop(columns=drop_cols)
        csv_path = os.path.join(
            self.eval_results_dir, f"eval_report_{general_config.get_run_timestamp()}.csv"
        )
        report_for_csv.reset_index().rename(columns={"index": "metric"}).to_csv(
            csv_path, index=False
        )
