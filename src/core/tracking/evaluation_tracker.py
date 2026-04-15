"""Evaluation-run tracker.

``EvaluationTracker`` mirrors ``ModelTracker`` and ``SimulationTracker`` for
the evaluation stage. Unlike the other two — which start a fresh MLflow run
— this tracker *attaches* to the existing simulation run (looked up by
``simulation_id``) and adds evaluation metrics, per-metric detail JSON
reports, and the clean CSV report as artifacts on that same run, so a
simulation and its evaluation live together in MLflow.
"""

import json
import logging
import os
from types import TracebackType

import config.general_config as general_config
import mlflow
import pandas as pd
import sagemaker_mlflow  # noqa: F401
from config.general_config import MLFLOW_EXPERIMENT_SIMULATION, MLFLOW_TRACKING_URI

from src.core.logging_config import get_logger
from src.core.tracking._session_logger import attach_session_file_handler

logger = get_logger(__name__)


class EvaluationTracker:
    """Manages local outputs and MLflow logging for an evaluation run.

    Use as a context manager. On enter, creates the eval directory, attaches
    a per-run file logger, and resolves the parent simulation's MLflow run.
    On exit, closes the MLflow run if one was opened.

    Args:
        simulation_id (str | None): Identifier of the parent simulation
            whose MLflow run will receive the evaluation metrics. When
            ``None`` (e.g. ad-hoc CLI runs), MLflow logging is skipped.
        eval_results_dir (str): Directory where evaluation outputs are saved.

    Example:
        >>> with EvaluationTracker(simulation_id, eval_dir) as tracker:
        ...     report = runner.run(real, synth, ...)
        ...     tracker.save_report(report)
    """

    def __init__(self, simulation_id: str | None, eval_results_dir: str) -> None:
        self.simulation_id = simulation_id
        self.eval_results_dir = eval_results_dir

        self._mlflow_run: mlflow.ActiveRun | None = None
        self._run_logger: logging.Logger | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> "EvaluationTracker":
        os.makedirs(self.eval_results_dir, exist_ok=True)
        logger.info("Created evaluation output directory: %s", self.eval_results_dir)

        self._run_logger = attach_session_file_handler(self.eval_results_dir, __name__)
        self._open_parent_simulation_run()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self._mlflow_run is None:
            return

        if exc_type is not None:
            mlflow.set_tag("evaluation_error", str(exc_val))
        else:
            mlflow.set_tag("evaluation_completed", "true")

        mlflow.end_run()
        logger.info("Evaluation MLflow run ended.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def save_report(self, report: pd.DataFrame) -> None:
        """Persist the evaluation report locally and to MLflow.

        Per-metric ``additional`` dicts are written as
        ``<metric>_report.json``; the clean CSV strips ``figure`` and
        ``additional`` columns. If the parent simulation MLflow run was
        resolved, the metrics, figures, and JSON/CSV artifacts are also
        logged there.

        Args:
            report (pd.DataFrame): Report produced by ``EvaluationRunner.run``.
        """
        self._save_per_metric_detail_json(report)
        self._save_clean_csv(report)

        if self._mlflow_run is None:
            logger.warning("No parent simulation run resolved; evaluation saved locally only.")
            return

        self._log_metrics_and_figures(report)
        self._log_local_artifacts()
        logger.info("Evaluation metrics added to simulation run %s", self.simulation_id)

    # ------------------------------------------------------------------
    # Internal helpers — MLflow lifecycle
    # ------------------------------------------------------------------
    def _open_parent_simulation_run(self) -> None:
        """Look up the simulation's MLflow run and reopen it for appending."""
        if not self.simulation_id:
            return

        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT_SIMULATION)

        try:
            experiment = mlflow.get_experiment_by_name(MLFLOW_EXPERIMENT_SIMULATION)
            if experiment is None:
                return
            runs = mlflow.search_runs(
                experiment_ids=[experiment.experiment_id],
                filter_string=f"run_name = '{self.simulation_id}'",
                max_results=1,
            )
            if runs.empty:
                logger.warning("Simulation run %s not found in MLflow.", self.simulation_id)
                return
            run_id = runs.iloc[0]["run_id"]
            self._mlflow_run = mlflow.start_run(run_id=run_id)
        except Exception as exc:
            logger.warning("Could not open MLflow run for %s: %s", self.simulation_id, exc)

    # ------------------------------------------------------------------
    # Internal helpers — local artifacts
    # ------------------------------------------------------------------
    def _save_per_metric_detail_json(self, report: pd.DataFrame) -> None:
        """Write each metric's ``additional`` dict as ``<metric>_report.json``."""
        if "additional" not in report.columns:
            return
        for metric_name, row in report.iterrows():
            additional = row.get("additional")
            if not isinstance(additional, dict) or not additional:
                continue
            base_name = metric_name.split(".")[0] if "." in metric_name else metric_name
            path = os.path.join(self.eval_results_dir, f"{base_name}_report.json")
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(additional, fh, indent=2, ensure_ascii=False, default=str)
            logger.info("Saved %s detail report to %s", base_name, path)

    def _save_clean_csv(self, report: pd.DataFrame) -> None:
        """Write the report as CSV without the ``figure`` and ``additional`` columns."""
        drop_cols = [c for c in ("figure", "additional") if c in report.columns]
        report_for_csv = report.drop(columns=drop_cols)
        csv_path = os.path.join(
            self.eval_results_dir, f"eval_report_{general_config.get_run_timestamp()}.csv"
        )
        report_for_csv.reset_index().rename(columns={"index": "metric"}).to_csv(
            csv_path, index=False
        )
        logger.info("Evaluation CSV report saved to %s", csv_path)

    # ------------------------------------------------------------------
    # Internal helpers — MLflow logging
    # ------------------------------------------------------------------
    def _log_metrics_and_figures(self, report: pd.DataFrame) -> None:
        """Log scalar metrics and figures for each row of the report."""
        if "mean" not in report.columns:
            return
        for metric_name, row in report.iterrows():
            if pd.notna(row.get("mean")):
                mlflow.log_metric(f"eval_{metric_name}", float(row["mean"]))
            if pd.notna(row.get("figure")):
                mlflow.log_figure(row["figure"], f"eval_{metric_name}_fig.png")

    def _log_local_artifacts(self) -> None:
        """Upload every JSON/CSV file from the eval directory under ``evaluation/``."""
        for fname in os.listdir(self.eval_results_dir):
            fpath = os.path.join(self.eval_results_dir, fname)
            if os.path.isfile(fpath) and fname.endswith((".json", ".csv")):
                mlflow.log_artifact(fpath, "evaluation")
