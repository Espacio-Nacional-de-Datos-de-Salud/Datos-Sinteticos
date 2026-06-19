"""Evaluation-run tracker.

``EvaluationTracker`` mirrors ``SimulationTracker`` for the evaluation stage.
It creates its own output folder under ``outputs/evaluations/``, writes an
``eval_card.json`` linking back to the parent simulation, and persists the
evaluation report and per-metric detail artifacts on disk.
"""

import json
import os
from pathlib import Path

import pandas as pd

import backend.src.config.general as general_config
from backend.src.config.general import (
    EVAL_CARD_FILENAME,
    EVALUATION_RUN_FOLDER_PREFIX,
    EVALUATIONS_DIR,
    NO_PIPELINE_ID,
    USERPROFILENAME,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.runs.tracking.base_tracker import BaseRunTracker

logger = get_logger(__name__)


class EvaluationTracker(BaseRunTracker):
    """Manages local outputs for an evaluation run.

    Use as a context manager. On enter, creates the eval directory, attaches a
    per-run file logger, and writes the initial eval card. On exit, flips the
    card status and generates the HTML evaluation report.

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

    card_filename = EVAL_CARD_FILENAME
    run_kind = "evaluation"

    def __init__(
        self,
        simulation_id: str,
        model_id: str,
        pipeline_id: str = NO_PIPELINE_ID,
        job_name: str = "",
        evaluation_id: str | None = None,
        training_parameters: dict | None = None,
        evaluation_parameters: dict | None = None,
    ) -> None:
        super().__init__()
        self.simulation_id = simulation_id
        self.model_id = model_id
        self.pipeline_id = pipeline_id
        self.job_name = job_name
        self.training_parameters = training_parameters or {}
        self.evaluation_parameters = evaluation_parameters or {}

        self.evaluation_id: str = evaluation_id or (
            f"{EVALUATION_RUN_FOLDER_PREFIX}_{general_config.get_run_timestamp()}"
        )
        self.run_id = self.evaluation_id
        self.output_directory: str = os.path.join(EVALUATIONS_DIR, self.evaluation_id)

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def _on_enter(self) -> None:
        self.save_eval_card()

    def _on_exit(self, exc_type, exc_val, exc_tb) -> None:
        if exc_type is None:
            try:
                from backend.src.domain.evaluation.reporting.report_artifacts import (
                    generate_report_artifacts,
                )

                self.update_card_status("completed")
                generate_report_artifacts(Path(self.output_directory))
            except Exception as report_exc:
                logger.exception("Failed to generate HTML evaluation report: %s", report_exc)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def save_eval_card(self) -> None:
        """Write ``eval_card.json`` linking this evaluation to its parent simulation."""
        self.write_initial_card(
            {
                "evaluation_id": self.evaluation_id,
                "simulation_id": self.simulation_id,
                "model_id": self.model_id,
                "USERPROFILENAME": USERPROFILENAME,
                "timestamp": general_config.get_run_timestamp(),
                "pipeline_id": self.pipeline_id,
                "job_name": self.job_name,
                "training_parameters": self.training_parameters,
                "evaluation_parameters": self.evaluation_parameters,
            }
        )

    def save_report(self, report: pd.DataFrame) -> None:
        """Persist the evaluation report locally.

        Per-metric ``additional`` dicts are written as ``<metric>_report.json``;
        the clean CSV strips ``figure`` and ``additional`` columns.
        """
        self._save_per_metric_detail_json(report)
        self._save_clean_csv(report)
        self.patch_card(metrics_evaluated=report.index.tolist())

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
