"""Data loading abstractions for the synthetic data pipeline.

Defines the ``DataLoader`` abstract interface and a ``FileDataLoader``
implementation that reads CSV, Excel, and Parquet files (single paths or
directories) into a ``{table_name: DataFrame}`` dictionary used across the
inspection, training, and evaluation flows.
"""

import os
from abc import ABC, abstractmethod

import pandas as pd

from backend.src.config.general import DEFAULT_CSV_DELIMITER
from backend.src.infrastructure.errors import DataLoadError
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


class DataLoader(ABC):
    """Abstract interface for loading data from different sources.

    Defines the contract that all data loader implementations must follow,
    guaranteeing a standard input to the processing pipeline.
    """

    @abstractmethod
    def load(self, source: str | list[str], **kwargs) -> dict[str, pd.DataFrame]:
        """Loads data from one or multiple sources into DataFrames.

        Args:
            source (str | list[str]): Path(s) to data file(s) or directory.
            **kwargs: Additional arguments specific to each implementation.

        Returns:
            dict[str, pd.DataFrame]: Dictionary {table_name: dataframe} where
                table_name is derived from the file name.
        """
        pass


class FileDataLoader(DataLoader):
    """Loads data from local files (CSV, Excel, Parquet).

    Supports multiple formats and converts each file into a table within
    a dictionary of DataFrames, using the file name as the key.
    """

    def load(self, source_paths: str | list[str], **kwargs) -> dict[str, pd.DataFrame]:
        """Loads one or multiple local files into a dictionary of DataFrames.

        Args:
            source_paths (str | list[str]): Path to file/directory or list of paths.
            **kwargs: Optional arguments such as 'sep' for custom CSV delimiter.

        Returns:
            dict[str, pd.DataFrame]: Dictionary {table_name: dataframe}.

        Raises:
            ValueError: If no valid table is loaded.
            RuntimeError: If an error occurs while processing a file.

        Example:
            >>> loader = FileDataLoader()
            >>> data = loader.load('data/users.csv')
        """
        loaded_data = {}

        sources = list(source_paths) if isinstance(source_paths, str) else source_paths

        for file_path in sources:
            if not os.path.exists(file_path):
                logger.warning("File %s does not exist. Skipping.", file_path)
                continue

            base_name = os.path.basename(file_path)
            table_name, _ = os.path.splitext(base_name)
            file_ext = file_path.split(".")[-1].lower()

            try:
                if file_ext == "csv":
                    sep = kwargs.get("sep", DEFAULT_CSV_DELIMITER)
                    df = pd.read_csv(file_path, sep=sep)
                elif file_ext == "parquet":
                    df = pd.read_parquet(file_path)
                elif file_ext in ["xls", "xlsx"]:
                    df = pd.read_excel(file_path)
                else:
                    logger.warning("Unsupported format for %s. Skipping.", base_name)
                    continue

                loaded_data[table_name] = df
                logger.info("\t-> Table loaded: '%s' (%d rows)", table_name, len(df))

            except Exception as e:
                logger.warning("Error loading %s: %s. Skipping.", base_name, e)
                continue

        if not loaded_data:
            raise DataLoadError("Could not load any valid table.")

        return loaded_data
