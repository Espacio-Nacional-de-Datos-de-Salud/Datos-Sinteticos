from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.utils import ModelEncodingType

logger = get_logger(__name__)


class MetadataFormatter:
    """Converts extracted metadata to the format expected by the synthesis engine.

    Transforms table, column, type, and relationship information into a
    specific JSON structure that the engine interprets to configure synthetic generation.

    Args:
        engine_name (str): Engine name ('mostly' or another one). Defaults to \"mostly\".
    """

    def __init__(self, engine_name: str = "mostly") -> None:
        """Initializes the metadata formatter for a specific engine.

        Args:
            engine_name (str): Engine name. Defaults to \"mostly\".
        """
        self.engine_name = engine_name

    def format(
        self,
        data_dfs: dict,
        relationships_data: dict | None = None,
        types_data: dict | None = None,
    ) -> dict:
        """Formats metadata in the structure expected by the synthesis engine.

        Organizes table, column, data type, and relationship information
        into a JSON format that the engine interprets to configure generation.

        Args:
            data_dfs (dict[str, pd.DataFrame]): Processed DataFrames.
            relationships_data (dict | None): Detected PKs and FKs. Defaults to None.
            types_data (dict | None): Column encoding types. Defaults to None.

        Returns:
            dict: Formatted metadata {tables: [{name, columns, foreign_keys, ...}, ...]}.

        Example:
            >>> formatter = MetadataFormatter()
            >>> metadata = formatter.format(data_dict, relationships, types)
        """

        logger.info("--- Formatting metadata ---")

        relationships_data = relationships_data or {"pks": {}, "fks": []}
        types_data = types_data or {}

        tables_config = []

        for name, df in data_dfs.items():
            # A. Prepare Columns
            cols_config = []
            t_types = types_data.get(name, {})

            for col in df.columns:
                ctype = t_types.get(col, ModelEncodingType.tabular_categorical)
                cols_config.append({"name": col, "model_encoding_type": ctype})

            # B. Prepare FKs
            # Filter raw relationships where child == current table
            table_fks = []
            raw_fks = [
                rel
                for rel in relationships_data["fks"]
                if rel["child"] == name and rel["fk_column"] in df.columns
            ]

            for rel in raw_fks:
                table_fks.append(
                    {
                        "column": rel["fk_column"],
                        "referenced_table": rel["parent"],
                        "is_context": bool(rel.get("is_context", False)),
                        "direct": bool(rel.get("direct", False)),
                    }
                )

            # C. Assemble Table
            table_def = {"name": name, "columns": cols_config, "foreign_keys": table_fks}

            pk = relationships_data["pks"].get(name)
            if pk:
                table_def["primary_key"] = pk

            tables_config.append(table_def)

        formatted_metadata = {"tables": tables_config}
        return formatted_metadata
