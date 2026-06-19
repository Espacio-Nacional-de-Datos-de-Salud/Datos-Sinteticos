"""Data-file discovery service.

Walks ``backend/data/`` and returns files matching the allowed extensions.
Kept separate from the API router so it can be reused (CLI, workers, tests).
"""

import csv
import json
import os
from pathlib import Path
from typing import BinaryIO

from backend.src.api.schemas.files import DataFile, FilePreview
from backend.src.config.general import (
    SUPPORTED_FILE_FORMATS,
    UPLOAD_SIZE_LIMIT_BYTES,
)

# backend/src/sessions/files.py  ->  backend/
_DATA_ROOT = Path(__file__).resolve().parents[2] / "data"
UPLOADS_DIR = _DATA_ROOT / "uploads"

ALLOWED_EXTENSIONS = {"csv", "parquet", "json", "xls", "xlsx"}


class UploadConflictError(Exception):
    """Raised when an uploaded file would overwrite an existing one."""


class UploadExtensionError(Exception):
    """Raised when an uploaded file has an extension outside ALLOWED_EXTENSIONS."""


class UploadNameError(Exception):
    """Raised when an uploaded filename is unsafe (path separators, traversal)."""


class UploadSizeLimitError(Exception):
    """Raised when an upload would exceed the configured storage quota."""


def get_upload_stats() -> dict:
    """Returns storage usage statistics for the uploads directory.

    Returns:
        dict: A dictionary containing:
            - used_bytes (int): Total size of all files in the uploads directory.
            - limit_bytes (int): The configured storage quota in bytes.
    """
    used = 0
    if UPLOADS_DIR.exists():
        used = sum(p.stat().st_size for p in UPLOADS_DIR.iterdir() if p.is_file())
    return {"used_bytes": used, "limit_bytes": UPLOAD_SIZE_LIMIT_BYTES}


class UploadNotFoundError(Exception):
    """Raised when the requested upload file does not exist."""


def delete_one_upload(filename: str) -> str:
    """Deletes a single file from the uploads directory.

    Rejects path-traversal attempts and missing files.

    Returns:
        str: The name of the deleted file.
    """
    safe = Path(filename).name
    if safe != filename or not filename:
        raise UploadNameError(filename)
    target = UPLOADS_DIR / safe
    if not target.is_file():
        raise UploadNotFoundError(filename)
    target.unlink()
    return safe


def delete_all_uploads() -> list[str]:
    """Deletes every file under ``backend/data/uploads/``.

    Subdirectories are left alone — uploads are flat by design.

    Returns:
        list[str]: The names of the files that were removed.
    """
    if not UPLOADS_DIR.exists():
        return []
    removed: list[str] = []
    for path in sorted(UPLOADS_DIR.iterdir()):
        if path.is_file():
            path.unlink()
            removed.append(path.name)
    return removed


def save_uploaded_file(filename: str, stream: BinaryIO) -> DataFile:
    """Persists a binary stream as a file in the uploads directory.

    Rejects unsafe names, unsupported extensions, name collisions, and
    uploads that would exceed the configured storage quota.

    Args:
        filename (str): The name of the file to save.
        stream (BinaryIO): The binary content stream.

    Returns:
        DataFile: Metadata of the saved file.

    Raises:
        UploadNameError: If the filename is unsafe.
        UploadExtensionError: If the extension is not supported.
        UploadConflictError: If the file already exists.
        UploadSizeLimitError: If the upload exceeds the storage quota.
    """
    if not filename or "/" in filename or "\\" in filename or filename in {".", ".."}:
        raise UploadNameError(filename)

    if len(filename) > 100:
        raise UploadNameError(filename)

    extension = Path(filename).suffix.lstrip(".").lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise UploadExtensionError(extension)

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    target = UPLOADS_DIR / filename
    if target.exists():
        raise UploadConflictError(str(target))

    # Read into memory so we can check size before writing to disk.
    content = stream.read()
    incoming_bytes = len(content)
    stats = get_upload_stats()
    if stats["used_bytes"] + incoming_bytes > UPLOAD_SIZE_LIMIT_BYTES:
        raise UploadSizeLimitError(
            f"Upload would exceed the {UPLOAD_SIZE_LIMIT_BYTES // (1024**2)} MB storage limit. "
            f"Current usage: {stats['used_bytes'] // (1024**2)} MB. "
            f"File size: {incoming_bytes // 1024} KB."
        )

    with open(target, "wb") as out:
        out.write(content)

    return DataFile(
        path=str(target),
        name=target.name,
        size_bytes=target.stat().st_size,
        extension=extension,
    )


def list_data_files(extensions: set[str] | None = None) -> list[DataFile]:
    """Returns data files under ``backend/data/`` matching specified extensions.

    Args:
        extensions (set[str] | None): Lowercase extensions to include (without the dot).
            ``None`` or empty means all allowed extensions. Anything outside
            ``ALLOWED_EXTENSIONS`` is ignored.

    Returns:
        list[DataFile]: List of discovered data files.
    """
    wanted = (extensions or ALLOWED_EXTENSIONS) & ALLOWED_EXTENSIONS

    if not _DATA_ROOT.exists():
        return []

    files: list[DataFile] = []
    for path in _DATA_ROOT.rglob("*"):
        if not path.is_file():
            continue
        extension = path.suffix.lstrip(".").lower()
        if extension not in wanted:
            continue
        files.append(
            DataFile(
                path=str(path),
                name=path.name,
                size_bytes=path.stat().st_size,
                extension=extension,
            )
        )
    files.sort(key=lambda f: f.name.lower())
    return files


class FilePreviewError(Exception):
    """Raised when a file's columns cannot be read (missing, unreadable, unsupported)."""


def preview_file(
    path: str,
    sample_rows: int = 0,
    offset: int = 0,
    include_total: bool = False,
    csv_delimiter: str = ",",
) -> FilePreview:
    """Returns table name, columns, and optional sample rows for a file path.

    Resolves the path against ``backend/data/`` to prevent traversal outside
    the data root. With ``sample_rows=0`` only headers/metadata are read.

    Args:
        path (str): The file path to preview.
        sample_rows (int): Number of sample rows to include in the preview.
        offset (int): Skip this many data rows before sampling. Lets callers
            page through a file without loading it whole.
        include_total (bool): When True, also populate ``total_rows`` on the
            response. For CSV this means streaming the file once.

    Returns:
        FilePreview: Metadata and sample rows of the file.

    Raises:
        FilePreviewError: If the file is unreadable or the path is invalid.
    """
    target = Path(path).resolve()
    data_root = _DATA_ROOT.resolve()
    if data_root not in target.parents and target != data_root:
        raise FilePreviewError(f"Path outside data root: {path}")
    return read_file_preview(
        target,
        sample_rows=sample_rows,
        offset=offset,
        include_total=include_total,
        csv_delimiter=csv_delimiter,
    )


def read_file_preview(
    target: Path,
    sample_rows: int = 0,
    offset: int = 0,
    include_total: bool = False,
    csv_delimiter: str = ",",
) -> FilePreview:
    """Reads columns and (optionally) sample rows from a resolved file path.

    Caller is responsible for path-safety checks. Use this when previewing
    files outside ``backend/data/`` (e.g. preprocessed/synthetic outputs).
    """
    if not target.is_file():
        raise FilePreviewError(f"File not found: {target}")

    extension = target.suffix.lstrip(".").lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise FilePreviewError(f"Unsupported extension: {extension!r}")

    n = max(0, int(sample_rows))
    skip = max(0, int(offset))
    columns: list[str] = []
    rows: list[list[str]] = []
    total_rows: int | None = None

    def _stringify(v: object) -> str:
        if v is None:
            return ""
        return str(v)

    try:
        if extension == "csv":
            with open(target, encoding="utf-8", newline="") as fh:
                reader = csv.reader(fh, delimiter=csv_delimiter)
                columns = next(reader, []) or []
                # Skip+sample in one pass; if include_total, keep iterating
                # past the sample to count remaining rows.
                taken = 0
                seen = 0
                for row in reader:
                    if seen < skip:
                        seen += 1
                        continue
                    if taken < n:
                        rows.append([_stringify(c) for c in row])
                        taken += 1
                    elif not include_total:
                        break
                    seen += 1
                if include_total:
                    total_rows = seen
        elif extension == "parquet":
            import pyarrow.parquet as pq

            pf = pq.ParquetFile(str(target))
            columns = list(pf.schema_arrow.names)
            if include_total:
                total_rows = pf.metadata.num_rows
            if n > 0:
                # iter_batches lets us skip whole batches cheaply, then trim
                # inside the first relevant one.
                remaining_skip = skip
                remaining_take = n
                batch_size = max(n, 1024)
                for batch in pf.iter_batches(batch_size=batch_size):
                    if remaining_skip >= batch.num_rows:
                        remaining_skip -= batch.num_rows
                        continue
                    records = batch.to_pylist()
                    if remaining_skip:
                        records = records[remaining_skip:]
                        remaining_skip = 0
                    for record in records[:remaining_take]:
                        rows.append([_stringify(record.get(c)) for c in columns])
                    remaining_take -= len(records[:remaining_take])
                    if remaining_take <= 0:
                        break
        elif extension == "json":
            with open(target, encoding="utf-8") as fh:
                payload = json.load(fh)
            if isinstance(payload, list) and payload and isinstance(payload[0], dict):
                columns = list(payload[0].keys())
                if include_total:
                    total_rows = len(payload)
                if n > 0:
                    for record in payload[skip : skip + n]:
                        rows.append([_stringify(record.get(c)) for c in columns])
            elif isinstance(payload, dict):
                columns = list(payload.keys())
                if include_total:
                    total_rows = 1
                if n > 0 and skip == 0:
                    rows.append([_stringify(payload.get(c)) for c in columns])
        elif extension in ["xls", "xlsx"]:
            import pandas as pd

            df = pd.read_excel(target)
            columns = [str(c) for c in df.columns]
            if include_total:
                total_rows = len(df)
            if n > 0:
                for _, record in df.iloc[skip : skip + n].iterrows():
                    rows.append([_stringify(record.get(c)) for c in columns])
    except Exception as e:
        raise FilePreviewError(str(e)) from e

    return FilePreview(
        path=str(target),
        table=target.stem,
        columns=[str(c) for c in columns],
        rows=rows,
        total_rows=total_rows,
    )


def get_files_from_directory(directory: str) -> list[str]:
    """Gets the list of supported files from a directory.

    Args:
        directory (str): Path to the directory.

    Returns:
        list[str]: List of file paths with supported formats.

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
