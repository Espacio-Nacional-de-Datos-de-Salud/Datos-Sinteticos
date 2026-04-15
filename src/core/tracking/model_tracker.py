"""Model-training tracker.

``ModelTracker`` is the context manager that wraps a training run: it creates
the timestamped output folder, archives the effective configuration, starts
an MLflow run, manages a temporary directory for Mostly AI, and offers the
``save_*`` methods that the training flow calls as training progresses.
"""

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
    METADATA_FILENAME,
    MLFLOW_EXPERIMENT_TRAINING,
    MLFLOW_TRACKING_URI,
    MODEL_CARD_FILENAME,
    MODEL_RUN_FOLDER_PREFIX,
    MODELS_DIR,
    MOSTLYAI_CONFIG_PATH,
    MOSTLYAI_DIR,
    NO_PIPELINE_ID,
    RULES_CONFIG_PATH,
    SESSION_LOG_FILENAME,
    SIMULATIONS_DIR,
    USERPROFILENAME,
)

from src.core.logging_config import get_logger
from src.core.preprocessing.logical_rules import LogicalRuleManager
from src.core.tracking._mostly_config import load_mostly_config, log_mostly_config_params
from src.core.tracking._session_logger import attach_session_file_handler
from src.core.tracking.helpers import compute_file_sha256

logger = get_logger(__name__)


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

        self._run_logger = attach_session_file_handler(self.output_directory, __name__)
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
        forwards them to MLflow.

        Args:
            generator: MostlyAI Generator object with ``export_to_file`` method.
        """
        generator_path = os.path.join(self.output_directory, GENERATOR_ZIP_NAME)
        generator.export_to_file(generator_path)
        logger.info("Generator saved to '%s'.", generator_path)
        mlflow.log_artifact(generator_path)

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
        """Pull statistics from ``generator.json`` and log them to MLflow and the model card.

        Args:
            generator_id (str): The generator ID (directory name under
                outputs/mostlyai/generators/).
        """
        generator_data = self._read_generator_json(generator_id)
        if generator_data is None:
            return

        mostly_statistics: dict = {}

        generator_accuracy = generator_data.get("accuracy")
        if generator_accuracy is not None:
            mlflow.log_metric("mostly.generator_accuracy", generator_accuracy)
            mostly_statistics["generator_accuracy"] = generator_accuracy

        mostly_statistics["tables"] = self._collect_and_log_table_statistics(
            generator_data.get("tables", [])
        )
        self._update_model_card_with_statistics(mostly_statistics)

    # ------------------------------------------------------------------
    # Internal helpers — statistics extraction
    # ------------------------------------------------------------------
    @staticmethod
    def _read_generator_json(generator_id: str) -> dict | None:
        """Load ``generator.json`` for a given generator, or return ``None`` if missing."""
        generator_json_path = os.path.join(
            MOSTLYAI_DIR, "generators", generator_id, "generator.json"
        )
        if not os.path.exists(generator_json_path):
            logger.warning("Generator JSON file not found: %s", generator_json_path)
            return None
        with open(generator_json_path, encoding="utf-8") as f:
            return json.load(f)

    def _collect_and_log_table_statistics(self, tables: list[dict]) -> dict[str, dict]:
        """Walk every table entry and log its tabular model metrics.

        Args:
            tables (list[dict]): ``tables`` array from ``generator.json``.

        Returns:
            dict[str, dict]: Mapping of table name to the logged statistics.
        """
        tables_stats: dict[str, dict] = {}
        for table_idx, table in enumerate(tables):
            table_name = table.get("name", f"table_{table_idx}")
            tabular_metrics = table.get("tabularModelMetrics")
            if not tabular_metrics:
                logger.debug("No tabular model metrics found for table '%s'", table_name)
                continue
            tables_stats[table_name] = self._log_table_statistics(table_name, tabular_metrics)
            logger.info("Logged tabular metrics for table '%s' to MLflow.", table_name)
        return tables_stats

    def _log_table_statistics(self, table_name: str, tabular_metrics: dict) -> dict:
        """Log all three metric sections (accuracy, distances, similarity) for one table.

        Args:
            table_name (str): Table name used in the MLflow metric keys.
            tabular_metrics (dict): ``tabularModelMetrics`` block for the table.

        Returns:
            dict: Per-section metrics that were logged (non-``None`` values only).
        """
        return {
            section: self._log_metric_section(table_name, section, tabular_metrics.get(section, {}))
            for section in ("accuracy", "distances", "similarity")
            if tabular_metrics.get(section)
        }

    @staticmethod
    def _log_metric_section(table_name: str, section: str, section_metrics: dict) -> dict:
        """Log non-null metrics from one named section to MLflow and return what was logged.

        Args:
            table_name (str): Parent table name.
            section (str): Section label — ``accuracy``, ``distances``, or ``similarity``.
            section_metrics (dict): Raw metric mapping from ``generator.json``.

        Returns:
            dict: The subset of ``section_metrics`` with non-null values.
        """
        logged: dict = {}
        for metric_name, metric_value in section_metrics.items():
            if metric_value is None:
                continue
            mlflow.log_metric(f"mostly.{table_name}.{section}.{metric_name}", metric_value)
            logged[metric_name] = metric_value
        return logged

    # ------------------------------------------------------------------
    # Internal helpers — train metrics
    # ------------------------------------------------------------------
    def _save_train_metrics(self, progress_path: str) -> None:
        """Extract per-epoch metrics from ``job_progress.json`` and upload to MLflow.

        Args:
            progress_path (str): Path to ``job_progress.json`` emitted by MostlyAI.
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
                    epoch = int(msg["epoch"])
                    if msg.get("trn_loss"):
                        mlflow.log_metric(f"{modelLabel} Train Loss", msg["trn_loss"], epoch)
                    if msg.get("val_loss"):
                        mlflow.log_metric(f"{modelLabel} Val Loss", msg["val_loss"], epoch)

                # log number of epochs and total time from last message
                lastMsg = step["messages"][-1]
                mlflow.log_metric(f"{modelLabel} Total Epochs", lastMsg["epoch"])
                mlflow.log_metric(f"{modelLabel} Total Time s", lastMsg["total_time"])

    # ------------------------------------------------------------------
    # Internal helpers — model card & configs
    # ------------------------------------------------------------------
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
                {"path": path, "sha256": sha256_hash}
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
        """Archive every configuration input into the run's ``configs/`` subfolder."""
        self._archive_mostly_config()
        self._archive_general_config_snapshot()
        self._archive_rules_config()
        logger.info("Configs archived to '%s'.", self.configs_directory)

    def _archive_mostly_config(self) -> None:
        """Dump the effective (override-merged) Mostly AI config as JSON."""
        mostly_config = load_mostly_config(self.mostly_config_path, self.mostly_ai_overrides)
        out_path = os.path.join(self.configs_directory, "mostly_config.json")
        with open(out_path, "w", encoding="utf-8") as file_handle:
            json.dump(mostly_config, file_handle, indent=4)

    def _archive_general_config_snapshot(self) -> None:
        """Persist a small snapshot of ``general_config`` constants for provenance."""
        from config.general_config import (
            DEFAULT_SAMPLE_SIZE,
            ENABLE_DATA_PROFILING,
            LOG_LEVEL,
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

    def _archive_rules_config(self) -> None:
        """Copy the rules YAML (converted to JSON) next to the other configs."""
        if not os.path.exists(self.rules_config_path):
            return
        with open(self.rules_config_path, encoding="utf-8") as file_handle:
            rules_config = yaml.safe_load(file_handle)
        out_path = os.path.join(self.configs_directory, "rules_config.json")
        with open(out_path, "w", encoding="utf-8") as file_handle:
            json.dump(rules_config, file_handle, indent=4)

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

        try:
            mostly_config = load_mostly_config(self.mostly_config_path, self.mostly_ai_overrides)
            log_mostly_config_params(mostly_config, self.data_file_paths)
        except Exception:
            logger.warning("Failed to log config params to MLflow.", exc_info=True)

        mlflow.log_artifacts(self.configs_directory, artifact_path="configs")
        logger.info("MLflow run started: %s", self._mlflow_run.info.run_id)
