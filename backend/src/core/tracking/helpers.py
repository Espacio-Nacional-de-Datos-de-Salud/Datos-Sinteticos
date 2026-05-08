"""File hashing helpers used for dataset provenance in model cards."""

import hashlib
import os

from backend.src.core.logging_config import get_logger

logger = get_logger(__name__)


def compute_file_sha256(file_path: str) -> str:
    """Compute the SHA-256 hash of a file.

    Reads the file in 64 KB chunks to avoid loading large files entirely
    into memory.

    Args:
        file_path (str): Absolute or relative path to the file.

    Returns:
        str: Hexadecimal SHA-256 digest of the file contents.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as file_handle:
            for chunk in iter(lambda: file_handle.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except FileNotFoundError:
        # print absolute path for debugging
        logger.error("File not found for hashing: %s", os.path.abspath(file_path))
        raise FileNotFoundError()


def ensure_clean_mlflow_storage() -> None:
    """Scan the local MLflow storage and remove directories missing meta.yaml.

    This prevents MLflow from crashing or emitting noisy warnings when it
    encounters partially created experiment folders (e.g. from interrupted
    runs).
    """
    import os
    import shutil

    from backend.src.config.general import PROJECT_ROOT
    from backend.src.core.logging_config import get_logger

    logger = get_logger(__name__)
    mlruns_dir = PROJECT_ROOT / "mlruns"

    if not mlruns_dir.exists() or not mlruns_dir.is_dir():
        return

    for entry in os.scandir(mlruns_dir):
        if entry.is_dir() and entry.name != ".trash":
            # A valid MLflow experiment directory MUST have a meta.yaml
            meta_path = os.path.join(entry.path, "meta.yaml")
            if not os.path.exists(meta_path):
                logger.debug(
                    "Cleaning up malformed MLflow experiment directory (missing meta.yaml): %s",
                    entry.path,
                )
                try:
                    shutil.rmtree(entry.path)
                except Exception:
                    logger.warning("Failed to clean up malformed MLflow directory: %s", entry.path)
