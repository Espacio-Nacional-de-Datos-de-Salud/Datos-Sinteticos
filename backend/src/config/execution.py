"""Non-interactive execution configuration.

Values come from the ``execution:`` section of ``general.yaml`` (default,
overridden per-install). The dataclass is kept for the API / tests, which
construct it directly.
"""

import os
from dataclasses import dataclass

from backend.src.config.general import (
    _EXECUTION,
    DEFAULT_DATA_PATH,
)
from backend.src.services.files import get_files_from_directory


@dataclass(frozen=True)
class ExecutionConfig:
    """Resolved parameters to run the main pipeline."""

    mode: str
    file_paths: list[str] | None
    sample_size: int | None
    model_id: str | None = None
    simulation_id: str | None = None
    inspection_id: str | None = None


def get_execution_config() -> ExecutionConfig:
    """Build ExecutionConfig from ``general.yaml``'s ``execution:`` section.

    Rules:
    - In train/inspect modes, if ``file_paths`` is null/empty, use all files from DEFAULT_DATA_PATH.
    - If ``file_paths`` is a single directory, expand it to its supported files.
    """
    mode = _EXECUTION.get("mode", "i")
    raw_paths = _EXECUTION.get("file_paths") or []
    selected_files = list(raw_paths)

    if mode in ("t", "i"):
        if not selected_files:
            selected_files = get_files_from_directory(DEFAULT_DATA_PATH)
        elif len(selected_files) == 1 and os.path.isdir(selected_files[0]):
            selected_files = get_files_from_directory(selected_files[0])

    return ExecutionConfig(
        mode=mode,
        file_paths=selected_files if selected_files else None,
        sample_size=_EXECUTION.get("sample_size"),
        model_id=_EXECUTION.get("model_id"),
        simulation_id=_EXECUTION.get("simulation_id"),
        inspection_id=_EXECUTION.get("inspection_id"),
    )
