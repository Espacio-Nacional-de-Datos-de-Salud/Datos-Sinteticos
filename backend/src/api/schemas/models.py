"""Pydantic schemas for model-related API responses."""

from pydantic import BaseModel, Field

from backend.src.api.schemas.jobs import JobProgress
from backend.src.domain.id_validation import INSPECTION_ID_PATTERN


class ModelSummary(BaseModel):
    """Summary of a trained model returned by the catalog."""

    model_id: str
    model_name: str | None = None
    status: str = ""
    timestamp: str = ""
    timestamp_ms: int | None = None
    tables: str = ""
    train_size: int | None = None
    training_table_sizes: dict[str, int] = {}
    subject_tables: list[str] = []
    accuracy: float | None = None
    qa_report_filename: str | None = None
    progress: JobProgress | None = None
    inspection_id: str | None = None
    brc_id: str | None = None
    brc_name: str | None = None
    duration_seconds: float | None = None
    started_at_ms: int | None = None


class RenameRequest(BaseModel):
    """Body of a rename PATCH endpoint."""

    name: str


class TrainingCreateRequest(BaseModel):
    """Body of ``POST /models``: inputs required to launch a training run.

    Exactly one of ``file_paths`` or ``inspection_id`` must be provided.
    """

    name: str | None = Field(
        default=None,
        description="Optional human-readable name for this training run.",
    )
    file_paths: list[str] | None = Field(
        default=None,
        description="Paths to raw input data files or directories. Mutually exclusive with inspection_id.",
    )
    inspection_id: str | None = Field(
        default=None,
        description="ID of a completed inspection to train from. Mutually exclusive with file_paths.",
        pattern=INSPECTION_ID_PATTERN,
    )
    brc_id: str | None = Field(
        default=None,
        description=(
            "Optional ID of a completed business-rules-configuration run. When "
            "provided, training reads the already-PRE-applied parquet from the BRC "
            "folder (instead of re-applying rules in vivo). Requires inspection_id."
        ),
    )
    mostly_config_path: str | None = Field(
        default=None,
        description="Override for the Mostly AI config path; uses server default when omitted.",
    )
    rules_config_path: str | None = Field(
        default=None,
        description="Override for the rules config path; uses server default when omitted.",
    )
    enable_data_profiling: bool = Field(
        default=False,
        description="Whether to run data profiling during preprocessing (only with file_paths).",
    )
    csv_delimiter: str = Field(
        default=",",
        description="Delimiter used when parsing CSV files (only with file_paths).",
    )


class TrainingJob(BaseModel):
    """Acknowledgement returned by ``POST /models`` (HTTP 202).

    Clients poll ``GET /models/{model_id}`` to observe progress via the
    ``status`` field.
    """

    model_id: str
    status: str = "in_progress"


class DeletedModel(BaseModel):
    """Confirmation returned after successfully deleting a model."""

    deleted_id: str
    deleted_simulation_ids: list[str] = []
    deleted_evaluation_ids: list[str] = []


class CleanupResult(BaseModel):
    """Result of a bulk cleanup operation on the models catalog."""

    deleted_ids: list[str]
    empty: list[str]
    orphans: list[str]
    skipped_ids: list[str] = []
