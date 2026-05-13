"""Endpoints for evaluation runs."""

import json
import os
from typing import Literal

from backend.src.api.schemas import CancelResponse
from backend.src.api.schemas.evaluations import (
    CleanupResult,
    DeletedEvaluation,
    EvaluationCreateRequest,
    EvaluationJob,
    EvaluationSummary,
    RenameRequest,
)
from backend.src.config.general import EVAL_CARD_FILENAME, EVALUATIONS_DIR
from backend.src.infrastructure.cancellation import register as register_cancel
from backend.src.infrastructure.cancellation import request_cancel
from backend.src.runs.card_io import update_card_status
from backend.src.runs.catalog.downloads import build_evaluation_bundle, build_zip_stream
from backend.src.runs.catalog.evaluations import (
    cleanup_evaluations as cleanup_evaluations_catalog,
)
from backend.src.runs.catalog.evaluations import (
    delete_evaluation as delete_evaluation_catalog,
)
from backend.src.runs.catalog.evaluations import (
    list_available_evaluations,
)
from backend.src.runs.catalog.evaluations import (
    purge_all_evaluations as purge_all_evaluations_catalog,
)
from backend.src.runs.catalog.evaluations import (
    rename_evaluation as rename_evaluation_catalog,
)
from backend.src.runs.catalog.simulations import resolve_simulation_inputs
from backend.src.infrastructure.errors import EvaluationNotFoundError
from backend.src.domain.id_validation import EvaluationId
from backend.src.sessions.evaluation import (
    initialize_evaluation_session,
    run_evaluation_flow_from_simulation,
)
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import HTMLResponse, StreamingResponse

_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])


@router.get("/", response_model=list[EvaluationSummary])
def get_evaluations() -> list[dict]:
    """Returns all evaluation runs available in the catalog."""
    return list_available_evaluations()


@router.post(
    "/",
    response_model=EvaluationJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_evaluation(
    request: EvaluationCreateRequest,
    background_tasks: BackgroundTasks,
) -> EvaluationJob:
    """Launches a new evaluation run asynchronously from a completed simulation."""
    try:
        inputs = resolve_simulation_inputs(request.simulation_id)
    except Exception as exc:
        raise HTTPException(
            status_code=404,
            detail=f"Simulation '{request.simulation_id}' or its dependencies not found: {exc}",
        ) from None

    session = initialize_evaluation_session(
        simulation_id=inputs.simulation_id,
        model_id=inputs.model_id,
    )
    cancel_event = register_cancel(session.evaluation_id)

    background_tasks.add_task(
        run_evaluation_flow_from_simulation,
        simulation_id=inputs.simulation_id,
        session=session,
        cancel_event=cancel_event,
    )
    return EvaluationJob(evaluation_id=session.evaluation_id, status="in_progress")


@router.delete("/cleanup", response_model=CleanupResult)
def cleanup_evaluations(
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
            "Minimum age in hours before a run without a completed status is considered orphaned."
        ),
    ),
) -> CleanupResult:
    """Bulk-deletes evaluation folders that are empty or dead (orphaned runs)."""
    deleted_empty, deleted_orphans = cleanup_evaluations_catalog(mode=mode, stale_hours=stale_hours)

    all_deleted = deleted_empty + deleted_orphans
    return CleanupResult(deleted_ids=all_deleted, empty=deleted_empty, orphans=deleted_orphans)


@router.delete("/purge", response_model=CleanupResult)
def purge_evaluations() -> CleanupResult:
    """Delete every evaluation folder regardless of status (destructive)."""
    deleted = purge_all_evaluations_catalog()
    return CleanupResult(deleted_ids=deleted, empty=[], orphans=[])


@router.post("/{evaluation_id}/cancel", response_model=CancelResponse)
def cancel_evaluation(evaluation_id: EvaluationId) -> CancelResponse:
    """Request cancellation of an in-progress evaluation run.

    Safe to call on a finished evaluation — returns the current status with a
    ``"job already finished"`` message instead of an error.
    """
    card_path = os.path.join(EVALUATIONS_DIR, evaluation_id, EVAL_CARD_FILENAME)
    if not os.path.exists(card_path):
        raise HTTPException(status_code=404, detail=f"Evaluation '{evaluation_id}' not found.")

    with open(card_path, encoding="utf-8") as fh:
        current_status = json.load(fh).get("status", "unknown")

    if current_status in _TERMINAL_STATUSES:
        return CancelResponse(
            id=evaluation_id, status=current_status, message="job already finished"
        )

    update_card_status(card_path, "cancelled")
    request_cancel(evaluation_id)
    return CancelResponse(id=evaluation_id, status="cancelled", message="cancellation requested")


@router.patch("/{evaluation_id}/name", response_model=EvaluationSummary)
def rename_evaluation(evaluation_id: EvaluationId, body: RenameRequest) -> dict:
    """Updates the human-readable name stored in the evaluation card."""
    if not rename_evaluation_catalog(evaluation_id, body.name):
        raise HTTPException(status_code=404, detail=f"Evaluation '{evaluation_id}' not found.")
    for evaluation in list_available_evaluations():
        if evaluation["evaluation_id"] == evaluation_id:
            return evaluation
    raise HTTPException(status_code=404, detail=f"Evaluation '{evaluation_id}' not found.")


@router.get("/{evaluation_id}", response_model=EvaluationSummary)
def get_evaluation(evaluation_id: EvaluationId) -> dict:
    """Returns the details of a single evaluation run by its ID."""
    for evaluation in list_available_evaluations():
        if evaluation["evaluation_id"] == evaluation_id:
            return evaluation
    raise HTTPException(status_code=404, detail=f"Evaluation '{evaluation_id}' not found.")


@router.delete("/{evaluation_id}", response_model=DeletedEvaluation)
def delete_evaluation(evaluation_id: EvaluationId) -> DeletedEvaluation:
    """Deletes an evaluation run and all its stored artifacts."""
    if not delete_evaluation_catalog(evaluation_id):
        raise HTTPException(status_code=404, detail=f"Evaluation '{evaluation_id}' not found.")
    return DeletedEvaluation(deleted_id=evaluation_id)


@router.get(
    "/{evaluation_id}/download",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_evaluation_folder(evaluation_id: EvaluationId) -> StreamingResponse:
    """Downloads the entire evaluation folder as a zip archive."""
    try:
        bundle = build_evaluation_bundle(evaluation_id)
    except EvaluationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle.archive_name}"'},
    )


@router.get(
    "/{evaluation_id}/report",
    response_class=HTMLResponse,
    responses={200: {"content": {"text/html": {}}}},
)
def get_evaluation_report(evaluation_id: EvaluationId) -> HTMLResponse:
    """Returns the HTML evaluation report for inline display."""
    report_path = os.path.join(EVALUATIONS_DIR, evaluation_id, "synthetic_eval_report.html")
    if not os.path.exists(report_path):
        raise HTTPException(
            status_code=404,
            detail=f"HTML report for evaluation '{evaluation_id}' not found.",
        )
    with open(report_path, encoding="utf-8") as fh:
        content = fh.read()
    return HTMLResponse(content=content)


@router.get("/{evaluation_id}/report-data")
def get_evaluation_report_data(evaluation_id: EvaluationId) -> dict:
    """Returns the structured report data (scores, summary, metadata) as JSON."""
    report_data_path = os.path.join(EVALUATIONS_DIR, evaluation_id, "report_data.json")
    if not os.path.exists(report_data_path):
        raise HTTPException(
            status_code=404,
            detail=f"Report data for evaluation '{evaluation_id}' not found.",
        )
    with open(report_data_path, encoding="utf-8") as fh:
        return json.load(fh)
