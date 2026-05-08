"""Synthesis engine wrapper around the Mostly AI SDK.

Exposes ``MostlyAIEngine``, which loads configuration from
``mostly_ai.yaml`` (optionally deep-merged with per-job overrides),
trains a generator on the preprocessed tables, persists the ``generator.zip``
artifact, and offers sampling helpers used by the simulation flow.
"""

import logging
import os
import socket
import threading

import pandas as pd
import psutil
import yaml
from backend.src.config.general import (
    GENERATOR_ZIP_NAME,
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    LOG_LEVEL,
    MODELS_DIR,
    MOSTLY_LOCAL_PORT,
    SESSION_LOG_FILENAME,
    get_run_timestamp,
    MOSTLYAI_DIR
)
from backend.src.core.cancellation import JobCancelled
from backend.src.core.errors import TableMetadataMissingError
from backend.src.core.logging_config import get_logger
from backend.src.core.utils import deep_merge
from mostlyai.sdk import MostlyAI
from mostlyai.sdk.domain import Generator


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _kill_mostlyai_processes(job_id: str):
    """Force kill any local mostlyai CLI processes related to this job ID, including descendants."""
    logger.info("Force killing local mostlyai processes for job %s", job_id)
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any("mostlyai" in str(cmd) for cmd in cmdline) and str(job_id) in cmdline:
                logger.info("Killing stuck mostlyai process: PID %s", proc.info["pid"])
                # Kill children first to prevent orphans
                for child in proc.children(recursive=True):
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


logger = get_logger(__name__)


class MostlyAIEngine:
    """Data synthesis engine using Mostly AI.

    Orchestrates training, loading, and synthetic data generation through
    the Mostly AI SDK, allowing custom model configuration
    and access to previously trained generators.
    """

    def __init__(
        self,
        config_path: str,
        run_dir: str | None = None,
        local: bool = True,
        config_overrides: dict | None = None,
        local_dir: str | None = None,
    ) -> None:
        """Initializes the engine with configuration and connection to Mostly AI.

        Args:
            config_path (str): Path to a YAML file with generator configuration.
            run_dir (str | None): Directory for session logging. Defaults to None.
            local (bool): If True, uses a local Mostly AI instance. Defaults to True.
            config_overrides (dict | None): Deep-merge overrides applied on top of the
                base YAML config.  Only the keys you specify are changed; everything
                else keeps its default value.
            local_dir (str | None): Where mostlyai saves its results. Defaults to $HOME/mostlyai
        """
        if run_dir:
            self.setup_mostlyai_logging(run_directory=run_dir)
        port = _find_free_port() if local else MOSTLY_LOCAL_PORT
        if not local_dir:
            local_dir = MOSTLYAI_DIR
        self.mostly = MostlyAI(local=local, local_port=port, local_dir=local_dir)
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        if config_overrides:
            self.config = deep_merge(self.config, config_overrides)
        self.config["generator"]["name"] += get_run_timestamp()

    def train(
        self,
        data_dict: dict[str, pd.DataFrame],
        metadata: dict,
        cancel_event: threading.Event | None = None,
    ) -> Generator:
        """Trains a synthetic generator on preprocessed data.

        Configures tables, applies metadata and model configuration, then
        starts training.

        Args:
            data_dict (dict[str, pd.DataFrame]): Preprocessed data
                {table_name: dataframe}.
            metadata (dict): Metadata with table structure, PKs, FKs, and types.
            cancel_event (threading.Event | None): Optional cancellation signal.

        Returns:
            Generator: Trained generator object (MostlyAI Generator).

        Raises:
            ValueError: If a table in data_dict has no corresponding metadata.
            Exception: If training fails in the Mostly AI SDK.

        Example:
            >>> generator = engine.train(processed_data, metadata)
            >>> print(generator.name)  # Name of the trained generator
        """
        tables_config = []
        for table_name, df in data_dict.items():
            # extract metadata using table_name to ensure consistency
            metadata_table = next((t for t in metadata["tables"] if t["name"] == table_name), None)
            if not metadata_table:
                raise TableMetadataMissingError(f"No metadata found for table: {table_name}")

            table_entry = {
                "name": table_name,
                "data": df,
                "tabular_model_configuration": self.config["model_settings"],
                # TODO: [#1] can we select a specific type of model?
                "primary_key": metadata_table.get("primary_key"),
                "foreign_keys": metadata_table.get("foreign_keys", []),
                "columns": metadata_table["columns"],
            }
            tables_config.append(table_entry)

        # create generator
        full_config = {
            "name": self.config["generator"]["name"],
            "description": self.config["generator"]["description"],
            "random_state": self.config["generator"]["random_state"],
            "tables": tables_config,
        }

        # start training
        generator = self.mostly.generators.create(config=full_config)
        generator.training.start()

        if cancel_event is None:
            generator.training.wait()
        else:
            stop_watcher = threading.Event()

            def watcher_thread():
                while not stop_watcher.wait(timeout=1.0):
                    if cancel_event.is_set():
                        logger.info("Cancelling generator %s...", generator.id)
                        generator.training.cancel()
                        _kill_mostlyai_processes(generator.id)
                        break

            t = threading.Thread(target=watcher_thread)
            t.start()

            try:
                generator.training.wait()
            except Exception as e:
                if cancel_event.is_set():
                    pass  # Will be handled below
                else:
                    raise e
            finally:
                stop_watcher.set()
                t.join(timeout=2.0)

            if cancel_event.is_set():
                raise JobCancelled("Training cancelled by user")

        return generator

    def load_generator_by_id(self, model_id: str) -> tuple[Generator, str]:
        """Loads a trained generator by its model ID (non-interactive).

        Args:
            model_id (str): Model identifier (folder name under outputs/models/).

        Returns:
            tuple[Generator, str]: Tuple of (generator object, path to the model run folder).

        Raises:
            FileNotFoundError: If the model folder or generator.zip does not exist.
        """
        model_folder = os.path.join(MODELS_DIR, model_id)
        if not os.path.isdir(model_folder):
            raise FileNotFoundError(f"Model folder not found: {model_folder}")

        generator_zip = os.path.join(model_folder, GENERATOR_ZIP_NAME)
        if not os.path.exists(generator_zip):
            raise FileNotFoundError(f"Generator file not found: {generator_zip}")

        logger.info("Loading generator from %s", generator_zip)
        generator_obj = self.mostly.generators.import_from_file(generator_zip)
        logger.info("Generator '%s' loaded successfully.", generator_obj.name)

        return generator_obj, model_folder

    def simulate(
        self,
        generator: object,
        simulation_configuration: dict,
        cancel_event: threading.Event | None = None,
    ) -> dict[str, pd.DataFrame]:
        """Generates synthetic data using a trained generator.

        Starts a generation job with the specified configuration and returns
        synthetic data in dictionary-of-DataFrames format.

        Args:
            generator (object): Trained generator object (MostlyAI Generator).
            simulation_configuration (dict): Config with {tables: [{name, configuration}, ...]}.
            cancel_event (threading.Event | None): Optional cancellation signal.

        Returns:
            dict[str, pd.DataFrame]: Generated synthetic data
                {table_name: dataframe}.

        Raises:
            Exception: If generation fails or configuration is invalid.

        Example:
            >>> config = {"tables": [{"name": "users", "configuration": {...}}]}
            >>> synthetic_data = engine.simulate(generator, config)
            >>> print(synthetic_data['users'].shape)
        """
        # self.mostly.generate is a blocking wrapper that creates, starts and waits.
        # We need to manually do it to support cancellation
        config = {"generator_id": generator.id, "name": "simulation"}
        config.update(simulation_configuration)

        synthetic_dataset = self.mostly.synthetic_datasets.create(config=config)
        synthetic_dataset.generation.start()

        if cancel_event is None:
            synthetic_dataset.generation.wait()
        else:
            stop_watcher = threading.Event()

            def watcher_thread():
                while not stop_watcher.wait(timeout=1.0):
                    if cancel_event.is_set():
                        logger.info("Cancelling simulation %s...", synthetic_dataset.id)
                        synthetic_dataset.generation.cancel()
                        _kill_mostlyai_processes(synthetic_dataset.id)
                        break

            t = threading.Thread(target=watcher_thread)
            t.start()

            try:
                synthetic_dataset.generation.wait()
            except Exception as e:
                if cancel_event.is_set():
                    pass
                else:
                    raise e
            finally:
                stop_watcher.set()
                t.join(timeout=2.0)

            if cancel_event.is_set():
                raise JobCancelled("Simulation cancelled by user")

        # reload to get data
        synthetic_dataset = self.mostly.synthetic_datasets.get(synthetic_dataset.id)

        synthetic_data_dict = synthetic_dataset.data()
        sd_config = synthetic_dataset.config()

        if isinstance(synthetic_data_dict, pd.DataFrame):
            synthetic_data_dict = {sd_config.tables[0].name: synthetic_data_dict}

        return synthetic_data_dict

    def setup_mostlyai_logging(self, run_directory: str) -> None:
        """Configure MostlyAI SDK logger to output to session.log.

        Args:
            run_directory (str): Directory where session.log will be created.

        Returns:
            None
        """
        mostlyai_logger = logging.getLogger("mostlyai")
        mostlyai_logger.handlers.clear()
        session_log_path = os.path.join(run_directory, SESSION_LOG_FILENAME)

        file_handler = logging.FileHandler(session_log_path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        mostlyai_logger.addHandler(file_handler)
        mostlyai_logger.setLevel(LOG_LEVEL)
