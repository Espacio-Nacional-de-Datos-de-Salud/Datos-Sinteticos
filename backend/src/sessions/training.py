"""Training flow service for the synthetic data tool."""

import os
import shutil
import threading
from dataclasses import dataclass

import pandas as pd
import yaml

from backend.src.config.general import (
    AUTODETECTED_INSPECTION_METADATA_FILENAME,
    BRC_CARD_FILENAME,
    BRC_DIR,
    INSPECTION_CARD_FILENAME,
    INSPECTION_METADATA_FILENAME,
    INSPECTIONS_DIR,
    MODEL_CARD_FILENAME,
    MODEL_RUN_FOLDER_PREFIX,
    MODELS_DIR,
    MOSTLYAI_DIR,
    PROCESSED_DATA_DIRNAME,
    SKIP_DATA_CLEANING_TABLES,
    TIME_PROFILING_REPORT_FILENAME,
    refresh_run_timestamp,
)
from backend.src.domain.loader import FileDataLoader
from backend.src.domain.modeling_configuration import build_modeling_configuration
from backend.src.domain.preprocessing.logical_rules import LogicalRuleManager
from backend.src.domain.preprocessing.logical_rules_serialization import (
    reconstruct_logical_rule_manager_from_dict,
)
from backend.src.domain.preprocessing.metadata_extractor import MetadataExtractor
from backend.src.domain.preprocessing.metadata_formatter import MetadataFormatter
from backend.src.domain.preprocessing.preprocessor import DataPreprocessor
from backend.src.domain.preprocessing.utils import (
    format_relationships,
    infer_foreign_keys_consistency_rules,
)
from backend.src.domain.rules_config import extract_rules_and_rejection_config
from backend.src.domain.synthesis import create_engine, resolve_active_engine
from backend.src.domain.synthesis.training_diagnostics import collect_preflight_issues
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import (
    TRAINING_PHASES,
    ProfilerPhase,
    TrainingPhase,
    advance_progress,
    initial_progress,
)
from backend.src.infrastructure.time_profiling import profiler
from backend.src.runs.card_io import mark_card_failed, read_json, update_card_status, write_json
from backend.src.runs.tracking import ModelTracker
from backend.src.sessions.inspection import load_inspection_artifacts
from backend.src.sessions.rules import (
    INSPECTION_RULE_MANAGER_FILENAME,
    resolve_inspection_rules_config_path,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class TrainingSession:
    """Pre-initialized training session created before the background task runs.

    Mirrors ``InspectionSession``: the folder and initial card are written
    synchronously so the API endpoint can return the ``model_id`` immediately,
    while the heavy training work executes in the background.
    """

    model_id: str
    output_directory: str
    card_path: str
    timestamp: str


def initialize_training_session(name: str | None = None) -> TrainingSession:
    """Create the output folder and the ``in_progress`` model card.

    Refreshes the run timestamp and materializes the session on disk.

    Returns:
        TrainingSession: Descriptor of the newly created training session.
    """
    timestamp = refresh_run_timestamp()
    model_id = f"{MODEL_RUN_FOLDER_PREFIX}_{timestamp}"
    output_directory = os.path.join(MODELS_DIR, model_id)
    configs_directory = os.path.join(output_directory, "configs")
    card_path = os.path.join(output_directory, MODEL_CARD_FILENAME)

    os.makedirs(configs_directory, exist_ok=True)
    logger.info("Created training output directory: %s", output_directory)

    write_json(
        card_path,
        {
            "model_id": model_id,
            "model_name": name.strip() if name and name.strip() else model_id,
            "status": "in_progress",
            "timestamp": timestamp,
            "progress": initial_progress(TRAINING_PHASES),
        },
        indent=4,
    )

    return TrainingSession(
        model_id=model_id,
        output_directory=output_directory,
        card_path=card_path,
        timestamp=timestamp,
    )


def run_training_flow(
    file_paths: list[str],
    mostly_config_path: str,
    rules_config_path: str,
    enable_data_profiling: bool,
    csv_delimiter: str = ",",
    mostly_ai_overrides: dict | None = None,
    pipeline_id: str = "none",
    job_name: str | None = None,
    session: TrainingSession | None = None,
    cancel_event: threading.Event | None = None,
    skip_data_cleaning_tables: list[str] | tuple[str, ...] | set[str] | None = None,
) -> tuple[str | None, object | None, object | None, object | None]:
    """Execute the core training workflow isolated from CLI or Pipeline.

    This function sets up the tracking context, reads the raw data, applies the
    preprocessing pipeline (including logical rules), and finally trains the
    Mostly AI generator.

    Args:
        file_paths (list[str]): Paths to input data files or directories.
        mostly_config_path (str): Path to the Mostly AI configuration file.
        rules_config_path (str): Path to the logical rules configuration file.
        enable_data_profiling (bool): Whether to run data profiling during preprocessing.
        csv_delimiter (str, optional): Parsing delimiter. Defaults to ",".
        mostly_ai_overrides (dict | None, optional): Specific engine overrides.
        pipeline_id (str, optional): The ID tying jobs together if part of pipeline.
        job_name (str | None, optional): The human name of the job currently executing.
        skip_data_cleaning_tables (list[str] | tuple[str, ...] | set[str] | None, optional):
            Table names that should bypass the data-cleaning step.

    Returns:
        tuple[str | None, object | None, object | None, object | None]:
            Provides (model_id, generator, metadata, rule_manager). On failure,
            returns (None, None, None, None).
    """
    from backend.src.infrastructure.cancellation import JobCancelled

    if cancel_event is not None and cancel_event.is_set():
        logger.info(
            "Training %s cancelled before execution started.", session.model_id if session else ""
        )
        if session:
            update_card_status(session.card_path, "cancelled")
        return None, None, None, None

    try:
        with ModelTracker(
            data_file_paths=file_paths,
            mostly_config_path=mostly_config_path,
            rules_config_path=rules_config_path,
            pipeline_id=pipeline_id,
            mostly_ai_overrides=mostly_ai_overrides,
            job_name=job_name,
            model_id=session.model_id if session else None,
        ) as model_tracker:
            engine_name = resolve_active_engine()
            engine = create_engine(
                engine_name=engine_name,
                config_path=mostly_config_path,
                config_overrides=mostly_ai_overrides,
                run_dir=model_tracker.output_directory,
                local_dir=MOSTLYAI_DIR,
            )

            with profiler.phase(ProfilerPhase.LOAD_FILES):
                raw_data = FileDataLoader().load(file_paths, sep=csv_delimiter)
            effective_skip_tables = (
                SKIP_DATA_CLEANING_TABLES
                if skip_data_cleaning_tables is None
                else tuple(skip_data_cleaning_tables)
            )
            preprocessor = DataPreprocessor(
                raw_data,
                skip_data_cleaning_tables=effective_skip_tables,
            )

            rules, rejection_config = extract_rules_and_rejection_config(rules_config_path)
            for rule in rules:
                preprocessor.rule_manager.add_rule(rule)
            preprocessor.rule_manager.rejection_sampling_config = rejection_config.as_dict()

            with profiler.phase(ProfilerPhase.PREPROCESS_AUTODETECT):
                preprocessing_result = preprocessor.run(run_data_profiling=enable_data_profiling)

            with profiler.phase(ProfilerPhase.APPLY_RULES):
                processed_data = preprocessor.rule_manager.apply_all_pre(
                    preprocessing_result.processed_data,
                    relationships=format_relationships(preprocessing_result.relationships),
                )
            encoding_types = MetadataExtractor(processed_data).extract_encoding_types()
            metadata = MetadataFormatter(engine_name=engine_name).format(
                data_dfs=processed_data,
                relationships_data=preprocessing_result.relationships,
                types_data=encoding_types,
            )
            engine_config = getattr(engine, "config", {}) or {}
            model_settings = engine_config.get("model_settings") or {}
            modeling_configuration = build_modeling_configuration(model_settings, metadata)
            metadata["modeling_configuration"] = modeling_configuration

            with profiler.phase(ProfilerPhase.SAVE_METADATA_AND_REPORTS):
                model_tracker.save_training_table_sizes(processed_data)
                model_tracker.save_rule_manager(preprocessing_result.rule_manager)
                model_tracker.save_metadata(metadata)
                save_modeling_configuration = getattr(
                    model_tracker, "save_modeling_configuration", None
                )
                if save_modeling_configuration is not None:
                    save_modeling_configuration(modeling_configuration)
                if preprocessing_result.data_profiles:
                    model_tracker.save_data_profiles(preprocessing_result.data_profiles)

            with profiler.phase(ProfilerPhase.MOSTLYAI_TRAIN):
                generator = engine.train(processed_data, metadata, cancel_event=cancel_event)
            with profiler.phase(ProfilerPhase.SAVE_ARTIFACTS):
                model_tracker.save_generator(generator)
                model_tracker.save_qa_reports(generator.id)
                model_tracker.save_mostly_statistics(generator.id)

            return (
                model_tracker.model_id,
                generator,
                metadata,
                preprocessing_result.rule_manager,
            )

    except JobCancelled:
        return None, None, None, None
    except Exception as error:
        logger.error("Train flow failed: %s", error, exc_info=True)
        if session:
            mark_card_failed(session.card_path, error)
        return None, None, None, None
    finally:
        if session:
            timing_report_path = os.path.join(
                session.output_directory,
                TIME_PROFILING_REPORT_FILENAME,
            )
            profiler.report("Training timing breakdown", output_path=timing_report_path)


def _drop_excluded_columns(
    processed_data: dict,
    encoding_types: dict,
    relationships: dict,
    excluded: dict[str, list[str]] | None,
) -> tuple[dict, dict, dict]:
    """Drop training-time excluded columns from the in-memory inputs.

    Mirrors the inspection's column exclusion but never touches disk: it filters
    the dataframes, the encoding-type map, and any FK/PK relationship that
    references an excluded column. Used to honor the reversible ``excluded_columns``
    recorded in the inspection metadata (auto-flagged mixes, opt-out toggles).
    """
    drop = {t: set(cols) for t, cols in (excluded or {}).items() if cols}
    if not drop:
        return processed_data, encoding_types, relationships

    filtered_data = {}
    for table_name, df in processed_data.items():
        cols = [c for c in drop.get(table_name, set()) if c in df.columns]
        filtered_data[table_name] = df.drop(columns=cols) if cols else df

    filtered_types = {
        table_name: {c: v for c, v in cols.items() if c not in drop.get(table_name, set())}
        for table_name, cols in encoding_types.items()
    }

    fks = [
        fk
        for fk in relationships.get("fks", [])
        if fk.get("fk_column") not in drop.get(fk.get("child", ""), set())
        and fk.get("pk_column") not in drop.get(fk.get("parent", ""), set())
    ]
    pks = {
        table_name: pk
        for table_name, pk in relationships.get("pks", {}).items()
        if pk not in drop.get(table_name, set())
    }
    if drop:
        logger.info(
            "Dropped training-excluded columns: %s", {t: sorted(c) for t, c in drop.items()}
        )
    return filtered_data, filtered_types, {"pks": pks, "fks": fks}


def collect_training_preflight(inspection_id: str) -> list[dict]:
    """Evaluate known training preconditions for an inspection, before launch.

    Cheap by design: uses the inspection card's per-table row counts and the
    saved relationships instead of loading the processed parquets, plus the
    *current* Mostly AI config — the same file a training launched now would
    read. Returns one dict per detected issue: ``{id, title, guidance, tables}``
    (empty list = nothing known would make the run fail).
    """
    output_directory = os.path.join(INSPECTIONS_DIR, inspection_id)
    if not os.path.isdir(output_directory):
        raise FileNotFoundError(f"Inspection not found: {output_directory}")
    card = read_json(os.path.join(output_directory, INSPECTION_CARD_FILENAME))
    inspection_metadata = read_json(os.path.join(output_directory, INSPECTION_METADATA_FILENAME))
    foreign_keys = (inspection_metadata.get("relationships") or {}).get("fks") or []

    row_counts = {str(table): int(count) for table, count in (card.get("tables") or {}).items()}
    # Length-only stand-ins: the detectors need row counts and table
    # membership, never actual cell values.
    data = {
        name: pd.DataFrame(index=pd.RangeIndex(count)) for name, count in row_counts.items()
    }
    metadata = {
        "tables": [
            {
                "name": name,
                "foreign_keys": [
                    {
                        "column": fk.get("fk_column"),
                        "referenced_table": fk.get("parent"),
                        "is_context": bool(fk.get("is_context")),
                    }
                    for fk in foreign_keys
                    if fk.get("child") == name
                ],
            }
            for name in row_counts
        ]
    }

    from backend.src.sessions.configs import resolve_config_path

    config_path = card.get("mostly_config_path")
    if not config_path or not os.path.exists(config_path):
        config_path = str(resolve_config_path("mostly_ai"))
    model_settings: dict = {}
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f) or {}
            model_settings = config.get("model_settings") or {}
        except (OSError, yaml.YAMLError):
            logger.warning("Could not read Mostly AI config at %s for preflight.", config_path)

    issues = collect_preflight_issues(data, metadata, model_settings)
    return [
        {"id": issue.id, "title": issue.title, "guidance": issue.guidance, "tables": issue.tables}
        for issue in issues
    ]


def run_training_flow_from_inspection(
    inspection_id: str,
    mostly_ai_overrides: dict | None = None,
    pipeline_id: str = "none",
    job_name: str | None = None,
    session: TrainingSession | None = None,
    cancel_event: threading.Event | None = None,
    brc_id: str | None = None,
    skip_rules: bool = False,
) -> tuple[str | None, object | None, object | None, object | None]:
    """Train directly from a previously produced inspection session.

    Reuses the processed tables cached as parquet by ``run_inspection_flow``.
    ``inspection_metadata.json`` is the **single source of truth**: the engine
    metadata is regenerated from it at training time via ``MetadataFormatter``
    so any manual edits to relationships or encoding types take effect. The
    rule manager is rebuilt from the inspection's own frozen rules snapshot
    plus the FK consistency rules inferred from the current relationships.

    For traceability the resulting model card is stamped with the source
    ``inspection_id`` and ``inspection_name``.

    Args:
        inspection_id: Folder name produced by ``run_inspection_flow``.
        mostly_ai_overrides: Engine overrides; when None, the ones saved in
            the inspection session are used.
        pipeline_id: Pipeline ID grouping this run.
        job_name: Human name of the job currently executing.

    Returns:
        ``(model_id, generator, metadata, rule_manager)`` or ``(None, ...)`` on failure.
    """
    from backend.src.infrastructure.cancellation import JobCancelled

    if cancel_event is not None and cancel_event.is_set():
        logger.info(
            "Training %s cancelled before execution started.", session.model_id if session else ""
        )
        if session:
            update_card_status(session.card_path, "cancelled")
        return None, None, None, None

    try:
        if session:
            advance_progress(session.card_path, TRAINING_PHASES, TrainingPhase.PREPARING)

        card, processed_data, inspection_metadata = load_inspection_artifacts(inspection_id)

        output_directory = os.path.join(INSPECTIONS_DIR, inspection_id)
        autodetected_path = os.path.join(
            output_directory, AUTODETECTED_INSPECTION_METADATA_FILENAME
        )
        rules_config_path = resolve_inspection_rules_config_path(inspection_id, card)

        # When a BRC run is selected as input, swap the inspection's
        # processed_data with the BRC's already-PRE-applied parquets and
        # arrange for the rule manager to be loaded from the BRC folder
        # later in the flow. The inspection metadata (relationships,
        # encoding types, excluded columns) still drives the rest of the
        # pipeline, since the BRC is just a materialised PRE on top.
        brc_dir = None
        brc_card = None
        if brc_id:
            brc_dir = os.path.join(BRC_DIR, brc_id)
            brc_card_path = os.path.join(brc_dir, BRC_CARD_FILENAME)
            if not os.path.exists(brc_card_path):
                raise FileNotFoundError(f"BRC card not found for '{brc_id}'.")
            brc_card = read_json(brc_card_path)
            if brc_card.get("inspection_id") != inspection_id:
                raise ValueError(
                    f"BRC run '{brc_id}' belongs to inspection "
                    f"'{brc_card.get('inspection_id')}', not '{inspection_id}'."
                )
            brc_processed_dir = os.path.join(brc_dir, PROCESSED_DATA_DIRNAME)
            if not os.path.isdir(brc_processed_dir):
                raise FileNotFoundError(
                    f"BRC processed data not found for '{brc_id}': {brc_processed_dir}"
                )
            import pandas as pd

            processed_data = {}
            for filename in sorted(os.listdir(brc_processed_dir)):
                if filename.endswith(".parquet"):
                    table_name = os.path.splitext(filename)[0]
                    processed_data[table_name] = pd.read_parquet(
                        os.path.join(brc_processed_dir, filename)
                    )
            logger.info(
                "Training using BRC '%s' (tables=%s).",
                brc_id,
                sorted(processed_data),
            )

        relationships = inspection_metadata.get("relationships", {"pks": {}, "fks": []})
        encoding_types = inspection_metadata.get("encoding_types", {})
        date_formats = inspection_metadata.get("date_formats", {}) or {}

        # When training from a BRC the parquet already represents the final
        # state the user picked; do not re-run preprocessing from raw even if
        # autodetect metadata changed afterwards.
        if brc_dir is None and os.path.exists(autodetected_path):
            autodetected_metadata = read_json(autodetected_path)
            if autodetected_metadata != inspection_metadata:
                logger.info("Inspection metadata was modified. Re-running preprocessing.")

                raw_data = FileDataLoader().load(
                    card.get("file_paths", []), sep=card.get("csv_delimiter", ",")
                )
                preprocessor = DataPreprocessor(raw_data)

                rules, rejection_config = extract_rules_and_rejection_config(
                    card["rules_config_path"]
                )

                preprocessing_result = preprocessor.run(
                    run_data_profiling=False,
                    user_defined_relationships=relationships,
                    user_defined_types=encoding_types,
                )

                processed_dir = os.path.join(output_directory, PROCESSED_DATA_DIRNAME)
                shutil.rmtree(processed_dir, ignore_errors=True)
                os.makedirs(processed_dir, exist_ok=True)

                processed_data = preprocessing_result.processed_data
                for table_name, df in processed_data.items():
                    df.to_parquet(os.path.join(processed_dir, f"{table_name}.parquet"))

        # Drop columns the user (or the auto-flagger) marked excluded from training.
        # Non-destructive: the cached parquet keeps them, we only skip them for this
        # run. Done before rules/encoding so they never reach MostlyAI.
        processed_data, encoding_types, relationships = _drop_excluded_columns(
            processed_data,
            encoding_types,
            relationships,
            inspection_metadata.get("excluded_columns", {}),
        )

        mostly_config_path = card["mostly_config_path"]
        effective_overrides = (
            mostly_ai_overrides
            if mostly_ai_overrides is not None
            else card.get("mostly_ai_overrides") or None
        )

        rule_manager = None
        reapply = True
        if skip_rules and brc_dir is None:
            rule_manager = LogicalRuleManager()
            rule_manager.relationships = format_relationships(relationships)
            rule_manager.rejection_sampling_config = {}
            reapply = False
        elif brc_dir is not None:
            rule_manager_path = os.path.join(brc_dir, INSPECTION_RULE_MANAGER_FILENAME)
            if os.path.exists(rule_manager_path):
                logger.debug("Found existing rule manager for BRC %s. Attempting to load.", brc_id)
                try:
                    serialized = read_json(rule_manager_path)
                    rule_manager = reconstruct_logical_rule_manager_from_dict(serialized)
                    rule_manager.relationships = format_relationships(relationships)
                    reapply = False
                except Exception as exc:
                    logger.warning(
                        "Failed to load BRC rule manager '%s': %s. Rebuilding from config.",
                        rule_manager_path,
                        exc,
                    )
                    rule_manager = None

        if rule_manager is None:
            logger.debug("Rule manager did not exist. Building from config: %s", rules_config_path)
            rule_manager = LogicalRuleManager()
            rule_manager.relationships = format_relationships(relationships)
            rules, rejection_config = extract_rules_and_rejection_config(rules_config_path)
            for rule in rules:
                rule_manager.add_rule(rule)
            rule_manager.rejection_sampling_config = rejection_config.as_dict()

        if date_formats:
            rule_manager.date_formats = date_formats
        for rule in infer_foreign_keys_consistency_rules(relationships):
            rule_manager.add_rule(rule)

        if reapply:
            logger.debug("REAPPLY=TRUE; Applying rules PRE to inspection data for training.")
            processed_data = rule_manager.apply_all_pre(
                processed_data, relationships=format_relationships(relationships)
            )
            encoding_types = MetadataExtractor(processed_data).extract_encoding_types()
        else:
            processed_data = rule_manager.apply_foreign_key_consistency_pre(processed_data)

        engine_name = resolve_active_engine()
        metadata = MetadataFormatter(engine_name=engine_name).format(
            data_dfs=processed_data,
            relationships_data=relationships,
            types_data=encoding_types,
        )

        with ModelTracker(
            data_file_paths=card.get("file_paths", []),
            mostly_config_path=mostly_config_path,
            rules_config_path=rules_config_path,
            pipeline_id=pipeline_id,
            mostly_ai_overrides=effective_overrides,
            job_name=job_name,
            model_id=session.model_id if session else None,
        ) as model_tracker:
            engine = create_engine(
                engine_name=engine_name,
                config_path=mostly_config_path,
                config_overrides=effective_overrides,
                run_dir=model_tracker.output_directory,
                local_dir=MOSTLYAI_DIR,
            )
            engine_config = getattr(engine, "config", {}) or {}
            model_settings = engine_config.get("model_settings") or {}
            modeling_configuration = build_modeling_configuration(model_settings, metadata)
            metadata["modeling_configuration"] = modeling_configuration

            with profiler.phase(ProfilerPhase.SAVE_METADATA_AND_REPORTS):
                model_tracker.save_training_table_sizes(processed_data)
                model_tracker.save_rule_manager(rule_manager)
                model_tracker.save_metadata(metadata)
                save_modeling_configuration = getattr(
                    model_tracker, "save_modeling_configuration", None
                )
                if save_modeling_configuration is not None:
                    save_modeling_configuration(modeling_configuration)
                _stamp_inspection_info_on_model_card(
                    output_directory=model_tracker.output_directory,
                    inspection_id=inspection_id,
                    inspection_name=card.get("inspection_name"),
                    brc_id=brc_id,
                    brc_name=brc_card.get("brc_name") if brc_card else None,
                )

            if session:
                advance_progress(session.card_path, TRAINING_PHASES, TrainingPhase.TRAINING)
            with profiler.phase(ProfilerPhase.MOSTLYAI_TRAIN):
                generator = engine.train(processed_data, metadata, cancel_event=cancel_event)
            with profiler.phase(ProfilerPhase.SAVE_ARTIFACTS):
                model_tracker.save_generator(generator)
                if session:
                    advance_progress(
                        session.card_path, TRAINING_PHASES, TrainingPhase.SAVING_REPORTS
                    )
                model_tracker.save_qa_reports(generator.id)
                model_tracker.save_mostly_statistics(generator.id)

            return model_tracker.model_id, generator, metadata, rule_manager

    except JobCancelled:
        return None, None, None, None
    except Exception as error:
        logger.error("Train-from-inspection flow failed: %s", error, exc_info=True)
        if session:
            mark_card_failed(session.card_path, error)
        return None, None, None, None
    finally:
        if session:
            timing_report_path = os.path.join(
                session.output_directory,
                TIME_PROFILING_REPORT_FILENAME,
            )
            profiler.report("Training timing breakdown", output_path=timing_report_path)


def _stamp_inspection_info_on_model_card(
    output_directory: str,
    inspection_id: str,
    inspection_name: str | None,
    brc_id: str | None = None,
    brc_name: str | None = None,
) -> None:
    """Record the originating inspection details in the model card.

    Args:
        output_directory (str): Path to the model output directory.
        inspection_id (str): ID of the source inspection.
        inspection_name (str | None): Human-readable name of the source inspection.
        brc_id (str | None): Optional BRC run used as the training input.
        brc_name (str | None): Human-readable name of the BRC run.
    """
    card_path = os.path.join(output_directory, MODEL_CARD_FILENAME)
    if not os.path.exists(card_path):
        return
    card = read_json(card_path)
    card["inspection_id"] = inspection_id
    if inspection_name:
        card["inspection_name"] = inspection_name
    if brc_id:
        card["brc_id"] = brc_id
        if brc_name:
            card["brc_name"] = brc_name
    write_json(card_path, card, indent=4)
