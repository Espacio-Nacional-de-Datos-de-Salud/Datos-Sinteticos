import os
from abc import ABC, abstractmethod

import pandas as pd
from config.general_config import DEFAULT_CSV_DELIMITER

from src.core.errors import DataLoadError
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class DataLoader(ABC):
    """Interfaz abstracta para cargar datos desde diferentes fuentes.

    Define el contrato que deben cumplir todas las implementaciones de cargadores
    de datos, garantizando una entrada estándar al pipeline de procesamiento.
    """

    @abstractmethod
    def load(self, source: str | list[str], **kwargs) -> dict[str, pd.DataFrame]:
        """Carga datos de una o múltiples fuentes en DataFrames.

        Args:
            source (str | list[str]): Ruta(s) a archivo(s) de datos o directorio.
            **kwargs: Argumentos adicionales específicos de cada implementación.

        Returns:
            dict[str, pd.DataFrame]: Diccionario {nombre_tabla: dataframe} donde
                nombre_tabla se deriva del nombre del archivo.
        """
        pass


class FileDataLoader(DataLoader):
    """Carga datos desde archivos locales (CSV, Excel, Parquet).

    Soporta múltiples formatos y convierte cada archivo en una tabla dentro
    de un diccionario de DataFrames, usando el nombre del archivo como clave.
    """

    def load(self, source_paths: str | list[str], **kwargs) -> dict[str, pd.DataFrame]:
        """Carga uno o múltiples archivos locales en un diccionario de DataFrames.

        Args:
            source_paths (str | list[str]): Ruta a archivo/directorio o lista de rutas.
            **kwargs: Argumentos opcionales como 'sep' para delimitador CSV personalizado.

        Returns:
            dict[str, pd.DataFrame]: Diccionario {nombre_tabla: dataframe}.

        Raises:
            ValueError: Si no se carga ninguna tabla válida.
            RuntimeError: Si ocurre error al procesar un archivo.

        Example:
            >>> loader = FileDataLoader()
            >>> data = loader.load('data/users.csv')
            >>> print(data.keys())  # dict_keys(['users'])
        """
        loaded_data = {}

        # si es un string único, lo convertimos a lista
        sources = list(source_paths) if isinstance(source_paths, str) else source_paths

        for file_path in sources:
            if not os.path.exists(file_path):
                logger.warning("El archivo %s no existe. Saltando.", file_path)
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
                    logger.warning("Formato no soportado para %s. Saltando.", base_name)
                    continue

                loaded_data[table_name] = df
                logger.info("\t-> Tabla cargada: '%s' (%d filas)", table_name, len(df))

            except Exception as e:
                logger.warning("Error al cargar %s: %s. Saltando.", base_name, e)
                continue

        if not loaded_data:
            raise DataLoadError("No se pudo cargar ninguna tabla válida.")

        return loaded_data
