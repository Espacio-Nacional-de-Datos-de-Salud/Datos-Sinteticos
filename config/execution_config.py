"""Non-interactive execution configuration for the main tool.

Defines execution parameters without depending on an interactive CLI.
Facilitates external injection (API, testing) by replacing default values.

Usage:
    1. Edit the parameters directly in this module.
    2. Or create an ExecutionConfig instance programmatically and pass it to main().
    3. In the future, an API could inject these values without touching any parsing logic.
"""

import os
from dataclasses import dataclass

from config.general_config import DEFAULT_DATA_PATH, SUPPORTED_FILE_FORMATS


@dataclass(frozen=True)
class ExecutionConfig:
    """Resolved parameters to run the main pipeline."""

    mode: str
    file_paths: list[str] | None
    sample_size: int
    model_id: str | None = None
    simulation_id: str | None = None
    inspection_id: str | None = None


# ============================================================================
# PARÁMETROS DE CONFIGURACIÓN POR DEFECTO
# ============================================================================
EXECUTION_MODE: str = "i"  # modo de ejecución en caso de correr src.main() directamente
# FILE_PATHS: list[str] | None = [
#     DEFAULT_DATA_PATH + "/sintetico omop/person.csv",
#     DEFAULT_DATA_PATH + "/sintetico omop/visit_occurrence.csv",
#     DEFAULT_DATA_PATH + "/sintetico omop/condition_occurrence.csv",
# ]
FILE_PATHS: list[str] | None = [DEFAULT_DATA_PATH + "/dataset_prueba_tecnica_v2.csv"]
SAMPLE_SIZE: int = None
MODEL_ID: str | None = None
SIMULATION_ID: str | None = "simulation_20260408_153348"
INSPECTION_ID: str | None = None


def _get_files_from_directory(directory: str) -> list[str]:
    """Gets supported files from a directory."""
    if not os.path.exists(directory):
        return []
    return [
        os.path.join(directory, filename)
        for filename in os.listdir(directory)
        if filename.endswith(SUPPORTED_FILE_FORMATS)
    ]


def get_execution_config() -> ExecutionConfig:
    """Builds ExecutionConfig from parameters defined in this module.

    Rules:
    - In train mode, if FILE_PATHS is None/empty, use all files from DEFAULT_DATA_PATH.
    - If FILE_PATHS contains a single folder, expand it to its supported files.

    Returns:
        ExecutionConfig: Resolved configuration ready to pass to main().

    Example:
        >>> config = get_execution_config()
        >>> # Luego pasar a main(config.mode, config.file_paths, ...)
    """
    mode = EXECUTION_MODE
    selected_files = FILE_PATHS if FILE_PATHS else []

    if mode in ("t", "i"):
        if not selected_files:
            selected_files = _get_files_from_directory(DEFAULT_DATA_PATH)
        elif len(selected_files) == 1 and os.path.isdir(selected_files[0]):
            selected_files = _get_files_from_directory(selected_files[0])

    return ExecutionConfig(
        mode=mode,
        file_paths=selected_files if selected_files else None,
        sample_size=SAMPLE_SIZE,
        model_id=MODEL_ID,
        simulation_id=SIMULATION_ID,
        inspection_id=INSPECTION_ID,
    )
