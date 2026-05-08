"""Evaluation-run tracker.

``EvaluationTracker`` mirrors ``SimulationTracker`` for the evaluation stage.
It creates its own output folder under ``outputs/evaluations/``, writes an
``eval_card.json``, and starts a fresh MLflow run in the Evaluation experiment,
linking back to the parent simulation.
"""

import json
import logging
import os
from types import TracebackType

import backend.src.config.general as general_config
import mlflow
import pandas as pd
import sagemaker_mlflow  # noqa: F401
from backend.src.config.general import (
    EVAL_CARD_FILENAME,
    EVALUATION_RUN_FOLDER_PREFIX,
    EVALUATIONS_DIR,
    MLFLOW_EXPERIMENT_EVALUATION,
    MLFLOW_TRACKING_URI,
    NO_PIPELINE_ID,
    SESSION_LOG_FILENAME,
    USERPROFILENAME,
)
from backend.src.core.logging_config import get_logger
from backend.src.core.tracking._session_logger import (
    attach_session_file_handler,
    detach_session_file_handler,
)
from backend.src.core.tracking.helpers import ensure_clean_mlflow_storage

logger = get_logger(__name__)


class EvaluationTracker:
    """Manages local outputs and MLflow logging for an evaluation run.

    Use as a context manager. On enter, creates the eval directory, attaches
    a per-run file logger, writes the initial sim card, and starts the MLflow run.
    On exit, updates the card status and closes the MLflow run.

    Args:
        simulation_id (str): Identifier of the parent simulation.
        model_id (str): Identifier of the parent model.
        pipeline_id (str): Optional pipeline grouping.
        job_name (str): Optional job name.
        evaluation_id (str | None): Optional specific ID, otherwise generated.

    Example:
        >>> with EvaluationTracker(simulation_id, model_id) as tracker:
        ...     report = runner.run(real, synth, ...)
        ...     tracker.save_report(report)
    """

    def __init__(
        self,
        simulation_id: str,
        model_id: str,
        pipeline_id: str = NO_PIPELINE_ID,
        job_name: str = "",
        evaluation_id: str | None = None,
    ) -> None:
        self.simulation_id = simulation_id
        self.model_id = model_id
        self.pipeline_id = pipeline_id
        self.job_name = job_name

        self.evaluation_id: str = evaluation_id or (
            f"{EVALUATION_RUN_FOLDER_PREFIX}_{general_config.get_run_timestamp()}"
        )
        self.output_directory: str = os.path.join(EVALUATIONS_DIR, self.evaluation_id)

        self._mlflow_run: mlflow.ActiveRun | None = None
        self._run_logger: logging.Logger | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> "EvaluationTracker":
        os.makedirs(self.output_directory, exist_ok=True)
        logger.info("Created evaluation output directory: %s", self.output_directory)

        self._run_logger = attach_session_file_handler(self.output_directory, __name__)
        self._start_mlflow_run()

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        from backend.src.core.cancellation import JobCancelled, unregister

        if exc_type is JobCancelled:
            card_status, mlflow_status = "cancelled", "CANCELLED"
        elif exc_type is not None:
            card_status, mlflow_status = "failed", "FAILED"
        else:
            card_status, mlflow_status = "completed", "SUCCESS"

        self._update_card_status(card_status)
        unregister(self.evaluation_id)

        if self._mlflow_run is not None:
            mlflow.set_tag("run_status", mlflow_status)
            if exc_type is not None:
                mlflow.set_tag("error", str(exc_val))

            detach_session_file_handler()

            log_path = os.path.join(self.output_directory, SESSION_LOG_FILENAME)
            if os.path.exists(log_path):
                mlflow.log_artifact(log_path)

            mlflow.end_run()
            logger.info("MLflow evaluation run ended.")
        else:
            detach_session_file_handler()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def save_eval_card(self) -> None:
        """Write ``eval_card.json`` linking this evaluation to its parent simulation."""
        eval_card = {
            "evaluation_id": self.evaluation_id,
            "status": "in_progress",
            "simulation_id": self.simulation_id,
            "model_id": self.model_id,
            "USERPROFILENAME": USERPROFILENAME,
            "timestamp": general_config.get_run_timestamp(),
            "pipeline_id": self.pipeline_id,
            "job_name": self.job_name,
        }
        card_path = os.path.join(self.output_directory, EVAL_CARD_FILENAME)
        with open(card_path, "w", encoding="utf-8") as file_handle:
            json.dump(eval_card, file_handle, indent=4)
        logger.info("Eval card saved to '%s'.", card_path)
        mlflow.log_artifact(card_path)

    def save_report(self, report: pd.DataFrame) -> None:
        """Persist the evaluation report locally and to MLflow.

        Per-metric ``additional`` dicts are written as
        ``<metric>_report.json``; the clean CSV strips ``figure`` and
        ``additional`` columns.
        """
        self._save_per_metric_detail_json(report)
        self._save_clean_csv(report)
        self._update_card_metrics_list(report)

        if self._mlflow_run:
            self._log_metrics_and_figures(report)
            self._log_local_artifacts()

    # ------------------------------------------------------------------
    # Internal helpers — MLflow lifecycle
    # ------------------------------------------------------------------
    def _start_mlflow_run(self) -> None:
        """Configure MLflow tracking and start a new run for evaluation."""
        ensure_clean_mlflow_storage()
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT_EVALUATION)
        os.environ["MLFLOW_TRACKING_USERNAME"] = USERPROFILENAME
        self._mlflow_run = mlflow.start_run(run_name=self.evaluation_id)

        mlflow.set_tag("simulation_id", self.simulation_id)
        mlflow.set_tag("model_id", self.model_id)
        mlflow.set_tag("phase", "evaluation")
        mlflow.set_tag("user-profile-name", USERPROFILENAME)
        mlflow.set_tag("pipeline_id", self.pipeline_id)
        mlflow.set_tag("job_name", self.job_name)

        logger.info("MLflow evaluation run started: %s", self._mlflow_run.info.run_id)

    def _update_card_status(self, status: str) -> None:
        """Overwrite the ``status`` field in ``eval_card.json``."""
        card_path = os.path.join(self.output_directory, EVAL_CARD_FILENAME)
        if not os.path.exists(card_path):
            return
        with open(card_path, encoding="utf-8") as file_handle:
            card = json.load(file_handle)
        card["status"] = status
        with open(card_path, "w", encoding="utf-8") as file_handle:
            json.dump(card, file_handle, indent=4)

    def _update_card_metrics_list(self, report: pd.DataFrame) -> None:
        """Overwrite the ``metrics_evaluated`` field in ``eval_card.json``."""
        card_path = os.path.join(self.output_directory, EVAL_CARD_FILENAME)
        if not os.path.exists(card_path):
            return
        with open(card_path, encoding="utf-8") as file_handle:
            card = json.load(file_handle)
        card["metrics_evaluated"] = report.index.tolist()
        with open(card_path, "w", encoding="utf-8") as file_handle:
            json.dump(card, file_handle, indent=4)

    # ------------------------------------------------------------------
    # Internal helpers — local artifacts
    # ------------------------------------------------------------------
    def _save_per_metric_detail_json(self, report: pd.DataFrame) -> None:
        if "additional" not in report.columns:
            return
        for metric_name, row in report.iterrows():
            additional = row.get("additional")
            if not isinstance(additional, dict) or not additional:
                continue
            base_name = metric_name.split(".")[0] if "." in metric_name else metric_name
            path = os.path.join(self.output_directory, f"{base_name}_report.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(additional, fh, indent=2, ensure_ascii=False, default=str)

    def _save_clean_csv(self, report: pd.DataFrame) -> None:
        drop_cols = [c for c in ("figure", "additional") if c in report.columns]
        report_for_csv = report.drop(columns=drop_cols)
        csv_path = os.path.join(self.output_directory, "eval_report.csv")
        report_for_csv.reset_index().rename(columns={"index": "metric"}).to_csv(
            csv_path, index=False
        )

    # ------------------------------------------------------------------
    # Internal helpers — MLflow logging
    # ------------------------------------------------------------------
    def _log_metrics_and_figures(self, report: pd.DataFrame) -> None:
        if "mean" not in report.columns:
            return
        for metric_name, row in report.iterrows():
            if pd.notna(row.get("mean")):
                mlflow.log_metric(f"eval_{metric_name}", float(row["mean"]))
            if pd.notna(row.get("figure")):
                mlflow.log_figure(row["figure"], f"eval_{metric_name}_fig.png")

    def _log_local_artifacts(self) -> None:
        """Upload every JSON/CSV file from the eval directory."""
        for fname in os.listdir(self.output_directory):
            fpath = os.path.join(self.output_directory, fname)
            if os.path.isfile(fpath) and fname.endswith((".json", ".csv")):
                mlflow.log_artifact(fpath)
