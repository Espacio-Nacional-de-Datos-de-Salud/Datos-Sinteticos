"""Endpoints for evaluation runs."""

import json
import os
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from backend.src.api.schemas import CancelResponse, TimeProfilingReport, load_time_profiling_report
from backend.src.api.schemas.evaluations import (
    CleanupResult,
    DeletedEvaluation,
    EvaluationCreateRequest,
    EvaluationJob,
    EvaluationSummary,
    EvaluationTables,
    RenameRequest,
)
from backend.src.config.general import EVAL_CARD_FILENAME, EVALUATIONS_DIR
from backend.src.domain.id_validation import EvaluationId
from backend.src.infrastructure.cancellation import register as register_cancel
from backend.src.infrastructure.cancellation import request_cancel
from backend.src.infrastructure.errors import EvaluationNotFoundError
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
from backend.src.sessions.evaluation import (
    initialize_evaluation_session,
    run_evaluation_flow_from_simulation,
)

_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

_TABLES_DIRNAME = "tables"
_HTML_REPORT_FILENAME = "synthetic_eval_report.html"
_REPORT_DATA_FILENAME = "report_data.json"

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])


def _validate_table_name(table: str) -> None:
    if "/" in table or "\\" in table or table.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid table name.")


def _list_report_tables(evaluation_id: str) -> list[str]:
    """Tables (subdirs of ``tables/``) that hold a generated report."""
    tables_dir = os.path.join(EVALUATIONS_DIR, evaluation_id, _TABLES_DIRNAME)
    if not os.path.isdir(tables_dir):
        return []
    tables = [
        entry
        for entry in os.listdir(tables_dir)
        if os.path.isfile(os.path.join(tables_dir, entry, _REPORT_DATA_FILENAME))
    ]
    return sorted(tables)


def _resolve_report_dir(evaluation_id: str, table: str | None = None) -> str:
    """Return the directory holding the report artifacts.

    With ``table`` set, the per-table subdir. Without it (legacy callers), the
    evaluation root if it has a flat report, else the first per-table subdir.
    """
    base = os.path.join(EVALUATIONS_DIR, evaluation_id)
    if not os.path.isdir(base):
        raise HTTPException(status_code=404, detail=f"Evaluation '{evaluation_id}' not found.")

    if table is not None:
        _validate_table_name(table)
        return os.path.join(base, _TABLES_DIRNAME, table)

    if os.path.exists(os.path.join(base, _HTML_REPORT_FILENAME)):
        return base
    tables = _list_report_tables(evaluation_id)
    if tables:
        return os.path.join(base, _TABLES_DIRNAME, tables[0])
    return base


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
        name=request.name,
    )
    cancel_event = register_cancel(session.evaluation_id)

    table_configs = (
        [cfg.model_dump() for cfg in request.evaluated_tables]
        if request.evaluated_tables
        else None
    )
    background_tasks.add_task(
        run_evaluation_flow_from_simulation,
        simulation_id=inputs.simulation_id,
        session=session,
        cancel_event=cancel_event,
        table_configs=table_configs,
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


@router.get("/{evaluation_id}/time-profiling", response_model=TimeProfilingReport)
def get_evaluation_time_profiling(evaluation_id: EvaluationId) -> TimeProfilingReport:
    """Returns the structured per-phase timing breakdown of an evaluation run."""
    folder = os.path.join(EVALUATIONS_DIR, evaluation_id)
    if not os.path.isdir(folder):
        raise HTTPException(status_code=404, detail=f"Evaluation '{evaluation_id}' not found.")
    report = load_time_profiling_report(folder)
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No time profiling report for evaluation '{evaluation_id}'.",
        )
    return report


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
    "/{evaluation_id}/download/report",
    response_class=FileResponse,
    responses={200: {"content": {"text/html": {}}}},
)
def download_evaluation_report(evaluation_id: EvaluationId) -> FileResponse:
    """Downloads the HTML evaluation report as an attachment."""
    report_path = os.path.join(_resolve_report_dir(evaluation_id), _HTML_REPORT_FILENAME)
    if not os.path.exists(report_path):
        raise HTTPException(
            status_code=404,
            detail=f"HTML report for evaluation '{evaluation_id}' not found.",
        )
    return FileResponse(
        report_path,
        media_type="text/html",
        filename=f"{evaluation_id}_report.html",
    )


@router.get(
    "/{evaluation_id}/report",
    response_class=HTMLResponse,
    responses={200: {"content": {"text/html": {}}}},
)
def get_evaluation_report(evaluation_id: EvaluationId) -> HTMLResponse:
    """Returns the HTML evaluation report for inline display (primary table)."""
    return _read_html_report(evaluation_id, None)


@router.get("/{evaluation_id}/report-data")
def get_evaluation_report_data(evaluation_id: EvaluationId) -> dict:
    """Returns the structured report data (scores, summary, metadata) as JSON."""
    return _read_report_data(evaluation_id, None)


@router.get("/{evaluation_id}/tables", response_model=EvaluationTables)
def list_evaluation_tables(evaluation_id: EvaluationId) -> EvaluationTables:
    """Lists the tables that have a per-table report for this evaluation.

    Returns an empty list for legacy evaluations stored in the flat layout.
    """
    if not os.path.isdir(os.path.join(EVALUATIONS_DIR, evaluation_id)):
        raise HTTPException(status_code=404, detail=f"Evaluation '{evaluation_id}' not found.")
    return EvaluationTables(
        evaluation_id=evaluation_id,
        tables=_list_report_tables(evaluation_id),
    )


@router.get(
    "/{evaluation_id}/report/{table}",
    response_class=HTMLResponse,
    responses={200: {"content": {"text/html": {}}}},
)
def get_evaluation_table_report(evaluation_id: EvaluationId, table: str) -> HTMLResponse:
    """Returns the HTML report for a single evaluated table."""
    return _read_html_report(evaluation_id, table)


@router.get("/{evaluation_id}/report-data/{table}")
def get_evaluation_table_report_data(evaluation_id: EvaluationId, table: str) -> dict:
    """Returns the structured report data for a single evaluated table."""
    return _read_report_data(evaluation_id, table)


def _read_html_report(evaluation_id: str, table: str | None) -> HTMLResponse:
    report_path = os.path.join(_resolve_report_dir(evaluation_id, table), _HTML_REPORT_FILENAME)
    if not os.path.exists(report_path):
        raise HTTPException(
            status_code=404,
            detail=f"HTML report for evaluation '{evaluation_id}' not found.",
        )
    with open(report_path, encoding="utf-8") as fh:
        content = fh.read()
    return HTMLResponse(content=content)


def _read_report_data(evaluation_id: str, table: str | None) -> dict:
    report_data_path = os.path.join(
        _resolve_report_dir(evaluation_id, table), _REPORT_DATA_FILENAME
    )
    if not os.path.exists(report_data_path):
        raise HTTPException(
            status_code=404,
            detail=f"Report data for evaluation '{evaluation_id}' not found.",
        )
    with open(report_data_path, encoding="utf-8") as fh:
        return json.load(fh)
