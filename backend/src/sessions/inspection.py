"""Inspection flow service.

Runs load + preprocessing + autodetection and persists the results to a
session directory so the user can review (and optionally edit) the
autodetected metadata before launching training. Mirrors the shape of
``run_training_flow`` but stops right before ``engine.train``.

The on-disk session bookkeeping (folder creation, card writes, status
transitions, per-run log file) lives in
:class:`backend.src.runs.tracking.inspection_tracker.InspectionTracker`,
so the rest of the file only deals with the inspection flow itself.

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
import threading
from dataclasses import dataclass

import pandas as pd

from backend.src.config.general import (
    AUTODETECTED_INSPECTION_METADATA_FILENAME,
    INSPECTION_CARD_FILENAME,
    INSPECTION_METADATA_FILENAME,
    INSPECTIONS_DIR,
    PROCESSED_DATA_DIRNAME,
    PROFILING_REPORT_PATTERN,
    PROFILING_REPORTS_DIRNAME,
    TIME_PROFILING_REPORT_FILENAME,
)
from backend.src.domain.loader import FileDataLoader
from backend.src.domain.preprocessing.preprocessor import DataPreprocessor
from backend.src.domain.rules_config import extract_rules_and_rejection_config
from backend.src.infrastructure.errors import (
    DataLoadError,
    RelationshipNotDefinedError,
    TableMetadataMissingError,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import (
    INSPECTION_PHASES,
    INSPECTION_PHASES_NO_PROFILING,
    InspectionPhase,
    ProfilerPhase,
    advance_progress,
)
from backend.src.infrastructure.time_profiling import profiler
from backend.src.infrastructure.utils import detect_incompatible_type_mix
from backend.src.runs.card_io import mark_card_failed, read_json, update_card_status, write_json
from backend.src.runs.tracking.inspection_tracker import (
    InspectionSession,
    InspectionTracker,
)
from backend.src.sessions import rules as rules_session

logger = get_logger(__name__)

RULES_SNAPSHOT_FILENAME = rules_session.RULES_SNAPSHOT_FILENAME
INSPECTION_RULE_MANAGER_FILENAME = rules_session.INSPECTION_RULE_MANAGER_FILENAME


def apply_inspection_rules(
    inspection_id: str,
    rules_config_path: str | None = None,
) -> dict:
    """Run the rules stage scoped to this module's inspection directory."""
    return rules_session.apply_inspection_rules(
        inspection_id=inspection_id,
        rules_config_path=rules_config_path,
        inspections_dir=INSPECTIONS_DIR,
    )


# Re-exported so callers (API layer, tests) can keep importing
# ``InspectionSession`` from this module.
__all__ = [
    "InspectionResult",
    "InspectionSession",
    "initialize_inspection_session",
    "apply_inspection_rules",
    "extract_rules_and_rejection_config",
    "load_inspection_artifacts",
    "resolve_inspection_rules_config_path",
    "run_inspection_flow",
    "RULES_SNAPSHOT_FILENAME",
    "INSPECTION_RULE_MANAGER_FILENAME",
]


@dataclass(frozen=True)
class InspectionResult:
    """Summary of an inspection session ready for user review.

    Compare with :class:`InspectionSession`: that descriptor is *infrastructure
    plumbing* used during setup, while this one carries the business data
    (tables, relationships, encoding types) returned to whoever called the
    flow once it has completed.
    """

    inspection_id: str
    inspection_name: str
    output_directory: str
    tables: dict[str, int]
    relationships: dict
    encoding_types: dict


def initialize_inspection_session(name: str | None = None) -> InspectionSession:
    """Create the output folder and the ``in_progress`` inspection card.

    Thin wrapper around :meth:`InspectionTracker.initialize_session` kept for
    backward compatibility with API endpoints that pre-create the session
    synchronously and pass it into a background task.
    """
    return InspectionTracker.initialize_session(name=name)


def run_inspection_flow(
    file_paths: list[str],
    mostly_config_path: str,
    rules_config_path: str,
    enable_data_profiling: bool,
    csv_delimiter: str = ",",
    excluded_columns: dict[str, list[str]] | None = None,
    composite_pks: dict[str, list[str]] | None = None,
    session: InspectionSession | None = None,
    cancel_event: threading.Event | None = None,
) -> InspectionResult | None:
    """Load, preprocess and autodetect metadata; persist session for later training.

    ``file_paths`` are the same raw inputs the current train flow uses (driven
    by ``execution.file_paths`` in ``backend/config/general.yaml`` when invoked
    from the CLI). They are loaded with ``FileDataLoader`` and fed through
    ``DataPreprocessor``; the outputs are cached under the session directory
    so the subsequent training run can skip preprocessing.

    Args:
        file_paths: Paths to input data files or directories.
        mostly_config_path: Path to the Mostly AI configuration file.
        rules_config_path: Path to the logical rules configuration file. The
            inspection step snapshots it for reproducibility, but logical rule
            definition happens in a separate step.
        enable_data_profiling: Whether to run data profiling during preprocessing.
        csv_delimiter: Parsing delimiter. Defaults to ",".
        excluded_columns: Optional mapping of ``table_name → [col, …]``. Columns
            listed here are removed from the autodetect metadata **and** from the
            cached processed parquet files after the inspection run, making them
            invisible to training and all downstream pipeline steps.
        composite_pks: Optional mapping of ``table_name → [col, …]`` declaring
            composite primary keys. For each listed table a single unique PK
            column is synthesized by concatenating the named columns. Falls back
            to heuristic detection if the columns are missing or non-unique.
        session: Pre-initialized session (folder + ``in_progress`` card already
            on disk). When ``None`` the function creates it itself. Callers that
            need the ``inspection_id`` before the flow starts (e.g. an async API
            endpoint) should create the session up-front and pass it in.

    Returns:
        InspectionResult with ``inspection_id`` and autodetected artefacts,
        or ``None`` on failure.
    """
    session = session or initialize_inspection_session()
    phases = INSPECTION_PHASES if enable_data_profiling else INSPECTION_PHASES_NO_PROFILING

    if cancel_event is not None and cancel_event.is_set():
        logger.info("Inspection %s cancelled before execution started.", session.inspection_id)
        update_card_status(session.card_path, "cancelled")
        return None

    try:
        with InspectionTracker.from_session(session) as tracker:
            with profiler.phase(ProfilerPhase.INSPECT):
                advance_progress(tracker.card_path, phases, InspectionPhase.LOADING)
                with profiler.phase(ProfilerPhase.LOAD_FILES):
                    raw_data = FileDataLoader().load(file_paths, sep=csv_delimiter)
                preprocessor = DataPreprocessor(raw_data, composite_pk_config=composite_pks)

                effective_rules_config_path = rules_session._snapshot_rules_file(
                    rules_config_path, tracker.output_directory
                )

                advance_progress(tracker.card_path, phases, InspectionPhase.PREPROCESSING)
                with profiler.phase(ProfilerPhase.PREPROCESS_AUTODETECT):
                    preprocessing_result = preprocessor.run(
                        run_data_profiling=enable_data_profiling
                    )

                advance_progress(tracker.card_path, phases, InspectionPhase.SAVING_PROCESSED)
                processed_data_dir = os.path.join(tracker.output_directory, PROCESSED_DATA_DIRNAME)
                with profiler.phase(ProfilerPhase.SAVE_PROCESSED_DATA):
                    for table_name, df in preprocessing_result.processed_data.items():
                        df.to_parquet(os.path.join(processed_data_dir, f"{table_name}.parquet"))

                table_sizes = {
                    name: int(len(df)) for name, df in preprocessing_result.processed_data.items()
                }

                with profiler.phase(ProfilerPhase.WRITE_METADATA):
                    # Flag columns that mix numbers and free text. They have no safe
                    # encoding (they crash Mostly AI's language-model report generation),
                    # so we surface them alongside the autodetected types and recommend
                    # excluding them. This is non-destructive: the column stays in the
                    # schema so the frontend can render it flagged (pre-selected as
                    # excluded, toggleable). The physical drop happens later through the
                    # user-driven excluded-columns flow / training, never here.
                    flagged_columns = _detect_incompatible_columns(
                        preprocessing_result.processed_data
                    )
                    warnings = _build_incompatible_warnings(flagged_columns)
                    for warning in warnings:
                        logger.warning(warning["message"])
                    # Flagged columns are excluded from training by default. The
                    # data stays on disk; training drops these in memory. The user
                    # can opt back in by toggling them off in the autodetect view.
                    auto_excluded = {
                        table: sorted(cols.keys()) for table, cols in flagged_columns.items()
                    }

                    encoding_types, relationships = _apply_column_exclusions(
                        encoding_types=preprocessing_result.encoding_types,
                        relationships=preprocessing_result.relationships,
                        excluded_columns=excluded_columns,
                        processed_data_dir=processed_data_dir,
                    )
                    inspection_metadata_payload = {
                        "relationships": relationships,
                        "encoding_types": encoding_types,
                        "date_formats": getattr(preprocessing_result, "date_formats", {}) or {},
                        "warnings": warnings,
                        "excluded_columns": auto_excluded,
                    }
                    write_json(
                        os.path.join(tracker.output_directory, INSPECTION_METADATA_FILENAME),
                        inspection_metadata_payload,
                    )
                    write_json(
                        os.path.join(
                            tracker.output_directory,
                            AUTODETECTED_INSPECTION_METADATA_FILENAME,
                        ),
                        inspection_metadata_payload,
                    )

                if enable_data_profiling:
                    advance_progress(tracker.card_path, phases, InspectionPhase.PROFILING_REPORTS)
                if preprocessing_result.data_profiles:
                    with profiler.phase(ProfilerPhase.WRITE_PROFILING_REPORTS):
                        _write_profiling_reports(
                            preprocessing_result.data_profiles, tracker.output_directory
                        )

                # Preserve the user-assigned name (set via PATCH /name after the
                # session was created) instead of resetting it to the raw id.
                existing_card = read_json(session.card_path)
                inspection_name = existing_card.get("inspection_name") or session.inspection_id

                tracker.finalize_card(
                    {
                        "inspection_id": session.inspection_id,
                        "inspection_name": inspection_name,
                        "step_name": inspection_name,
                        "timestamp": session.timestamp,
                        "tables": table_sizes,
                        "file_paths": list(file_paths),
                        "mostly_config_path": mostly_config_path,
                        "rules_config_path": effective_rules_config_path,
                        "source_rules_config_path": rules_config_path,
                        "enable_data_profiling": enable_data_profiling,
                        "csv_delimiter": csv_delimiter,
                        "composite_pks": composite_pks or {},
                        "warnings": warnings,
                    }
                )

                logger.info(
                    "Inspection session saved: %s (tables=%s).",
                    session.inspection_id,
                    list(table_sizes),
                )

                return InspectionResult(
                    inspection_id=session.inspection_id,
                    inspection_name=inspection_name,
                    output_directory=tracker.output_directory,
                    tables=table_sizes,
                    relationships=relationships,
                    encoding_types=encoding_types,
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


def _detect_incompatible_columns(
    processed_data: dict[str, pd.DataFrame],
) -> dict[str, dict[str, dict]]:
    """Scan tables for columns mixing numbers and free text.

    See :func:`detect_incompatible_type_mix`. Detection is non-destructive: the
    flagged columns stay in the schema/data; the result is surfaced as warnings
    so the frontend can show them alongside the autodetected types (pre-selected
    as excluded, but toggleable by the user).

    Returns ``{table_name: {column: summary}}`` for every flagged column.
    """
    flagged: dict[str, dict[str, dict]] = {}
    for table_name, df in processed_data.items():
        for col in df.columns:
            summary = detect_incompatible_type_mix(df[col])
            if summary is not None:
                flagged.setdefault(table_name, {})[col] = summary
    return flagged


def _build_incompatible_warnings(
    flagged_columns: dict[str, dict[str, dict]],
) -> list[dict]:
    """Turn flagged columns into user-facing warning records for the card/metadata.

    ``default_excluded`` tells the frontend to pre-select the column for
    exclusion; the user can still toggle it back on (after splitting/cleaning it).
    """
    warnings: list[dict] = []
    for table_name, cols in flagged_columns.items():
        for col, summary in cols.items():
            warnings.append(
                {
                    "table": table_name,
                    "column": col,
                    "kind": "incompatible_type_mix",
                    "default_excluded": True,
                    "message": (
                        "Mezcla números y texto sin un tipo seguro. Excluida del "
                        "entreno por defecto; sepárala o límpiala para conservarla."
                    ),
                    "details": summary,
                }
            )
    return warnings


def _apply_column_exclusions(
    encoding_types: dict,
    relationships: dict,
    excluded_columns: dict[str, list[str]] | None,
    processed_data_dir: str,
) -> tuple[dict, dict]:
    """Strip user-excluded columns from the autodetect outputs and parquet cache.

    Removes the columns from the encoding-types map, drops any FK/PK
    relationships that reference them, and rewrites the cached parquet
    files so the excluded columns never leak into training.
    """
    excluded = {t: set(cols) for t, cols in (excluded_columns or {}).items() if cols}
    if not excluded:
        return encoding_types, relationships

    filtered_types: dict = {}
    for tbl, cols in encoding_types.items():
        drop = excluded.get(tbl, set())
        filtered_types[tbl] = {c: v for c, v in cols.items() if c not in drop}

    fks = relationships.get("fks", [])
    filtered_fks = [
        fk
        for fk in fks
        if fk.get("fk_column") not in excluded.get(fk.get("child", ""), set())
        and fk.get("pk_column") not in excluded.get(fk.get("parent", ""), set())
    ]
    pks = {
        tbl: pk_col
        for tbl, pk_col in relationships.get("pks", {}).items()
        if pk_col not in excluded.get(tbl, set())
    }

    for tbl, drop_cols in excluded.items():
        parquet_path = os.path.join(processed_data_dir, f"{tbl}.parquet")
        if not os.path.exists(parquet_path):
            continue
        df = pd.read_parquet(parquet_path)
        cols_to_drop = [c for c in drop_cols if c in df.columns]
        if cols_to_drop:
            df = df.drop(columns=cols_to_drop)
            df.to_parquet(parquet_path)
            logger.info("Dropped excluded columns %s from '%s'.", cols_to_drop, tbl)

    return filtered_types, {"pks": pks, "fks": filtered_fks}


def _write_profiling_reports(data_profiles: dict, output_directory: str) -> None:
    """Persist ydata-profiling HTML reports under ``profiling_reports/``."""
    profiling_dir = os.path.join(output_directory, PROFILING_REPORTS_DIRNAME)
    os.makedirs(profiling_dir, exist_ok=True)
    for name, profile in data_profiles.items():
        report_path = os.path.join(profiling_dir, PROFILING_REPORT_PATTERN.format(name=name))
        profile.to_file(report_path)
        logger.info("Data profile for '%s' saved to %s.", name, report_path)


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

    Uses the inspection-scoped rules helper but anchors lookups to the
    inspections directory configured for this module (useful for tests).
    """
    return rules_session.resolve_inspection_rules_config_path(
        inspection_id,
        card=card,
        inspections_dir=INSPECTIONS_DIR,
    )
