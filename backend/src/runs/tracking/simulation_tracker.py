"""Simulation-run tracker.

``SimulationTracker`` mirrors ``ModelTracker`` for the generation/simulation
stage: it creates the output folder, writes a sim card linking back to the
parent model, and offers ``save_*`` helpers used by the simulation flow.
"""

import json
import os
import shutil

import backend.src.config.general as general_config
import pandas as pd
from backend.src.config.general import (
    MODEL_CARD_FILENAME,
    MODELS_DIR,
    MOSTLYAI_DIR,
    NO_PIPELINE_ID,
    SIM_CARD_FILENAME,
    SIM_CONFIG_FILENAME,
    SIMULATION_RUN_FOLDER_PREFIX,
    SIMULATIONS_DIR,
    SYNTHETIC_DATA_FILE_FORMAT,
    USERPROFILENAME,
    synthetic_data_file_extension,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.runs.tracking.base_tracker import BaseRunTracker

logger = get_logger(__name__)


class SimulationTracker(BaseRunTracker):
    """Manages lineage, directory structure, and on-disk artifacts for a simulation run.

    Use as a context manager. Automatically creates the output directory and
    writes the sim card linking back to the parent model.

    Args:
        model_id (str): Identifier of the parent model
            (e.g. ``model_20260226_104157``).

    Example:
        >>> with SimulationTracker("model_20260226_104157") as tracker:
        ...     results = engine.simulate(generator, sim_config)
        ...     tracker.save_synthetic_results(results)
    """

    card_filename = SIM_CARD_FILENAME
    run_kind = "simulation"

    def __init__(
        self,
        model_id: str,
        pipeline_id: str = NO_PIPELINE_ID,
        job_name: str = "",
        simulation_id: str | None = None,
        synthetic_data_file_format: str = SYNTHETIC_DATA_FILE_FORMAT,
    ) -> None:
        super().__init__()
        self.model_id = model_id
        self.pipeline_id = pipeline_id
        self.job_name = job_name
        self.synthetic_data_file_format = synthetic_data_file_format
        self.simulation_id: str = simulation_id or (
            f"{SIMULATION_RUN_FOLDER_PREFIX}_{general_config.get_run_timestamp()}"
        )
        self.run_id = self.simulation_id
        self.output_directory: str = os.path.join(SIMULATIONS_DIR, self.simulation_id)
        self.synthetic_data_directory: str = os.path.join(self.output_directory, "synthetic_data")

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def _on_enter(self) -> None:
        os.makedirs(self.synthetic_data_directory, exist_ok=True)
        self._copy_parent_training_artifacts()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def save_sim_card(self, sample_size: int | None = None) -> None:
        """Write ``sim_card.json`` linking this simulation to its parent model.

        Written at the start of the run with ``status: "in_progress"``.
        The status is updated to ``"completed"`` or ``"failed"`` on context exit.

        Args:
            sample_size (int | None): Number of synthetic records requested.
        """
        self.write_initial_card(
            {
                "simulation_id": self.simulation_id,
                "model_id": self.model_id,
                "USERPROFILENAME": USERPROFILENAME,
                "timestamp": general_config.get_run_timestamp(),
                "pipeline_id": self.pipeline_id,
                "job_name": self.job_name,
                "sample_size": sample_size,
                "synthetic_data_file_format": self.synthetic_data_file_format,
            }
        )

    def save_sim_config(self, simulation_config: dict) -> None:
        """Serialize the simulation configuration to JSON inside the run folder.

        Args:
            simulation_config (dict): The simulation configuration dictionary.
        """
        config_path = os.path.join(self.output_directory, SIM_CONFIG_FILENAME)
        with open(config_path, "w", encoding="utf-8") as file_handle:
            json.dump(simulation_config, file_handle, indent=4)
        logger.info("Sim config saved to '%s'.", config_path)

    def save_synthetic_results(self, synthetic_results: dict[str, pd.DataFrame]) -> None:
        """Save generated tables to ``synthetic_data/``.

        Args:
            synthetic_results (dict[str, pd.DataFrame]): Mapping of table name
                to its DataFrame of synthetic records.
        """
        file_extension = synthetic_data_file_extension(self.synthetic_data_file_format)
        for table_name, dataframe in synthetic_results.items():
            file_path = os.path.join(
                self.synthetic_data_directory, f"{table_name}_synthetic{file_extension}"
            )
            if self.synthetic_data_file_format == "parquet":
                dataframe.to_parquet(file_path, index=False)
            else:
                dataframe.to_csv(file_path, index=False)
            logger.info(
                "Synthetic data for '%s' saved to '%s' (%d rows).",
                table_name,
                file_path,
                len(dataframe),
            )

    def save_sanity_report(self, report_dataframe: pd.DataFrame) -> None:
        """Save the unified sanity checks CSV report.

        Args:
            report_dataframe (pd.DataFrame): Concatenated sanity check results.
        """
        report_path = os.path.join(self.output_directory, "sanity_checks_report.csv")
        report_dataframe.to_csv(report_path, index=False)
        logger.info("Sanity checks report saved to '%s'.", report_path)

    def save_rejection_sampling_report(self, stats: dict) -> None:
        """Save rejection sampling stats locally and patch them onto the sim card."""
        report_path = os.path.join(self.output_directory, "rejection_sampling_report.json")
        with open(report_path, "w", encoding="utf-8") as file_handle:
            json.dump(stats, file_handle, indent=4)
        logger.info("Rejection sampling report saved to '%s'.", report_path)
        self.patch_card(rejection_sampling=stats)

    def save_job_progress(self, synthetic_dataset_id: str) -> None:
        """Copy job_progress.json from MostlyAI's synthetic-dataset folder to the sim folder.

        Args:
            synthetic_dataset_id (str): The MostlyAI synthetic dataset UUID returned by simulate().
        """
        src = os.path.join(MOSTLYAI_DIR, "synthetic-datasets", synthetic_dataset_id, "job_progress.json")
        dst = os.path.join(self.output_directory, "job_progress.json")
        if not os.path.exists(src):
            logger.warning("job_progress.json not found at '%s'; skipping copy.", src)
            return
        shutil.copy2(src, dst)
        logger.info("Job progress copied to '%s'.", dst)

    def save_sim_metadata(self, metadata: dict) -> None:
        """Save the extracted metadata from synthetic data to JSON.

        Writes the synthetic data metadata to ``sim_metadata.json`` within the
        simulation output directory.
        """
        metadata_path = os.path.join(self.output_directory, "sim_metadata.json")
        with open(metadata_path, "w", encoding="utf-8") as file_handle:
            json.dump(metadata, file_handle, indent=4)
        logger.info("Synthetic data metadata saved to '%s'.", metadata_path)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _copy_parent_training_artifacts(self) -> None:
        """Copy the parent model's configs and card into this sim's ``training/`` subfolder.

        Gives the simulation run a self-contained record of the training it
        depends on, in case the original model folder is later moved or pruned.
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
