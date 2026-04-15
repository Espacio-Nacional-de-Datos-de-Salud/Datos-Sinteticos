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
import shutil
import tempfile
import zipfile
from pathlib import Path
from types import TracebackType

import config.general_config as general_config
import mlflow
import pandas as pd
import sagemaker_mlflow  # noqa: F401
import yaml
from config.general_config import (
    GENERATOR_ZIP_NAME,
    LOG_LEVEL,
    METADATA_FILENAME,
    MLFLOW_EXPERIMENT_SIMULATION,
    MLFLOW_EXPERIMENT_TRAINING,
    MLFLOW_TRACKING_URI,
    MODEL_CARD_FILENAME,
    MODEL_RUN_FOLDER_PREFIX,
    MODELS_DIR,
    MOSTLYAI_CONFIG_PATH,
    MOSTLYAI_DIR,
    NO_PIPELINE_ID,
    PIPELINE_RUN_FOLDER_PREFIX,
    PIPELINES_DIR,
    RULES_CONFIG_PATH,
    SESSION_LOG_FILENAME,
    SIM_CARD_FILENAME,
    SIM_CONFIG_FILENAME,
    SIMULATION_RUN_FOLDER_PREFIX,
    SIMULATIONS_DIR,
    USERPROFILENAME,
)

from src.core.logging_config import get_logger, setup_run_logger
from src.core.preprocessing.logical_rules import LogicalRuleManager
from src.core.utils import deep_merge

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


def _load_mostly_config(config_path: str, overrides: dict | None = None) -> dict:
    """Load a Mostly AI YAML config and optionally apply overrides."""
    with open(config_path, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    if overrides:
        logger.debug("Applying mostly_ai overrides: %s", overrides)
        config = deep_merge(config, overrides)
    else:
        logger.debug("No mostly_ai overrides to apply.")
    return config


def _log_mostly_config_params(
    mostly_config: dict, data_file_paths: list[str], prefix: str = ""
) -> None:
    """Log Mostly AI configuration as MLflow params.

    Logs generator settings, model settings (flat keys), differential privacy
    parameters, model type, and training data file paths so they are
    filterable/sortable in the MLflow UI.

    Extracted so that it can be used by both the Model and Simulation trackers.

    Args:
        mostly_config: Parsed Mostly AI YAML configuration dict.
        data_file_paths: Paths to the original data files used for training.
        prefix: Optional prefix prepended to every param key (e.g. ``"train."``).
    """
    p = prefix

    generator_params = mostly_config.get("generator", {})
    mlflow.log_params({f"{p}mostly.{key}": str(value) for key, value in generator_params.items()})

    model_settings = mostly_config.get("model_settings", {})
    mlflow.log_params(
        {
            f"{p}mostly.model.{key}": str(value)
            for key, value in model_settings.items()
            if not isinstance(value, dict)
        }
    )

    # Differential privacy params
    dp_config = model_settings.get("differential_privacy", {})
    mlflow.log_param(f"{p}mostly.model.dp.enabled", bool(dp_config))
    if dp_config:
        mlflow.log_params(
            {f"{p}mostly.model.dp.{key}": str(value) for key, value in dp_config.items()}
        )

    # Model type (defaults to MOSTLY_AI/Medium when not specified)
    mlflow.log_param(f"{p}mostly.model.type", model_settings.get("model", "MOSTLY_AI/Medium"))

    # Training data files
    for idx, file_path in enumerate(data_file_paths):
        mlflow.log_param(f"{p}.file.{idx}", file_path)


class ModelTracker:
    """Manages lineage, directory structure, and MLflow tracking for a training run.

    Use as a context manager to automatically create the output directory tree,
    compute dataset hashes, start an MLflow run, provision a temporary directory
    for MostlyAI, and clean everything up on exit.

    Args:
        data_file_paths (list[str]): Paths to the original data files in ``data/``.
        mostly_config_path (str): Path to the MostlyAI YAML configuration.
        rules_config_path (str): Path to the rules YAML configuration.
        mostly_ai_overrides (dict | None): Per-job overrides to deep-merge
            into the base Mostly AI config before logging and archiving.

    Example:
        >>> with ModelTracker(data_files, mostly_cfg, rules_cfg) as tracker:
        ...     engine = MostlyAIEngine(config_path=mostly_cfg)
        ...     generator = engine.train(data, metadata, tracker.output_directory)
        ...     tracker.save_generator(generator)
    """

    def __init__(
        self,
        data_file_paths: list[str],
        mostly_config_path: str = MOSTLYAI_CONFIG_PATH,
        rules_config_path: str = RULES_CONFIG_PATH,
        pipeline_id: str = NO_PIPELINE_ID,
        mostly_ai_overrides: dict | None = None,
        job_name: str = "",
    ) -> None:
        self.data_file_paths = data_file_paths
        self.mostly_config_path = mostly_config_path
        self.rules_config_path = rules_config_path
        self.pipeline_id = pipeline_id
        self.mostly_ai_overrides = mostly_ai_overrides
        self.job_name = job_name

        self.model_id: str = f"{MODEL_RUN_FOLDER_PREFIX}_{general_config.get_run_timestamp()}"
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

        Extracts job_progress.json from the generator ZIP and saves it both
        locally and as an MLflow artifact. Extracts metrics from job_progress and
        forwards them to MLflow
        Args:
            generator: MostlyAI Generator object with ``export_to_file`` method.
        """
        generator_path = os.path.join(self.output_directory, GENERATOR_ZIP_NAME)
        generator.export_to_file(generator_path)
        logger.info("Generator saved to '%s'.", generator_path)
        mlflow.log_artifact(generator_path)

        # Extract job_progress.json from the ZIP
        job_progress_path = os.path.join(self.output_directory, "job_progress.json")
        with zipfile.ZipFile(generator_path, "r") as zip_file:
            zip_file.extract("job_progress.json", self.output_directory)
        logger.info("Job progress extracted to '%s'.", job_progress_path)
        mlflow.log_artifact(job_progress_path)
        self._save_train_metrics(progress_path=job_progress_path)

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

    def save_training_table_sizes(self, processed_data: dict[str, pd.DataFrame]) -> None:
        """Persist training row counts per table to model_card.json and MLflow.

        Args:
            processed_data (dict[str, pd.DataFrame]): Final training input tables.
        """
        table_sizes: dict[str, int] = {}
        for table_name, table_df in processed_data.items():
            if hasattr(table_df, "__len__"):
                table_sizes[table_name] = int(len(table_df))

        if not table_sizes:
            logger.warning("No training table sizes were detected to persist in model card.")
            return

        card_path = os.path.join(self.output_directory, MODEL_CARD_FILENAME)
        if not os.path.exists(card_path):
            logger.warning(
                "Model card not found at '%s'; cannot update training table sizes.", card_path
            )
            return

        with open(card_path, encoding="utf-8") as file_handle:
            model_card = json.load(file_handle)

        model_card["training_table_sizes"] = table_sizes

        with open(card_path, "w", encoding="utf-8") as file_handle:
            json.dump(model_card, file_handle, indent=4)

        for table_name, size in table_sizes.items():
            mlflow.log_metric(f"training_rows.{table_name}", size)

        logger.info("Model card updated with training table sizes: %s", table_sizes)

    def save_qa_reports(self, generator_id: str) -> None:
        """Copy MostlyAI QA report HTML files to the model output directory and log to MLflow.

        Locates all HTML files from the MostlyAI generator's ModelQAReports
        directory, copies them to the local output directory, and logs them
        as MLflow artifacts.

        Args:
            generator_id (str): The generator ID (directory name under
                outputs/mostlyai/generators/).
        """
        qa_reports_dir = os.path.join(MOSTLYAI_DIR, "generators", generator_id, "ModelQAReports")

        if not os.path.exists(qa_reports_dir):
            logger.warning("QA reports directory not found: %s", qa_reports_dir)
            return

        if not os.path.isdir(qa_reports_dir):
            logger.warning("QA reports path is not a directory: %s", qa_reports_dir)
            return

        html_files = [f for f in os.listdir(qa_reports_dir) if f.endswith(".html")]

        if not html_files:
            logger.info("No HTML files found in QA reports directory: %s", qa_reports_dir)
            return

        local_qa_dir = os.path.join(self.output_directory, "qa_reports")
        os.makedirs(local_qa_dir, exist_ok=True)
        for filename in html_files:
            shutil.copy2(
                os.path.join(qa_reports_dir, filename), os.path.join(local_qa_dir, filename)
            )
        logger.info("Copied %d QA reports to '%s'.", len(html_files), local_qa_dir)

        mlflow.log_artifacts(qa_reports_dir, artifact_path="qa_reports")
        logger.info("Logged %d QA reports to MLflow from %s", len(html_files), qa_reports_dir)

    def save_mostly_statistics(self, generator_id: str) -> None:
        """Pulls useful statistics from generator.json and logs them to MLflow and model card

        Extracts generator-level and table-specific tabular model metrics,
        including accuracy, distances, and similarity metrics for each table.

        Args:
            generator_id (str): The generator ID (directory name under
                outputs/mostlyai/generators/).
        """

        generator_json_path = os.path.join(
            MOSTLYAI_DIR, "generators", generator_id, "generator.json"
        )

        if not os.path.exists(generator_json_path):
            logger.warning("Generator JSON file not found: %s", generator_json_path)
            return

        with open(generator_json_path, encoding="utf-8") as f:
            generator_data = json.load(f)

        mostly_statistics = {}

        # Log generator-level statistics
        generator_accuracy = generator_data.get("accuracy")
        if generator_accuracy is not None:
            mlflow.log_metric("mostly.generator_accuracy", generator_accuracy)
            mostly_statistics["generator_accuracy"] = generator_accuracy

        # Log table-specific tabular model metrics
        tables = generator_data.get("tables", [])
        tables_stats = {}
        for table_idx, table in enumerate(tables):
            table_name = table.get("name", f"table_{table_idx}")

            tabular_metrics = table.get("tabularModelMetrics")
            if tabular_metrics:
                current_table_stats = {}

                # Accuracy metrics
                accuracy_metrics = tabular_metrics.get("accuracy", {})
                if accuracy_metrics:
                    current_table_stats["accuracy"] = {}
                    for metric_name, metric_value in accuracy_metrics.items():
                        if metric_value is not None:
                            mlflow.log_metric(
                                f"mostly.{table_name}.accuracy.{metric_name}", metric_value
                            )
                            current_table_stats["accuracy"][metric_name] = metric_value

                # Distance metrics
                distance_metrics = tabular_metrics.get("distances", {})
                if distance_metrics:
                    current_table_stats["distances"] = {}
                    for metric_name, metric_value in distance_metrics.items():
                        if metric_value is not None:
                            mlflow.log_metric(
                                f"mostly.{table_name}.distances.{metric_name}", metric_value
                            )
                            current_table_stats["distances"][metric_name] = metric_value

                # Similarity metrics
                similarity_metrics = tabular_metrics.get("similarity", {})
                if similarity_metrics:
                    current_table_stats["similarity"] = {}
                    for metric_name, metric_value in similarity_metrics.items():
                        if metric_value is not None:
                            mlflow.log_metric(
                                f"mostly.{table_name}.similarity.{metric_name}", metric_value
                            )
                            current_table_stats["similarity"][metric_name] = metric_value

                tables_stats[table_name] = current_table_stats
                logger.info("Logged tabular metrics for table '%s' to MLflow.", table_name)
            else:
                logger.debug("No tabular model metrics found for table '%s'", table_name)

        mostly_statistics["tables"] = tables_stats
        self._update_model_card_with_statistics(mostly_statistics)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _save_train_metrics(self, progress_path: str) -> None:
        """Extracts metrics from job_progress.json and uploads them to MLflow

        Args:
            progress_path (str): Path to job_progress.json, one file inside
                generator.json as created by MostlyAI

        """
        with open(progress_path, encoding="utf-8") as f:
            job_progress = json.load(f)

        for step in job_progress.get("steps", []):
            if (
                step.get("stepCode") == "TRAIN_MODEL"
                and step.get("messages")
                and len(step["messages"]) > 1
            ):
                modelLabel = step.get("modelLabel")

                for msg in step["messages"]:
                    epoch = msg["epoch"]
                    epoch = int(epoch)

                    if msg.get("trn_loss"):
                        mlflow.log_metric(f"{modelLabel} Train Loss", msg["trn_loss"], epoch)
                    if msg.get("val_loss"):
                        mlflow.log_metric(f"{modelLabel} Val Loss", msg["val_loss"], epoch)

                # log number of epochs and total time from last message
                lastMsg = step["messages"][-1]
                mlflow.log_metric(f"{modelLabel} Total Epochs", lastMsg["epoch"])
                mlflow.log_metric(f"{modelLabel} Total Time s", lastMsg["total_time"])

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
            "timestamp": general_config.get_run_timestamp(),
            "pipeline_id": self.pipeline_id,
            "job_name": self.job_name,
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

    def _update_model_card_with_statistics(self, statistics: dict) -> None:
        """Update the model card with mostly statistics.

        Args:
            statistics (dict): Dictionary of statistics to add to the model card.
        """
        card_path = os.path.join(self.output_directory, MODEL_CARD_FILENAME)

        if not os.path.exists(card_path):
            logger.warning(
                "Model card not found at '%s'; cannot update with statistics.", card_path
            )
            return

        with open(card_path, encoding="utf-8") as file_handle:
            model_card = json.load(file_handle)

        model_card["mostly_statistics"] = statistics

        with open(card_path, "w", encoding="utf-8") as file_handle:
            json.dump(model_card, file_handle, indent=4)

        logger.info("Model card updated with mostly statistics.")

    def _save_configs(self) -> None:
        """Copy and archive configuration files into the ``configs/`` subfolder."""
        # mostly_config.json (convert from YAML, applying any per-job overrides)
        mostly_config = _load_mostly_config(self.mostly_config_path, self.mostly_ai_overrides)
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
        mlflow.set_tag("pipeline_id", self.pipeline_id)
        mlflow.set_tag("job_name", self.job_name)

        # Log configs as params
        try:
            mostly_config = _load_mostly_config(self.mostly_config_path, self.mostly_ai_overrides)
            _log_mostly_config_params(mostly_config, self.data_file_paths)
        except Exception:
            logger.warning("Failed to log config params to MLflow.", exc_info=True)

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
        mlflow.set_tag("pipeline_id", self.pipeline_id)
        mlflow.set_tag("job_name", self.job_name)

        # Log training config params from the parent model's saved artifacts
        self._log_training_params_and_artifacts()

        logger.info("MLflow simulation run started: %s", self._mlflow_run.info.run_id)

    def _log_training_params_and_artifacts(self) -> None:
        """Log training params (with ``train.`` prefix) and copy artifacts."""
        model_dir = os.path.join(MODELS_DIR, self.model_id)
        mostly_config_path = os.path.join(model_dir, "configs", "mostly_config.json")
        model_card_path = os.path.join(model_dir, MODEL_CARD_FILENAME)

        # -- params --
        try:
            if os.path.exists(mostly_config_path):
                with open(mostly_config_path, encoding="utf-8") as fh:
                    mostly_config = json.load(fh)

                data_file_paths: list[str] = []
                if os.path.exists(model_card_path):
                    with open(model_card_path, encoding="utf-8") as fh:
                        model_card = json.load(fh)
                    data_file_paths = [src["path"] for src in model_card.get("data_sources", [])]

                _log_mostly_config_params(mostly_config, data_file_paths, prefix="train.")
            else:
                logger.warning(
                    "Parent model config not found at '%s'; skipping config params.",
                    mostly_config_path,
                )
        except Exception:
            logger.warning("Failed to log training config params to MLflow.", exc_info=True)

        # -- artifacts --
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

        # Register globally so future get_logger() calls auto-attach it.
        logging_config._pipeline_handler = self._log_handler

        # Attach to every logger that already exists.
        self._attached_loggers = []
        manager = logging.Logger.manager
        for name, logger_ref in manager.loggerDict.items():
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
