"""Synthesis engine wrapper around the Mostly AI SDK.

Exposes ``MostlyAIEngine``, which loads configuration from
``mostly_ai.yaml`` (optionally deep-merged with per-job overrides),
trains a generator on the preprocessed tables, persists the ``generator.zip``
artifact, and offers sampling helpers used by the simulation flow.
"""

import logging
import os
import shutil
import socket
import threading

import pandas as pd
import psutil
import yaml
from mostlyai.sdk import MostlyAI
from mostlyai.sdk.domain import Generator, ProgressStatus

from backend.src.config.general import (
    GENERATOR_ZIP_NAME,
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    LOG_LEVEL,
    MODELS_DIR,
    MOSTLY_LOCAL_PORT,
    MOSTLYAI_DIR,
    SESSION_LOG_FILENAME,
    get_run_timestamp,
)
from backend.src.infrastructure.cancellation import JobCancelled
from backend.src.infrastructure.errors import TableMetadataMissingError, TrainingJobFailedError
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.utils import deep_merge


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
            if any("mostlyai" in str(cmd) for cmd in cmdline) and any(
                str(job_id) in str(cmd) for cmd in cmdline
            ):
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


def _shutdown_local_server(mostly) -> None:
    """Force the embedded MostlyAI uvicorn server to exit, off the hot path.

    The SDK runs its local server as a uvicorn instance in a daemon thread
    *inside this very process* (see ``mostlyai.sdk._local.server.LocalServer``).
    It must therefore never be killed by port — that socket is owned by our own
    PID. Worse, ``LocalServer.__del__`` calls ``stop()`` which does an unbounded
    ``thread.join()``; when a polling ``wait()`` keeps the server busy, that join
    blocks the FastAPI event loop indefinitely during garbage collection.

    Setting ``force_exit`` makes uvicorn skip graceful shutdown and return
    immediately, so: (1) the daemon ``wait`` thread's next poll fails fast and
    the thread dies, and (2) ``_server.started`` flips to False, turning the
    later ``__del__``/``stop()`` into a harmless no-op.
    """
    local_server = None
    try:
        for value in list(vars(mostly).values()):
            if hasattr(value, "_server") and hasattr(value, "_thread") and hasattr(value, "stop"):
                local_server = value
                break
    except TypeError:
        local_server = None
    if local_server is None:
        logger.warning("Could not locate embedded MostlyAI local server to shut down.")
        return
    logger.info("Forcing embedded MostlyAI local server to exit.")
    uvicorn_server = getattr(local_server, "_server", None)
    if uvicorn_server is not None:
        uvicorn_server.should_exit = True
        uvicorn_server.force_exit = True
    # LocalServer.stop() joins the uvicorn thread with no timeout; run it in a
    # daemon so the caller (and the event loop) is never blocked by that join.
    threading.Thread(target=local_server.stop, daemon=True).start()


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
        self._local_port = port
        self.local_dir = local_dir
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
            self._wait_with_cancellation(
                wait_fn=generator.training.wait,
                cancel_fn=generator.training.cancel,
                job_id=generator.id,
                label="training",
                cancel_event=cancel_event,
            )
            if cancel_event.is_set():
                raise JobCancelled("Training cancelled by user")

        self._raise_if_training_failed(generator)

        return generator

    @staticmethod
    def _raise_if_training_failed(generator: Generator) -> None:
        """Raise a clear error if the training job did not finish successfully.

        Inspects the job progress and includes the failing step's table/model
        label and engine error message so the failure is actionable instead of
        surfacing as a downstream export error.
        """
        if generator.training_status == ProgressStatus.done:
            return

        details = ""
        try:
            steps = generator.training.progress().steps or []
            failed = [s for s in steps if s.status == ProgressStatus.failed]
            if failed:
                details = "; ".join(
                    f"{s.model_label or s.step_code} — {s.error_message or 'no error message'}"
                    for s in failed
                )
        except Exception as progress_error:  # pragma: no cover - best-effort detail
            logger.warning("Could not read training job progress: %s", progress_error)

        message = f"Mostly AI training job ended with status '{generator.training_status.value}'."
        if details:
            message += f" Failing step(s): {details}"
        logger.error(message)
        raise TrainingJobFailedError(message)

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
        progress_copy_dest: str | None = None,
        progress_copy_interval: float = 120.0,
    ) -> tuple[dict[str, pd.DataFrame], str]:
        """Generates synthetic data using a trained generator.

        Starts a generation job with the specified configuration and returns
        synthetic data in dictionary-of-DataFrames format along with the
        MostlyAI synthetic dataset ID (needed to locate job_progress.json).

        Args:
            generator (object): Trained generator object (MostlyAI Generator).
            simulation_configuration (dict): Config with {tables: [{name, configuration}, ...]}.
            cancel_event (threading.Event | None): Optional cancellation signal.
            progress_copy_dest (str | None): If set, copy job_progress.json from the MostlyAI
                synthetic-dataset folder to this path every ``progress_copy_interval`` seconds
                while generation is running, plus once more after it completes.
            progress_copy_interval (float): Seconds between periodic progress copies (default 120).

        Returns:
            tuple[dict[str, pd.DataFrame], str]: Generated synthetic data
                {table_name: dataframe} and the MostlyAI synthetic_dataset ID.

        Raises:
            Exception: If generation fails or configuration is invalid.

        Example:
            >>> config = {"tables": [{"name": "users", "configuration": {...}}]}
            >>> synthetic_data, sd_id = engine.simulate(generator, config)
            >>> print(synthetic_data['users'].shape)
        """
        # self.mostly.generate is a blocking wrapper that creates, starts and waits.
        # We need to manually do it to support cancellation
        config = {"generator_id": generator.id, "name": "simulation"}
        config.update(simulation_configuration)

        synthetic_dataset = self.mostly.synthetic_datasets.create(config=config)
        synthetic_dataset_id = synthetic_dataset.id

        src_job_progress = os.path.join(
            self.local_dir, "synthetic-datasets", str(synthetic_dataset_id), "job_progress.json"
        )

        synthetic_dataset.generation.start()

        # Background thread that copies job_progress.json periodically so callers can
        # monitor generation progress without waiting for the job to finish.
        stop_copier = threading.Event()

        def _progress_copier():
            while not stop_copier.wait(timeout=progress_copy_interval):
                if os.path.exists(src_job_progress):
                    shutil.copy2(src_job_progress, progress_copy_dest)
                    logger.debug("Copied job_progress.json to '%s'.", progress_copy_dest)

        copier_thread: threading.Thread | None = None
        if progress_copy_dest:
            copier_thread = threading.Thread(target=_progress_copier, daemon=True)
            copier_thread.start()

        try:
            if cancel_event is None:
                synthetic_dataset.generation.wait()
            else:
                self._wait_with_cancellation(
                    wait_fn=synthetic_dataset.generation.wait,
                    cancel_fn=synthetic_dataset.generation.cancel,
                    job_id=synthetic_dataset.id,
                    label="simulation",
                    cancel_event=cancel_event,
                )
                if cancel_event.is_set():
                    raise JobCancelled("Simulation cancelled by user")
        finally:
            stop_copier.set()
            if copier_thread is not None:
                copier_thread.join(timeout=2.0)
                # Final authoritative copy once generation has settled
                if os.path.exists(src_job_progress):
                    shutil.copy2(src_job_progress, progress_copy_dest)
                    logger.info("Final job_progress.json copied to '%s'.", progress_copy_dest)

        # reload to get data
        synthetic_dataset = self.mostly.synthetic_datasets.get(synthetic_dataset_id)

        synthetic_data_dict = synthetic_dataset.data()
        sd_config = synthetic_dataset.config()

        if isinstance(synthetic_data_dict, pd.DataFrame):
            synthetic_data_dict = {sd_config.tables[0].name: synthetic_data_dict}

        return synthetic_data_dict, synthetic_dataset_id

    def _wait_with_cancellation(
        self,
        wait_fn,
        cancel_fn,
        job_id: str,
        label: str,
        cancel_event: threading.Event,
    ) -> None:
        """Wait for a MostlyAI job while remaining responsive to cancellation.

        Runs ``wait_fn`` in a daemon thread so the main thread can check
        ``cancel_event`` every two seconds instead of being blocked inside the
        SDK.  When cancellation is requested: calls ``cancel_fn`` with a 10-second
        grace period, force-kills the generation/training subprocess, then
        force-exits the embedded local server so nothing blocks afterwards.
        """
        wait_done = threading.Event()
        wait_exc: list[BaseException | None] = [None]

        def _do_wait() -> None:
            try:
                wait_fn()
            except Exception as exc:
                wait_exc[0] = exc
            finally:
                wait_done.set()

        wait_thread = threading.Thread(target=_do_wait, daemon=True)
        wait_thread.start()

        cancelled = False
        while not wait_done.wait(timeout=2.0):
            if cancel_event.is_set():
                cancelled = True
                logger.info("Cancelling %s %s...", label, job_id)
                cancel_t = threading.Thread(target=cancel_fn, daemon=True)
                cancel_t.start()
                cancel_t.join(timeout=10.0)
                if cancel_t.is_alive():
                    logger.warning(
                        "%s.cancel() timed out after 10 s; proceeding to force kill.", label
                    )
                _kill_mostlyai_processes(str(job_id))
                _shutdown_local_server(self.mostly)
                break

        if not cancelled and wait_exc[0] is not None:
            raise wait_exc[0]

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
