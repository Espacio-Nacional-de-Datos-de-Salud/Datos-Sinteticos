import pandas as pd
from backend.src.infrastructure.logging_config import get_logger

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

        Applies several operations:
        1. Removes completely empty columns (all NaN).
        2. Normalizes column names (strip whitespace and lowercase).
        3. Converts numeric columns containing only integers to Nullable Int64.
        4. Removes duplicate rows.

        Returns:
            dict[str, pd.DataFrame]: Dictionary of cleaned tables {table_name: dataframe}.

        Example:
            >>> cleaner = DataCleaner(raw_data_dict)
            >>> cleaned = cleaner.run()
        """
        logger.info("----- Starting Data Cleaning -----")
        for name, df in self.raw_data.items():
            logger.info(f"Cleaning table: {name}...")
            clean_df = df.copy()
            changes_log = []

            # 1. Empty check
            if clean_df.empty:
                logger.info(f"!! Table {name} is empty. Skipping...")
                continue

            # 2. Remove completely empty columns (NaN)
            cols_before = set(clean_df.columns)
            clean_df.dropna(axis=1, how="all", inplace=True)
            cols_after = set(clean_df.columns)
            dropped_cols = cols_before - cols_after

            if dropped_cols:
                changes_log.append(f"Columns removed (100% empty): {', '.join(dropped_cols)}")

            # 3. Standardize column names
            old_names = clean_df.columns.tolist()
            clean_df.columns = clean_df.columns.str.strip().str.lower()
            new_names = clean_df.columns.tolist()

            renamed_cols = []
            for old, new in zip(old_names, new_names):
                if old != new:
                    renamed_cols.append(f"'{old}' -> '{new}'")

            if renamed_cols:
                changes_log.append(f"Names normalized: {', '.join(renamed_cols)}")

            # 4. Convert floats that represent integers to nullable Int64
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
                    "Float columns converted to Int64 because they contain integers: "
                    + ", ".join(converted_cols)
                )

            # 5. Handle duplicates
            rows_before = len(clean_df)
            clean_df.drop_duplicates(inplace=True)
            rows_after = len(clean_df)
            duplicates_removed = rows_before - rows_after

            if duplicates_removed > 0:
                changes_log.append(f"Duplicate rows removed: {duplicates_removed}")

            if changes_log:
                for log in changes_log:
                    logger.info(log)
            else:
                logger.info("No changes required.")

            self.cleaned_data[name] = clean_df

        logger.info("----- Data Cleaning Completed -----")
        return self.cleaned_data
