from typing import Any

import pandas as pd
from backend.src.core.logging_config import get_logger
from backend.src.core.preprocessing.utils import validate_referential_integrity
from backend.src.core.utils import ModelEncodingType, auto_detect_encoding_type

logger = get_logger(__name__)


class MetadataExtractor:
    """Extracts structural metadata from a set of relational tables.

    Analyzes data to detect structural facts such as table relationships
    (primary and foreign keys) and column encoding types through
    naming heuristics and value analysis, without coupling to any
    specific output format.

    Args:
        data (dict[str, pd.DataFrame]): Dictionary of raw tables with structure
            {table_name: dataframe}.

    Attributes:
        data (dict[str, pd.DataFrame]): Stored raw tables.

    Raises:
        ValueError: If `data` is None or empty.

    Example:
        >>> data = {'users': users_df, 'orders': orders_df}
        >>> extractor = MetadataExtractor(data)
        >>> relationships = extractor.extract_relationships()
        >>> encoding_types = extractor.extract_encoding_types(relationships['pks'])
    """

    def __init__(self, data: dict[str, pd.DataFrame]) -> None:
        """Initializes the metadata extractor with a set of tables.

        Args:
            data (dict[str, pd.DataFrame]): Dictionary with raw tables
                {table_name: dataframe}.
        """
        self.data = data

    def extract_primary_keys(self) -> dict[str, str]:
        """Identifies primary keys in each table using heuristics.

        Applies two sequential strategies: first it searches columns with
        typical PK names (id, {table}_id, etc.), and if no match is found,
        it analyzes all columns to find those with unique values
        without null values. Prints warnings for tables with no detected PK.

        Returns:
            dict[str, str]: Mapping {table_name: pk_column}. Skips tables
                where no PK was detected.
        """
        pks = {}
        for name, df in self.data.items():
            pk = None
            # 1. Heuristic: Name matching
            candidates = [
                c for c in df.columns if c.lower() in ["idx", "id", f"{name}_id", f"{name[:-1]}_id"]
            ]
            for col in candidates:
                if df[col].is_unique and not df[col].hasnans:
                    pk = col
                    break

            # 2. Heuristic: Unique Object/Int check
            if pk is None:
                for col in df.columns:
                    if df[col].dtype.kind in "Oiu":
                        if df[col].is_unique and not df[col].hasnans:
                            pk = col
                            break

            if pk:
                pks[name] = pk
                logger.debug(f"Table '{name}': PK detected -> '{pk}'")
            else:
                logger.error(f"Could not infer PK for table '{name}'")
                logger.warning(
                    "Synthetic data engine requires PK. Consider adding an idx column or ensuring a unique identifier exists."
                )

        return pks

    def extract_foreign_keys(self, pks: dict[str, str]) -> list[dict[str, str]]:
        """Detects foreign-key relationships between tables.

        For each parent table (identified by its PK), it searches foreign-key
        candidates in other tables using naming heuristics. It validates
        each candidate through a referential-integrity check before
        including it in detected relationships. Prints success and
        discards to console during the process.

        Args:
            pks (dict[str, str]): Mapping of detected primary keys
                {table_name: pk_column}.

        Returns:
            list[dict[str, str]]: List of validated relationships, each with:
                {
                    'parent': str parent table name,
                    'child': str child table name,
                    'fk_column': str FK column name in child table,
                    'pk_column': str PK column name in parent table
                }
        """
        relationships = []
        for parent_name, pk in pks.items():
            parent_df = self.data[parent_name]

            # Possible FK names in other tables
            possible_names = {
                pk,
                f"preceding_{pk}",
                f"{parent_name}_{pk}",
                f"{parent_name}_id",
                f"{parent_name[:-1]}_id",
            }

            for child_name, child_df in self.data.items():
                # Allow self-relationships
                # if parent_name == child_name:
                #    continue

                matches = [col for col in child_df.columns if col in possible_names]
                for candidate_fk in matches:
                    if candidate_fk == pk and parent_name == child_name:
                        continue  # Skip if same column in the same table

                    # skip if both are idx
                    if candidate_fk.lower() == "idx" and pk.lower() == "idx":
                        continue

                    is_valid, reason = self._internal_sanity_check_relationship(
                        parent_df, pk, child_df, candidate_fk
                    )
                    if is_valid:
                        relationships.append(
                            {
                                "parent": parent_name,
                                "child": child_name,
                                "fk_column": candidate_fk,
                                "pk_column": pk,  # Storing this helps downstream tools
                            }
                        )
                        logger.info(
                            f"Relationship: {child_name}.{candidate_fk} -> {parent_name}.{pk}"
                        )
                    else:
                        logger.warning(
                            f"Discarded: {child_name}.{candidate_fk} -> {parent_name}.{pk} ({reason})"
                        )
        return relationships

    def extract_encoding_types(
        self, pks: dict[str, str] | None = None
    ) -> dict[str, dict[str, Any]]:
        """Detects encoding types for each column of each table.

        Analyzes each column's content to classify it by encoding type
        (numeric, categorical, etc.) using heuristics based on
        data types and value analysis. If PKs are provided, it excludes them
        from detailed analysis to optimize detection.

        Args:
            pks (dict[str, str] | None, optional): Mapping of primary keys
                {table_name: pk_column}. If None, each column is analyzed
                independently. Defaults to None.

        Returns:
            dict[str, dict[str, Any]]: Hierarchical mapping
                {table_name: {column_name: encoding_type, ...}, ...}
                where encoding_type is a ModelEncodingType.

        Example:
            >>> extractor = MetadataExtractor(data)
            >>> pks = {'users': 'user_id'}
            >>> types = extractor.extract_encoding_types(pks)
        """
        logger.info("--- Detecting encoding types ---")
        types_map = {}
        for name, df in self.data.items():
            # If we know the PK, we avoid analyzing it as a categorical
            table_pk = pks.get(name) if pks else None
            types_map[name] = self._detect_table_types(df, table_pk)
        return types_map

    # --- Internal Detection Logic ---

    def _detect_table_types(self, df: pd.DataFrame, pk_col: str | None = None) -> dict[str, Any]:
        """Detects encoding types for each column in a table.

        Classifies each column as numeric or categorical through initial analysis,
        then applies advanced heuristics to categorical columns (except the PK)
        to identify specific types such as text, date, etc. Excludes the PK
        from detailed analysis for efficiency.

        Args:
            df (pd.DataFrame): DataFrame of the table to analyze.
            pk_col (str | None, optional): Name of the PK column to exclude
                from detailed analysis. Defaults to None.

        Returns:
            dict[str, Any]: Mapping {column_name: ModelEncodingType} for
                each table column.
        """
        col_types = {}
        for col in df.columns:
            # Default heuristic
            if pd.api.types.is_numeric_dtype(df[col]):
                ctype = ModelEncodingType.tabular_numeric_auto
            else:
                ctype = ModelEncodingType.tabular_categorical

            # Refinement: If it's categorical and NOT the PK, inspect deeper
            if ctype == ModelEncodingType.tabular_categorical and col != pk_col:
                ctype = auto_detect_encoding_type(df[col])

            col_types[col] = ctype
        return col_types

    def _internal_sanity_check_relationship(
        self,
        parent_df: pd.DataFrame,
        pk_col: str,
        child_df: pd.DataFrame,
        fk_col: str,
    ) -> tuple[bool, str]:
        """Validates the integrity of a potential foreign-key relationship.

        Performs three validations: data type compatibility between PK and FK,
        orphan check (FK values with no PK match), and referential-integrity
        rate calculation. A relationship is valid if types are
        compatible and the orphan percentage does not exceed 10%.

        Args:
            parent_df (pd.DataFrame): DataFrame of the parent table.
            pk_col (str): Name of the PK column in the parent table.
            child_df (pd.DataFrame): DataFrame of the child table.
            fk_col (str): Name of the FK column in the child table.

        Returns:
            tuple[bool, str]: Tuple (is_valid, message) where:
                - bool: True if the relationship is valid, False otherwise.
                - str: Result description or rejection reason.

        Raises:
            KeyError: If pk_col does not exist in parent_df or fk_col does not exist in child_df.
        """
        if parent_df[pk_col].dtype.kind != child_df[fk_col].dtype.kind:
            return False, "Incompatible types"

        orphan_count, total = validate_referential_integrity(
            parent_df[pk_col], child_df[fk_col].drop_duplicates()
        )

        if total == 0:
            return False, "Empty child column"

        orphan_rate = orphan_count / total
        if orphan_rate > 0.1:
            return False, f"Too many orphans ({orphan_rate:.1%})"
        return True, "OK"
