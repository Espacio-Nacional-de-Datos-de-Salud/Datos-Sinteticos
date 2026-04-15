"""Pipeline-run tracker.

``PipelineTracker`` wraps an entire multi-job pipeline execution: it creates
one timestamped output directory, captures a combined log file across every
job, and records a ``pipeline_summary.json`` index pointing at each model and
simulation run the pipeline produced (without duplicating their artifacts).
"""

import json
import logging
import os
from types import TracebackType

import config.general_config as general_config
from config.general_config import (
    LOG_LEVEL,
    MODELS_DIR,
    PIPELINE_RUN_FOLDER_PREFIX,
    PIPELINES_DIR,
    SESSION_LOG_FILENAME,
    SIMULATIONS_DIR,
)

from src.core.logging_config import get_logger

logger = get_logger(__name__)

PIPELINE_SUMMARY_FILENAME = "pipeline_summary.json"


class PipelineTracker:
    """Manages an overarching output folder for a full pipeline execution.

    Creates a timestamped directory under ``outputs/pipelines/`` that:
    - Captures the combined log output of every job in the pipeline.
    - Writes a ``pipeline_summary.json`` referencing all individual run
      output directories (models, simulations) without duplicating artifacts.

    Use as a context manager wrapping the entire pipeline run.

    Args:
        config_path (str): Path to the pipeline YAML configuration file.

    Example:
        >>> with PipelineTracker("config/pipelines/my_pipeline.yaml") as tracker:
        ...     for job in jobs:
        ...         tracker.register_job_result(job_name, model_id, simulation_id)
    """

    def __init__(self, config_path: str) -> None:
        self.config_path = config_path
        self.pipeline_id: str = f"{PIPELINE_RUN_FOLDER_PREFIX}_{general_config.get_run_timestamp()}"
        self.output_directory: str = os.path.join(PIPELINES_DIR, self.pipeline_id)
        self._job_results: list[dict] = []
        self._log_handler: logging.FileHandler | None = None
        self._attached_loggers: list[logging.Logger] = []

    def __enter__(self) -> "PipelineTracker":
        """Create pipeline output directory and attach a log handler."""
        os.makedirs(self.output_directory, exist_ok=True)
        logger.info("Created pipeline output directory: %s", self.output_directory)
        self._setup_logger()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Write the pipeline summary and detach the log handler."""
        import src.core.logging_config as logging_config

        status = "FAILED" if exc_type is not None else "SUCCESS"
        self._save_summary(status)

        if self._log_handler is not None:
            logging_config._pipeline_handler = None
            for child_logger in self._attached_loggers:
                child_logger.removeHandler(self._log_handler)
            self._log_handler.close()

    def register_job_result(
        self,
        job_name: str,
        model_id: str | None = None,
        simulation_id: str | None = None,
    ) -> None:
        """Record the output references produced by a pipeline job.

        Args:
            job_name (str): Human-readable name of the job.
            model_id (str | None): Model folder name, if a train step ran.
            simulation_id (str | None): Simulation folder name, if a simulate step ran.
        """
        entry: dict = {"job_name": job_name}
        if model_id is not None:
            entry["model_id"] = model_id
            entry["model_output_dir"] = os.path.join(MODELS_DIR, model_id)
        if simulation_id is not None:
            entry["simulation_id"] = simulation_id
            entry["simulation_output_dir"] = os.path.join(SIMULATIONS_DIR, simulation_id)
        self._job_results.append(entry)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _setup_logger(self) -> None:
        """Create the pipeline file handler and attach it to all existing loggers.

        Registers the handler globally in ``logging_config`` so that any
        logger created later (e.g. by lazy imports) also picks it up
        automatically via ``get_logger()``.
        """
        import src.core.logging_config as logging_config

        log_path = os.path.join(self.output_directory, SESSION_LOG_FILENAME)
        self._log_handler = logging.FileHandler(log_path, encoding="utf-8")
        self._log_handler.setLevel(LOG_LEVEL)
        self._log_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )

        logging_config._pipeline_handler = self._log_handler

        self._attached_loggers = []
        manager = logging.Logger.manager
        for _name, logger_ref in manager.loggerDict.items():
            if isinstance(logger_ref, logging.Logger):
                logger_ref.addHandler(self._log_handler)
                self._attached_loggers.append(logger_ref)

        logger.info("Pipeline logger initialised: %s", log_path)

    def _save_summary(self, status: str) -> None:
        """Write ``pipeline_summary.json`` with references to all job outputs.

        Args:
            status (str): Overall pipeline outcome (``SUCCESS`` or ``FAILED``).
        """
        summary = {
            "pipeline_id": self.pipeline_id,
            "config_path": self.config_path,
            "timestamp": general_config.get_run_timestamp(),
            "status": status,
            "jobs": self._job_results,
        }
        summary_path = os.path.join(self.output_directory, PIPELINE_SUMMARY_FILENAME)
        with open(summary_path, "w", encoding="utf-8") as file_handle:
            json.dump(summary, file_handle, indent=4)
        logger.info("Pipeline summary saved to '%s'.", summary_path)
