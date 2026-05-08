"""Pydantic schemas for pipeline-related API responses."""

from typing import Any

from pydantic import BaseModel, Field


class PipelineSummary(BaseModel):
    """Summary of a pipeline session returned by the catalog."""

    pipeline_id: str
    status: str
    timestamp: str
    config_path: str = ""
    jobs: list[dict[str, Any]] = []
    # Coarse "Job X of N" progress while ``status == "in_progress"``. ``None``
    # for older runs that did not record it or once the run is terminal.
    progress: dict[str, Any] | None = None


class PipelineCreateRequest(BaseModel):
    """Body of ``POST /pipelines``: path to the YAML pipeline configuration."""

    config_path: str = Field(
        ..., description="Absolute path to the pipeline YAML configuration file."
    )


class PipelineJob(BaseModel):
    """Acknowledgement returned by ``POST /pipelines`` (HTTP 202).

    Clients poll ``GET /pipelines/{pipeline_id}`` to observe progress via the
    ``status`` field (``in_progress`` → ``completed`` / ``partial`` / ``failed``).
    """

    pipeline_id: str
    status: str = "in_progress"


class DeletedPipeline(BaseModel):
    """Confirmation returned after successfully deleting a pipeline.

    Deleting a pipeline cascades to every model and simulation the pipeline
    produced, so the response lists the IDs that were removed along with it.
    """

    deleted_id: str
    deleted_model_ids: list[str] = []
    deleted_simulation_ids: list[str] = []


class CleanupResult(BaseModel):
    """Result of a bulk cleanup operation on the pipelines catalog."""

    deleted_ids: list[str]
    empty: list[str]
    orphans: list[str]


# ---------------------------------------------------------------------------
# Pipeline-config (YAML) authoring schemas — used by the dev-mode UI builder.
# These let the frontend save a designed pipeline to disk without forcing the
# user to know the absolute filesystem path.
# ---------------------------------------------------------------------------


class PipelineConfigFile(BaseModel):
    """A pipeline YAML file available to launch."""

    name: str  # filename stem, e.g. "my_pipeline"
    filename: str  # full filename, e.g. "my_pipeline.yaml"
    path: str  # absolute path on disk
    size_bytes: int


class PipelineConfigContent(PipelineConfigFile):
    """Full YAML text of a pipeline config file."""

    content: str


class PipelineConfigSaveRequest(BaseModel):
    """Body of ``PUT /pipelines/configs/{name}``."""

    content: str = Field(..., description="Raw YAML content of the pipeline.")


class PipelineConfigSnapshot(BaseModel):
    """Configuration snapshots archived alongside a pipeline run.

    The ``PipelineTracker`` copies the launched YAML and freezes a small set of
    ``general_config`` constants under ``<pipeline_folder>/configs/``. The UI
    fetches this so users can inspect what actually ran without opening files
    on the server.
    """

    pipeline_id: str
    config_path: str = ""
    pipeline_config_yaml: str | None = None
    pipeline_config: dict[str, Any] | None = None
    general_config: dict[str, Any] | None = None
