import pandas as pd


class DataCleaner:
    """Limpia tablas eliminando columnas vacías, normalizando nombres y removiendo duplicados.

    Prepara datos crudos para extracción de metadatos mediante operaciones
    de limpieza estándar: eliminación de columnas vacías, normalización de nombres
    de columnas y remoción de filas duplicadas.

    Args:
        raw_data (dict[str, pd.DataFrame]): Diccionario de tablas crudas
            {nombre_tabla: dataframe}.
    """

    def __init__(self, raw_data: dict[str, pd.DataFrame]) -> None:
        """Inicializa limpiador con un conjunto de tablas crudas.

        Args:
            raw_data (dict[str, pd.DataFrame]): Diccionario de tablas crudas
                {nombre_tabla: dataframe}.
        """
        self.raw_data = raw_data
        self.cleaned_data = {}

    def run(self) -> dict[str, pd.DataFrame]:
        """Ejecuta el pipeline de limpieza en todas las tablas.

        Aplica tres operaciones: elimina columnas completamente vacías, normaliza
        nombres de columnas (strip y lowercase) y elimina filas duplicadas. Imprime
        un log de cambios realizados en cada tabla.

        Returns:
            dict[str, pd.DataFrame]: Diccionario de tablas limpias
                {nombre_tabla: dataframe}.

        Raises:
            ValueError: Si alguna tabla contiene valores inválidos durante el proceso.

        Example:
            >>> cleaner = DataCleaner(raw_data_dict)
            >>> cleaned = cleaner.run()
            >>> print(cleaned['users'].shape)  # (987, 5)\n"""
        print("----- Starting Data Cleaning -----")
        for name, df in self.raw_data.items():
            print(f"Cleaning table: {name}...")
            clean_df = df.copy()
            changes_log = []

            # 1. Chequeo de vacío
            if clean_df.empty:
                print(f"!! La tabla {name} está vacía. Saltando...")
                continue

            # 2. Eliminar columnas completamente vacías (NaN)
            cols_before = set(clean_df.columns)
            clean_df.dropna(axis=1, how="all", inplace=True)
            cols_after = set(clean_df.columns)
            dropped_cols = cols_before - cols_after

            if dropped_cols:
                changes_log.append(f"Columnas eliminadas (100% vacías): {', '.join(dropped_cols)}")

            # 3. Estandarizar nombres de columnas
            old_names = clean_df.columns.tolist()
            clean_df.columns = clean_df.columns.str.strip().str.lower()
            new_names = clean_df.columns.tolist()

            renamed_cols = []
            for old, new in zip(old_names, new_names):
                if old != new:
                    renamed_cols.append(f"'{old}' -> '{new}'")

            if renamed_cols:
                changes_log.append(f"Nombres normalizados: {', '.join(renamed_cols)}")

            # 4. Manejar duplicados
            rows_before = len(clean_df)
            clean_df.drop_duplicates(inplace=True)
            rows_after = len(clean_df)
            duplicates_removed = rows_before - rows_after

            if duplicates_removed > 0:
                changes_log.append(f"Filas duplicadas eliminadas: {duplicates_removed}")

            if changes_log:
                for log in changes_log:
                    print(log)
            else:
                print("No se requirieron cambios.")

            self.cleaned_data[name] = clean_df

        print("----- Data Cleaning Completed -----")
        return self.cleaned_data
