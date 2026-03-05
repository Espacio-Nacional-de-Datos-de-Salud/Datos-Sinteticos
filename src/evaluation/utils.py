import os

import pandas as pd
import synthcity.logger as log
from config.general_config import (
    DEFAULT_DATA_PATH,
    SIMULATION_RUN_FOLDER_PREFIX,
    SIMULATIONS_DIR,
)

from src.core.logging_config import get_logger
from src.core.utils import interactive_file_selection

logger = get_logger(__name__)


def select_original_files() -> list[str]:
    """
    Solicita al usuario un directorio base y permite seleccionar archivos originales.

    Returns:
        list[str]: Lista de rutas a los archivos originales seleccionados.

    Raises:
        None.

    Example:
        >>> archivos = select_original_files()
        >>> print(len(archivos))
        3
    """
    user_path = input(
        f"Directorio base para buscar archivos originales (Enter para '{DEFAULT_DATA_PATH}'): "
    ).strip()
    base_dir = user_path if user_path else DEFAULT_DATA_PATH
    return interactive_file_selection(base_dir)


def select_synthetic_files(original_files: list[str]) -> tuple[list[str], str]:
    """
    Solicita un directorio base y permite seleccionar el run con datos sinteticos.

    Args:
        original_files (list[str]): Rutas de los archivos originales.

    Returns:
        tuple[list[str], str]: Lista de rutas a los archivos sinteticos y el
        directorio del run seleccionado.

    Example:
        >>> sint, run_dir = select_synthetic_files(["/data/tabla.csv"])
        >>> print(run_dir)
        /outputs/simulation/run_20260206_132709
    """
    selected_tables = [os.path.basename(f) for f in original_files]

    user_path = input(
        f"Directorio base para buscar archivos sintéticos: (Enter para '{SIMULATIONS_DIR}'): "
    ).strip()
    base_dir = user_path if user_path else SIMULATIONS_DIR

    return interactive_result_selection(base_dir, selected_tables)


def setup_synthcity_environment(run_directory: str):
    """
    Configura Synthcity para usar el directorio del run para logs y cache.

    Args:
        run_directory (str): Ruta del directorio del run.

    Example:
        >>> setup_synthcity_environment("/outputs/simulation/run_20260206_132709")
    """
    log.add(os.path.join(run_directory, "synthcity.log"))
    os.environ["SYNTHCITY_WORKSPACE"] = os.path.join(run_directory, "cache")


def align_datasets_structure_and_types(
    data_original: dict[str, pd.DataFrame], data_synthetic: dict[str, pd.DataFrame]
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    """
    Alinea nombres de tablas, interseca columnas y homogeneiza tipos de datos.

    Args:
        data_original (dict[str, pd.DataFrame]): Tablas originales.
        data_synthetic (dict[str, pd.DataFrame]): Tablas sinteticas.

    Returns:
        tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]: Diccionarios
        alineados de datos originales y sinteticos.

    Example:
        >>> orig, synth = align_datasets_structure_and_types({"t": df1}, {"t": df2})
        >>> list(orig["t"].columns) == list(synth["t"].columns)
        True
    """
    # 1. Unify Dictionary Keys (Table Names)
    # We force both dicts to use the name of the first original table to ensure matching
    if not data_original or not data_synthetic:
        return data_original, data_synthetic

    primary_table_name = next(iter(data_original))

    # We create new dictionaries pointing to the dataframes
    aligned_original = {primary_table_name: df for df in data_original.values()}  # noqa: B035
    aligned_synthetic = {primary_table_name: df for df in data_synthetic.values()}  # noqa: B035

    # 2. Intersect Columns (Keep only shared columns)
    cols_original = set(aligned_original[primary_table_name].columns)
    cols_synthetic = set(aligned_synthetic[primary_table_name].columns)
    common_columns = list(cols_original.intersection(cols_synthetic))

    # 3. Filter Columns and Fix Data Types
    for table in aligned_original.keys():
        # Filter columns AND CREATE A COPY to avoid SettingWithCopyError
        # This .copy() is the critical fix
        aligned_original[table] = aligned_original[table][common_columns].copy()
        aligned_synthetic[table] = aligned_synthetic[table][common_columns].copy()

        # Fix Type Mismatches (e.g., int vs str)
        for col in common_columns:
            dtype_orig = aligned_original[table][col].dtype
            dtype_syn = aligned_synthetic[table][col].dtype

            if dtype_orig != dtype_syn:
                logger.info(
                    "Aligning types for '%s' column '%s': %s vs %s -> str",
                    table,
                    col,
                    dtype_orig,
                    dtype_syn,
                )
                aligned_original[table][col] = aligned_original[table][col].astype(str)
                aligned_synthetic[table][col] = aligned_synthetic[table][col].astype(str)

    return aligned_original, aligned_synthetic


def interactive_result_selection(
    base_directory: str, real_table_names: list
) -> tuple[list[str], str]:
    """
    Busca simulaciones con versiones sinteticas de las tablas y permite seleccionar uno.

    Args:
        base_directory (str): Directorio donde buscar carpetas 'simulation_'.
        real_table_names (list): Nombres de las tablas reales a buscar.
    Returns:
        tuple[list[str], str]: Lista de rutas de tablas sinteticas y el
        directorio del run. Si falla, devuelve ([], "").

    Example:
        >>> files, run_dir = interactive_result_selection("/outputs/simulation", ["t.csv"])
        >>> print(files)
        ['/outputs/simulation/run_20260206_132709/synthetic_dataset/t_synthetic.csv']
    """
    valid_runs = []

    if not os.path.exists(base_directory):
        print(f"Error: Directory '{base_directory}' does not exist.")
        return [], ""

    for run_folder in os.listdir(base_directory):
        run_path = os.path.join(base_directory, run_folder)

        if os.path.isdir(run_path) and run_folder.startswith(SIMULATION_RUN_FOLDER_PREFIX + "_"):
            synthetic_dir = os.path.join(run_path, "synthetic_data")

            if os.path.isdir(synthetic_dir):
                run_files = []
                all_tables_found = True

                for table_full_name in real_table_names:
                    name, ext = os.path.splitext(table_full_name)

                    potential_file = f"{name}_synthetic{ext}"
                    full_path = os.path.join(synthetic_dir, potential_file)

                    if os.path.exists(full_path):
                        run_files.append(full_path)
                    else:
                        all_tables_found = False
                        break

                if all_tables_found:
                    valid_runs.append({"run_name": run_folder, "files": run_files})

    if not valid_runs:
        print(f"No se encontraron simulations que contengan todas las tablas: {real_table_names}")
        return [], ""

    print(f"\nRuns encontrados con las tablas {real_table_names}:")
    for i, run_info in enumerate(valid_runs):
        print(f"  [{i}] {run_info['run_name']}")

    seleccion = input("\nSelecciona el índice del run a cargar: ").strip()

    try:
        idx = int(seleccion)
        if 0 <= idx < len(valid_runs):
            selected_run = valid_runs[idx]
            run_directory = os.path.join(base_directory, selected_run["run_name"])
            return selected_run["files"], run_directory
    except (ValueError, IndexError):
        pass

    print("Selección no válida.")
    return [], ""
