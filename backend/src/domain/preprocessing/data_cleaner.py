import pandas as pd
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


class DataCleaner:
    """Cleans tables by removing empty columns, normalizing names, and removing duplicates.

    Prepares raw data for metadata extraction through standard cleaning
    operations: removal of empty columns, normalization of column names,
    and removal of duplicate rows.

    .. warning::
        This **consumes and mutates its input in place** — the DataFrames in the
        ``raw_data`` dict are modified directly (``dropna``/``drop_duplicates``
        with ``inplace=True``). Do not reuse the original ``raw_data`` after
        calling :meth:`run`; treat it as owned by the cleaner. Every current
        caller loads ``raw_data``, preprocesses, and never reads it again, so
        this is safe today — but a future flow that re-reads the raw input
        (e.g. to diff before/after or run two engines on the same data) would
        silently see the cleaned version. (See ``test_does_not_mutate_original``,
        which asserts the purity this intentionally does not provide.)

    Args:
        raw_data (dict[str, pd.DataFrame]): Dictionary of raw tables
            {table_name: dataframe}. Mutated in place; see warning above.
    """

    def __init__(
        self,
        raw_data: dict[str, pd.DataFrame],
        skip_tables: list[str] | tuple[str, ...] | set[str] | None = None,
    ) -> None:
        """Initializes the cleaner with a set of raw tables.

        Args:
            raw_data (dict[str, pd.DataFrame]): Dictionary of raw tables
                {table_name: dataframe}.
            skip_tables (list[str] | tuple[str, ...] | set[str] | None): Optional
                table names that should bypass cleaning entirely.
        """
        self.raw_data = raw_data
        self.cleaned_data = {}
        self.skip_tables = set(skip_tables or [])

    def run(self) -> dict[str, pd.DataFrame]:
        """Runs the cleaning pipeline on all tables.

        Applies several operations:
        1. Removes completely empty columns (all NaN).
        2. Normalizes column names (strip whitespace).
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
            if name in self.skip_tables:
                logger.info("Skipping data cleaning for table %s by configuration.", name)
                self.cleaned_data[name] = df
                continue

            logger.info(f"Cleaning table: {name}...")
            changes_log = []

            # 1. Empty check
            if df.empty:
                logger.info(f"!! Table {name} is empty. Skipping...")
                continue

            # 2. Remove completely empty columns (NaN)
            cols_before = set(df.columns)
            df.dropna(axis=1, how="all", inplace=True)
            cols_after = set(df.columns)
            dropped_cols = cols_before - cols_after

            if dropped_cols:
                changes_log.append(f"Columns removed (100% empty): {', '.join(dropped_cols)}")

            # 3. Standardize column names (strip surrounding whitespace only; case is preserved)
            old_names = df.columns.tolist()
            df.columns = df.columns.str.strip()
            new_names = df.columns.tolist()

            renamed_cols = []
            for old, new in zip(old_names, new_names):
                if old != new:
                    renamed_cols.append(f"'{old}' -> '{new}'")

            if renamed_cols:
                changes_log.append(f"Names normalized: {', '.join(renamed_cols)}")

            # 4. Convert floats that represent integers to nullable Int64
            converted_cols = []
            for col in df.columns:
                if not pd.api.types.is_float_dtype(df[col]):
                    continue

                non_null = df[col].dropna()
                if non_null.empty:
                    continue

                if non_null.mod(1).eq(0).all():
                    df[col] = df[col].astype("Int64")
                    converted_cols.append(col)

            if converted_cols:
                changes_log.append(
                    "Float columns converted to Int64 because they contain integers: "
                    + ", ".join(converted_cols)
                )

            # 5. Handle duplicates
            rows_before = len(df)
            df.drop_duplicates(inplace=True)
            rows_after = len(df)
            duplicates_removed = rows_before - rows_after

            if duplicates_removed > 0:
                changes_log.append(f"Duplicate rows removed: {duplicates_removed}")

            if changes_log:
                for log in changes_log:
                    logger.info(log)
            else:
                logger.info("No changes required.")

            self.cleaned_data[name] = df

        logger.info("----- Data Cleaning Completed -----")
        return self.cleaned_data
