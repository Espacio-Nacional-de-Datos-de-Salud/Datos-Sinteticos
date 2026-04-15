"""Simulation-run tracker.

``SimulationTracker`` mirrors ``ModelTracker`` for the generation/simulation
stage: it creates the output folder, starts an MLflow run linked to the
parent model, and forwards the parent model's training parameters to the
simulation run so both are filterable side-by-side in the MLflow UI.
"""

import json
import logging
import os
import shutil
from types import TracebackType

import config.general_config as general_config
import mlflow
import pandas as pd
import sagemaker_mlflow  # noqa: F401
from config.general_config import (
    MLFLOW_EXPERIMENT_SIMULATION,
    MLFLOW_TRACKING_URI,
    MODEL_CARD_FILENAME,
    MODELS_DIR,
    NO_PIPELINE_ID,
    SESSION_LOG_FILENAME,
    SIM_CARD_FILENAME,
    SIM_CONFIG_FILENAME,
    SIMULATION_RUN_FOLDER_PREFIX,
    SIMULATIONS_DIR,
    USERPROFILENAME,
)

from src.core.logging_config import get_logger
from src.core.tracking._mostly_config import log_mostly_config_params
from src.core.tracking._session_logger import attach_session_file_handler

logger = get_logger(__name__)


class SimulationTracker:
    """Manages lineage, directory structure, and MLflow tracking for a simulation run.

    Use as a context manager. Automatically creates the output directory,
    writes the sim card linking back to the parent model, and starts an
    MLflow run.

    Args:
        model_id (str): Identifier of the parent model
            (e.g. ``model_20260226_104157``).

    Example:
        >>> with SimulationTracker("model_20260226_104157") as tracker:
        ...     results = engine.simulate(generator, sim_config)
        ...     tracker.save_synthetic_results(results)
    """

    def __init__(
        self, model_id: str, pipeline_id: str = NO_PIPELINE_ID, job_name: str = ""
    ) -> None:
        self.model_id = model_id
        self.pipeline_id = pipeline_id
        self.job_name = job_name
        self.simulation_id: str = (
            f"{SIMULATION_RUN_FOLDER_PREFIX}_{general_config.get_run_timestamp()}"
        )
        self.output_directory: str = os.path.join(SIMULATIONS_DIR, self.simulation_id)
        self.synthetic_data_directory: str = os.path.join(self.output_directory, "synthetic_data")

        self._mlflow_run: mlflow.ActiveRun | None = None
        self._run_logger: logging.Logger | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> "SimulationTracker":
        """Create directories, logger, MLflow run, and initial sim card."""
        os.makedirs(self.synthetic_data_directory, exist_ok=True)
        logger.info("Created simulation output directory: %s", self.output_directory)

        self._run_logger = attach_session_file_handler(self.output_directory, __name__)
        self._start_mlflow_run()

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """End MLflow run."""
        if self._mlflow_run is not None:
            if exc_type is not None:
                mlflow.set_tag("run_status", "FAILED")
                mlflow.set_tag("error", str(exc_val))
            else:
                mlflow.set_tag("run_status", "SUCCESS")

            log_path = os.path.join(self.output_directory, SESSION_LOG_FILENAME)
            if os.path.exists(log_path):
                mlflow.log_artifact(log_path)

            mlflow.end_run()
            logger.info("MLflow simulation run ended.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def save_sim_card(self, sample_size: int | None = None) -> None:
        """Write ``sim_card.json`` linking this simulation to its parent model.

        Args:
            sample_size (int | None): Number of synthetic records requested.
        """
        sim_card = {
            "simulation_id": self.simulation_id,
            "model_id": self.model_id,
            "USERPROFILENAME": USERPROFILENAME,
            "timestamp": general_config.get_run_timestamp(),
            "pipeline_id": self.pipeline_id,
            "job_name": self.job_name,
            "sample_size": sample_size,
        }
        card_path = os.path.join(self.output_directory, SIM_CARD_FILENAME)
        with open(card_path, "w", encoding="utf-8") as file_handle:
            json.dump(sim_card, file_handle, indent=4)
        logger.info("Sim card saved to '%s'.", card_path)
        mlflow.log_artifact(card_path)

    def save_sim_config(self, simulation_config: dict) -> None:
        """Serialize the simulation configuration to JSON and log to MLflow.

        Args:
            simulation_config (dict): The simulation configuration dictionary.
        """
        config_path = os.path.join(self.output_directory, SIM_CONFIG_FILENAME)
        with open(config_path, "w", encoding="utf-8") as file_handle:
            json.dump(simulation_config, file_handle, indent=4)
        logger.info("Sim config saved to '%s'.", config_path)
        mlflow.log_artifact(config_path)

        for table_entry in simulation_config.get("tables", []):
            table_name = table_entry.get("name", "unknown")
            table_config = table_entry.get("configuration", {})
            for key, value in table_config.items():
                mlflow.log_param(f"sim.{table_name}.{key}", value)

    def save_synthetic_results(self, synthetic_results: dict[str, pd.DataFrame]) -> None:
        """Save generated CSV tables to ``synthetic_data/`` and log to MLflow.

        Args:
            synthetic_results (dict[str, pd.DataFrame]): Mapping of table name
                to its DataFrame of synthetic records.
        """
        for table_name, dataframe in synthetic_results.items():
            file_path = os.path.join(self.synthetic_data_directory, f"{table_name}_synthetic.csv")
            dataframe.to_csv(file_path, index=False)
            logger.info(
                "Synthetic data for '%s' saved to '%s' (%d rows).",
                table_name,
                file_path,
                len(dataframe),
            )
        mlflow.log_artifacts(self.synthetic_data_directory, artifact_path="synthetic_data")

    def save_sanity_report(self, report_dataframe: pd.DataFrame) -> None:
        """Save the unified sanity checks CSV report and log to MLflow.

        Args:
            report_dataframe (pd.DataFrame): Concatenated sanity check results.
        """
        report_path = os.path.join(self.output_directory, "sanity_checks_report.csv")
        report_dataframe.to_csv(report_path, index=False)
        logger.info("Sanity checks report saved to '%s'.", report_path)
        mlflow.log_artifact(report_path)

        total_checks = len(report_dataframe)
        failed_checks = int((report_dataframe.get("status", pd.Series()) == "FAIL").sum())
        mlflow.log_metrics(
            {"sanity_total_checks": total_checks, "sanity_failed_checks": failed_checks}
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _start_mlflow_run(self) -> None:
        """Configure MLflow tracking and start a new run for simulation."""
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT_SIMULATION)
        os.environ["MLFLOW_TRACKING_USERNAME"] = USERPROFILENAME
        self._mlflow_run = mlflow.start_run(run_name=self.simulation_id)

        mlflow.set_tag("model_id", self.model_id)
        mlflow.set_tag("phase", "simulation")
        mlflow.set_tag("user-profile-name", USERPROFILENAME)
        mlflow.set_tag("pipeline_id", self.pipeline_id)
        mlflow.set_tag("job_name", self.job_name)

        self._log_parent_training_params()
        self._copy_parent_training_artifacts()

        logger.info("MLflow simulation run started: %s", self._mlflow_run.info.run_id)

    def _log_parent_training_params(self) -> None:
        """Mirror the parent model's Mostly AI config into MLflow with a ``train.`` prefix."""
        model_dir = os.path.join(MODELS_DIR, self.model_id)
        mostly_config_path = os.path.join(model_dir, "configs", "mostly_config.json")
        model_card_path = os.path.join(model_dir, MODEL_CARD_FILENAME)

        try:
            if not os.path.exists(mostly_config_path):
                logger.warning(
                    "Parent model config not found at '%s'; skipping config params.",
                    mostly_config_path,
                )
                return

            with open(mostly_config_path, encoding="utf-8") as fh:
                mostly_config = json.load(fh)

            data_file_paths: list[str] = []
            if os.path.exists(model_card_path):
                with open(model_card_path, encoding="utf-8") as fh:
                    model_card = json.load(fh)
                data_file_paths = [src["path"] for src in model_card.get("data_sources", [])]

            log_mostly_config_params(mostly_config, data_file_paths, prefix="train.")
        except Exception:
            logger.warning("Failed to log training config params to MLflow.", exc_info=True)

    def _copy_parent_training_artifacts(self) -> None:
        """Copy the parent model's configs and card into this sim's ``training/`` subfolder.

        Also logs the copied bundle to MLflow so the simulation run carries a
        self-contained record of the training it depends on.
        """
        model_dir = os.path.join(MODELS_DIR, self.model_id)
        model_card_path = os.path.join(model_dir, MODEL_CARD_FILENAME)

        if not os.path.exists(model_dir):
            logger.warning(
                "Training model directory not found locally: '%s'. "
                "Training artifacts will not be copied.",
                model_dir,
            )
            return

        training_artifacts_dir = os.path.join(self.output_directory, "training")
        os.makedirs(training_artifacts_dir, exist_ok=True)

        configs_src = os.path.join(model_dir, "configs")
        if os.path.exists(configs_src):
            configs_dst = os.path.join(training_artifacts_dir, "configs")
            shutil.copytree(configs_src, configs_dst, dirs_exist_ok=True)
            logger.info("Copied training configs to '%s'.", configs_dst)

        if os.path.exists(model_card_path):
            model_card_dst = os.path.join(training_artifacts_dir, MODEL_CARD_FILENAME)
            shutil.copy2(model_card_path, model_card_dst)
            logger.info("Copied training model card to '%s'.", model_card_dst)

        mlflow.log_artifacts(training_artifacts_dir, artifact_path="training")
        logger.info("Logged training artifacts to MLflow.")
