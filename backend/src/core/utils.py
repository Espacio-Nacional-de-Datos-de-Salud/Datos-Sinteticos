"""Utilities for user interaction, file handling, and encoding types.

Provides helper functions for artifact loading/saving, interactive file
selection, automatic column type detection, and synthesis configuration
management."""

import json
import os
import re
from enum import Enum

import pandas as pd
from backend.src.config.general import (
    METADATA_FILENAME,
)
from backend.src.core.errors import MetadataNotFoundError, RuleManagerNotFoundError
from backend.src.core.logging_config import get_logger
from backend.src.core.preprocessing.logical_rules import LogicalRuleManager

logger = get_logger(__name__)

LAT_LONG_REGEX = re.compile(r"^\s*-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?\s*$")


class ModelEncodingType(str, Enum):
    """Column encoding types supported by the Mostly AI SDK.

    Enumeration of data encoding types for training the synthesis engine.
    Taken from the Mostly AI SDK to avoid unnecessary external dependencies.
    """

    auto = "AUTO"
    tabular_categorical = "TABULAR_CATEGORICAL"
    tabular_numeric_auto = "TABULAR_NUMERIC_AUTO"
    tabular_numeric_discrete = "TABULAR_NUMERIC_DISCRETE"
    tabular_numeric_binned = "TABULAR_NUMERIC_BINNED"
    tabular_numeric_digit = "TABULAR_NUMERIC_DIGIT"
    tabular_character = "TABULAR_CHARACTER"
    tabular_datetime = "TABULAR_DATETIME"
    tabular_datetime_relative = "TABULAR_DATETIME_RELATIVE"
    tabular_lat_long = "TABULAR_LAT_LONG"
    language_text = "LANGUAGE_TEXT"
    language_categorical = "LANGUAGE_CATEGORICAL"
    language_numeric = "LANGUAGE_NUMERIC"
    language_datetime = "LANGUAGE_DATETIME"


def auto_detect_encoding_type(x: pd.Series) -> ModelEncodingType:
    """Automatically detects the most appropriate encoding type for a column.

    Analyzes series values by applying sequential heuristics: detects
    dates, geographic coordinates, unique text vs repeated text, etc. Returns
    the most specific available encoding type.

    Args:
        x (pd.Series): Data series to analyze (may contain null values).

    Returns:
        ModelEncodingType: Most appropriate encoding type for the series.

    Example:
        >>> s = pd.Series(['2023-01-01', '2023-01-02', '2023-01-03'])
        >>> auto_detect_encoding_type(s)
        <ModelEncodingType.tabular_datetime: 'TABULAR_DATETIME'>
    """
    x = x.astype(str)
    x = x[x.str.strip() != ""]  # filter out empty and whitespace-only strings

    # if all values are null or empty, default to categorical
    if len(x) == 0:
        return ModelEncodingType.tabular_categorical

    # if all non-null values can be converted to datetime -> datetime encoding
    if pd.to_datetime(x, errors="coerce").notna().all():
        return ModelEncodingType.tabular_datetime

    # if all values match lat/long pattern -> lat_long (geo) encoding
    if x.str.match(LAT_LONG_REGEX).all():
        return ModelEncodingType.tabular_lat_long

    # if more than 5% of rows contain unique values
    if len(x) >= 100 and x.value_counts().eq(1).reindex(x).mean() > 0.05:
        if (
            x.str.len().nunique() == 1 or x.str.len().max() <= 36
        ):  # if all values are of the same length or shorter than 36 chars -> character encoding
            return ModelEncodingType.tabular_character
        else:  # if values are of different lengths -> text encoding
            return ModelEncodingType.language_text

    return ModelEncodingType.tabular_categorical


def load_metadata(path_run_folder: str) -> dict:
    """Loads metadata from a previous run directory.

    Args:
        path_run_folder (str): Path to the run directory.

    Returns:
        dict: Metadata loaded from JSON.

    Raises:
        FileNotFoundError: Si no existe arquivo metadata.json.

    Example:
        >>> metadata = load_metadata('outputs/training/run_20230101_120000/')
        >>> print(metadata.keys())  # dict_keys(['tables', ...])
    """

    metadata_path = os.path.join(path_run_folder, METADATA_FILENAME)
    if not os.path.exists(metadata_path):
        raise MetadataNotFoundError(f"Metadata file not found at {metadata_path}")
    with open(metadata_path) as f:
        metadata = json.load(f)
    return metadata


def load_rule_manager(path_run_folder: str) -> LogicalRuleManager:
    """Loads RuleManager from a JSON file of a previous run.

    Args:
        path_run_folder (str): Path to the run directory.

    Returns:
        LogicalRuleManager: Loaded rule manager.

    Raises:
        RuleManagerNotFoundError: If ``rule_manager.json`` does not exist. Models
            trained before the JSON cutover (which used ``rule_manager.pkl``)
            must be retrained — pickle loading is no longer supported because
            it allows arbitrary code execution from a tampered file.

    Example:
        >>> rm = load_rule_manager('outputs/training/run_20230101/')
        >>> print(rm.rules)  # [...]
    """
    from backend.src.core.preprocessing.logical_rules_serialization import (
        reconstruct_logical_rule_manager_from_dict,
    )

    rule_manager_path = os.path.join(path_run_folder, "rule_manager.json")
    if not os.path.exists(rule_manager_path):
        legacy_path = os.path.join(path_run_folder, "rule_manager.pkl")
        if os.path.exists(legacy_path):
            raise RuleManagerNotFoundError(
                f"Found legacy '{legacy_path}'; pickle loading is disabled for security. "
                "Retrain the model to regenerate 'rule_manager.json'."
            )
        raise RuleManagerNotFoundError(f"RuleManager file not found at {rule_manager_path}")
    with open(rule_manager_path, encoding="utf-8") as f:
        payload = json.load(f)
    return reconstruct_logical_rule_manager_from_dict(payload)


def delete_empty_folders(root_path: str) -> None:
    """Recursively deletes all empty folders under a path.

    Walks directories from bottom to top to remove empty folders
    after processing their contents.

    Args:
        root_path (str): Root path where empty folders are searched.

    Example:
        >>> delete_empty_folders('outputs/')
    """
    for root, dirs, _ in os.walk(root_path, topdown=False):
        for name in dirs:
            full_path = os.path.join(root, name)

            # Check if the directory is empty
            if not os.listdir(full_path):
                logger.debug("Deleting empty folder: %s", full_path)
                os.rmdir(full_path)


def create_simulation_config(metadata: dict, sample_size: int) -> dict:
    """Generates simulation configuration for the Mostly AI engine.

    Creates a configuration structure with simulation parameters for each table.

    Args:
        metadata (dict): Dictionary with metadata that includes the table list.
        sample_size (int): Number of synthetic records to generate per table.

    Returns:
        dict: Simulation configuration with structure
            {tables: [{name, configuration}, ...]}.

    Example:
        >>> config = create_simulation_config(metadata, sample_size=1000)
        >>> print(config['tables'][0])  # {'name': 'users', 'configuration': {...}}
    """
    simulation_tables = []

    for table_meta in metadata.get("tables", []):
        table_name = table_meta["name"]

        table_configuration = {"sample_size": sample_size, "enable_data_report": False}

        table_entry = {"name": table_name, "configuration": table_configuration}

        simulation_tables.append(table_entry)

    return {"tables": simulation_tables}


def deep_merge(base: dict, overrides: dict) -> dict:
    """Recursively merge *overrides* into a copy of *base*.

    Args:
        base: Base dictionary (not mutated).
        overrides: Values to overlay.

    Returns:
        Merged dictionary.
    """
    merged = base.copy()
    for key, value in overrides.items():
        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged
