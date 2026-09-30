"""File hashing helpers used for dataset provenance in model cards."""

import hashlib
import os

from backend.src.infrastructure.logging_config import get_logger

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
        logger.error("File not found for hashing: %s", os.path.abspath(file_path))
        raise FileNotFoundError()
