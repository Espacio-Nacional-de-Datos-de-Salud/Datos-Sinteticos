"""Pydantic schemas for the /files discovery endpoint."""

from pydantic import BaseModel


class DataFile(BaseModel):
    """A data file available under ``backend/data/``.

    The API exposes this so the frontend can let the user pick input files
    without having to know absolute server-side paths (which differ between
    Docker and local runs).
    """

    path: str
    name: str
    size_bytes: int
    extension: str


class FilePreview(BaseModel):
    """Lightweight schema preview for a single data file.

    Read by inspecting only the file's header (CSV) or schema metadata
    (parquet/JSON), so the rules editor can offer table/column dropdowns
    before a full inspection has run.
    """

    path: str
    table: str
    columns: list[str]
    # Sample rows as lists of stringified values, aligned with ``columns``.
    # Empty when the caller did not request rows or the file has none.
    rows: list[list[str]] = []


class FilePreviewRequest(BaseModel):
    paths: list[str]
    # Number of sample rows to return per file. 0 = headers only.
    sample_rows: int = 0
