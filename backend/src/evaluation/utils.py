import json
import os
import re

import pandas as pd
import synthcity.logger as log
from backend.src.core.logging_config import get_logger

logger = get_logger(__name__)


def get_id_columns(data: pd.DataFrame, metadata_path: str | None = None) -> list[str]:
    """Identify ID columns to exclude from evaluation.

    ID columns are identified by:
    1. Column names matching patterns like 'id', 'idk', '*_id', 'id_*' (case-insensitive)
    2. Columns listed as primary keys in metadata.json
    3. Columns listed as foreign keys in metadata.json

    Args:
        data (pd.DataFrame): Dataset to analyze.
        metadata_path (str | None): Path to metadata.json. If None, key constraints are not checked.

    Returns:
        list[str]: List of column names to exclude.
    """
    id_columns = []

    # Pattern matching for ID-like column names
    id_pattern = re.compile(r"^id|_id$|^idk$|_idk$", re.IGNORECASE)
    for col in data.columns:
        if id_pattern.search(col):
            id_columns.append(col)
            logger.debug(f"Identified ID column by name pattern: {col}")

    # Load metadata to check for primary/foreign keys
    if metadata_path and os.path.exists(metadata_path):
        try:
            with open(metadata_path) as f:
                metadata = json.load(f)

            tables = metadata.get("tables", [])
            for table in tables:
                # Check primary keys
                primary_key = table.get("primary_key")
                if primary_key:
                    if isinstance(primary_key, str):
                        if primary_key in data.columns and primary_key not in id_columns:
                            id_columns.append(primary_key)
                            logger.debug(f"Identified primary key column: {primary_key}")
                    elif isinstance(primary_key, list):
                        for pk in primary_key:
                            if pk in data.columns and pk not in id_columns:
                                id_columns.append(pk)
                                logger.debug(f"Identified primary key column: {pk}")

                # Check foreign keys
                foreign_keys = table.get("foreign_keys", [])
                for fk in foreign_keys:
                    if isinstance(fk, str) and fk in data.columns and fk not in id_columns:
                        id_columns.append(fk)
                        logger.debug(f"Identified foreign key column: {fk}")
                    elif isinstance(fk, dict):
                        fk_col = fk.get("column")
                        if fk_col and fk_col in data.columns and fk_col not in id_columns:
                            id_columns.append(fk_col)
                            logger.debug(f"Identified foreign key column: {fk_col}")

        except Exception as e:
            logger.warning(f"Failed to load metadata from {metadata_path}: {e}")

    return id_columns


def filter_id_columns(data: pd.DataFrame, metadata_path: str | None = None) -> pd.DataFrame:
    """Remove ID columns from dataset.

    Args:
        data (pd.DataFrame): Dataset to filter.
        metadata_path (str | None): Path to metadata.json file.

    Returns:
        pd.DataFrame: Dataset with ID columns removed.
    """
    id_columns = get_id_columns(data, metadata_path)
    if id_columns:
        logger.info(f"Removing ID columns from evaluation: {id_columns}")
        data = data.drop(columns=id_columns, errors="ignore")
    return data


def setup_synthcity_environment(run_directory: str) -> None:
    """Configure Synthcity to use the run directory for logs and cache.

    Args:
        run_directory (str): Run directory path.

    Returns:
        None: Function configures process environment in place.

    Example:
        >>> setup_synthcity_environment("/outputs/simulation/run_20260206_132709")
    """
    log.add(os.path.join(run_directory, "synthcity.log"))
    os.environ["SYNTHCITY_WORKSPACE"] = os.path.join(run_directory, "cache")


def align_datasets_structure_and_types(
    data_original: dict[str, pd.DataFrame], data_synthetic: dict[str, pd.DataFrame]
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Align table names, intersect columns, and homogenize data types.

    Args:
        data_original (dict[str, pd.DataFrame]): Original tables.
        data_synthetic (dict[str, pd.DataFrame]): Synthetic tables.

    Returns:
        tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]: Aligned dictionaries
            for original and synthetic data.

    Example:
        >>> orig, synth = align_datasets_structure_and_types({"t": df1}, {"t": df2})
        >>> list(orig["t"].columns) == list(synth["t"].columns)
        True
    """
    # 1. Unify Dictionary Keys (Table Names)
    # We force both dicts to use the name of the first original table to ensure matching
    if not data_original or not data_synthetic:
        return data_original, data_synthetic

    primary_table_name = next(iter(data_original))

    # We create new dictionaries pointing to the dataframes
    aligned_original = {primary_table_name: df for df in data_original.values()}  # noqa: B035
    aligned_synthetic = {primary_table_name: df for df in data_synthetic.values()}  # noqa: B035

    # 2. Intersect Columns (Keep only shared columns)
    cols_original = set(aligned_original[primary_table_name].columns)
    cols_synthetic = set(aligned_synthetic[primary_table_name].columns)
    common_columns = list(cols_original.intersection(cols_synthetic))

    # 3. Filter Columns and Fix Data Types
    for table in aligned_original.keys():
        # Filter columns AND CREATE A COPY to avoid SettingWithCopyError
        # This .copy() is the critical fix
        aligned_original[table] = aligned_original[table][common_columns].copy()
        aligned_synthetic[table] = aligned_synthetic[table][common_columns].copy()

        # Fix Type Mismatches (e.g., int vs str)
        for col in common_columns:
            dtype_orig = aligned_original[table][col].dtype
            dtype_syn = aligned_synthetic[table][col].dtype

            if dtype_orig != dtype_syn:
                logger.info(
                    "Aligning types for '%s' column '%s': %s vs %s -> str",
                    table,
                    col,
                    dtype_orig,
                    dtype_syn,
                )
                aligned_original[table][col] = aligned_original[table][col].astype(str)
                aligned_synthetic[table][col] = aligned_synthetic[table][col].astype(str)

    return aligned_original, aligned_synthetic
