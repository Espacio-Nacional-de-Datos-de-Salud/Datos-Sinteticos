import pandas as pd

from src.core.logging_config import get_logger

logger = get_logger(__name__)


class DataCleaner:
    """Cleans tables by removing empty columns, normalizing names, and removing duplicates.

    Prepares raw data for metadata extraction through standard cleaning
    operations: removal of empty columns, normalization of column names,
    and removal of duplicate rows.

    Args:
        raw_data (dict[str, pd.DataFrame]): Dictionary of raw tables
            {table_name: dataframe}.
    """

    def __init__(self, raw_data: dict[str, pd.DataFrame]) -> None:
        """Initializes the cleaner with a set of raw tables.

        Args:
            raw_data (dict[str, pd.DataFrame]): Dictionary of raw tables
                {table_name: dataframe}.
        """
        self.raw_data = raw_data
        self.cleaned_data = {}

    def run(self) -> dict[str, pd.DataFrame]:
        """Runs the cleaning pipeline on all tables.

        Applies three operations: removes completely empty columns, normalizes
        column names (strip and lowercase), and removes duplicate rows. Prints
        a log of changes made in each table.

        Returns:
            dict[str, pd.DataFrame]: Dictionary of cleaned tables
                {table_name: dataframe}.

        Raises:
            ValueError: If any table contains invalid values during the process.

        Example:
            >>> cleaner = DataCleaner(raw_data_dict)
            >>> cleaned = cleaner.run()
        """
        logger.info("----- Starting Data Cleaning -----")
        for name, df in self.raw_data.items():
            logger.info(f"Cleaning table: {name}...")
            clean_df = df.copy()
            changes_log = []

            # 1. Chequeo de vacío
            if clean_df.empty:
                logger.info(f"!! La tabla {name} está vacía. Saltando...")
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

            # 4. Convertir floats que en realidad representan enteros a nullables Int64
            converted_cols = []
            for col in clean_df.columns:
                if not pd.api.types.is_float_dtype(clean_df[col]):
                    continue

                non_null = clean_df[col].dropna()
                if non_null.empty:
                    continue

                if non_null.mod(1).eq(0).all():
                    clean_df[col] = clean_df[col].astype("Int64")
                    converted_cols.append(col)

            if converted_cols:
                changes_log.append(
                    "Columnas float convertidas a Int64 por contener enteros: "
                    + ", ".join(converted_cols)
                )

            # 5. Manejar duplicados
            rows_before = len(clean_df)
            clean_df.drop_duplicates(inplace=True)
            rows_after = len(clean_df)
            duplicates_removed = rows_before - rows_after

            if duplicates_removed > 0:
                changes_log.append(f"Filas duplicadas eliminadas: {duplicates_removed}")

            if changes_log:
                for log in changes_log:
                    logger.info(log)
            else:
                logger.info("No se requirieron cambios.")

            self.cleaned_data[name] = clean_df

        logger.info("----- Data Cleaning Completed -----")
        return self.cleaned_data
