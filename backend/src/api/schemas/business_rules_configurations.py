"""Pydantic schemas for the business-rules-configuration (BRC) API."""

from pydantic import BaseModel, Field

from backend.src.api.schemas.jobs import JobProgress


class BRCRuleWarning(BaseModel):
    """Advisory raised while loading or applying a rule during the BRC run."""

    rule: str | None = None
    table: str | None = None
    column: str | None = None
    constraint: str | None = None
    message: str


class BRCSummary(BaseModel):
    """Catalogue entry for a BRC run."""

    brc_id: str
    brc_name: str = ""
    inspection_id: str = ""
    status: str = ""
    timestamp: str = ""
    timestamp_ms: int | None = None
    tables: dict[str, int] = {}
    new_columns: dict[str, list[str]] = {}
    excluded_columns: dict[str, list[str]] = {}
    rules_excluded_columns: dict[str, list[str]] = {}
    rules_count: int = 0
    warnings: list[BRCRuleWarning] = []
    progress: JobProgress | None = None
    duration_seconds: float | None = None
    started_at_ms: int | None = None
    error_message: str | None = None


class BRCCreateRequest(BaseModel):
    """Body of ``POST /business-rules-configurations``."""

    inspection_id: str = Field(
        ...,
        description="Source upload (inspection) id whose preprocessed data is the input.",
    )
    name: str | None = Field(
        default=None,
        max_length=100,
        description="Optional human-readable name for this run.",
    )
    rules_config_path: str | None = Field(
        default=None,
        description=(
            "Override for the rules YAML path; when null, the server resolves the "
            "current ``rules`` config (override if present, else default)."
        ),
    )
    enable_profiling: bool = Field(
        default=True,
        description="Whether to generate ydata-profiling reports for the new columns.",
    )


class BRCJob(BaseModel):
    """HTTP 202 ack for ``POST /business-rules-configurations``."""

    brc_id: str


class BRCRenameRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class BRCProfilingReport(BaseModel):
    table: str
    filename: str


class BRCProfilingReports(BaseModel):
    brc_id: str
    reports: list[BRCProfilingReport] = []


class BRCDeletedResponse(BaseModel):
    brc_id: str
    deleted: bool = True
