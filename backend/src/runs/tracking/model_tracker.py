"""Model-training tracker.

``ModelTracker`` is the context manager that wraps a training run: it creates
the timestamped output folder, archives the effective configuration, writes
the model card, manages a temporary directory for Mostly AI, and offers the
``save_*`` methods that the training flow calls as training progresses.
"""

import json
import logging
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

import pandas as pd
import yaml

import backend.src.config.general as general_config
from backend.src.config.general import (
    GENERATOR_ZIP_NAME,
    METADATA_FILENAME,
    MODEL_CARD_FILENAME,
    MODEL_RUN_FOLDER_PREFIX,
    MODELS_DIR,
    MOSTLYAI_DIR,
    NO_PIPELINE_ID,
    SIMULATIONS_DIR,
    USERPROFILENAME,
)
from backend.src.domain.preprocessing.logical_rules import LogicalRuleManager
from backend.src.domain.preprocessing.logical_rules_serialization import (
    serialize_logical_rule_manager_to_dict,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.runs.tracking.base_tracker import BaseRunTracker
from backend.src.runs.tracking.helpers import compute_file_sha256

logger = get_logger(__name__)


def _load_mostly_config(mostly_config_path: str, overrides: dict | None) -> dict:
    """Load the Mostly AI YAML and deep-merge any per-job overrides."""
    if not os.path.exists(mostly_config_path):
        return {}
    with open(mostly_config_path, encoding="utf-8") as fh:
        base = yaml.safe_load(fh) or {}
    if not overrides:
        return base

    def _merge(dst: dict, src: dict) -> dict:
        for key, value in src.items():
            if isinstance(value, dict) and isinstance(dst.get(key), dict):
                _merge(dst[key], value)
            else:
                dst[key] = value
        return dst

    return _merge(base, overrides)


class ModelTracker(BaseRunTracker):
    """Manages lineage, directory structure, and on-disk artifacts for a training run.

    Use as a context manager to automatically create the output directory tree,
    compute dataset hashes, provision a temporary directory for MostlyAI, and
    clean everything up on exit.

    Args:
        data_file_paths (list[str]): Paths to the original data files in ``data/``.
        mostly_config_path (str): Path to the MostlyAI YAML configuration.
        rules_config_path (str): Path to the rules YAML configuration.
        mostly_ai_overrides (dict | None): Per-job overrides to deep-merge
            into the base Mostly AI config before archiving.

    Example:
        >>> with ModelTracker(data_files, mostly_cfg, rules_cfg) as tracker:
        ...     engine = MostlyAIEngine(config_path=mostly_cfg)
        ...     generator = engine.train(data, metadata, tracker.output_directory)
        ...     tracker.save_generator(generator)
    """

    card_filename = MODEL_CARD_FILENAME
    run_kind = "model"

    def __init__(
        self,
        data_file_paths: list[str],
        mostly_config_path: str | None = None,
        rules_config_path: str | None = None,
        pipeline_id: str = NO_PIPELINE_ID,
        mostly_ai_overrides: dict | None = None,
        job_name: str = "",
        model_id: str | None = None,
    ) -> None:
        from backend.src.sessions.configs import resolve_config_path

        super().__init__()
        self.data_file_paths = data_file_paths
        self.mostly_config_path = mostly_config_path or str(resolve_config_path("mostly_ai"))
        self.rules_config_path = rules_config_path or str(resolve_config_path("rules"))
        self.pipeline_id = pipeline_id
        self.mostly_ai_overrides = mostly_ai_overrides
        self.job_name = job_name

        self.model_id: str = (
            model_id or f"{MODEL_RUN_FOLDER_PREFIX}_{general_config.get_run_timestamp()}"
        )
        self.run_id = self.model_id
        self.output_directory: str = os.path.join(MODELS_DIR, self.model_id)
        self.configs_directory: str = os.path.join(self.output_directory, "configs")

        self._tempdir: tempfile.TemporaryDirectory | None = None

    # ------------------------------------------------------------------
    # Lifecycle hooks
    # ------------------------------------------------------------------
    def _on_enter(self) -> None:
        os.makedirs(self.configs_directory, exist_ok=True)
        self._save_configs()
        self._save_model_card()
        self._tempdir = tempfile.TemporaryDirectory(prefix="mostlyai_")
        logger.info("MostlyAI temp directory: %s", self._tempdir.name)

    def _on_exit(self, exc_type, exc_val, exc_tb) -> None:
        if self._tempdir is not None:
            self._tempdir.cleanup()
            logger.info("Cleaned up MostlyAI temp directory.")

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def save_metadata(self, metadata: dict) -> None:
        """Save metadata JSON to the model output directory.

        Args:
            metadata (dict): Table metadata dictionary.
        """
        metadata_path = os.path.join(self.output_directory, METADATA_FILENAME)
        with open(metadata_path, "w", encoding="utf-8") as file_handle:
            json.dump(metadata, file_handle, indent=4)
        logger.info("Metadata saved to '%s'.", metadata_path)

    def save_rule_manager(self, rule_manager: LogicalRuleManager) -> None:
        """Save the rule manager as a JSON file.

        Args:
            rule_manager (LogicalRuleManager): The rule manager to persist.
        """
        rule_manager_path = os.path.join(self.output_directory, "rule_manager.json")
        with open(rule_manager_path, "w", encoding="utf-8") as file_handle:
            json.dump(
                serialize_logical_rule_manager_to_dict(rule_manager),
                file_handle,
                indent=2,
            )
        logger.info("Rule manager saved to '%s'.", rule_manager_path)

    def save_generator(self, generator: object) -> None:
        """Export the trained generator to a ZIP file and extract its progress JSON.

        Args:
            generator: MostlyAI Generator object with ``export_to_file`` method.
        """
        generator_path = os.path.join(self.output_directory, GENERATOR_ZIP_NAME)
        generator.export_to_file(generator_path)
        logger.info("Generator saved to '%s'.", generator_path)

        job_progress_path = os.path.join(self.output_directory, "job_progress.json")
        with zipfile.ZipFile(generator_path, "r") as zip_file:
            zip_file.extract("job_progress.json", self.output_directory)
        logger.info("Job progress extracted to '%s'.", job_progress_path)

    def save_data_profiles(self, data_profiles: dict[str, object]) -> None:
        """Save data profiling HTML reports.

        Args:
            data_profiles (dict[str, object]): Mapping of table name to profile
                object with a ``to_file`` method.
        """
        for name, profile in data_profiles.items():
            output_file = os.path.join(self.output_directory, f"{name}_profiling_report.html")
            profile.to_file(output_file)
            logger.info("Data profile for '%s' saved.", name)

    def save_training_table_sizes(self, processed_data: dict[str, pd.DataFrame]) -> None:
        """Persist training row counts per table to ``model_card.json``."""
        table_sizes: dict[str, int] = {}
        for table_name, table_df in processed_data.items():
            if hasattr(table_df, "__len__"):
                table_sizes[table_name] = int(len(table_df))

        if not table_sizes:
            logger.warning("No training table sizes were detected to persist in model card.")
            return

        self.patch_card(training_table_sizes=table_sizes)
        logger.info("Model card updated with training table sizes: %s", table_sizes)

    def save_qa_reports(self, generator_id: str) -> None:
        """Copy MostlyAI QA report HTML files to the model output directory.

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

    def save_mostly_statistics(self, generator_id: str) -> None:
        """Pull statistics from ``generator.json`` and persist them on the model card.

        Also detects whether each table was modeled as a FlatModel or SequentialModel
        by reading Mostly AI's internal stats.json, and persists that in both
        the model card and the model's metadata.json.

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
            mostly_statistics["generator_accuracy"] = generator_accuracy

        mostly_statistics["tables"] = self._collect_table_statistics(
            generator_data.get("tables", [])
        )

        # Detect the model type (FlatModel vs SequentialModel) for each table
        tables_model_types: dict[str, str] = {}
        for table in generator_data.get("tables", []):
            table_name = table.get("name")
            if not table_name:
                continue

            # Tabular or Language statistics path
            stats_json_path = os.path.join(
                MOSTLYAI_DIR,
                "generators",
                generator_id,
                "ModelStore",
                f"{table_name}:tabular",
                "tgt-stats",
                "stats.json",
            )
            if not os.path.exists(stats_json_path):
                stats_json_path = os.path.join(
                    MOSTLYAI_DIR,
                    "generators",
                    generator_id,
                    "ModelStore",
                    f"{table_name}:language",
                    "tgt-stats",
                    "stats.json",
                )

            if os.path.exists(stats_json_path):
                try:
                    with open(stats_json_path, encoding="utf-8") as f:
                        stats_data = json.load(f)
                    is_seq = stats_data.get("is_sequential", False)
                    tables_model_types[table_name] = "SequentialModel" if is_seq else "FlatModel"
                except Exception as e:
                    logger.warning("Could not read stats.json for table %s: %s", table_name, e)

        # Inject into mostly_statistics tables map
        for table_name, model_type in tables_model_types.items():
            if table_name not in mostly_statistics["tables"]:
                mostly_statistics["tables"][table_name] = {}
            mostly_statistics["tables"][table_name]["detected_model_type"] = model_type

        self.patch_card(mostly_statistics=mostly_statistics)
        logger.info("Model card updated with mostly statistics.")

        # Update metadata.json with the detected types
        metadata_path = os.path.join(self.output_directory, METADATA_FILENAME)
        if os.path.exists(metadata_path) and tables_model_types:
            try:
                with open(metadata_path, encoding="utf-8") as file_handle:
                    metadata = json.load(file_handle)

                if "tables" in metadata and isinstance(metadata["tables"], list):
                    for table_meta in metadata["tables"]:
                        t_name = table_meta.get("name")
                        if t_name in tables_model_types:
                            table_meta["detected_model_type"] = tables_model_types[t_name]

                with open(metadata_path, "w", encoding="utf-8") as file_handle:
                    json.dump(metadata, file_handle, indent=4)
                logger.info("Updated metadata.json with detected model types.")
            except Exception as e:
                logger.warning("Could not update metadata.json with model types: %s", e)

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

    def _collect_table_statistics(self, tables: list[dict]) -> dict[str, dict]:
        """Walk every table entry and collect its tabular model metrics."""
        tables_stats: dict[str, dict] = {}
        for table_idx, table in enumerate(tables):
            table_name = table.get("name", f"table_{table_idx}")
            tabular_metrics = table.get("tabularModelMetrics")
            if not tabular_metrics:
                logger.debug("No tabular model metrics found for table '%s'", table_name)
                continue
            tables_stats[table_name] = {
                section: {
                    metric_name: metric_value
                    for metric_name, metric_value in tabular_metrics.get(section, {}).items()
                    if metric_value is not None
                }
                for section in ("accuracy", "distances", "similarity")
                if tabular_metrics.get(section)
            }
        return tables_stats

    # ------------------------------------------------------------------
    # Internal helpers — model card & configs
    # ------------------------------------------------------------------
    def _compute_dataset_hashes(self) -> dict[str, str]:
        """Compute SHA-256 hashes for all original data files."""
        hashes: dict[str, str] = {}
        for file_path in self.data_file_paths:
            resolved = str(Path(file_path).resolve())
            hashes[resolved] = compute_file_sha256(file_path)
            logger.info("SHA-256 for '%s': %s", resolved, hashes[resolved])
        return hashes

    def _save_model_card(self) -> None:
        """Generate and write ``model_card.json`` with status ``in_progress``."""
        dataset_hashes = self._compute_dataset_hashes()
        self.write_initial_card(
            {
                "model_id": self.model_id,
                "USERPROFILENAME": USERPROFILENAME,
                "timestamp": general_config.get_run_timestamp(),
                "timestamp_ms": int(pd.Timestamp.utcnow().timestamp() * 1000),
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
        )

    def _save_configs(self) -> None:
        """Archive every configuration input into the run's ``configs/`` subfolder."""
        self._archive_mostly_config()
        self._archive_general_config_snapshot()
        self._archive_rules_config()
        logger.info("Configs archived to '%s'.", self.configs_directory)

    def _archive_mostly_config(self) -> None:
        """Dump the effective (override-merged) Mostly AI config as JSON."""
        mostly_config = _load_mostly_config(self.mostly_config_path, self.mostly_ai_overrides)
        out_path = os.path.join(self.configs_directory, "mostly_config.json")
        with open(out_path, "w", encoding="utf-8") as file_handle:
            json.dump(mostly_config, file_handle, indent=4)

    def _archive_general_config_snapshot(self) -> None:
        """Persist a small snapshot of ``general_config`` constants for provenance."""
        from backend.src.config.general import (
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
