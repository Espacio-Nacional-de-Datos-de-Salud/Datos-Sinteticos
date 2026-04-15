"""Inspection flow service.

Runs load + preprocessing + autodetection and persists the results to a
session directory so the user can review (and optionally edit) the
autodetected metadata before launching training. Mirrors the shape of
``run_training_flow`` but stops right before ``engine.train``.

Session layout under ``outputs/inspections/inspection_<ts>/``:
    - inspection_card.json  Session descriptor and summary. Holds the reproducible
                            inputs (file paths, config paths, overrides) plus the
                            user-facing fields (``inspection_name``, ``tables``).
                            Rename the session by editing ``inspection_name`` here.
    - autodetect.json       **Single source of truth** for PKs/FKs and encoding types.
                            Editing this file changes what training will consume.
    - metadata.json         Engine-ready preview derived from autodetect.json. Only
                            for inspection; it is regenerated at training time from
                            autodetect.json so manual edits here have no effect.
    - processed_data/*.parquet  Preprocessed tables cached to skip re-preprocessing.
"""

import json
import os
from dataclasses import dataclass

import pandas as pd
from config.general_config import (
    AUTODETECT_FILENAME,
    INSPECTION_CARD_FILENAME,
    INSPECTION_RUN_FOLDER_PREFIX,
    INSPECTIONS_DIR,
    METADATA_FILENAME,
    PROCESSED_DATA_DIRNAME,
    get_run_timestamp,
)

from src.core.errors import (
    DataLoadError,
    RelationshipNotDefinedError,
    TableMetadataMissingError,
)
from src.core.loader import FileDataLoader
from src.core.logging_config import get_logger
from src.core.preprocessing.preprocessor import DataPreprocessor
from src.core.rules_config import extract_rules_from_config

logger = get_logger(__name__)

PREVIEW_METADATA_DISCLAIMER = (
    "This file is a preview only. Edits here will have no effect; "
    "make changes in autodetect.json instead."
)


@dataclass(frozen=True)
class InspectionResult:
    """Summary of an inspection session ready for user review."""

    inspection_id: str
    inspection_name: str
    output_directory: str
    tables: dict[str, int]
    relationships: dict
    encoding_types: dict


def run_inspection_flow(
    file_paths: list[str],
    mostly_config_path: str,
    rules_config_path: str,
    enable_data_profiling: bool,
    csv_delimiter: str = ",",
    mostly_ai_overrides: dict | None = None,
) -> InspectionResult | None:
    """Load, preprocess and autodetect metadata; persist session for later training.

    ``file_paths`` are the same raw inputs the current train flow uses (driven
    by ``FILE_PATHS`` in ``config/execution_config.py`` when invoked from the
    CLI). They are loaded with ``FileDataLoader`` and fed through
    ``DataPreprocessor``; the outputs are cached under the session directory
    so the subsequent training run can skip preprocessing.

    Args:
        file_paths: Paths to input data files or directories.
        mostly_config_path: Path to the Mostly AI configuration file.
        rules_config_path: Path to the logical rules configuration file.
        enable_data_profiling: Whether to run data profiling during preprocessing.
        csv_delimiter: Parsing delimiter. Defaults to ",".
        mostly_ai_overrides: Specific engine overrides to persist for later training.

    Returns:
        InspectionResult with ``inspection_id`` and autodetected artefacts,
        or ``None`` on failure.
    """
    try:
        inspection_id = f"{INSPECTION_RUN_FOLDER_PREFIX}_{get_run_timestamp()}"
        output_directory = os.path.join(INSPECTIONS_DIR, inspection_id)
        processed_data_dir = os.path.join(output_directory, PROCESSED_DATA_DIRNAME)
        os.makedirs(processed_data_dir, exist_ok=True)
        logger.info("Created inspection output directory: %s", output_directory)

        raw_data = FileDataLoader().load(file_paths, sep=csv_delimiter)
        preprocessor = DataPreprocessor(raw_data)

        for rule in extract_rules_from_config(rules_config_path):
            preprocessor.rule_manager.add_rule(rule)

        processed_data, metadata, _rule_manager, _profiles = preprocessor.run(
            run_data_profiling=enable_data_profiling
        )

        for table_name, df in processed_data.items():
            df.to_parquet(os.path.join(processed_data_dir, f"{table_name}.parquet"))

        table_sizes = {name: int(len(df)) for name, df in processed_data.items()}

        card = {
            "inspection_id": inspection_id,
            "inspection_name": inspection_id,
            "timestamp": get_run_timestamp(),
            "tables": table_sizes,
            "file_paths": list(file_paths),
            "mostly_config_path": mostly_config_path,
            "rules_config_path": rules_config_path,
            "enable_data_profiling": enable_data_profiling,
            "csv_delimiter": csv_delimiter,
            "mostly_ai_overrides": mostly_ai_overrides or {},
        }
        _write_json(os.path.join(output_directory, INSPECTION_CARD_FILENAME), card)
        preview_metadata = {"disclaimer": PREVIEW_METADATA_DISCLAIMER, **metadata}
        _write_json(os.path.join(output_directory, METADATA_FILENAME), preview_metadata)
        _write_json(
            os.path.join(output_directory, AUTODETECT_FILENAME),
            {
                "relationships": preprocessor.relationships,
                "encoding_types": preprocessor.encoding_types,
            },
        )

        logger.info(
            "Inspection session saved: %s (tables=%s).",
            inspection_id,
            list(table_sizes),
        )

        return InspectionResult(
            inspection_id=inspection_id,
            inspection_name=inspection_id,
            output_directory=output_directory,
            tables=table_sizes,
            relationships=preprocessor.relationships,
            encoding_types=preprocessor.encoding_types,
        )

    except (DataLoadError, TableMetadataMissingError, RelationshipNotDefinedError) as error:
        logger.error("Inspection flow failed: %s", error)
        return None


def load_inspection_artifacts(
    inspection_id: str,
) -> tuple[dict, dict[str, pd.DataFrame], dict, dict]:
    """Load card, processed data, engine metadata and autodetect info.

    Args:
        inspection_id: Folder name produced by ``run_inspection_flow``.

    Returns:
        Tuple (card, processed_data, metadata, autodetect).
    """
    output_directory = os.path.join(INSPECTIONS_DIR, inspection_id)
    if not os.path.isdir(output_directory):
        raise FileNotFoundError(f"Inspection not found: {output_directory}")

    card = _read_json(os.path.join(output_directory, INSPECTION_CARD_FILENAME))
    metadata = _read_json(os.path.join(output_directory, METADATA_FILENAME))
    autodetect = _read_json(os.path.join(output_directory, AUTODETECT_FILENAME))

    processed_dir = os.path.join(output_directory, PROCESSED_DATA_DIRNAME)
    processed_data: dict[str, pd.DataFrame] = {}
    for filename in sorted(os.listdir(processed_dir)):
        if filename.endswith(".parquet"):
            table_name = os.path.splitext(filename)[0]
            processed_data[table_name] = pd.read_parquet(os.path.join(processed_dir, filename))

    return card, processed_data, metadata, autodetect


def _write_json(path: str, payload: dict) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False, default=str)


def _read_json(path: str) -> dict:
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)
