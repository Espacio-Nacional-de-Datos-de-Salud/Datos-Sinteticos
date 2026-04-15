"""Training flow service for the synthetic data tool."""

from src.core.errors import (
    DataLoadError,
    RelationshipNotDefinedError,
    TableMetadataMissingError,
)
from src.core.loader import FileDataLoader
from src.core.logging_config import get_logger
from src.core.preprocessing.logical_rules import LogicalRuleManager
from src.core.preprocessing.metadata_formatter import MetadataFormatter
from src.core.preprocessing.preprocessor import DataPreprocessor
from src.core.preprocessing.utils import infer_foreign_keys_consistency_rules
from src.core.rules_config import extract_rules_from_config
from src.core.synthesis import MostlyAIEngine
from src.core.tracking import ModelTracker
from src.services.inspection import load_inspection_artifacts

logger = get_logger(__name__)


def run_training_flow(
    file_paths: list[str],
    mostly_config_path: str,
    rules_config_path: str,
    enable_data_profiling: bool,
    csv_delimiter: str = ",",
    mostly_ai_overrides: dict | None = None,
    pipeline_id: str = "none",
    job_name: str | None = None,
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
    try:
        with ModelTracker(
            data_file_paths=file_paths,
            mostly_config_path=mostly_config_path,
            rules_config_path=rules_config_path,
            pipeline_id=pipeline_id,
            mostly_ai_overrides=mostly_ai_overrides,
            job_name=job_name,
        ) as model_tracker:
            engine = MostlyAIEngine(
                config_path=mostly_config_path,
                config_overrides=mostly_ai_overrides,
                run_dir=model_tracker.output_directory,
            )

            raw_data = FileDataLoader().load(file_paths, sep=csv_delimiter)
            preprocessor = DataPreprocessor(raw_data)

            for rule in extract_rules_from_config(rules_config_path):
                preprocessor.rule_manager.add_rule(rule)

            processed_data, metadata, rule_manager, data_profiles = preprocessor.run(
                run_data_profiling=enable_data_profiling
            )

            model_tracker.save_training_table_sizes(processed_data)
            model_tracker.save_rule_manager(rule_manager)
            model_tracker.save_metadata(metadata)
            if data_profiles:
                model_tracker.save_data_profiles(data_profiles)

            generator = engine.train(processed_data, metadata)
            model_tracker.save_generator(generator)
            model_tracker.save_qa_reports(generator.id)
            model_tracker.save_mostly_statistics(generator.id)

            return model_tracker.model_id, generator, metadata, rule_manager

    except (DataLoadError, TableMetadataMissingError, RelationshipNotDefinedError) as error:
        logger.error("Train flow failed: %s", error)
        return None, None, None, None


def run_training_flow_from_inspection(
    inspection_id: str,
    mostly_ai_overrides: dict | None = None,
    pipeline_id: str = "none",
    job_name: str | None = None,
) -> tuple[str | None, object | None, object | None, object | None]:
    """Train directly from a previously produced inspection session.

    Reuses the processed tables cached as parquet by ``run_inspection_flow``.
    ``autodetect.json`` is the **single source of truth**: the engine metadata
    is regenerated from it at training time via ``MetadataFormatter`` so any
    manual edits to relationships or encoding types take effect. The
    pre-existing ``metadata.json`` in the inspection folder is a preview and
    is intentionally ignored here. The rule manager is rebuilt from
    ``rules_config_path`` plus the FK consistency rules inferred from the
    current autodetect relationships.

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
    try:
        card, processed_data, _preview_metadata, autodetect = load_inspection_artifacts(
            inspection_id
        )

        mostly_config_path = card["mostly_config_path"]
        rules_config_path = card["rules_config_path"]
        effective_overrides = (
            mostly_ai_overrides
            if mostly_ai_overrides is not None
            else card.get("mostly_ai_overrides") or None
        )

        relationships = autodetect.get("relationships", {"pks": {}, "fks": []})
        encoding_types = autodetect.get("encoding_types", {})
        metadata = MetadataFormatter(engine_name="mostly").format(
            data_dfs=processed_data,
            relationships_data=relationships,
            types_data=encoding_types,
        )

        rule_manager = LogicalRuleManager()
        for rule in extract_rules_from_config(rules_config_path):
            rule_manager.add_rule(rule)
        for rule in infer_foreign_keys_consistency_rules(relationships):
            rule_manager.add_rule(rule)

        with ModelTracker(
            data_file_paths=card.get("file_paths", []),
            mostly_config_path=mostly_config_path,
            rules_config_path=rules_config_path,
            pipeline_id=pipeline_id,
            mostly_ai_overrides=effective_overrides,
            job_name=job_name,
        ) as model_tracker:
            engine = MostlyAIEngine(
                config_path=mostly_config_path,
                config_overrides=effective_overrides,
                run_dir=model_tracker.output_directory,
            )

            model_tracker.save_training_table_sizes(processed_data)
            model_tracker.save_rule_manager(rule_manager)
            model_tracker.save_metadata(metadata)
            _stamp_inspection_info_on_model_card(
                output_directory=model_tracker.output_directory,
                inspection_id=inspection_id,
                inspection_name=card.get("inspection_name"),
            )

            generator = engine.train(processed_data, metadata)
            model_tracker.save_generator(generator)
            model_tracker.save_qa_reports(generator.id)
            model_tracker.save_mostly_statistics(generator.id)

            return model_tracker.model_id, generator, metadata, rule_manager

    except (
        FileNotFoundError,
        DataLoadError,
        TableMetadataMissingError,
        RelationshipNotDefinedError,
    ) as error:
        logger.error("Train-from-inspection flow failed: %s", error)
        return None, None, None, None


def _stamp_inspection_info_on_model_card(
    output_directory: str, inspection_id: str, inspection_name: str | None
) -> None:
    """Record the originating inspection details in the model card."""
    import json
    import os

    from config.general_config import MODEL_CARD_FILENAME

    card_path = os.path.join(output_directory, MODEL_CARD_FILENAME)
    if not os.path.exists(card_path):
        return
    with open(card_path, encoding="utf-8") as handle:
        card = json.load(handle)
    card["inspection_id"] = inspection_id
    if inspection_name:
        card["inspection_name"] = inspection_name
    with open(card_path, "w", encoding="utf-8") as handle:
        json.dump(card, handle, indent=4)
