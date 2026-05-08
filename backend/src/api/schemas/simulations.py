"""Pydantic schemas for simulation-related API responses."""

from backend.src.api.schemas.jobs import JobProgress
from backend.src.config.general import SYNTHETIC_DATA_FILE_FORMATS
from backend.src.core.validation import MODEL_ID_PATTERN
from pydantic import BaseModel, Field


class SimulationSummary(BaseModel):
    """Summary of a simulation run returned by the catalog."""

    simulation_id: str
    simulation_name: str | None = None
    status: str = ""
    timestamp: str = ""
    model_id: str | None = None
    sample_size: int | None = None
    tables: str = ""
    training_table_sizes: dict[str, int] = {}
    model_accuracy: float | None = None
    progress: JobProgress | None = None


class RenameRequest(BaseModel):
    """Body of a rename PATCH endpoint."""

    name: str


class SimulationCreateRequest(BaseModel):
    """Body of ``POST /simulations``: inputs required to launch a simulation run."""

    model_id: str = Field(
        ...,
        description="ID of the trained model to simulate from.",
        pattern=MODEL_ID_PATTERN,
    )
    sample_size: int | None = Field(
        default=None,
        gt=0,
        description="Number of synthetic records to generate. Uses model default when omitted.",
    )
    synthetic_data_file_format: str | None = Field(
        default=None,
        description="Synthetic output table format for this simulation run.",
        pattern=f"^({'|'.join(SYNTHETIC_DATA_FILE_FORMATS)})$",
    )


class SimulationJob(BaseModel):
    """Acknowledgement returned by ``POST /simulations`` (HTTP 202).

    Clients poll ``GET /simulations/{simulation_id}`` to observe progress via
    the ``status`` field.
    """

    simulation_id: str
    status: str = "in_progress"


class EvaluationJob(BaseModel):
    """Acknowledgement returned by ``POST /simulations/{id}/evaluate`` (HTTP 202).

    Results land in ``outputs/simulations/{simulation_id}/evaluation/`` once
    completed. Poll via ``GET /simulations/{simulation_id}/download/evaluation``
    (returns 404 while running, 200 once done).
    """

    simulation_id: str
    status: str = "submitted"


class DeletedSimulation(BaseModel):
    """Confirmation returned after successfully deleting a simulation."""

    deleted_id: str


class CleanupResult(BaseModel):
    """Result of a bulk cleanup operation on the simulations catalog."""

    deleted_ids: list[str]
    empty: list[str]
    orphans: list[str]
    skipped_ids: list[str] = []
