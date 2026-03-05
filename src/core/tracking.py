"""MLOps tracking for the synthetic data pipeline.

Provides ModelTracker and SimulationTracker context managers that handle:
- Directory structure creation with timestamped IDs.
- SHA-256 hashing of original datasets for data provenance.
- Model/simulation card JSON generation.
- Configuration archiving (mostly_config, general_config, rules).
- Per-run file logging (train.log / sim.log).
- MLflow experiment tracking (parameters, metrics, artifacts).
- Temporary directory management for MostlyAI intermediate output.
"""

import hashlib
import json
import logging
import os
import pickle
import tempfile
from pathlib import Path
from types import TracebackType

import mlflow
import pandas as pd
import sagemaker_mlflow  # noqa: F401
import yaml
from config.general_config import (
    GENERATOR_ZIP_NAME,
    METADATA_FILENAME,
    MLFLOW_EXPERIMENT_SIMULATION,
    MLFLOW_EXPERIMENT_TRAINING,
    MLFLOW_TRACKING_URI,
    MODEL_CARD_FILENAME,
    MODEL_RUN_FOLDER_PREFIX,
    MODELS_DIR,
    MOSTLYAI_CONFIG_PATH,
    RULES_CONFIG_PATH,
    RUN_TIMESTAMP,
    SIM_CARD_FILENAME,
    SIM_CONFIG_FILENAME,
    SIMULATION_RUN_FOLDER_PREFIX,
    SIMULATIONS_DIR,
    SESSION_LOG_FILENAME,
    USERPROFILENAME,
)

from src.core.logging_config import get_logger, setup_run_logger
from src.core.preprocessing.logical_rules import LogicalRuleManager

logger = get_logger(__name__)


def compute_file_sha256(file_path: str) -> str:
    """Compute the SHA-256 hash of a file.

    Reads the file in 64 KB chunks to avoid loading large files entirely
    into memory.

    Args:
        file_path (str): Absolute or relative path to the file.

    Returns:
        str: Hexadecimal SHA-256 digest of the file contents.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as file_handle:
        for chunk in iter(lambda: file_handle.read(65536), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


class ModelTracker:
    """Manages lineage, directory structure, and MLflow tracking for a training run.

    Use as a context manager to automatically create the output directory tree,
    compute dataset hashes, start an MLflow run, provision a temporary directory
    for MostlyAI, and clean everything up on exit.

    Args:
        data_file_paths (list[str]): Paths to the original data files in ``data/``.
        mostly_config_path (str): Path to the MostlyAI YAML configuration.
        rules_config_path (str): Path to the rules YAML configuration.

    Example:
        >>> with ModelTracker(data_files, mostly_cfg, rules_cfg) as tracker:
        ...     engine = MostlyAIEngine(config_path=mostly_cfg)
        ...     os.environ["MOSTLYAI_LOCAL_DIR"] = tracker.get_tempdir()
        ...     generator = engine.train(data, metadata, tracker.output_directory)
        ...     tracker.save_generator(generator)
    """

    def __init__(
        self,
        data_file_paths: list[str],
        mostly_config_path: str = MOSTLYAI_CONFIG_PATH,
        rules_config_path: str = RULES_CONFIG_PATH,
    ) -> None:
        self.data_file_paths = data_file_paths
        self.mostly_config_path = mostly_config_path
        self.rules_config_path = rules_config_path

        self.model_id: str = f"{MODEL_RUN_FOLDER_PREFIX}_{RUN_TIMESTAMP}"
        self.output_directory: str = os.path.join(MODELS_DIR, self.model_id)
        self.configs_directory: str = os.path.join(self.output_directory, "configs")

        self._tempdir: tempfile.TemporaryDirectory | None = None
        self._mlflow_run: mlflow.ActiveRun | None = None
        self._run_logger: logging.Logger | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self) -> "ModelTracker":
        """Set up directories, configs, MLflow run, logger, and tempdir."""
        os.makedirs(self.configs_directory, exist_ok=True)
        logger.info("Created model output directory: %s", self.output_directory)

        self._setup_logger()
        self._save_configs()
        self._save_model_card()
        self._start_mlflow_run()
        self._tempdir = tempfile.TemporaryDirectory(prefix="mostlyai_")
        logger.info("MostlyAI temp directory: %s", self._tempdir.name)

        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Clean up tempdir and end MLflow run."""
        if self._tempdir is not None:
            self._tempdir.cleanup()
            logger.info("Cleaned up MostlyAI temp directory.")

        if self._mlflow_run is not None:
            if exc_type is not None:
                mlflow.set_tag("run_status", "FAILED")
                mlflow.set_tag("error", str(exc_val))
            else:
                mlflow.set_tag("run_status", "SUCCESS")

            card_path = os.path.join(self.output_directory, MODEL_CARD_FILENAME)
            if os.path.exists(card_path):
                mlflow.log_artifact(card_path)
            log_path = os.path.join(self.output_directory, SESSION_LOG_FILENAME)
            if os.path.exists(log_path):
                mlflow.log_artifact(log_path)

            mlflow.end_run()
            logger.info("MLflow run ended.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get_tempdir(self) -> str:
        """Return the path to the managed temporary directory for MostlyAI.

        Returns:
            str: Path to the temporary directory. Only valid while the
                context manager is active.

        Raises:
            RuntimeError: If called outside the context manager.
        """
        if self._tempdir is None:
            raise RuntimeError("Temporary directory not available outside context manager.")
        return self._tempdir.name

    def save_metadata(self, metadata: dict) -> None:
        """Save metadata JSON and log it as an MLflow artifact.

        Args:
            metadata (dict): Table metadata dictionary.
        """
        metadata_path = os.path.join(self.output_directory, METADATA_FILENAME)
        with open(metadata_path, "w", encoding="utf-8") as file_handle:
            json.dump(metadata, file_handle, indent=4)
        logger.info("Metadata saved to '%s'.", metadata_path)
        mlflow.log_artifact(metadata_path)

    def save_rule_manager(self, rule_manager: LogicalRuleManager) -> None:
        """Save the rule manager as a pickle file and log to MLflow.

        Args:
            rule_manager (LogicalRuleManager): The rule manager to persist.
        """
        rule_manager_path = os.path.join(self.output_directory, "rule_manager.pkl")
        with open(rule_manager_path, "wb") as file_handle:
            pickle.dump(rule_manager, file_handle)
        logger.info("Rule manager saved to '%s'.", rule_manager_path)
        mlflow.log_artifact(rule_manager_path)

    def save_generator(self, generator: object) -> None:
        """Export the trained generator to a ZIP file and log to MLflow.

        Args:
            generator: MostlyAI Generator object with ``export_to_file`` method.
        """
        generator_path = os.path.join(self.output_directory, GENERATOR_ZIP_NAME)
        generator.export_to_file(generator_path)
        logger.info("Generator saved to '%s'.", generator_path)
        mlflow.log_artifact(generator_path)

    def save_data_profiles(self, data_profiles: dict[str, object]) -> None:
        """Save data profiling HTML reports and log to MLflow.

        Args:
            data_profiles (dict[str, object]): Mapping of table name to profile
                object with a ``to_file`` method.
        """
        for name, profile in data_profiles.items():
            output_file = os.path.join(self.output_directory, f"{name}_profiling_report.html")
            profile.to_file(output_file)
            logger.info("Data profile for '%s' saved.", name)
            mlflow.log_artifact(output_file)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _setup_logger(self) -> None:
        """Attach a file handler writing to ``session.log`` in the output directory."""
        log_path = os.path.join(self.output_directory, SESSION_LOG_FILENAME)
        self._run_logger = setup_run_logger(__name__, self.output_directory)
        # Also redirect the root pipeline logger so all modules log here
        root_logger = logging.getLogger("src")
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(handler)
        logger.info("Training run logger initialised: %s", log_path)

    def _compute_dataset_hashes(self) -> dict[str, str]:
        """Compute SHA-256 hashes for all original data files.

        Returns:
            dict[str, str]: Mapping of file path to its SHA-256 hex digest.
        """
        hashes: dict[str, str] = {}
        for file_path in self.data_file_paths:
            resolved = str(Path(file_path).resolve())
            hashes[resolved] = compute_file_sha256(file_path)
            logger.info("SHA-256 for '%s': %s", resolved, hashes[resolved])
        return hashes

    def _save_model_card(self) -> None:
        """Generate and write ``model_card.json``."""
        dataset_hashes = self._compute_dataset_hashes()
        model_card = {
            "model_id": self.model_id,
            "USERPROFILENAME": USERPROFILENAME,
            "timestamp": RUN_TIMESTAMP,
            "data_sources": [
                {
                    "path": path,
                    "sha256": sha256_hash,
                }
                for path, sha256_hash in dataset_hashes.items()
            ],
            "configs": {
                "mostly_config": os.path.join(self.configs_directory, "mostly_config.json"),
                "general_config": os.path.join(self.configs_directory, "general_config.json"),
                "rules_config": os.path.join(self.configs_directory, "rules_config.json"),
            },
        }
        card_path = os.path.join(self.output_directory, MODEL_CARD_FILENAME)
        with open(card_path, "w", encoding="utf-8") as file_handle:
            json.dump(model_card, file_handle, indent=4)
        logger.info("Model card saved to '%s'.", card_path)

    def _save_configs(self) -> None:
        """Copy and archive configuration files into the ``configs/`` subfolder."""
        # mostly_config.json (convert from YAML)
        with open(self.mostly_config_path, encoding="utf-8") as file_handle:
            mostly_config = yaml.safe_load(file_handle)
        mostly_out = os.path.join(self.configs_directory, "mostly_config.json")
        with open(mostly_out, "w", encoding="utf-8") as file_handle:
            json.dump(mostly_config, file_handle, indent=4)

        # general_config.json (snapshot of key constants)
        from config.general_config import (
            DEFAULT_SAMPLE_SIZE,
            ENABLE_DATA_PROFILING,
            LOG_LEVEL,
        )

        general_snapshot = {
            "default_sample_size": DEFAULT_SAMPLE_SIZE,
            "enable_data_profiling": ENABLE_DATA_PROFILING,
            "log_level": logging.getLevelName(LOG_LEVEL),
            "models_dir": MODELS_DIR,
            "simulations_dir": SIMULATIONS_DIR,
        }
        general_out = os.path.join(self.configs_directory, "general_config.json")
        with open(general_out, "w", encoding="utf-8") as file_handle:
            json.dump(general_snapshot, file_handle, indent=4)

        # rules_config.json (copy from YAML as JSON)
        if os.path.exists(self.rules_config_path):
            with open(self.rules_config_path, encoding="utf-8") as file_handle:
                rules_config = yaml.safe_load(file_handle)
            rules_out = os.path.join(self.configs_directory, "rules_config.json")
            with open(rules_out, "w", encoding="utf-8") as file_handle:
                json.dump(rules_config, file_handle, indent=4)

        logger.info("Configs archived to '%s'.", self.configs_directory)

    def _start_mlflow_run(self) -> None:
        """Configure MLflow tracking and start a new run for training."""
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT_TRAINING)
        self._mlflow_run = mlflow.start_run(run_name=self.model_id)

        mlflow.set_tag("model_id", self.model_id)
        mlflow.set_tag("phase", "training")
        mlflow.set_tag("user-profile-name", USERPROFILENAME)

        # Log configs as params
        with open(self.mostly_config_path, encoding="utf-8") as file_handle:
            mostly_config = yaml.safe_load(file_handle)
        generator_params = mostly_config.get("generator", {})
        mlflow.log_params({f"mostly.{key}": str(value) for key, value in generator_params.items()})
        mlflow.log_params(
            {
                f"mostly.model.{key}": str(value)
                for key, value in mostly_config.get("model_settings", {}).items()
                if not isinstance(value, dict)
            }
        )

        # Log config artifacts
        mlflow.log_artifacts(self.configs_directory, artifact_path="configs")
        logger.info("MLflow run started: %s", self._mlflow_run.info.run_id)


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

    def __init__(self, model_id: str) -> None:
        self.model_id = model_id
        self.simulation_id: str = f"{SIMULATION_RUN_FOLDER_PREFIX}_{RUN_TIMESTAMP}"
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

        self._setup_logger()
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
            "timestamp": RUN_TIMESTAMP,
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

        # Log key params
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

        # Log summary metrics
        total_checks = len(report_dataframe)
        failed_checks = int((report_dataframe.get("status", pd.Series()) == "FAIL").sum())
        mlflow.log_metrics(
            {"sanity_total_checks": total_checks, "sanity_failed_checks": failed_checks}
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _setup_logger(self) -> None:
        """Attach a file handler writing to ``sim.log`` in the output directory."""
        log_path = os.path.join(self.output_directory, SESSION_LOG_FILENAME)
        self._run_logger = setup_run_logger(__name__, self.output_directory)
        root_logger = logging.getLogger("src")
        handler = logging.FileHandler(log_path, encoding="utf-8")
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        root_logger.addHandler(handler)
        logger.info("Simulation run logger initialised: %s", log_path)

    def _start_mlflow_run(self) -> None:
        """Configure MLflow tracking and start a new run for simulation."""
        mlflow.set_tracking_uri(MLFLOW_TRACKING_URI)
        mlflow.set_experiment(MLFLOW_EXPERIMENT_SIMULATION)
        os.environ["MLFLOW_TRACKING_USERNAME"] = USERPROFILENAME
        self._mlflow_run = mlflow.start_run(run_name=self.simulation_id)

        mlflow.set_tag("model_id", self.model_id)
        mlflow.set_tag("phase", "simulation")
        mlflow.set_tag("user-profile-name", USERPROFILENAME)
        logger.info("MLflow simulation run started: %s", self._mlflow_run.info.run_id)
