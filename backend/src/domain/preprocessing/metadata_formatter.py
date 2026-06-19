from backend.src.domain.encoding_types import (
    EncodingTypeMapper,
    get_encoding_type_mapper,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.utils import detect_series_encoding

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

        Dispatches to the engine-specific formatter selected by ``engine_name``.
        Organizes table, column, data type, and relationship information into the
        JSON format that engine interprets to configure generation.

        Args:
            data_dfs (dict[str, pd.DataFrame]): Processed DataFrames.
            relationships_data (dict | None): Detected PKs and FKs. Defaults to None.
            types_data (dict | None): Column encoding types. Defaults to None.

        Returns:
            dict: Formatted metadata {tables: [{name, columns, foreign_keys, ...}, ...]}.

        Raises:
            ValueError: If ``engine_name`` has no registered formatter.

        Example:
            >>> formatter = MetadataFormatter()
            >>> metadata = formatter.format(data_dict, relationships, types)
        """
        logger.info("--- Formatting metadata for engine '%s' ---", self.engine_name)

        relationships_data = relationships_data or {"pks": {}, "fks": []}
        types_data = types_data or {}

        if self.engine_name == "mostly":
            encoding_mapper = get_encoding_type_mapper(self.engine_name)
            return self._format_for_mostly(
                data_dfs, relationships_data, types_data, encoding_mapper
            )
        raise ValueError(
            f"No metadata formatter registered for engine: {self.engine_name!r}. "
            "Supported: 'mostly'."
        )

    def _format_for_mostly(
        self,
        data_dfs: dict,
        relationships_data: dict,
        types_data: dict,
        encoding_mapper: EncodingTypeMapper,
    ) -> dict:
        """Format metadata into the structure expected by the Mostly AI SDK.

        Each column carries a ``model_encoding_type`` (its canonical
        :class:`ModelEncodingType` translated through ``encoding_mapper`` — the
        identity for Mostly); foreign keys carry the ``is_context``/``direct``
        flags Mostly uses to model relational context.

        Args:
            data_dfs (dict[str, pd.DataFrame]): Processed DataFrames.
            relationships_data (dict): Detected PKs and FKs (never None here).
            types_data (dict): Column encoding types (never None here).
            encoding_mapper (EncodingTypeMapper): Per-engine encoding-type
                translator, resolved by engine name in :meth:`format`.

        Returns:
            dict: Mostly-formatted metadata {tables: [{name, columns, foreign_keys, ...}, ...]}.
        """
        tables_config = []

        for name, df in data_dfs.items():
            # A. Prepare Columns
            cols_config = []
            t_types = types_data.get(name, {})

            for col in df.columns:
                ctype = t_types.get(col)
                if ctype is None:
                    # Rule-created columns (duration/age aux cols) are absent from
                    # the inspection's encoding map. A blanket categorical default
                    # makes every value of a high-cardinality numeric "rare", so the
                    # engine's rare-category protection generates the column 100%
                    # null — detect from the actual data instead.
                    ctype = detect_series_encoding(df[col])
                    logger.info(
                        "Column '%s'.'%s' missing from encoding map; detected '%s' from data.",
                        name,
                        col,
                        ctype.value,
                    )
                cols_config.append({"name": col, "model_encoding_type": encoding_mapper(ctype)})

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
