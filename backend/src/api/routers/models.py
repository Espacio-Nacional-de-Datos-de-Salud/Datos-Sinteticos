"""Endpoints for trained models."""

import json
import os
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Path, Query, status
from fastapi.responses import FileResponse, StreamingResponse

from backend.src.api.schemas import CancelResponse, TimeProfilingReport, load_time_profiling_report
from backend.src.api.schemas.models import (
    CleanupResult,
    DeletedModel,
    ModelSummary,
    RenameRequest,
    TrainingCreateRequest,
    TrainingJob,
)
from backend.src.config.general import MODEL_CARD_FILENAME, MODELS_DIR
from backend.src.domain.id_validation import ModelId
from backend.src.infrastructure.cancellation import register as register_cancel
from backend.src.infrastructure.cancellation import request_cancel
from backend.src.infrastructure.errors import (
    GeneratorEssentialsIncompleteError,
    ModelNotFoundError,
)
from backend.src.runs.card_io import update_card_status
from backend.src.runs.catalog.downloads import (
    build_full_model_bundle,
    build_generator_essentials_bundle,
    build_zip_stream,
)
from backend.src.runs.catalog.models import (
    cleanup_models as cleanup_models_catalog,
)
from backend.src.runs.catalog.models import (
    delete_model as delete_model_catalog,
)
from backend.src.runs.catalog.models import (
    list_available_models,
    list_model_column_types,
    list_model_column_values,
    list_model_columns,
)
from backend.src.runs.catalog.models import (
    purge_all_models as purge_all_models_catalog,
)
from backend.src.runs.catalog.models import (
    rename_model as rename_model_catalog,
)
from backend.src.sessions.configs import resolve_config_path
from backend.src.sessions.training import (
    initialize_training_session,
    run_training_flow,
    run_training_flow_from_inspection,
)

_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

router = APIRouter(prefix="/models", tags=["Models"])


@router.get("/", response_model=list[ModelSummary])
def get_models() -> list[dict]:
    """Returns all trained models available in the catalog."""
    return list_available_models()


@router.post(
    "/",
    response_model=TrainingJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_training(
    request: TrainingCreateRequest,
    background_tasks: BackgroundTasks,
) -> TrainingJob:
    """Launches a new training run asynchronously.

    Provide either ``file_paths`` (train from raw data) or ``inspection_id``
    (train from a completed inspection). Exactly one must be set.

    The session folder and its ``in_progress`` card are created synchronously
    so the returned ``model_id`` is immediately queryable via
    ``GET /models/{model_id}``. Clients poll that endpoint to observe the
    ``status`` transition to ``completed`` or ``failed``.
    """
    if request.file_paths is None and request.inspection_id is None:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'file_paths' or 'inspection_id'.",
        )
    if request.file_paths is not None and request.inspection_id is not None:
        raise HTTPException(
            status_code=422,
            detail="Provide either 'file_paths' or 'inspection_id', not both.",
        )

    session = initialize_training_session(name=request.name)
    cancel_event = register_cancel(session.model_id)

    if request.inspection_id is not None:
        background_tasks.add_task(
            run_training_flow_from_inspection,
            inspection_id=request.inspection_id,
            brc_id=request.brc_id,
            skip_rules=request.brc_id is None,
            session=session,
            cancel_event=cancel_event,
        )
    else:
        background_tasks.add_task(
            run_training_flow,
            file_paths=request.file_paths,
            mostly_config_path=request.mostly_config_path or str(resolve_config_path("mostly_ai")),
            rules_config_path=request.rules_config_path or str(resolve_config_path("rules")),
            enable_data_profiling=request.enable_data_profiling,
            csv_delimiter=request.csv_delimiter,
            session=session,
            cancel_event=cancel_event,
        )

    return TrainingJob(model_id=session.model_id, status="in_progress")


# NOTE: /cleanup must be defined before /{model_id} so FastAPI does not
# treat the literal string "cleanup" as a model_id path parameter.
@router.delete("/cleanup", response_model=CleanupResult)
def cleanup_models(
    mode: Literal["empty", "orphans", "both"] = Query(
        default="both",
        description=(
            "**empty** — completely empty folders (no files at all). "
            "**orphans** — folders with content but dead: status='failed', "
            "no card but started more than stale_hours ago, "
            "or status='in_progress' started more than stale_hours ago. "
            "**both** — runs both (default)."
        ),
    ),
    stale_hours: int = Query(
        default=24,
        ge=1,
        description=(
            "Minimum age in hours (measured from the folder timestamp) before a run "
            "without a completed status is considered orphaned."
        ),
    ),
) -> CleanupResult:
    """Bulk-deletes model folders that are empty or dead (orphaned runs).

    Models with linked simulations are skipped and reported in ``skipped_ids``.
    Use ``DELETE /models/{model_id}`` to handle those individually.
    """
    deleted_empty, deleted_orphans, skipped = cleanup_models_catalog(
        mode=mode, stale_hours=stale_hours
    )

    all_deleted = deleted_empty + deleted_orphans
    return CleanupResult(
        deleted_ids=all_deleted,
        empty=deleted_empty,
        orphans=deleted_orphans,
        skipped_ids=skipped,
    )


@router.delete("/purge", response_model=CleanupResult)
def purge_models() -> CleanupResult:
    """Delete every model folder regardless of status (destructive)."""
    deleted = purge_all_models_catalog()
    return CleanupResult(deleted_ids=deleted, empty=[], orphans=[], skipped_ids=[])


@router.post("/{model_id}/cancel", response_model=CancelResponse)
def cancel_model(model_id: ModelId) -> CancelResponse:
    """Request cancellation of an in-progress training run.

    Safe to call on a finished model — returns the current status with a
    ``"job already finished"`` message instead of an error.
    """
    card_path = os.path.join(MODELS_DIR, model_id, MODEL_CARD_FILENAME)
    if not os.path.exists(card_path):
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")

    with open(card_path, encoding="utf-8") as fh:
        current_status = json.load(fh).get("status", "unknown")

    if current_status in _TERMINAL_STATUSES:
        return CancelResponse(id=model_id, status=current_status, message="job already finished")

    update_card_status(card_path, "cancelled")
    request_cancel(model_id)
    return CancelResponse(id=model_id, status="cancelled", message="cancellation requested")


@router.patch("/{model_id}/name", response_model=ModelSummary)
def rename_model(model_id: ModelId, body: RenameRequest) -> dict:
    """Updates the human-readable name stored in the model card."""
    if not rename_model_catalog(model_id, body.name):
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    for model in list_available_models():
        if model["model_id"] == model_id:
            return model
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")


@router.get("/{model_id}", response_model=ModelSummary)
def get_model(model_id: ModelId) -> dict:
    """Returns the details of a single trained model by its ID."""
    for model in list_available_models():
        if model["model_id"] == model_id:
            return model
    raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")


@router.get("/{model_id}/time-profiling", response_model=TimeProfilingReport)
def get_model_time_profiling(model_id: ModelId) -> TimeProfilingReport:
    """Returns the structured per-phase timing breakdown of a training run."""
    folder = os.path.join(MODELS_DIR, model_id)
    if not os.path.isdir(folder):
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    report = load_time_profiling_report(folder)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No time profiling report for model '{model_id}'.",
        )
    return report


@router.delete("/{model_id}", response_model=DeletedModel)
def delete_model(
    model_id: ModelId,
    mode: Literal["safe", "force", "cascade"] = Query(
        default="safe",
        description=(
            "**safe** — refuse (409) when linked simulations exist. "
            "**force** — delete the model only, leaving its simulations orphaned. "
            "**cascade** — delete the model, its simulations, and their evaluations."
        ),
    ),
) -> DeletedModel:
    """Deletes a trained model and all its stored artifacts.

    With ``mode=safe`` (default), returns 409 if the model has linked
    simulations. Use ``mode=force`` or ``mode=cascade`` to delete anyway.
    """
    outcome = delete_model_catalog(model_id, mode=mode)
    if outcome.status == "not_found":
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")
    if outcome.status == "has_linked_simulations":
        linked_count = len(outcome.linked_simulation_ids)
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"El modelo '{model_id}' tiene {linked_count} generación(es) asociada(s)."
                ),
                "linked_simulation_ids": outcome.linked_simulation_ids,
            },
        )
    return DeletedModel(
        deleted_id=model_id,
        deleted_simulation_ids=outcome.deleted_simulation_ids,
        deleted_evaluation_ids=outcome.deleted_evaluation_ids,
    )


@router.get("/{model_id}/columns", response_model=dict[str, list[str]])
def get_model_columns(model_id: ModelId) -> dict[str, list[str]]:
    """Returns ``{table: [columns]}`` for a trained model.

    Lets the conditional-generation UI populate column dropdowns before any
    simulation exists.
    """
    try:
        return list_model_columns(model_id)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.get("/{model_id}/columns/types", response_model=dict[str, dict[str, str]])
def get_model_column_types(model_id: ModelId) -> dict[str, dict[str, str]]:
    """Returns ``{table: {column: kind}}`` for a trained model.

    ``kind`` is ``numeric``, ``datetime`` or ``categorical``. The
    conditional-generation UI uses it to offer only the constraint types that
    fit a column. Returns an empty dict when encoding metadata is unavailable.
    """
    return list_model_column_types(model_id)


@router.get(
    "/{model_id}/columns/{column}/values",
    response_model=list[str],
)
def get_model_column_values(
    model_id: ModelId,
    column: str,
    table: str = Query(..., description="Table name the column belongs to."),
    limit: int = Query(200, ge=1, le=1000),
) -> list[str]:
    """Returns up to ``limit`` distinct values for ``column`` in ``table``.

    Reads from the model's original training data, sorted by frequency
    descending. Used to seed the value dropdown in the conditional-generation
    drawer.
    """
    try:
        return list_model_column_values(model_id, table=table, column=column, limit=limit)
    except ModelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


# NOTE: /{model_id}/download/generator must be defined before /{model_id}/download
# so FastAPI matches the more specific path first.
@router.get(
    "/{model_id}/download/generator",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_model_generator(model_id: ModelId) -> StreamingResponse:
    """Downloads the minimum files required to simulate from this model.

    The archive contains ``generator.zip``, ``metadata.json`` and ``rule_manager.json``.
    Returns 409 if the model folder is missing any of those files.
    """
    try:
        bundle = build_generator_essentials_bundle(model_id)
    except ModelNotFoundError:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.") from None
    except GeneratorEssentialsIncompleteError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None

    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle.archive_name}"'},
    )


@router.get(
    "/{model_id}/download",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_model_folder(model_id: ModelId) -> StreamingResponse:
    """Downloads the entire model folder as a zip archive."""
    try:
        bundle = build_full_model_bundle(model_id)
    except ModelNotFoundError:
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.") from None

    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle.archive_name}"'},
    )


@router.get(
    "/{model_id}/reports/{filename}",
    response_class=FileResponse,
    responses={200: {"content": {"text/html": {}}}},
)
def get_model_report(
    model_id: ModelId,
    filename: str = Path(..., description="The exact HTML filename returned by the list endpoint."),
) -> FileResponse:
    """Serves a single HTML QA report file for a model.

    Returns 404 if the model or the specific report file is missing.
    """
    # Simple path traversal protection
    if "/" in filename or "\\" in filename or filename.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid report filename.")

    model_folder = os.path.join(MODELS_DIR, model_id)
    if not os.path.isdir(model_folder):
        raise HTTPException(status_code=404, detail=f"Model '{model_id}' not found.")

    report_path = os.path.join(model_folder, "qa_reports", filename)
    if not os.path.isfile(report_path):
        raise HTTPException(
            status_code=404,
            detail=f"Report '{filename}' not found for model '{model_id}'.",
        )

    return FileResponse(report_path, media_type="text/html")
