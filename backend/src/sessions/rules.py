"""Rules stage for inspection sessions."""

import os
import shutil

import pandas as pd

from backend.src.config.general import (
    INSPECTION_CARD_FILENAME,
    INSPECTION_METADATA_FILENAME,
    INSPECTIONS_DIR,
    PROCESSED_DATA_DIRNAME,
)
from backend.src.domain.preprocessing.logical_rules import LogicalRuleManager
from backend.src.domain.preprocessing.logical_rules_serialization import (
    serialize_logical_rule_manager_to_dict,
)
from backend.src.domain.preprocessing.utils import format_relationships
from backend.src.domain.rules_config import extract_rules_and_rejection_config
from backend.src.infrastructure.logging_config import get_logger
from backend.src.runs.card_io import read_json, write_json

logger = get_logger(__name__)

RULES_SNAPSHOT_FILENAME = "rules_snapshot.yaml"
INSPECTION_RULE_MANAGER_FILENAME = "inspection_rule_manager.json"


def _snapshot_rules_file(rules_config_path: str, output_directory: str) -> str:
    """Freeze the rules YAML inside the inspection folder.

    Subsequent steps can then show the rules actually applied to the
    preprocessed dataset, even if the user later edits the global file.
    Falls back to the original path if the copy fails.
    """
    snapshot_path = os.path.join(output_directory, RULES_SNAPSHOT_FILENAME)
    try:
        shutil.copyfile(rules_config_path, snapshot_path)
        return snapshot_path
    except OSError as copy_error:
        logger.warning("Could not snapshot rules file: %s", copy_error)
        return rules_config_path


def resolve_inspection_rules_config_path(
    inspection_id: str,
    card: dict | None = None,
    inspections_dir: str | None = None,
) -> str:
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
    base_dir = inspections_dir or INSPECTIONS_DIR
    output_directory = os.path.join(base_dir, inspection_id)
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


def apply_inspection_rules(
    inspection_id: str,
    rules_config_path: str | None = None,
    inspections_dir: str | None = None,
) -> dict:
    """Build and persist the logical rule manager for an inspection.

    Loads the inspection metadata, resolves the rules configuration, and
    serializes the resulting ``LogicalRuleManager`` into the inspection
    folder. Applies PRE phase of rules.

    Args:
        inspection_id: Folder name produced by ``run_inspection_flow``.
        rules_config_path: Optional override for the rules YAML path.

    Returns:
        dict with ``inspection_id``, ``rules_config_path`` and ``rules_count``.

    Raises:
        FileNotFoundError: If the inspection folder or metadata file is missing.
    """
    base_dir = inspections_dir or INSPECTIONS_DIR
    output_directory = os.path.join(base_dir, inspection_id)
    if not os.path.isdir(output_directory):
        raise FileNotFoundError(f"Inspection not found: {output_directory}")

    card_path = os.path.join(output_directory, INSPECTION_CARD_FILENAME)
    if not os.path.exists(card_path):
        raise FileNotFoundError(f"Inspection card not found: {card_path}")

    inspection_metadata_path = os.path.join(output_directory, INSPECTION_METADATA_FILENAME)
    if not os.path.exists(inspection_metadata_path):
        raise FileNotFoundError(f"Inspection metadata not found: {inspection_metadata_path}")

    processed_dir = os.path.join(output_directory, PROCESSED_DATA_DIRNAME)
    if not os.path.isdir(processed_dir):
        raise FileNotFoundError(f"Processed data directory not found: {processed_dir}")

    card = read_json(card_path)
    inspection_metadata = read_json(inspection_metadata_path)
    relationships = inspection_metadata.get("relationships", {"pks": {}, "fks": []})

    resolved_rules_path = rules_config_path
    if resolved_rules_path:
        resolved_rules_path = _snapshot_rules_file(resolved_rules_path, output_directory)
        card["rules_config_path"] = resolved_rules_path
        write_json(card_path, card)
    else:
        resolved_rules_path = resolve_inspection_rules_config_path(inspection_id, card)

    formatted_relationships = format_relationships(relationships)
    rule_manager = LogicalRuleManager()
    rule_manager.relationships = formatted_relationships
    rules, rejection_config = extract_rules_and_rejection_config(resolved_rules_path)
    for rule in rules:
        rule_manager.add_rule(rule)
    rule_manager.rejection_sampling_config = rejection_config.as_dict()

    processed_data: dict[str, pd.DataFrame] = {}
    for filename in sorted(os.listdir(processed_dir)):
        if filename.endswith(".parquet"):
            table_name = os.path.splitext(filename)[0]
            processed_data[table_name] = pd.read_parquet(os.path.join(processed_dir, filename))

    processed_with_rules = rule_manager.apply_all_pre(
        processed_data, relationships=formatted_relationships
    )

    for table_name, df in processed_with_rules.items():
        df.to_parquet(os.path.join(processed_dir, f"{table_name}.parquet"))

    rule_manager_path = os.path.join(output_directory, INSPECTION_RULE_MANAGER_FILENAME)
    write_json(rule_manager_path, serialize_logical_rule_manager_to_dict(rule_manager), indent=2)

    return {
        "inspection_id": inspection_id,
        "rules_config_path": resolved_rules_path,
        "rules_count": len(rule_manager.rules),
    }
