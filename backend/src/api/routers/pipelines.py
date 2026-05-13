"""Endpoints for pipeline sessions."""

import json
import os
import re

import yaml
from backend.src.api.schemas import CancelResponse
from backend.src.api.schemas.pipelines import (
    DeletedPipeline,
    PipelineConfigContent,
    PipelineConfigFile,
    PipelineConfigSaveRequest,
    PipelineConfigSnapshot,
    PipelineCreateRequest,
    PipelineJob,
    PipelineSummary,
)
from backend.src.config.general import CONFIG_DIR, PIPELINE_CARD_FILENAME, PIPELINES_DIR
from backend.src.infrastructure.cancellation import register as register_cancel
from backend.src.infrastructure.cancellation import request_cancel
from backend.src.runs.card_io import update_card_status
from backend.src.runs.catalog.downloads import (
    build_full_pipeline_bundle,
    build_pipeline_with_jobs_bundle,
    build_zip_stream,
)
from backend.src.runs.catalog.pipelines import (
    delete_pipeline as delete_pipeline_catalog,
)
from backend.src.runs.catalog.pipelines import (
    list_available_pipelines,
)
from backend.src.infrastructure.errors import PipelineNotFoundError
from backend.src.domain.id_validation import PipelineId
from backend.src.sessions.pipeline import initialize_pipeline_session, run_pipeline_from_config
from fastapi import APIRouter, BackgroundTasks, HTTPException, status
from fastapi.responses import StreamingResponse

_TERMINAL_STATUSES = {"completed", "partial", "failed", "cancelled"}

# Pipeline YAML configs designed in the dev-mode UI live here. The dir mirrors
# the layout used by the CLI so launching from either entry point is identical.
_PIPELINE_CONFIG_DIR = os.path.join(str(CONFIG_DIR), "pipelines")
_PIPELINE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _pipeline_config_path(name: str) -> str:
    """Resolve a pipeline-config name to its absolute YAML path on disk.

    The name must match ``[A-Za-z0-9_-]+`` and is forbidden from traversing
    out of ``backend/config/pipelines/``.
    """
    if not _PIPELINE_NAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="Pipeline name must be alphanumeric (dashes/underscores allowed).",
        )
    abs_path = os.path.abspath(os.path.join(_PIPELINE_CONFIG_DIR, f"{name}.yaml"))
    if not abs_path.startswith(os.path.abspath(_PIPELINE_CONFIG_DIR) + os.sep):
        raise HTTPException(status_code=400, detail="Invalid pipeline name.")
    return abs_path


router = APIRouter(prefix="/pipelines", tags=["Pipelines"])


@router.get("/", response_model=list[PipelineSummary])
def get_pipelines() -> list[dict]:
    """Returns all pipeline sessions available in the catalog."""
    return list_available_pipelines()


# ---------------------------------------------------------------------------
# /pipelines/configs — CRUD on user-authored pipeline YAML files.
# Defined BEFORE the ``/{pipeline_id}`` routes so FastAPI matches them first.
# ---------------------------------------------------------------------------


@router.get("/configs", response_model=list[PipelineConfigFile])
def list_pipeline_configs() -> list[PipelineConfigFile]:
    """List every pipeline YAML present under ``backend/config/pipelines/``.

    Skips the committed ``*.example.yaml`` templates and the ``rules/``
    subfolder — only authored pipeline definitions are returned.
    """
    if not os.path.isdir(_PIPELINE_CONFIG_DIR):
        return []
    out: list[PipelineConfigFile] = []
    for entry in sorted(os.listdir(_PIPELINE_CONFIG_DIR)):
        if not entry.endswith(".yaml") or entry.endswith(".example.yaml"):
            continue
        abs_path = os.path.join(_PIPELINE_CONFIG_DIR, entry)
        if not os.path.isfile(abs_path):
            continue
        out.append(
            PipelineConfigFile(
                name=entry[: -len(".yaml")],
                filename=entry,
                path=abs_path,
                size_bytes=os.path.getsize(abs_path),
            )
        )
    return out


@router.get("/configs/{name}", response_model=PipelineConfigContent)
def get_pipeline_config(name: str) -> PipelineConfigContent:
    """Read a single pipeline YAML file by its name (filename stem)."""
    path = _pipeline_config_path(name)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail=f"Pipeline config '{name}' not found.")
    with open(path, encoding="utf-8") as fh:
        content = fh.read()
    return PipelineConfigContent(
        name=name,
        filename=f"{name}.yaml",
        path=path,
        size_bytes=os.path.getsize(path),
        content=content,
    )


@router.put("/configs/{name}", response_model=PipelineConfigContent)
def save_pipeline_config(name: str, payload: PipelineConfigSaveRequest) -> PipelineConfigContent:
    """Create or overwrite a pipeline YAML file.

    The body is YAML-validated and required to have a top-level ``jobs`` list
    so that downstream ``load_pipeline_config`` won't reject it later.
    """
    path = _pipeline_config_path(name)
    try:
        parsed = yaml.safe_load(payload.content)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {exc}") from None
    if not isinstance(parsed, dict) or "jobs" not in parsed:
        raise HTTPException(
            status_code=400,
            detail="Pipeline YAML must define a top-level 'jobs' list.",
        )
    os.makedirs(_PIPELINE_CONFIG_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(payload.content)
    return get_pipeline_config(name)


@router.delete("/configs/{name}", status_code=204)
def delete_pipeline_config(name: str) -> None:
    """Delete a pipeline YAML file. No-op if it does not exist."""
    path = _pipeline_config_path(name)
    if os.path.isfile(path):
        os.remove(path)
    return None


@router.post(
    "/",
    response_model=PipelineJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_pipeline(
    request: PipelineCreateRequest,
    background_tasks: BackgroundTasks,
) -> PipelineJob:
    """Launches a pipeline run from a YAML configuration file asynchronously.

    The session folder and its ``in_progress`` card are created synchronously
    so the returned ``pipeline_id`` is immediately queryable via
    ``GET /pipelines/{pipeline_id}``. The pipeline jobs run in the background;
    clients poll that endpoint to observe the ``status`` transition to
    ``completed``, ``partial``, or ``failed``.
    """
    session = initialize_pipeline_session(config_path=request.config_path)
    cancel_event = register_cancel(session.pipeline_id)
    background_tasks.add_task(
        run_pipeline_from_config,
        config_path=request.config_path,
        session=session,
        cancel_event=cancel_event,
    )
    return PipelineJob(pipeline_id=session.pipeline_id, status="in_progress")


@router.get("/{pipeline_id}/configs", response_model=PipelineConfigSnapshot)
def get_pipeline_run_configs(pipeline_id: PipelineId) -> PipelineConfigSnapshot:
    """Return the config snapshots archived with a pipeline run.

    The tracker copies the launched YAML to
    ``<pipeline_folder>/configs/pipeline_config.yaml`` and writes a JSON
    snapshot of relevant ``general_config`` constants beside it. We expose
    both — raw YAML text plus a parsed dict — so the UI can render a readable
    summary instead of forcing the user to open files on the server.
    """
    folder = os.path.join(PIPELINES_DIR, pipeline_id)
    card_path = os.path.join(folder, PIPELINE_CARD_FILENAME)
    if not os.path.isdir(folder) or not os.path.isfile(card_path):
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found.")

    with open(card_path, encoding="utf-8") as fh:
        card = json.load(fh)

    snapshot_dir = os.path.join(folder, "configs")
    pipeline_yaml_path = os.path.join(snapshot_dir, "pipeline_config.yaml")
    general_json_path = os.path.join(snapshot_dir, "general_config.json")

    pipeline_yaml: str | None = None
    pipeline_parsed: dict | None = None
    if os.path.isfile(pipeline_yaml_path):
        with open(pipeline_yaml_path, encoding="utf-8") as fh:
            pipeline_yaml = fh.read()
        try:
            parsed = yaml.safe_load(pipeline_yaml)
            if isinstance(parsed, dict):
                pipeline_parsed = parsed
        except yaml.YAMLError:
            pipeline_parsed = None

    general: dict | None = None
    if os.path.isfile(general_json_path):
        try:
            with open(general_json_path, encoding="utf-8") as fh:
                loaded = json.load(fh)
            if isinstance(loaded, dict):
                general = loaded
        except (OSError, json.JSONDecodeError):
            general = None

    return PipelineConfigSnapshot(
        pipeline_id=pipeline_id,
        config_path=card.get("config_path", "") or "",
        pipeline_config_yaml=pipeline_yaml,
        pipeline_config=pipeline_parsed,
        general_config=general,
    )


@router.get("/{pipeline_id}", response_model=PipelineSummary)
def get_pipeline(pipeline_id: PipelineId) -> dict:
    """Returns the details of a single pipeline session by its ID."""
    for pipeline in list_available_pipelines():
        if pipeline["pipeline_id"] == pipeline_id:
            return pipeline
    raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found.")


# NOTE: /{pipeline_id}/download/with-jobs must be defined before /{pipeline_id}/download
# so FastAPI matches the more specific path first.
@router.get(
    "/{pipeline_id}/download/with-jobs",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_pipeline_with_jobs(pipeline_id: PipelineId) -> StreamingResponse:
    """Downloads the pipeline folder plus every model and simulation it produced.

    The archive is laid out as ``<pipeline_id>/`` for the pipeline folder,
    ``models/<model_id>/`` for each produced model, and
    ``simulations/<simulation_id>/`` for each produced simulation. Artifacts
    no longer present on disk are silently skipped.
    """
    try:
        bundle = build_pipeline_with_jobs_bundle(pipeline_id)
    except PipelineNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Pipeline '{pipeline_id}' not found."
        ) from None

    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle.archive_name}"'},
    )


@router.get(
    "/{pipeline_id}/download",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_pipeline_folder(pipeline_id: PipelineId) -> StreamingResponse:
    """Downloads the entire pipeline folder as a zip archive."""
    try:
        bundle = build_full_pipeline_bundle(pipeline_id)
    except PipelineNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Pipeline '{pipeline_id}' not found."
        ) from None

    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle.archive_name}"'},
    )


@router.post("/{pipeline_id}/cancel", response_model=CancelResponse)
def cancel_pipeline(pipeline_id: PipelineId) -> CancelResponse:
    """Request cancellation of an in-progress pipeline.

    Safe to call on a finished pipeline — returns the current status with a
    ``"job already finished"`` message instead of an error.
    """
    card_path = os.path.join(PIPELINES_DIR, pipeline_id, PIPELINE_CARD_FILENAME)
    if not os.path.exists(card_path):
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found.")

    with open(card_path, encoding="utf-8") as fh:
        current_status = json.load(fh).get("status", "unknown")

    if current_status in _TERMINAL_STATUSES:
        return CancelResponse(id=pipeline_id, status=current_status, message="job already finished")

    update_card_status(card_path, "cancelled")
    request_cancel(pipeline_id)
    return CancelResponse(id=pipeline_id, status="cancelled", message="cancellation requested")


@router.delete("/{pipeline_id}", response_model=DeletedPipeline)
def delete_pipeline(pipeline_id: PipelineId) -> DeletedPipeline:
    """Deletes a pipeline session and **cascades** to every model and
    simulation folder it produced.

    A pipeline represents a grouped batch of training/simulation runs, so
    deletion removes every artifact referenced in its card alongside the
    pipeline folder itself. Unlike ``DELETE /models/{id}`` the operation
    does not return ``409`` for linked artifacts — cascading is the point.
    """
    outcome = delete_pipeline_catalog(pipeline_id)
    if not outcome.found:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pipeline_id}' not found.")
    return DeletedPipeline(
        deleted_id=pipeline_id,
        deleted_model_ids=outcome.deleted_model_ids,
        deleted_simulation_ids=outcome.deleted_simulation_ids,
    )
