import json
import logging
import os

import pandas as pd
import yaml
from config.general_config import (
    GENERATOR_ZIP_NAME,
    METADATA_FILENAME,
    MODEL_CARD_FILENAME,
    MODEL_RUN_FOLDER_PREFIX,
    MODELS_DIR,
    RUN_TIMESTAMP,
    LOG_LEVEL,
    LOG_FORMAT,
    LOG_DATE_FORMAT,
    SESSION_LOG_FILENAME
)
from mostlyai.sdk import MostlyAI
from mostlyai.sdk.domain import Generator

from src.core.errors import TableMetadataMissingError
from src.core.logging_config import get_logger

logger = get_logger(__name__)


class MostlyAIEngine:
    """Motor de síntesis de datos usando Mostly AI.

    Orquesta entrenamiento, carga y generación de datos sintéticos mediante
    la SDK de Mostly AI, permitiendo configuración personalizada del modelo
    y acceso a generadores entrenados previamente.
    """

    def __init__(self, config_path: str, run_dir: str | None = None, local: bool = True) -> None:
        """Inicializa motor con configuración y conexión a Mostly AI.

        Args:
            config_path (str): Ruta a archivo YAML con configuración del generador.
            local (bool): Si True, usa instancia local de Mostly AI. Defaults to True.
        """
        if run_dir:
            self.setup_mostlyai_logging(run_directory=run_dir)
        self.mostly = MostlyAI(local=local, local_port=8081)
        with open(config_path) as f:
            self.config = yaml.safe_load(f)
            self.config["generator"]["name"] += RUN_TIMESTAMP

    def train(
        self, data_dict: dict[str, pd.DataFrame], metadata: dict
    ) -> Generator:
        """Entrena generador sintético sobre datos preprocesados.

        Configura tablas, aplica metadatos y modelo de configuración, luego
        inicia entrenamiento.

        Args:
            data_dict (dict[str, pd.DataFrame]): Datos preprocesados
                {nombre_tabla: dataframe}.
            metadata (dict): Metadatos con estructura de tablas, PKs, FKs y tipos.

        Returns:
            Generator: Objeto generador entrenado (MostlyAI Generator).

        Raises:
            ValueError: Si tabla en data_dict no tiene metadatos correspondiente.
            Exception: Si entrenamiento falla en SDK de Mostly AI.

        Example:
            >>> generator = engine.train(processed_data, metadata)
            >>> print(generator.name)  # Nombre del generador entrenado
        """
        tables_config = []
        for table_name, df in data_dict.items():
            # extract metadata using table_name to ensure consistency
            metadata_table = next((t for t in metadata["tables"] if t["name"] == table_name), None)
            if not metadata_table:
                raise TableMetadataMissingError(f"No metadata found for table: {table_name}")

            table_entry = {
                "name": table_name,
                "data": df,
                "tabular_model_configuration": self.config["model_settings"],
                # TODO: [#1] can we select a specific type of model?
                "primary_key": metadata_table["primary_key"],
                "foreign_keys": metadata_table.get("foreign_keys", []),
                "columns": metadata_table["columns"],
            }
            tables_config.append(table_entry)

        # crear el generador
        full_config = {
            "name": self.config["generator"]["name"],
            "description": self.config["generator"]["description"],
            "random_state": self.config["generator"]["random_state"],
            "tables": tables_config,
        }

        # iniciar el entrenamiento
        generator = self.mostly.generators.create(config=full_config)
        generator.training.start()
        generator.training.wait()

        return generator

    def select_generator(self) -> tuple[Generator, str] | None:
        """Selecciona interactivamente un generador entrenado para usar.

        Lista carpetas de ejecución anteriores, extrae información de cada una
        y permite al usuario seleccionar cual generador cargar del almacenamiento.

        Returns:
            tuple[Generator, str] | None: Tupla (generator_obj, path_run_folder)
            o None si no hay generadores o se cancela selección.

        Raises:
            Exception: Si falla carga de generador desde archivo ZIP.

        Example:
            >>> result = engine.select_generator()
            >>> if result:
            ...     gen, path = result
            ...     print(f'Cargado: {gen.name}')
        """
        import glob
        import os

        # Definir ruta base donde están los runs
        run_folders = sorted(
            glob.glob(os.path.join(MODELS_DIR, MODEL_RUN_FOLDER_PREFIX + "_*")), reverse=True
        )

        if not run_folders:
            logger.warning("No se encontraron carpetas de ejecución en '%s'.", MODELS_DIR)
            return None

        available_options = []

        # Recorrer carpetas y extraer info desde model_card.json y metadata.json
        for folder in run_folders:
            generator_zip = os.path.join(folder, GENERATOR_ZIP_NAME)
            card_path = os.path.join(folder, MODEL_CARD_FILENAME)
            metadata_path = os.path.join(folder, METADATA_FILENAME)

            if not os.path.exists(generator_zip):
                continue

            try:
                model_id = os.path.basename(folder)
                timestamp = ""
                tables = "N/A"

                if os.path.exists(card_path):
                    with open(card_path, encoding="utf-8") as f:
                        card = json.load(f)
                    timestamp = card.get("timestamp", "")

                if os.path.exists(metadata_path):
                    with open(metadata_path, encoding="utf-8") as f:
                        meta = json.load(f)
                    tables = ", ".join(t["name"] for t in meta.get("tables", []))

                available_options.append(
                    {
                        "folder": folder,
                        "model_id": model_id,
                        "timestamp": timestamp,
                        "tables": tables,
                    }
                )
            except Exception as e:
                logger.error("Error leyendo metadatos de %s: %s", folder, e)

        if not available_options:
            logger.warning("Se encontraron carpetas, pero sin generator.zip válidos.")
            return None

        # --- Mostrar Tabla ---
        print("\n--- Runs Locales Disponibles (Outputs) ---")
        print(f"{'Idx':<4} | {'Model ID':<30} | {'Timestamp':<17} | {'Tables'}")
        print("-" * 100)

        for idx, opt in enumerate(available_options):
            tables_str = opt["tables"]
            if len(tables_str) > 40:
                tables_str = tables_str[:37] + "..."

            print(f"[{idx:<2}] | {opt['model_id']:<30} | {opt['timestamp']:<17} | {tables_str}")

        # --- Selección ---
        while True:
            try:
                choice_input = input("\nIntroduce el índice (Idx) del run que quieres usar: ")
                choice = int(choice_input)

                if 0 <= choice < len(available_options):
                    selected = available_options[choice]
                    clean_id = selected["model_id"]
                    path_run_folder = selected["folder"]

                    logger.info("Run seleccionado: %s", selected["model_id"])
                    logger.debug("ID recuperado: '%s'", clean_id)

                    try:
                        logger.info("Conectando con Mostly AI para obtener el objeto generador...")
                        # Recuperamos el objeto limpio
                        path_to_generator = os.path.join(path_run_folder, GENERATOR_ZIP_NAME)

                        generator_obj = self.mostly.generators.import_from_file(path_to_generator)
                        logger.info("Generador '%s' cargado correctamente.", generator_obj.name)
                        return generator_obj, path_run_folder
                    except Exception as api_error:
                        logger.error("Error recuperando el generador de la API: %s", api_error)
                        return None
                else:
                    print("Selección fuera de rango.")
            except ValueError:
                print("Entrada inválida. Introduce un número.")

    def simulate(
        self, generator: object, simulation_configuration: dict
    ) -> dict[str, pd.DataFrame]:
        """Genera datos sintéticos usando generador entrenado.

        Inicia job de generación con configuración especificada y retorna
        datos sintéticos en formato diccionario de DataFrames.

        Args:
            generator (object): Objeto generador entrenado (MostlyAI Generator).
            simulation_configuration (dict): Config con {tables: [{name, configuration}, ...]}.

        Returns:
            dict[str, pd.DataFrame]: Datos sintéticos generados
                {nombre_tabla: dataframe}.

        Raises:
            Exception: Si generación falla o configuración es inválida.

        Example:
            >>> config = {"tables": [{"name": "users", "configuration": {...}}]}
            >>> synthetic_data = engine.simulate(generator, config)
            >>> print(synthetic_data['users'].shape)
        """
        synthetic_dataset = self.mostly.generate(generator, config=simulation_configuration)

        synthetic_data_dict = synthetic_dataset.data()
        sd_config = synthetic_dataset.config()

        if isinstance(synthetic_data_dict, pd.DataFrame):
            synthetic_data_dict = {sd_config.tables[0].name: synthetic_data_dict}

        return synthetic_data_dict

    def setup_mostlyai_logging(self, run_directory: str) -> None:
        """Configure MostlyAI SDK logger to output to session.log."""
        mostlyai_logger = logging.getLogger("mostlyai")
        mostlyai_logger.handlers.clear()
        session_log_path = os.path.join(run_directory, SESSION_LOG_FILENAME)
        
        file_handler = logging.FileHandler(session_log_path, encoding="utf-8")
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        mostlyai_logger.addHandler(file_handler)
        mostlyai_logger.setLevel(LOG_LEVEL)

