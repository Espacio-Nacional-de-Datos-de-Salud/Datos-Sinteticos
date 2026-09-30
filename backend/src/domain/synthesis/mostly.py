"""Synthesis engine wrapper around the Mostly AI SDK.

Exposes ``MostlyAIEngine``, the Mostly AI implementation of the
:class:`~backend.src.domain.synthesis.base.SynthesisEngine` contract. It loads
configuration from ``mostly_ai.yaml`` (optionally deep-merged with per-job
overrides), trains a generator on the preprocessed tables, persists the
``generator.zip`` artifact, and offers sampling helpers used by the simulation
flow.

Construct engines through ``create_engine`` (see ``factory.py``) rather than
referencing this class directly, so call sites stay engine-agnostic.
"""

import logging
import os
import shutil
import socket
import threading
from typing import Any

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
    MOSTLY_LOCAL_TIMEOUT_SECONDS,
    MOSTLYAI_DIR,
    SESSION_LOG_FILENAME,
    get_run_timestamp,
)
from backend.src.domain.modeling_configuration import (
    backend_model_settings,
    build_modeling_configuration,
)
from backend.src.domain.synthesis.training_diagnostics import (
    run_preflight_checks,
    summarize_training_failure,
)
from backend.src.infrastructure.cancellation import JobCancelled
from backend.src.infrastructure.errors import TableMetadataMissingError, TrainingJobFailedError
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.utils import deep_merge


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
                for child in proc.children(recursive=True):
                    try:
                        child.kill()
                    except psutil.NoSuchProcess:
                        pass
                proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass


def _table_model_settings(
    base_settings: dict[str, Any],
    model_settings: dict[str, Any],
    table_name: str,
) -> dict[str, Any]:
    """Model settings for one table: the global config plus per-table overrides.

    ``model_settings.per_table.<table>`` deep-merges onto the global settings;
    an explicit ``null`` value removes the key for that table (e.g. disabling
    ``differential_privacy`` on a deep child while keeping it elsewhere).
    """
    per_table = model_settings.get("per_table") or {}
    overrides = per_table.get(table_name)
    if not isinstance(overrides, dict):
        return base_settings
    merged = deep_merge(base_settings, backend_model_settings(overrides))
    return {key: value for key, value in merged.items() if value is not None}


def _positive_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _cap_training_tables(
    data_dict: dict[str, pd.DataFrame],
    metadata: dict,
    max_sample_size: int | None,
    random_state: int | None,
) -> dict[str, pd.DataFrame]:
    """Limit oversized tables before handing them to the local SDK server."""
    if not max_sample_size:
        return data_dict

    metadata_by_name = {
        table.get("name"): table for table in metadata.get("tables", []) if table.get("name")
    }
    capped: dict[str, pd.DataFrame] = {}

    for table_name, df in data_dict.items():
        table_meta = metadata_by_name.get(table_name, {})
        scoped_df = df
        for foreign_key in table_meta.get("foreign_keys", []) or []:
            parent_name = foreign_key.get("referenced_table")
            parent = metadata_by_name.get(parent_name or "", {})
            parent_key = parent.get("primary_key")
            child_key = foreign_key.get("column")
            if (
                parent_name in capped
                and parent_key in capped[parent_name].columns
                and child_key in scoped_df.columns
            ):
                scoped_df = scoped_df[scoped_df[child_key].isin(capped[parent_name][parent_key])]

        if len(scoped_df) > max_sample_size:
            scoped_df = scoped_df.sample(n=max_sample_size, random_state=random_state)

        if len(scoped_df) != len(df):
            logger.info(
                "Limited training table '%s' from %s to %s rows before MostlyAI create().",
                table_name,
                len(df),
                len(scoped_df),
            )
        capped[table_name] = scoped_df

    return capped


def _normalize_object_columns_for_mostly_transport(
    table_name: str,
    df: pd.DataFrame,
) -> pd.DataFrame:
    """Make object columns safe for the SDK's pandas -> parquet conversion.

    Large CSV inputs can leave sparse categorical columns as ``object`` with
    strings and ``NaN`` floats. PyArrow may then infer a binary column and fail
    with "Expected bytes, got a 'float' object" while Mostly's SDK serializes
    the in-memory DataFrame. Pandas' nullable string dtype keeps the same
    logical values, preserves nulls, and writes cleanly to parquet.
    """
    object_columns = [
        column for column in df.columns if pd.api.types.is_object_dtype(df[column])
    ]
    if not object_columns:
        return df

    normalized = df.copy(deep=False)
    for column in object_columns:
        normalized[column] = normalized[column].astype("string")

    logger.info(
        "Normalized %d object columns in table '%s' to pandas string dtype before MostlyAI upload.",
        len(object_columns),
        table_name,
    )
    return normalized


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
        self.mostly = MostlyAI(
            local=local,
            local_port=port,
            local_dir=local_dir,
            timeout=MOSTLY_LOCAL_TIMEOUT_SECONDS,
        )
        self._local_port = port
        self.local_dir = local_dir
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
        if config_overrides:
            self.config = deep_merge(self.config, config_overrides)
        self.config["generator"]["name"] += get_run_timestamp()
        self.last_modeling_configuration: dict[str, Any] | None = None

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
        model_settings = self.config.get("model_settings") or {}
        self.last_modeling_configuration = build_modeling_configuration(model_settings, metadata)
        max_sample_size = _positive_int(model_settings.get("max_sample_size"))
        mostly_model_settings = backend_model_settings(model_settings)
        if max_sample_size:
            mostly_model_settings.pop("max_sample_size", None)
        data_for_training = _cap_training_tables(
            data_dict=data_dict,
            metadata=metadata,
            max_sample_size=max_sample_size,
            random_state=self.config.get("generator", {}).get("random_state"),
        )
        data_for_training = {
            table_name: _normalize_object_columns_for_mostly_transport(table_name, df)
            for table_name, df in data_for_training.items()
        }

        unknown_override_tables = set(model_settings.get("per_table") or {}) - set(
            data_for_training
        )
        if unknown_override_tables:
            logger.warning(
                "model_settings.per_table references tables not in this job "
                "(ignored): %s",
                ", ".join(sorted(unknown_override_tables)),
            )

        run_preflight_checks(data_for_training, metadata, model_settings)

        tables_config = []
        for table_name, df in data_for_training.items():
            # extract metadata using table_name to ensure consistency
            metadata_table = next((t for t in metadata["tables"] if t["name"] == table_name), None)
            if not metadata_table:
                raise TableMetadataMissingError(f"No metadata found for table: {table_name}")

            table_entry = {
                "name": table_name,
                "data": df,
                "tabular_model_configuration": _table_model_settings(
                    mostly_model_settings, model_settings, table_name
                ),
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
        """Raise a concise, actionable error if training did not succeed.

        Delegates to :func:`summarize_training_failure`, which collapses the
        per-step failure cascade into one entry per affected table and appends
        guidance when the engine error matches a known issue — instead of
        surfacing dozens of repeated "no error message" lines.
        """
        if generator.training_status == ProgressStatus.done:
            return

        message = summarize_training_failure(generator)
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
