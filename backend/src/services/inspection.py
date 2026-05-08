"""Inspection flow service.

Runs load + preprocessing + autodetection and persists the results to a
session directory so the user can review (and optionally edit) the
autodetected metadata before launching training. Mirrors the shape of
``run_training_flow`` but stops right before ``engine.train``.

Session layout under ``outputs/inspections/inspection_<ts>/``:
    - inspection_card.json                   Session descriptor and summary. Holds the
                                             reproducible inputs (file paths, config paths,
                                             overrides) plus the user-facing fields
                                             (``inspection_name``, ``tables``). Rename the
                                             session by editing ``inspection_name`` here.
    - inspection_metadata.json               **Single source of truth** for PKs/FKs and
                                             encoding types. Overwritten in place by
                                             ``PUT /inspections/{id}/autodetect`` when the
                                             user edits the schema; training reads this file.
    - autodetected_inspection_metadata.json  Frozen snapshot of the auto-detected schema as
                                             produced by the inspection run. Never modified
                                             after creation; kept for debugging and historical
                                             reference.
    - processed_data/*.parquet               Preprocessed tables cached to skip
                                             re-preprocessing at training time.
    - profiling_reports/<table>_profiling_report.html
                                             Per-table ydata-profiling reports. Only
                                             produced when ``enable_data_profiling`` is True.
    - time_profiling_report.txt              Elapsed-time breakdown for inspection phases.
"""

import os
import shutil
import threading
from dataclasses import dataclass

import pandas as pd
from backend.src.config.general import (
    AUTODETECTED_INSPECTION_METADATA_FILENAME,
    INSPECTION_CARD_FILENAME,
    INSPECTION_METADATA_FILENAME,
    INSPECTION_RUN_FOLDER_PREFIX,
    INSPECTIONS_DIR,
    PROCESSED_DATA_DIRNAME,
    PROFILING_REPORT_PATTERN,
    PROFILING_REPORTS_DIRNAME,
    TIME_PROFILING_REPORT_FILENAME,
    refresh_run_timestamp,
)
from backend.src.core.card_io import mark_card_failed, read_json, update_card_status, write_json
from backend.src.core.errors import (
    DataLoadError,
    RelationshipNotDefinedError,
    TableMetadataMissingError,
)
from backend.src.core.loader import FileDataLoader
from backend.src.core.logging_config import get_logger, setup_run_logger
from backend.src.core.preprocessing.preprocessor import DataPreprocessor
from backend.src.core.progress import (
    INSPECTION_PHASES,
    INSPECTION_PHASES_NO_PROFILING,
    InspectionPhase,
    advance_progress,
    initial_progress,
)
from backend.src.core.rules_config import extract_rules_and_rejection_config
from backend.src.core.time_profiling import profiler

logger = get_logger(__name__)

RULES_SNAPSHOT_FILENAME = "rules_snapshot.yaml"


@dataclass(frozen=True)
class InspectionResult:
    """Summary of an inspection session ready for user review."""

    inspection_id: str
    inspection_name: str
    output_directory: str
    tables: dict[str, int]
    relationships: dict
    encoding_types: dict


@dataclass(frozen=True)
class InspectionSession:
    """Bookkeeping for a session that has been created on disk but not yet executed.

    ``initialize_inspection_session`` writes the output folder and the initial
    ``in_progress`` card, then returns this object so the caller knows where
    everything lives before the heavy work starts. ``run_inspection_flow``
    receives it and continues from that point without recreating anything.

    The timestamp is stored here explicitly because the ContextVar
    ``RUN_TIMESTAMP`` is not guaranteed to propagate into background threads
    (FastAPI BackgroundTasks runs after the response is sent, possibly in a
    different context). Keeping it on the session ensures the card always
    gets the same timestamp that is part of the ``inspection_id``.

    Compare with ``InspectionResult``: that class is the *output* of a
    completed run — it carries the business data (tables, relationships,
    encoding types) returned to whoever called the flow. This class is
    pure *infrastructure plumbing* used only during the setup phase.
    """

    inspection_id: str
    output_directory: str
    card_path: str
    timestamp: str


def initialize_inspection_session() -> InspectionSession:
    """Create the output folder and the ``in_progress`` inspection card.

    Refreshes the run timestamp and materializes the session on disk.

    Returns:
        InspectionSession: Descriptor of the newly created inspection session.
    """
    timestamp = refresh_run_timestamp()
    inspection_id = f"{INSPECTION_RUN_FOLDER_PREFIX}_{timestamp}"
    output_directory = os.path.join(INSPECTIONS_DIR, inspection_id)
    processed_data_dir = os.path.join(output_directory, PROCESSED_DATA_DIRNAME)
    card_path = os.path.join(output_directory, INSPECTION_CARD_FILENAME)

    os.makedirs(processed_data_dir, exist_ok=True)
    logger.info("Created inspection output directory: %s", output_directory)

    write_json(
        card_path,
        {
            "inspection_id": inspection_id,
            "inspection_name": inspection_id,
            "status": "in_progress",
            # The flow patches the total once profiling is known (it may drop
            # the trailing phase). Default to the full list so the initial
            # poll already shows a sensible bar.
            "progress": initial_progress(INSPECTION_PHASES),
        },
    )

    return InspectionSession(
        inspection_id=inspection_id,
        output_directory=output_directory,
        card_path=card_path,
        timestamp=timestamp,
    )


def run_inspection_flow(
    file_paths: list[str],
    mostly_config_path: str,
    rules_config_path: str,
    enable_data_profiling: bool,
    csv_delimiter: str = ",",
    session: InspectionSession | None = None,
    cancel_event: threading.Event | None = None,
) -> InspectionResult | None:
    """Load, preprocess and autodetect metadata; persist session for later training.

    ``file_paths`` are the same raw inputs the current train flow uses (driven
    by ``execution.file_paths`` in ``backend/config/general.yaml`` when invoked
    from the CLI). They are loaded with
    ``FileDataLoader`` and fed through
    ``DataPreprocessor``; the outputs are cached under the session directory
    so the subsequent training run can skip preprocessing.

    Args:
        file_paths: Paths to input data files or directories.
        mostly_config_path: Path to the Mostly AI configuration file.
        rules_config_path: Path to the logical rules configuration file.
        enable_data_profiling: Whether to run data profiling during preprocessing.
        csv_delimiter: Parsing delimiter. Defaults to ",".
        session: Pre-initialized session (folder + ``in_progress`` card already
            on disk). When ``None`` the function creates it itself. Callers that
            need the ``inspection_id`` before the flow starts (e.g. an async API
            endpoint) should create the session up-front and pass it in.

    Returns:
        InspectionResult with ``inspection_id`` and autodetected artefacts,
        or ``None`` on failure.
    """
    session = session or initialize_inspection_session()
    setup_run_logger(__name__, session.output_directory)

    # totals reflect the work that will actually run.
    phases = INSPECTION_PHASES if enable_data_profiling else INSPECTION_PHASES_NO_PROFILING

    if cancel_event is not None and cancel_event.is_set():
        logger.info("Inspection %s cancelled before execution started.", session.inspection_id)
        update_card_status(session.card_path, "cancelled")
        return None

    try:
        with profiler.phase("inspect"):
            advance_progress(session.card_path, phases, InspectionPhase.LOADING)
            with profiler.phase("load files"):
                raw_data = FileDataLoader().load(file_paths, sep=csv_delimiter)
            preprocessor = DataPreprocessor(raw_data)

            rules, rejection_config = extract_rules_and_rejection_config(rules_config_path)
            for rule in rules:
                preprocessor.rule_manager.add_rule(rule)
            preprocessor.rule_manager.rejection_sampling_config = rejection_config.as_dict()

            effective_rules_config_path = rules_config_path
            # Snapshot the rules file used for this inspection so subsequent steps
            # can show the rules actually applied to the preprocessed dataset,
            # even if the user later edits ``rules.yaml``.
            try:
                snapshot_path = os.path.join(session.output_directory, RULES_SNAPSHOT_FILENAME)
                shutil.copyfile(
                    rules_config_path,
                    snapshot_path,
                )
                effective_rules_config_path = snapshot_path
            except OSError as copy_error:
                logger.warning("Could not snapshot rules file: %s", copy_error)

            advance_progress(session.card_path, phases, InspectionPhase.PREPROCESSING)
            with profiler.phase("preprocess and autodetect"):
                preprocessing_result = preprocessor.run(run_data_profiling=enable_data_profiling)

            advance_progress(session.card_path, phases, InspectionPhase.SAVING_PROCESSED)
            with profiler.phase("save processed data"):
                processed_data_dir = os.path.join(session.output_directory, PROCESSED_DATA_DIRNAME)
                for table_name, df in preprocessing_result.processed_data.items():
                    df.to_parquet(os.path.join(processed_data_dir, f"{table_name}.parquet"))

            table_sizes = {
                name: int(len(df)) for name, df in preprocessing_result.processed_data.items()
            }

            with profiler.phase("write metadata"):
                inspection_metadata_payload = {
                    "relationships": preprocessing_result.relationships,
                    "encoding_types": preprocessing_result.encoding_types,
                }
                write_json(
                    os.path.join(session.output_directory, INSPECTION_METADATA_FILENAME),
                    inspection_metadata_payload,
                )
                write_json(
                    os.path.join(
                        session.output_directory, AUTODETECTED_INSPECTION_METADATA_FILENAME
                    ),
                    inspection_metadata_payload,
                )

            if enable_data_profiling:
                advance_progress(session.card_path, phases, InspectionPhase.PROFILING_REPORTS)
            if preprocessing_result.data_profiles:
                with profiler.phase("write data profiling reports"):
                    profiling_dir = os.path.join(
                        session.output_directory, PROFILING_REPORTS_DIRNAME
                    )
                    os.makedirs(profiling_dir, exist_ok=True)
                    for name, profile in preprocessing_result.data_profiles.items():
                        report_path = os.path.join(
                            profiling_dir, PROFILING_REPORT_PATTERN.format(name=name)
                        )
                        profile.to_file(report_path)
                        logger.info("Data profile for '%s' saved to %s.", name, report_path)

            card = {
                "inspection_id": session.inspection_id,
                "step_name": session.inspection_id,
                "status": "completed",
                "timestamp": session.timestamp,
                "tables": table_sizes,
                "file_paths": list(file_paths),
                "mostly_config_path": mostly_config_path,
                "rules_config_path": effective_rules_config_path,
                "source_rules_config_path": rules_config_path,
                "enable_data_profiling": enable_data_profiling,
                "csv_delimiter": csv_delimiter,
            }
            write_json(session.card_path, card)

            logger.info(
                "Inspection session saved: %s (tables=%s).",
                session.inspection_id,
                list(table_sizes),
            )

            return InspectionResult(
                inspection_id=session.inspection_id,
                inspection_name=session.inspection_id,
                output_directory=session.output_directory,
                tables=table_sizes,
                relationships=preprocessing_result.relationships,
                encoding_types=preprocessing_result.encoding_types,
            )

    except (DataLoadError, TableMetadataMissingError, RelationshipNotDefinedError) as error:
        logger.error("Inspection flow failed: %s", error)
        mark_card_failed(session.card_path, error)
        return None
    except Exception as error:
        logger.error("Inspection flow failed unexpectedly: %s", error, exc_info=True)
        mark_card_failed(session.card_path, error)
        return None
    finally:
        timing_report_path = os.path.join(
            session.output_directory,
            TIME_PROFILING_REPORT_FILENAME,
        )
        profiler.report("Inspection timing breakdown", output_path=timing_report_path)


def load_inspection_artifacts(
    inspection_id: str,
) -> tuple[dict, dict[str, pd.DataFrame], dict]:
    """Load card, processed data and inspection metadata.

    Args:
        inspection_id: Folder name produced by ``run_inspection_flow``.

    Returns:
        Tuple (card, processed_data, inspection_metadata). ``inspection_metadata``
        is the current (possibly user-edited) contents of
        ``inspection_metadata.json`` — the source of truth for PKs/FKs and
        encoding types that training consumes.
    """
    output_directory = os.path.join(INSPECTIONS_DIR, inspection_id)
    if not os.path.isdir(output_directory):
        raise FileNotFoundError(f"Inspection not found: {output_directory}")

    card = read_json(os.path.join(output_directory, INSPECTION_CARD_FILENAME))
    inspection_metadata = read_json(os.path.join(output_directory, INSPECTION_METADATA_FILENAME))

    processed_dir = os.path.join(output_directory, PROCESSED_DATA_DIRNAME)
    processed_data: dict[str, pd.DataFrame] = {}
    for filename in sorted(os.listdir(processed_dir)):
        if filename.endswith(".parquet"):
            table_name = os.path.splitext(filename)[0]
            processed_data[table_name] = pd.read_parquet(os.path.join(processed_dir, filename))

    return card, processed_data, inspection_metadata


def resolve_inspection_rules_config_path(inspection_id: str, card: dict | None = None) -> str:
    """Return the rules YAML that belongs to an inspection.

    New inspections store a frozen ``rules_snapshot.yaml`` inside the
    inspection folder. Older ones may fallback to the original global path.

    Args:
        inspection_id (str): ID of the inspection session.
        card (dict | None): Optional inspection card content. If None, it is loaded.

    Returns:
        str: Absolute path to the resolved rules configuration file.

    Raises:
        FileNotFoundError: If no rules config can be resolved for the inspection.
    """
    output_directory = os.path.join(INSPECTIONS_DIR, inspection_id)
    snapshot_path = os.path.join(output_directory, RULES_SNAPSHOT_FILENAME)
    if os.path.exists(snapshot_path):
        return snapshot_path

    if card is None:
        card_path = os.path.join(output_directory, INSPECTION_CARD_FILENAME)
        card = read_json(card_path) if os.path.exists(card_path) else {}

    rules_config_path = card.get("rules_config_path")
    if rules_config_path:
        logger.warning(
            "Rules snapshot not found for inspection '%s'; falling back to card path '%s'.",
            inspection_id,
            rules_config_path,
        )
        return rules_config_path

    raise FileNotFoundError(f"Rules config not found for inspection: {inspection_id}")
