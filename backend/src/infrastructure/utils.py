"""Utilities for user interaction, file handling, and encoding types.

Provides helper functions for artifact loading/saving, interactive file
selection, automatic column type detection, and synthesis configuration
management."""

import json
import os
import re

import pandas as pd

from backend.src.config.general import (
    METADATA_FILENAME,
)
from backend.src.domain.encoding_types import ModelEncodingType
from backend.src.domain.preprocessing.logical_rules import LogicalRuleManager
from backend.src.infrastructure.date_parsing import parse_dates
from backend.src.infrastructure.errors import MetadataNotFoundError, RuleManagerNotFoundError
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)

LAT_LONG_REGEX = re.compile(r"^\s*-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?\s*$")

# Columns ending in ``_concept_id`` are OMOP vocabulary codes: identifiers that
# point into the (usually un-loaded) ``concept`` table, NOT magnitudes. Their
# integer dtype is incidental — modelled as numeric they get interpolated into
# values like 4001234.7 that map to no real concept. Treat them as categorical
# codes regardless of dtype (the user can still override per column in the UI).
CODE_IDENTIFIER_REGEX = re.compile(r"_concept_id$", re.IGNORECASE)

# ``ModelEncodingType`` now lives in ``backend.src.domain.encoding_types``; it is
# imported above both because this module uses it and so existing
# ``from backend.src.infrastructure.utils import ModelEncodingType`` imports keep
# working.


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
    # Booleans and 2-value binary flags are STATES, not magnitudes — never
    # treat them as numeric. MostlyAI has no native bool type, so categorical
    # is the closest semantic match (model uses softmax over the 2 classes
    # and learns P(state | covariates) instead of optimising L2 distance).
    if pd.api.types.is_bool_dtype(x):
        return ModelEncodingType.tabular_categorical
    non_null = x.dropna()
    if len(non_null) > 0 and non_null.nunique() <= 2:
        return ModelEncodingType.tabular_categorical

    # Drop nulls BEFORE stringifying: astype(str) turns NaN/NaT into the
    # literal strings "nan"/"NaT", which fail the datetime parse below and
    # would misclassify any datetime column containing nulls as character.
    x = x.dropna().astype(str)
    x = x[x.str.strip() != ""]  # filter out empty and whitespace-only strings

    # if all values are null or empty, default to categorical
    if len(x) == 0:
        return ModelEncodingType.tabular_categorical

    # if all non-null values can be converted to datetime -> datetime encoding
    if parse_dates(x, errors="coerce", log_warnings=False).notna().all():
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


def detect_series_encoding(
    series: pd.Series, *, refine: bool = True, column_name: str | None = None
) -> ModelEncodingType:
    """Detect the encoding type for a single column from its values and dtype.

    Columns whose name marks them as code identifiers (e.g. OMOP ``*_concept_id``
    vocabulary codes) stay categorical regardless of dtype — see
    :data:`CODE_IDENTIFIER_REGEX`. Booleans and 2-value binary flags are states,
    not magnitudes, so they stay categorical too. Numeric dtypes map to
    numeric-auto; the rest go through :func:`auto_detect_encoding_type` unless
    ``refine`` is False (used for PK columns, which skip the deeper heuristics).
    """
    if column_name is not None and CODE_IDENTIFIER_REGEX.search(column_name):
        return ModelEncodingType.tabular_categorical
    non_null = series.dropna()
    if pd.api.types.is_bool_dtype(series) or (len(non_null) > 0 and non_null.nunique() <= 2):
        return ModelEncodingType.tabular_categorical
    if pd.api.types.is_numeric_dtype(series):
        return ModelEncodingType.tabular_numeric_auto
    if refine:
        return auto_detect_encoding_type(series)
    return ModelEncodingType.tabular_categorical


INCOMPATIBLE_MIX_MIN_NUMERIC_FRACTION = 0.2


def detect_incompatible_type_mix(
    x: pd.Series, min_numeric_fraction: float = INCOMPATIBLE_MIX_MIN_NUMERIC_FRACTION
) -> dict | None:
    """Flag columns that mix free text and pure numbers in incompatible amounts.

    These columns have no clean encoding. Routed to a language model (which is
    what :func:`auto_detect_encoding_type` picks for free text) they crash Mostly
    AI's report generation with a primary-key dtype mismatch
    (``float64`` vs ``object``) across partitions; routed to numeric/categorical
    they silently drop half the information. Rather than guess how to split such a
    column, the caller excludes it and warns the user.

    Detection is intentionally narrow: only columns that would be modeled as free
    text *and* whose values are numeric in at least ``min_numeric_fraction`` are
    flagged. Pure-text columns and short-code categoricals are left untouched.

    Args:
        x: Column to analyse (may contain nulls).
        min_numeric_fraction: Minimum share of non-null values that must parse as
            numbers for the column to count as a mix.

    Returns:
        A summary dict (``numeric_fraction``, ``text_fraction``, ``text_samples``)
        when the column is an incompatible mix; otherwise ``None``.
    """
    if auto_detect_encoding_type(x) != ModelEncodingType.language_text:
        return None

    values = x.dropna().astype(str).str.strip()
    values = values[values != ""]
    if len(values) == 0:
        return None

    numeric_mask = pd.to_numeric(values, errors="coerce").notna()
    numeric_fraction = float(numeric_mask.mean())
    if numeric_fraction < min_numeric_fraction:
        return None

    return {
        "numeric_fraction": round(numeric_fraction, 4),
        "text_fraction": round(1.0 - numeric_fraction, 4),
        "text_samples": values[~numeric_mask].drop_duplicates().head(5).tolist(),
    }


# Columns missing at least this share of their values are flagged for attention.
# 0.40 follows Jakobsen et al. (2017): above ~40% missing, a variable's results are
# "hypothesis-generating only". It is a *warning* threshold, not a drop threshold —
# the column is kept and the user decides what to do.
HIGH_NULL_FRACTION_WARNING_THRESHOLD = 0.40


def detect_high_null_fraction(
    x: pd.Series, threshold: float = HIGH_NULL_FRACTION_WARNING_THRESHOLD
) -> dict | None:
    """Flag columns whose missing (null/blank) share meets or exceeds ``threshold``.

    High missingness is not fatal for synthesis (Mostly AI models nulls natively),
    but it (a) can derail naive type auto-detection — e.g. a heavily right-censored
    date column falling back to character encoding — and (b) degrades the utility of
    the synthetic column. Detection is purely informational and non-destructive: the
    column stays in the schema and is surfaced as a warning so the user can review
    the auto-detected type and decide whether to continue or clean the data
    themselves. Nothing is excluded or transformed automatically.

    "Missing" counts true nulls plus empty/whitespace-only strings, so textual blanks
    are treated the same as ``NaN``.

    Args:
        x: Column to analyse.
        threshold: Minimum missing fraction (0–1) that triggers the flag.

    Returns:
        A summary dict (``null_fraction``, ``threshold``) when the column meets the
        threshold; otherwise ``None``.
    """
    total = len(x)
    if total == 0:
        return None

    is_null = x.isna()
    is_blank_str = x.astype(str).str.strip().eq("") & ~is_null
    null_fraction = float((is_null | is_blank_str).mean())
    if null_fraction < threshold:
        return None

    return {
        "null_fraction": round(null_fraction, 4),
        "threshold": threshold,
    }


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
    from backend.src.domain.preprocessing.logical_rules_serialization import (
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


def _is_subject_table(table_meta: dict) -> bool:
    """A subject table has no ``is_context`` foreign key.

    Mostly AI's SDK only honors ``sample_size`` for subject tables; for context
    children it forces ``sample_size`` to ``None`` and cascades counts from the
    parent (see ``mostlyai.sdk.domain.SyntheticTableConfig._maybe_set_sample_size``).
    """
    return not any(fk.get("is_context") for fk in (table_meta.get("foreign_keys") or []))


def create_simulation_config(
    metadata: dict,
    sample_size: int | None = None,
    table_sample_sizes: dict[str, int] | None = None,
) -> dict:
    """Generates simulation configuration for the Mostly AI engine.

    Only subject tables (no ``is_context`` FK) receive ``sample_size``. Mostly AI
    silently drops it on context children and generates them cascading from their
    parent (the SDK's ``_maybe_set_sample_size`` forces ``sample_size = None`` for
    non-subjects). Per-table overrides targeting context children are accepted by
    the API for forward-compatibility but ignored here, with a warning logged so
    operators see they had no effect.

    Args:
        metadata: Dictionary with metadata that includes the table list.
        sample_size: Fallback row count applied to subject tables when no
            per-table override is provided.
        table_sample_sizes: Per-table overrides; only entries targeting subject
            tables affect this config.

    Returns:
        dict: Simulation configuration ``{tables: [{name, configuration}, ...]}``.
    """
    simulation_tables = []
    ignored_non_subject: list[str] = []

    for table_meta in metadata.get("tables", []):
        table_name = table_meta["name"]
        table_configuration = {"enable_data_report": False}

        if _is_subject_table(table_meta):
            t_size = sample_size
            if table_sample_sizes and table_name in table_sample_sizes:
                t_size = table_sample_sizes[table_name]
            if t_size is not None:
                table_configuration["sample_size"] = t_size
        elif table_sample_sizes and table_name in table_sample_sizes:
            ignored_non_subject.append(table_name)

        simulation_tables.append({"name": table_name, "configuration": table_configuration})

    if ignored_non_subject:
        logger.warning(
            "Ignoring per-table sample_size for context-child tables %s; Mostly AI "
            "cascades their counts from the parent and cannot honor explicit sizes.",
            ignored_non_subject,
        )

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
