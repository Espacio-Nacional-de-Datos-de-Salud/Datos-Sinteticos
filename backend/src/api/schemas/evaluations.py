"""Pydantic schemas for evaluation endpoints."""

from typing import Any

from pydantic import BaseModel, Field

from backend.src.api.schemas.jobs import JobProgress
from backend.src.domain.id_validation import SIMULATION_ID_PATTERN


class TableEvaluationConfig(BaseModel):
    """Per-table evaluation config.

    Each evaluated table is assessed independently (the evaluation is
    single-table). ``config`` is a full evaluation-config object (same shape as
    ``evaluation.yaml``), seeded on the frontend from the global config and then
    tweaked for this table. Any key it omits falls back to the global default.
    """

    table: str = Field(..., description="Synthetic table to evaluate.")
    config: dict[str, Any] | None = Field(
        default=None,
        description=(
            "Full per-table evaluation config (evaluation.yaml shape). "
            "None ⇒ global config for every field."
        ),
    )


class EvaluationCreateRequest(BaseModel):
    """Payload to start a synthetic data evaluation asynchronously."""

    name: str | None = Field(
        default=None,
        max_length=100,
        description="Optional human-readable name for this evaluation run.",
    )
    simulation_id: str = Field(
        ...,
        description="ID of the completely generated simulation.",
        pattern=SIMULATION_ID_PATTERN,
    )
    evaluated_tables: list[TableEvaluationConfig] | None = Field(
        default=None,
        description=(
            "Per-table evaluation configs (one report per table). Defaults to the "
            "master table with global settings when omitted."
        ),
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
    duration_seconds: float | None = None
    started_at_ms: int | None = None
    error_message: str | None = None


class RenameRequest(BaseModel):
    """Body of a rename PATCH endpoint."""

    name: str = Field(..., min_length=1, max_length=100)


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


class EvaluationTables(BaseModel):
    """Per-table reports available for an evaluation (one report per table)."""

    evaluation_id: str
    tables: list[str]
