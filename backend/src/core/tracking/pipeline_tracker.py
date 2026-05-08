"""Pipeline-run tracker.

``PipelineTracker`` wraps an entire multi-job pipeline execution: it creates
one timestamped output directory, captures a combined log file across every
job, and records a ``pipeline_card.json`` index pointing at each model and
simulation run the pipeline produced (without duplicating their artifacts).

The card is rewritten after every job finishes, so if the process is killed
mid-pipeline the on-disk state still reflects which jobs produced artifacts.
Overall status can be:
- ``in_progress``: entered the context, has not cleanly exited (may also mean
  the process crashed without closing the tracker).
- ``completed``: exited cleanly and every registered job ended with
  ``completed`` status.
- ``partial``: exited (cleanly or with an exception) with at least one job
  that produced artifacts and at least one that did not.
- ``failed``: exited with no job producing any artifact.
"""

import json
import logging
import os
import shutil
from types import TracebackType

import backend.src.config.general as general_config
from backend.src.config.general import (
    EVALUATIONS_DIR,
    LOG_LEVEL,
    MODELS_DIR,
    PIPELINE_CARD_FILENAME,
    PIPELINE_RUN_FOLDER_PREFIX,
    PIPELINES_DIR,
    SESSION_LOG_FILENAME,
    SIMULATIONS_DIR,
)
from backend.src.core.logging_config import get_logger

logger = get_logger(__name__)


class PipelineTracker:
    """Manages an overarching output folder for a full pipeline execution.

    Creates a timestamped directory under ``outputs/pipelines/`` that:
    - Captures the combined log output of every job in the pipeline.
    - Writes a pipeline card referencing all individual run
      output directories (models, simulations) without duplicating artifacts.
    - Updates the card incrementally after every job so the on-disk state
      survives a crash.

    Use as a context manager wrapping the entire pipeline run.

    Args:
        config_path (str): Path to the pipeline YAML configuration file.

    Example:
        >>> with PipelineTracker("config/pipelines/my_pipeline.yaml") as tracker:
        ...     for job in jobs:
        ...         tracker.register_job_result(job_name, model_id, simulation_id)
    """

    def __init__(self, config_path: str, pipeline_id: str | None = None) -> None:
        self.config_path = config_path
        self.pipeline_id: str = (
            pipeline_id or f"{PIPELINE_RUN_FOLDER_PREFIX}_{general_config.get_run_timestamp()}"
        )
        self.output_directory: str = os.path.join(PIPELINES_DIR, self.pipeline_id)
        self.configs_directory: str = os.path.join(self.output_directory, "configs")
        self._job_results: list[dict] = []
        self._log_handler: logging.FileHandler | None = None
        self._attached_loggers: list[logging.Logger] = []
        self._cancelled: bool = False
        # Coarse "Job X of N" progress, mirroring the contract used by the
        # other long-running flows (see ``core/progress.py``). Updated by the
        # executor before each job starts; consumed by the catalog/UI.
        self._progress: dict | None = None

    def __enter__(self) -> "PipelineTracker":
        """Create pipeline output directory and attach a log handler."""
        os.makedirs(self.configs_directory, exist_ok=True)
        logger.info("Created pipeline output directory: %s", self.output_directory)
        self._setup_logger()
        self._save_configs()
        self._save_summary("in_progress")
        return self

    def mark_cancelled(self) -> None:
        """Signal that the pipeline was externally cancelled between jobs."""
        self._cancelled = True

    def set_progress(self, step: int, total: int, label: str) -> None:
        """Stamp coarse "Job X of N" progress on the card.

        ``step`` is the count of jobs already finished; ``label`` is the job
        about to run. Persists immediately so polling clients see the update.
        """
        self._progress = {"step": step, "total": total, "label": label}
        self._save_summary("in_progress")

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Write the final pipeline summary and detach the log handler."""
        import backend.src.core.logging_config as logging_config
        from backend.src.core.cancellation import unregister

        unregister(self.pipeline_id)

        if self._cancelled:
            status = "cancelled"
            logger.info("Pipeline %s cancelled. Card updated to 'cancelled'.", self.pipeline_id)
        else:
            status = self._compute_final_status(interrupted=exc_type is not None)
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
        evaluation_id: str | None = None,
    ) -> None:
        """Record the output references produced by a pipeline job.

        A job with at least one produced artifact (model, simulation, or
        evaluation) is considered ``completed``. A job that registered none is
        ``failed``.

        Args:
            job_name (str): Human-readable name of the job.
            model_id (str | None): Model folder name, if a train step ran.
            simulation_id (str | None): Simulation folder name, if a simulate step ran.
            evaluation_id (str | None): Evaluation folder name, if an evaluate step ran.
        """
        produced_artifact = (
            model_id is not None or simulation_id is not None or evaluation_id is not None
        )
        job_status = "completed" if produced_artifact else "failed"
        entry: dict = {"job_name": job_name, "status": job_status}
        if model_id is not None:
            entry["model_id"] = model_id
            entry["model_output_dir"] = os.path.join(MODELS_DIR, model_id)
        if simulation_id is not None:
            entry["simulation_id"] = simulation_id
            entry["simulation_output_dir"] = os.path.join(SIMULATIONS_DIR, simulation_id)
        if evaluation_id is not None:
            entry["evaluation_id"] = evaluation_id
            entry["evaluation_output_dir"] = os.path.join(EVALUATIONS_DIR, evaluation_id)
        self._job_results.append(entry)
        self._save_summary("in_progress")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _compute_final_status(self, interrupted: bool) -> str:
        """Derive the overall pipeline status from the recorded jobs."""
        if not self._job_results:
            return "failed" if interrupted else "completed"

        completed_jobs = sum(1 for job in self._job_results if job.get("status") == "completed")
        total_jobs = len(self._job_results)

        if completed_jobs == 0:
            return "failed"
        if completed_jobs == total_jobs and not interrupted:
            return "completed"
        return "partial"

    def _setup_logger(self) -> None:
        """Create the pipeline file handler and attach it to all existing loggers.

        Registers the handler globally in ``logging_config`` so that any
        logger created later (e.g. by lazy imports) also picks it up
        automatically via ``get_logger()``.
        """
        import backend.src.core.logging_config as logging_config

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
        """Write the pipeline card with references to all job outputs.

        Args:
            status (str): Overall pipeline outcome
                (``in_progress``, ``completed``, ``partial`` or ``failed``).
        """
        card = {
            "pipeline_id": self.pipeline_id,
            "status": status,
            "timestamp": general_config.get_run_timestamp(),
            "config_path": self.config_path,
            "configs": {
                "pipeline_config": os.path.join(self.configs_directory, "pipeline_config.yaml"),
                "general_config": os.path.join(self.configs_directory, "general_config.json"),
            },
            "jobs": self._job_results,
        }
        if self._progress is not None and status == "in_progress":
            card["progress"] = self._progress
        card_path = os.path.join(self.output_directory, PIPELINE_CARD_FILENAME)
        with open(card_path, "w", encoding="utf-8") as file_handle:
            json.dump(card, file_handle, indent=4)
        logger.info("Pipeline card saved to '%s'.", card_path)

    def _save_configs(self) -> None:
        """Archive the input pipeline configuration and general settings."""
        self._archive_pipeline_config()
        self._archive_general_config_snapshot()
        logger.info("Configs archived to '%s'.", self.configs_directory)

    def _archive_pipeline_config(self) -> None:
        """Copy the pipeline YAML configuration to the output directory."""
        if not os.path.exists(self.config_path):
            logger.warning("Pipeline config file not found: %s", self.config_path)
            return

        dest_path = os.path.join(self.configs_directory, "pipeline_config.yaml")
        shutil.copy2(self.config_path, dest_path)

    def _archive_general_config_snapshot(self) -> None:
        """Persist a snapshot of ``general_config`` constants for provenance."""
        from backend.src.config.general import (
            DEFAULT_SAMPLE_SIZE,
            ENABLE_DATA_PROFILING,
            LOG_LEVEL,
            MODELS_DIR,
            SIMULATIONS_DIR,
        )

        snapshot = {
            "default_sample_size": DEFAULT_SAMPLE_SIZE,
            "enable_data_profiling": ENABLE_DATA_PROFILING,
            "log_level": logging.getLevelName(LOG_LEVEL),
            "models_dir": MODELS_DIR,
            "simulations_dir": SIMULATIONS_DIR,
        }
        out_path = os.path.join(self.configs_directory, "general_config.json")
        with open(out_path, "w", encoding="utf-8") as file_handle:
            json.dump(snapshot, file_handle, indent=4)
