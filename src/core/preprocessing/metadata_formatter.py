from src.core.utils import ModelEncodingType


class MetadataFormatter:
    """Convierte metadatos extraídos al formato esperado por motor de síntesis.

    Transforma información de tablas, columnas, tipos y relaciones en estructura
    JSON específica que el motor interpreta para configurar la generación sintética.

    Args:
        engine_name (str): Nombre del motor ('mostly' u otro). Defaults to \"mostly\".
    """

    def __init__(self, engine_name: str = "mostly") -> None:
        """Inicializa formateador de metadatos para motor específico.

        Args:
            engine_name (str): Nombre del motor. Defaults to \"mostly\".
        """
        self.engine_name = engine_name

    def format(
        self,
        data_dfs: dict,
        relationships_data: dict | None = None,
        types_data: dict | None = None,
    ) -> dict:
        """Formatea metadatos en estructura esperada por motor de síntesis.

        Organiza información de tablas, columnas, tipos de datos y relaciones
        en formato JSON que motor interpreta para configurar generación.

        Args:
            data_dfs (dict[str, pd.DataFrame]): DataFrames procesados.
            relationships_data (dict | None): PKs y FKs detectadas. Defaults to None.
            types_data (dict | None): Tipos de codificación de columnas. Defaults to None.

        Returns:
            dict: Metadatos formateados {tables: [{name, columns, foreign_keys, ...}, ...]}.

        Example:
            >>> formatter = MetadataFormatter()
            >>> metadata = formatter.format(data_dict, relationships, types)
            >>> print(metadata['tables'][0].keys())
        """

        print("--- Formatting metadata ---")

        relationships_data = relationships_data or {"pks": {}, "fks": []}
        types_data = types_data or {}

        tables_config = []

        for name, df in data_dfs.items():
            # A. Prepare Columns
            cols_config = []
            t_types = types_data.get(name, {})

            # If types weren't run, we just default or skip?
            # Ideally we check what columns exist in DF
            for col in df.columns:
                ctype = t_types.get(col, ModelEncodingType.tabular_categorical)  # Default
                cols_config.append({"name": col, "model_encoding_type": ctype})

            # B. Prepare FKs
            # Filter raw relationships where child == current table
            table_fks = []
            raw_fks = [r for r in relationships_data["fks"] if r["child"] == name]

            # Context heuristic (first one is context)
            for i, rel in enumerate(raw_fks):
                table_fks.append(
                    {
                        "column": rel["fk_column"],
                        "referenced_table": rel["parent"],
                        "is_context": (i == 0),  # Simple heuristic
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
