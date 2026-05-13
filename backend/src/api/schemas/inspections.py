"""Pydantic schemas for inspection-related API responses."""

from pydantic import BaseModel, Field

from backend.src.api.schemas.jobs import JobProgress


class InspectionSummary(BaseModel):
    """Summary of a data inspection session returned by the catalog."""

    inspection_id: str
    inspection_name: str = ""
    status: str = ""
    timestamp: str = ""
    tables: dict[str, int] = {}
    file_paths: list[str] = []
    progress: JobProgress | None = None


class InspectionCreateRequest(BaseModel):
    """Body of ``POST /inspections``: inputs required to launch an inspection run."""

    file_paths: list[str] = Field(
        ...,
        min_length=1,
        description="Paths to raw input data files or directories.",
    )
    mostly_config_path: str | None = Field(
        default=None,
        description=(
            "Override for the Mostly AI config path; when null, the server uses "
            "the resolved ``mostly_ai`` config (override if present, else default)."
        ),
    )
    rules_config_path: str | None = Field(
        default=None,
        description=(
            "Override for the rules config path; when null, the server uses "
            "the resolved ``rules`` config (override if present, else default)."
        ),
    )
    enable_data_profiling: bool = Field(
        default=False,
        description="Whether to run data profiling during preprocessing.",
    )
    csv_delimiter: str = Field(default=",", description="Delimiter used when parsing CSV files.")
    excluded_columns: dict[str, list[str]] = Field(
        default_factory=dict,
        description=(
            "Optional per-table column exclusion list (table name → list of column names). "
            "Listed columns are stripped from the autodetect metadata and the cached "
            "preprocessed data after the inspection run, so they are invisible to "
            "training and all downstream pipeline steps."
        ),
    )


class InspectionJob(BaseModel):
    """Acknowledgement returned by ``POST /inspections`` (HTTP 202).

    The run executes in the background; clients poll ``GET /inspections/{id}``
    to observe progress via the ``status`` field of the inspection card.
    """

    inspection_id: str
    status: str = "in_progress"


class RenameRequest(BaseModel):
    """Body of a rename PATCH endpoint."""

    name: str


class DeletedInspection(BaseModel):
    """Confirmation returned after successfully deleting an inspection."""

    deleted_id: str


class ForeignKey(BaseModel):
    """An autodetected foreign-key relationship between two tables."""

    parent: str
    child: str
    fk_column: str
    pk_column: str
    is_context: bool = False
    direct: bool = False


class Relationships(BaseModel):
    """Primary keys (one per table) and foreign-key edges."""

    pks: dict[str, str] = {}
    fks: list[ForeignKey] = []


class Autodetect(BaseModel):
    """Contents of ``inspection_metadata.json`` — the editable source of truth
    for an inspection's schema.

    ``encoding_types`` maps ``table -> column -> type`` where type is one of
    the MostlyAI labels (``TABULAR_NUMERIC_AUTO``, ``TABULAR_CATEGORICAL``,
    ``TABULAR_DATETIME``, ``TABULAR_CHARACTER``, ...).
    """

    relationships: Relationships = Relationships()
    encoding_types: dict[str, dict[str, str]] = {}


class ProfilingReport(BaseModel):
    """A single per-table ydata-profiling HTML report."""

    table: str
    filename: str


class ProfilingReports(BaseModel):
    """List of available profiling reports for an inspection."""

    inspection_id: str
    reports: list[ProfilingReport] = []


class CleanupResult(BaseModel):
    """Result of a bulk cleanup operation on the inspections catalog."""

    deleted_ids: list[str]
    empty: list[str]
    orphans: list[str]
    duplicates: list[str] = []
    skipped_ids: list[str] = []
