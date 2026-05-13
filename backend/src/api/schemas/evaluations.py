"""Pydantic schemas for evaluation endpoints."""

from backend.src.api.schemas.jobs import JobProgress
from backend.src.domain.id_validation import SIMULATION_ID_PATTERN
from pydantic import BaseModel, Field


class EvaluationCreateRequest(BaseModel):
    """Payload to start a synthetic data evaluation asynchronously."""

    simulation_id: str = Field(
        ...,
        description="ID of the completely generated simulation.",
        pattern=SIMULATION_ID_PATTERN,
    )


class EvaluationSummary(BaseModel):
    """Summary of a single evaluation run."""

    evaluation_id: str
    evaluation_name: str | None = None
    status: str
    timestamp: str
    simulation_id: str | None = None
    model_id: str | None = None
    pipeline_id: str | None = None
    job_name: str | None = None
    metrics_evaluated: list[str] | None = None
    progress: JobProgress | None = None


class RenameRequest(BaseModel):
    """Body of a rename PATCH endpoint."""

    name: str


class EvaluationJob(BaseModel):
    """Response representing a newly launched evaluation job."""

    evaluation_id: str = Field(..., description="The unique ID of the new evaluation session.")
    status: str = Field(..., description="Initial status, usually 'in_progress'.")


class CleanupResult(BaseModel):
    """Summary of the cleanup operation."""

    deleted_ids: list[str]
    empty: list[str]
    orphans: list[str]


class DeletedEvaluation(BaseModel):
    """Response indicating a successful deletion."""

    deleted_id: str
