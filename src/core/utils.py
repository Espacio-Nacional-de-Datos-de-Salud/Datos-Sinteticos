"""Utilidades para interacción con usuario, manejo de archivos y tipos de codificación.

Proporciona funciones auxiliares para carga/guardado de artefactos, selección
interactiva de archivos, detección automática de tipos de columnas y gestor
de configuración para síntesis de datos."""

import json
import os
import re
from enum import Enum

import numpy as np
import pandas as pd
import yaml
from config.general_config import (
    DEFAULT_SAMPLE_SIZE,
    GENERATOR_ZIP_NAME,
    METADATA_FILENAME,
    MODELS_DIR,
    PROFILING_REPORT_PATTERN,
    RULE_MAP,
    RUN_TIMESTAMP,
    SIMULATIONS_DIR,
    SUPPORTED_FILE_FORMATS,
)

from src.core.errors import MetadataNotFoundError, RuleManagerNotFoundError
from src.core.logging_config import get_logger
from src.core.preprocessing.logical_rules import LogicalRule, LogicalRuleManager

logger = get_logger(__name__)

LAT_LONG_REGEX = re.compile(r"^\s*-?\d+(\.\d+)?,\s*-?\d+(\.\d+)?\s*$")


class ModelEncodingType(str, Enum):
    """Tipos de codificación de columnas soportados por Mostly AI SDK.

    Enumeración de tipos de codificación de datos para entrenar el motor de síntesis.
    Tomado del SDK de Mostly AI para evitar dependencias externas innecesarias.
    """

    auto = "AUTO"
    tabular_categorical = "TABULAR_CATEGORICAL"
    tabular_numeric_auto = "TABULAR_NUMERIC_AUTO"
    tabular_numeric_discrete = "TABULAR_NUMERIC_DISCRETE"
    tabular_numeric_binned = "TABULAR_NUMERIC_BINNED"
    tabular_numeric_digit = "TABULAR_NUMERIC_DIGIT"
    tabular_character = "TABULAR_CHARACTER"
    tabular_datetime = "TABULAR_DATETIME"
    tabular_datetime_relative = "TABULAR_DATETIME_RELATIVE"
    tabular_lat_long = "TABULAR_LAT_LONG"
    language_text = "LANGUAGE_TEXT"
    language_categorical = "LANGUAGE_CATEGORICAL"
    language_numeric = "LANGUAGE_NUMERIC"
    language_datetime = "LANGUAGE_DATETIME"


def auto_detect_encoding_type(x: pd.Series) -> ModelEncodingType:
    """Detecta automáticamente el tipo de codificación más apropiado para una columna.

    Analiza los valores de la serie aplicando heurísticas secuenciales: detecta
    fechas, coordenadas geográficas, texto único vs texto repetido, etc. Retorna
    el tipo de codificación más específico disponible.

    Args:
        x (pd.Series): Serie de datos a analizar (puede contener valores nulos).

    Returns:
        ModelEncodingType: Tipo de codificación más apropiado para la serie.

    Example:
        >>> s = pd.Series(['2023-01-01', '2023-01-02', '2023-01-03'])
        >>> auto_detect_encoding_type(s)
        <ModelEncodingType.tabular_datetime: 'TABULAR_DATETIME'>
    """
    x = x.astype(str)
    x = x[x.str.strip() != ""]  # filter out empty and whitespace-only strings

    # if all values are null or empty, default to categorical
    if len(x) == 0:
        return ModelEncodingType.tabular_categorical

    # if all non-null values can be converted to datetime -> datetime encoding
    if pd.to_datetime(x, errors="coerce").notna().all():
        return ModelEncodingType.tabular_datetime

    # if all values match lat/long pattern -> lat_long (geo) encoding
    if x.str.match(LAT_LONG_REGEX).all():
        return ModelEncodingType.tabular_lat_long

    # if more than 5% of rows contain unique values
    if len(x) >= 100 and x.value_counts().eq(1).reindex(x).mean() > 0.05:
        if (
            x.str.len().nunique() == 1 or x.str.len().max() <= 36
        ):  # if all values are of the same length or shorter than 36 chars -> character encoding
            return ModelEncodingType.tabular_character
        else:  # if values are of different lengths -> text encoding
            return ModelEncodingType.language_text

    return ModelEncodingType.tabular_categorical


def generate_mock_data(n: int = 1000) -> pd.DataFrame:
    """Genera un DataFrame sintético con datos relacionales de prueba.

    Crea un dataset con distribuciones condicionales: pediatric (0/1),
    enfermedad según edad (niños: varicella/measles, adultos: diabetes/hypertension),
    y medicación según enfermedad. Útil para testing y demostración.

    Args:
        n (int): Número de registros a generar. Defaults to 1000.

    Returns:
        pd.DataFrame: Dataset con columnas [id, ispediatric, disease, medication].

    Example:
        >>> df = generate_mock_data(n=100)
        >>> print(df.shape)  # (100, 4)
        >>> print(df['disease'].unique())  # [...enfermedad...]
    """

    # Paso 1: Generar Edad (50% niños, 50% adultos)
    is_pediatric = np.random.choice([0, 1], size=n)

    diseases = []
    medications = []

    for pediatric in is_pediatric:
        # Paso 2: Generar Enfermedad según Edad
        if pediatric == 1:
            # Niños: 70% Varicella, 30% Measles
            dis = np.random.choice(["Varicella", "Measles"], p=[0.7, 0.3])
        else:
            # Adultos: 60% Diabetes, 40% Hypertension
            dis = np.random.choice(["Diabetes", "Hypertension"], p=[0.6, 0.4])

        diseases.append(dis)

        # Paso 3: Generar Medicación según Enfermedad
        if dis == "Varicella":
            med = np.random.choice(["Calamine Lotion", "Acetaminophen"], p=[0.8, 0.2])
        elif dis == "Measles":
            med = np.random.choice(["Vitamin A", "Supportive Care"], p=[0.9, 0.1])
        elif dis == "Diabetes":
            med = np.random.choice(["Metformin", "Insulin"], p=[0.5, 0.5])  # Muy dividido
        elif dis == "Hypertension":
            med = np.random.choice(["Lisinopril", "Amlodipine"], p=[0.7, 0.3])

        medications.append(med)

    return pd.DataFrame(
        {
            "id": range(len(is_pediatric)),
            "ispediatric": is_pediatric,
            "disease": diseases,
            "medication": medications,
        }
    )


def create_run_directory(run_type: str) -> str:
    """Crea un directorio timestampeado para una ejecución (entrenamiento o simulación).

    Genera estructura de carpetas timestampeadas bajo la ruta base correspondiente
    al tipo de ejecución. Ejemplo: outputs/training/run_20230101_120000/

    Args:
        run_type (str): Tipo de ejecución: 'generator' para entrenamiento o
            'simulation' para generación de datos sintéticos.

    Returns:
        str: Ruta al directorio creado.

    Raises:
        ValueError: Si run_type no es 'generator' o 'simulation'.

    Example:
        >>> path = create_run_directory('generator')
        >>> print(path)  # outputs/training/run_20230101_120000/
    """
    if run_type == "generator":
        base_path = MODELS_DIR
        prefix = "model"
    elif run_type == "simulation":
        base_path = SIMULATIONS_DIR
        prefix = "simulation"
    else:
        raise ValueError("run_type must be 'generator' or 'simulation'")

    # Example: outputs/models/modelo_20230101_120000/
    output_dir = os.path.join(base_path, f"{prefix}_{RUN_TIMESTAMP}/")
    os.makedirs(output_dir, exist_ok=True)
    return output_dir


def ask_simulation_configuration() -> int:
    """Solicita interactivamente al usuario el tamaño de muestra a generar.

    Pide un número entero positivo con reintentos en caso de entrada inválida.

    Returns:
        int: Número de registros sintéticos a generar.

    Example:
        >>> sample_size = ask_simulation_configuration()
        Enter the number of synthetic records to generate (default 1000): 5000
        >>> print(sample_size)  # 5000
    """
    while True:
        try:
            prompt = f"Enter the number of synthetic records to generate (default {DEFAULT_SAMPLE_SIZE}): "
            sample_size = int(input(prompt) or DEFAULT_SAMPLE_SIZE)
            if sample_size <= 0:
                print("Please enter a positive integer for sample size.")
                continue
            return sample_size
        except ValueError:
            print("Invalid input. Please enter a numeric value for sample size.")


def interactive_file_selection(directory_files: str) -> list[str]:
    """Permite al usuario seleccionar interactivamente archivos de un directorio.

    Lista archivos soportados (CSV, Excel, Parquet) y permite selección
    por índices individuales, múltiples o cargar todos.

    Args:
        directory_files (str): Ruta al directorio con archivos.

    Returns:
        list[str]: Lista de rutas a archivos seleccionados (puede estar vacía).

    Example:
        >>> files = interactive_file_selection('data/')
        Archivos encontrados en 'data/':
          [0] users.csv
          [1] orders.xlsx
        Selecciona los índices (separados por coma) o escribe 'all': 0,1
        >>> print(files)  # ['data/users.csv', 'data/orders.xlsx']
    """
    files = []
    for file in os.listdir(directory_files):
        if file.endswith(SUPPORTED_FILE_FORMATS):
            files.append(os.path.join(directory_files, file))

    if not files:
        print(f"No se encontraron archivos en '{directory_files}'.")
        return []

    print(f"\nArchivos encontrados en '{directory_files}':")
    for i, file_path in enumerate(files):
        print(f"  [{i}] {os.path.basename(file_path)}")

    print("  [all] Cargar todos los archivos")

    seleccion = (
        input("\nSelecciona los índices (separados por coma) o escribe 'all': ").strip().lower()
    )

    if seleccion == "all":
        return files

    try:
        indices = [int(idx.strip()) for idx in seleccion.split(",")]
        selected_files = [files[i] for i in indices if 0 <= i < len(files)]
        return selected_files
    except (ValueError, IndexError):
        print("Selección no válida. No se cargará ningún archivo.")
        return []


def get_files_from_directory(directory: str) -> list[str]:
    """Obtiene lista de archivos soportados de un directorio.

    Args:
        directory (str): Ruta al directorio.

    Returns:
        list[str]: Lista de rutas a archivos con formatos soportados.

    Example:
        >>> files = get_files_from_directory('data/')
        >>> print(files)  # ['data/users.csv', 'data/orders.xlsx']
    """
    if not os.path.exists(directory):
        print(f"Directory '{directory}' does not exist.")
        return []
    return [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.endswith(SUPPORTED_FILE_FORMATS)
    ]


def should_continue_after_training(sample_size: int | None = None) -> bool:
    """Determina si continuar con simulación tras entrenamiento.

    Si sample_size está definido, retorna True (flujo automático). Si es None,
    solicita confirmación interactiva al usuario.

    Args:
        sample_size (int | None): Tamaño de muestra. Si es None, pregunta al usuario.
            Defaults to None.

    Returns:
        bool: True para continuar con simulación, False para detener.
    """
    if sample_size is not None:
        return True

    continuar = (
        input("\n¿Desea simular datos con el generador recién entrenado? (y/n): ").strip().lower()
    )
    return continuar == "y"


def load_metadata(path_run_folder: str) -> dict:
    """Carga metadatos desde el directorio de una ejecución anterior.

    Args:
        path_run_folder (str): Ruta a directorio de ejecución.

    Returns:
        dict: Metadatos cargados desde JSON.

    Raises:
        FileNotFoundError: Si no existe arquivo metadata.json.

    Example:
        >>> metadata = load_metadata('outputs/training/run_20230101_120000/')
        >>> print(metadata.keys())  # dict_keys(['tables', ...])
    """
    import json

    metadata_path = os.path.join(path_run_folder, METADATA_FILENAME)
    if not os.path.exists(metadata_path):
        raise MetadataNotFoundError(f"Metadata file not found at {metadata_path}")
    with open(metadata_path) as f:
        metadata = json.load(f)
    return metadata


def save_rule_manager(rule_manager: LogicalRuleManager, path_run_folder: str) -> None:
    """Guarda el RuleManager en archivo pickle.

    Args:
        rule_manager (LogicalRuleManager): Gestor de reglas a guardar.
        path_run_folder (str): Ruta a directorio donde guardar.
    """
    import pickle

    rule_manager_path = os.path.join(path_run_folder, "rule_manager.pkl")
    with open(rule_manager_path, "wb") as f:
        pickle.dump(rule_manager, f)


def load_rule_manager(path_run_folder: str) -> LogicalRuleManager:
    """Carga RuleManager desde archivo pickle de ejecución anterior.

    Args:
        path_run_folder (str): Ruta a directorio de ejecución.

    Returns:
        LogicalRuleManager: Gestor de reglas cargado.

    Raises:
        FileNotFoundError: Si no existe rule_manager.pkl.

    Example:
        >>> rm = load_rule_manager('outputs/training/run_20230101/')
        >>> print(rm.rules)  # [...]
    """
    import pickle

    rule_manager_path = os.path.join(path_run_folder, "rule_manager.pkl")
    if not os.path.exists(rule_manager_path):
        raise RuleManagerNotFoundError(f"RuleManager file not found at {rule_manager_path}")
    with open(rule_manager_path, "rb") as f:
        rule_manager = pickle.load(f)
    return rule_manager


def delete_empty_folders(root_path: str) -> None:
    """Elimina recursivamente todas las carpetas vacías bajo una ruta.

    Recorre directorios de abajo hacia arriba para eliminar carpetas vacías
    tras procesar sus contenidos.

    Args:
        root_path (str): Ruta raíz donde buscar carpetas vacías.

    Example:
        >>> delete_empty_folders('outputs/')
    """
    for root, dirs, _ in os.walk(root_path, topdown=False):
        for name in dirs:
            full_path = os.path.join(root, name)

            # Check if the directory is empty
            if not os.listdir(full_path):
                logger.debug("Deleting empty folder: %s", full_path)
                os.rmdir(full_path)


def save_generator(generator, path_run_folder: str) -> None:
    """Guarda el generador entrenado en archivo ZIP.

    Args:
        generator: Objeto generador de Mostly AI a guardar.
        path_run_folder (str): Ruta a directorio donde guardar.

    """
    path_to_save = os.path.join(path_run_folder, GENERATOR_ZIP_NAME)
    generator.export_to_file(path_to_save)


def save_metadata(metadata: dict, output_dir: str) -> None:
    """Guarda metadatos en archivo JSON.

    Args:
        metadata (dict): Diccionario de metadatos.
        output_dir (str): Directorio destino.

    """
    with open(f"{output_dir}metadata.json", "w") as f:
        json.dump(metadata, f, indent=4)
    logger.info("Metadata guardada en '%smetadata.json'", output_dir)


def save_synthetic_results(synthetic_results: dict[str, pd.DataFrame], output_dir: str) -> None:
    """Guarda datos sintéticos generados en archivos CSV.

    Crea estructura de carpetas y guarda cada tabla en CSV separado.

    Args:
        synthetic_results (dict[str, pd.DataFrame]): Diccionario de tablas sintéticas.
        output_dir (str): Directorio base para los resultados.
    """
    for table_name, df in synthetic_results.items():
        file_path = os.path.join(output_dir, "synthetic_data", f"{table_name}_synthetic.csv")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        df.to_csv(file_path, index=False)
        logger.info("Synthetic data for table '%s' saved to '%s'", table_name, file_path)


def save_data_profiles(data_profiles: dict[str, object], output_dir: str) -> None:
    """Guarda reportes de profiling HTML de datos.

    Args:
        data_profiles (dict[str, object]): Diccionario {nombre_tabla: profile_object}.
        output_dir (str): Directorio donde guardar reportes HTML.
    """
    for name, profile in data_profiles.items():
        output_file = os.path.join(output_dir, PROFILING_REPORT_PATTERN.format(name=name))
        profile.to_file(output_file)


def extract_rules_from_config(config_path: str) -> list[LogicalRule]:
    """Carga reglas lógicas desde archivo YAML de configuración.

    Parsea YAML y crea instancias de LogicalRule según el tipo especificado.

    Args:
        config_path (str): Ruta a archivo YAML con definición de reglas.

    Returns:
        list[LogicalRule]: Lista de instancias LogicalRule creadas.
    """
    with open(config_path) as f:
        config_data = yaml.safe_load(f)

    extracted_rules = []

    for entry in config_data.get("rules", []):
        rule_type = entry.pop("type")

        if rule_type in RULE_MAP:
            # Instantiate the class using dictionary unpacking (**entry)
            # This passes the remaining keys as arguments to the dataclass
            rule_instance = RULE_MAP[rule_type](**entry)
            extracted_rules.append(rule_instance)
        else:
            logger.warning("Rule type '%s' not recognized. Skipping.", rule_type)

    return extracted_rules


def create_simulation_config(metadata: dict, sample_size: int | None = None) -> dict:
    """Genera configuración de simulación para el motor Mostly AI.

    Crea estructura de configuración con parámetros de simulación para cada tabla.

    Args:
        metadata (dict): Diccionario con metadatos que incluye lista de tablas.
        sample_size (int | None): Tamaño de muestra. Si es None, se solicita
            interactivamente. Defaults to None.

    Returns:
        dict: Configuración de simulación con estructura
            {tables: [{name, configuration}, ...]}.

    Example:
        >>> config = create_simulation_config(metadata, sample_size=1000)
        >>> print(config['tables'][0])  # {'name': 'users', 'configuration': {...}}
    """
    # TODO: [#2] we are creating a simulation config specific to mosly, that may be okay as the
    # defined parameters are relevant, but we should think about how to make this more generic
    # maybe the schema (eg. 'mostly-type-configuration') should be an argument
    simulation_tables = []

    sample_size = sample_size or ask_simulation_configuration()

    for table_meta in metadata.get("tables", []):
        table_name = table_meta["name"]

        table_configuration = {"sample_size": sample_size, "enable_data_report": False}

        table_entry = {"name": table_name, "configuration": table_configuration}

        simulation_tables.append(table_entry)

    return {"tables": simulation_tables}
