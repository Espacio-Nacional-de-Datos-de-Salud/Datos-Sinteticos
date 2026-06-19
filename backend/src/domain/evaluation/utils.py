import json
import os
import re

import pandas as pd

try:
    import synthcity.logger as synthcity_log
except ModuleNotFoundError:  # pragma: no cover - exercised when using .venv_core
    synthcity_log = None

from backend.src.domain.evaluation.dtype_alignment import align_dtypes
from backend.src.infrastructure.logging_config import get_logger

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
    if synthcity_log is not None:
        synthcity_log.add(os.path.join(run_directory, "synthcity.log"))
    else:
        logger.debug("Synthcity is not installed; skipping synthcity logger setup.")
    os.environ["SYNTHCITY_WORKSPACE"] = os.path.join(run_directory, "cache")


def _synthetic_table_candidates(table_name: str) -> tuple[str, ...]:
    return (
        table_name,
        f"{table_name}_synthetic",
        table_name.removesuffix("_synthetic"),
    )


def _find_synthetic_table(
    table_name: str, data_synthetic: dict[str, pd.DataFrame]
) -> tuple[str, pd.DataFrame] | None:
    for candidate in _synthetic_table_candidates(table_name):
        if candidate in data_synthetic:
            return candidate, data_synthetic[candidate]
    return None


def align_datasets_structure_and_types(
    data_original: dict[str, pd.DataFrame], data_synthetic: dict[str, pd.DataFrame]
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """Align table names, intersect columns, and homogenize data types.

    Synthetic files are usually named ``<table>_synthetic.csv``. The evaluator
    needs the aligned dictionaries to keep the original table names so
    multitable metrics and user-defined tests can address ``tabla_personas``
    and ``tabla_visitas`` independently.
    """
    if not data_original or not data_synthetic:
        return data_original, data_synthetic

    aligned_original: dict[str, pd.DataFrame] = {}
    aligned_synthetic: dict[str, pd.DataFrame] = {}

    for table_name, original_df in data_original.items():
        synthetic_match = _find_synthetic_table(table_name, data_synthetic)
        if synthetic_match is None:
            logger.warning(
                "Skipping evaluation table '%s': no matching synthetic table found. "
                "Available synthetic tables: %s",
                table_name,
                ", ".join(data_synthetic.keys()),
            )
            continue

        synthetic_name, synthetic_df = synthetic_match
        common_columns = [col for col in original_df.columns if col in synthetic_df.columns]
        if not common_columns:
            logger.warning(
                "Skipping evaluation table '%s': no shared columns with synthetic table '%s'.",
                table_name,
                synthetic_name,
            )
            continue

        aligned_original[table_name] = original_df[common_columns]
        aligned_synthetic[table_name] = synthetic_df[common_columns]

        # Fix type mismatches using the canonical align_dtypes logic
        # (bool→int, int→float, fallback to syn dtype) so booleans like
        # EXPIRE_FLAG are not corrupted into "True"/"False" strings.
        aligned_original[table_name], aligned_synthetic[table_name] = align_dtypes(
            aligned_original[table_name], aligned_synthetic[table_name]
        )

    return aligned_original, aligned_synthetic


def normalize_for_exact_match(
    real_df: pd.DataFrame,
    synthetic_df: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Normalize data for exact matching (e.g., common rows, EMR).

    Handles cases where semantically equivalent values have different
    representations: ``True`` vs ``1``, ``False`` vs ``0``, etc.

    Converts all boolean columns to a canonical form (int: 0/1) so that
    exact matching in synthcity's common_rows_proportion and downstream
    metrics work correctly.

    Args:
        real_df: Real data frame.
        synthetic_df: Synthetic data frame.

    Returns:
        Tuple of normalized (real_df, synthetic_df).
    """
    real_df = real_df
    synthetic_df = synthetic_df

    for col in real_df.columns:
        if col not in synthetic_df.columns:
            continue

        real_has_bool = _is_boolean_like(real_df[col])
        syn_has_bool = _is_boolean_like(synthetic_df[col])
        has_boolean_semantics = _has_boolean_semantics(real_df[col]) or _has_boolean_semantics(
            synthetic_df[col]
        )

        if real_has_bool and syn_has_bool and has_boolean_semantics:
            real_df[col] = _to_canonical_boolean(real_df[col])
            synthetic_df[col] = _to_canonical_boolean(synthetic_df[col])
            logger.debug("Normalized boolean column '%s' to canonical form (0/1)", col)

    return real_df, synthetic_df


def _is_boolean_like(series: pd.Series) -> bool:
    """Check if a series contains boolean-like values."""
    # Check dtype
    if pd.api.types.is_bool_dtype(series):
        return True
    if pd.api.types.is_numeric_dtype(series):
        unique_vals = series.dropna().unique()
        return len(unique_vals) <= 2 and all(v in (0, 1) for v in unique_vals)
    if series.dtype == "object":
        unique_vals = series.dropna().unique()
        normalized_vals = {
            v if isinstance(v, bool) else str(v).strip().lower() for v in unique_vals
        }
        if len(normalized_vals) <= 2:
            return all(
                isinstance(v, bool)
                or v in ("true", "false", "yes", "no", "1", "0")
                or (isinstance(v, (int, float)) and v in (0, 1))
                for v in normalized_vals
            )
    return False


def _has_boolean_semantics(series: pd.Series) -> bool:
    """Return whether a boolean-like series carries explicit boolean semantics."""
    if pd.api.types.is_bool_dtype(series):
        return True
    if series.dtype != "object":
        return False

    unique_vals = series.dropna().unique()
    return any(
        isinstance(v, bool) or str(v).strip().lower() in ("true", "false", "yes", "no")
        for v in unique_vals
    )


def _to_canonical_boolean(series: pd.Series) -> pd.Series:
    """Convert a boolean-like series to canonical form (0/1 as int)."""

    def convert_value(v):
        if pd.isna(v):
            return None
        if isinstance(v, bool):
            return 1 if v else 0
        if isinstance(v, (int, float)):
            return 1 if v else 0
        if isinstance(v, str):
            normalized = v.strip().lower()
            if normalized in ("true", "1", "yes"):
                return 1
            if normalized in ("false", "0", "no"):
                return 0
        return v

    return series.apply(convert_value).astype("Int64")  # nullable int
