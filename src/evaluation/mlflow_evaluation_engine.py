import os

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
    ) -> pd.DataFrame:
        """Run evaluation with MLflow tracking.

        Args:
            real_data_dict: Real data tables.
            synthetic_data_dict: Synthetic data tables.
            target_column: Target column for performance metrics.
            task_type: ML task type.
            model_id: ID of the model that generated synthetic data.
            simulation_id: ID of the simulation being evaluated.

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

        if simulation_run_id:
            # Add metrics to existing simulation run
            with mlflow.start_run(run_id=simulation_run_id):
                try:
                    # Run evaluation
                    report = self.synthcity_engine.run(
                        real_data_dict, synthetic_data_dict, target_column, task_type
                    )

                    # Log evaluation metrics
                    if "mean" in report.columns:
                        for metric_name, row in report.iterrows():
                            if pd.notna(row["mean"]):
                                mlflow.log_metric(f"eval_{metric_name}", float(row["mean"]))

                    # Log evaluation report as artifact
                    report_path = os.path.join(self.eval_results_dir, "eval_report.csv")
                    report.reset_index().rename(columns={"index": "metric"}).to_csv(
                        report_path, index=False
                    )
                    mlflow.log_artifact(report_path, "evaluation")

                    mlflow.set_tag("evaluation_completed", "true")
                    logger.info("Evaluation metrics added to simulation run %s", simulation_id)

                    return report

                except Exception as e:
                    mlflow.set_tag("evaluation_error", str(e))
                    logger.error("Evaluation failed: %s", e)
                    raise
        else:
            # Fallback: run without MLflow tracking
            logger.warning(
                "Could not find simulation run, running evaluation without MLflow tracking"
            )
            return self.synthcity_engine.run(
                real_data_dict, synthetic_data_dict, target_column, task_type
            )
