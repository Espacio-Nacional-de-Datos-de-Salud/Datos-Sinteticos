"""Training flow service for the synthetic data tool."""

import os
import shutil
import threading
from dataclasses import dataclass

from backend.src.config.general import (
    AUTODETECTED_INSPECTION_METADATA_FILENAME,
    INSPECTIONS_DIR,
    MODEL_CARD_FILENAME,
    MODEL_RUN_FOLDER_PREFIX,
    MODELS_DIR,
    MOSTLYAI_DIR,
    PROCESSED_DATA_DIRNAME,
    TIME_PROFILING_REPORT_FILENAME,
    refresh_run_timestamp,
)
from backend.src.domain.loader import FileDataLoader
from backend.src.domain.preprocessing.logical_rules import LogicalRuleManager
from backend.src.domain.preprocessing.metadata_formatter import MetadataFormatter
from backend.src.domain.preprocessing.preprocessor import DataPreprocessor
from backend.src.domain.preprocessing.utils import (
    format_relationships,
    infer_foreign_keys_consistency_rules,
)
from backend.src.domain.rules_config import extract_rules_and_rejection_config
from backend.src.domain.synthesis import MostlyAIEngine
from backend.src.sessions.inspection import (
    load_inspection_artifacts,
    resolve_inspection_rules_config_path,
)
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
            engine = MostlyAIEngine(
                config_path=mostly_config_path,
                config_overrides=mostly_ai_overrides,
                run_dir=model_tracker.output_directory,
                local_dir=MOSTLYAI_DIR,
            )

            with profiler.phase(ProfilerPhase.LOAD_FILES):
                raw_data = FileDataLoader().load(file_paths, sep=csv_delimiter)
            preprocessor = DataPreprocessor(raw_data)

            rules, rejection_config = extract_rules_and_rejection_config(rules_config_path)
            for rule in rules:
                preprocessor.rule_manager.add_rule(rule)
            preprocessor.rule_manager.rejection_sampling_config = rejection_config.as_dict()

            with profiler.phase(ProfilerPhase.PREPROCESS_AUTODETECT):
                preprocessing_result = preprocessor.run(run_data_profiling=enable_data_profiling)

            with profiler.phase(ProfilerPhase.SAVE_METADATA_AND_REPORTS):
                model_tracker.save_training_table_sizes(preprocessing_result.processed_data)
                model_tracker.save_rule_manager(preprocessing_result.rule_manager)
                model_tracker.save_metadata(preprocessing_result.metadata)
                if preprocessing_result.data_profiles:
                    model_tracker.save_data_profiles(preprocessing_result.data_profiles)

            with profiler.phase(ProfilerPhase.MOSTLYAI_TRAIN):
                generator = engine.train(
                    preprocessing_result.processed_data,
                    preprocessing_result.metadata,
                    cancel_event=cancel_event,
                )
            with profiler.phase(ProfilerPhase.SAVE_ARTIFACTS):
                model_tracker.save_generator(generator)
                model_tracker.save_qa_reports(generator.id)
                model_tracker.save_mostly_statistics(generator.id)

            return (
                model_tracker.model_id,
                generator,
                preprocessing_result.metadata,
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


def run_training_flow_from_inspection(
    inspection_id: str,
    mostly_ai_overrides: dict | None = None,
    pipeline_id: str = "none",
    job_name: str | None = None,
    session: TrainingSession | None = None,
    cancel_event: threading.Event | None = None,
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

        relationships = inspection_metadata.get("relationships", {"pks": {}, "fks": []})
        encoding_types = inspection_metadata.get("encoding_types", {})

        if os.path.exists(autodetected_path):
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
                for rule in rules:
                    preprocessor.rule_manager.add_rule(rule)
                preprocessor.rule_manager.rejection_sampling_config = rejection_config.as_dict()

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

        mostly_config_path = card["mostly_config_path"]
        effective_overrides = (
            mostly_ai_overrides
            if mostly_ai_overrides is not None
            else card.get("mostly_ai_overrides") or None
        )

        metadata = MetadataFormatter(engine_name="mostly").format(
            data_dfs=processed_data,
            relationships_data=relationships,
            types_data=encoding_types,
        )

        rule_manager = LogicalRuleManager()
        rule_manager.relationships = format_relationships(relationships)
        rules, rejection_config = extract_rules_and_rejection_config(rules_config_path)
        for rule in rules:
            rule_manager.add_rule(rule)
        rule_manager.rejection_sampling_config = rejection_config.as_dict()
        for rule in infer_foreign_keys_consistency_rules(relationships):
            rule_manager.add_rule(rule)

        with ModelTracker(
            data_file_paths=card.get("file_paths", []),
            mostly_config_path=mostly_config_path,
            rules_config_path=rules_config_path,
            pipeline_id=pipeline_id,
            mostly_ai_overrides=effective_overrides,
            job_name=job_name,
            model_id=session.model_id if session else None,
        ) as model_tracker:
            engine = MostlyAIEngine(
                config_path=mostly_config_path,
                config_overrides=effective_overrides,
                run_dir=model_tracker.output_directory,
                local_dir=MOSTLYAI_DIR,
            )

            with profiler.phase(ProfilerPhase.SAVE_METADATA_AND_REPORTS):
                model_tracker.save_training_table_sizes(processed_data)
                model_tracker.save_rule_manager(rule_manager)
                model_tracker.save_metadata(metadata)
                _stamp_inspection_info_on_model_card(
                    output_directory=model_tracker.output_directory,
                    inspection_id=inspection_id,
                    inspection_name=card.get("inspection_name"),
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
    output_directory: str, inspection_id: str, inspection_name: str | None
) -> None:
    """Record the originating inspection details in the model card.

    Args:
        output_directory (str): Path to the model output directory.
        inspection_id (str): ID of the source inspection.
        inspection_name (str | None): Human-readable name of the source inspection.
    """
    card_path = os.path.join(output_directory, MODEL_CARD_FILENAME)
    if not os.path.exists(card_path):
        return
    card = read_json(card_path)
    card["inspection_id"] = inspection_id
    if inspection_name:
        card["inspection_name"] = inspection_name
    write_json(card_path, card, indent=4)
