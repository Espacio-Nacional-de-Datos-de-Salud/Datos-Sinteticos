"""Endpoints for simulation runs."""

import json
import os
from typing import Literal

from backend.src.api.schemas import CancelResponse
from backend.src.api.schemas.simulations import (
    CleanupResult,
    DeletedSimulation,
    RenameRequest,
    SimulationCreateRequest,
    SimulationJob,
    SimulationSummary,
)
from backend.src.config.general import SIM_CARD_FILENAME, SIMULATIONS_DIR
from backend.src.infrastructure.cancellation import register as register_cancel
from backend.src.infrastructure.cancellation import request_cancel
from backend.src.runs.card_io import update_card_status
from backend.src.runs.catalog.downloads import (
    build_full_simulation_bundle,
    build_synthetic_data_bundle,
    build_zip_stream,
)
from backend.src.runs.catalog.simulations import (
    cleanup_simulations as cleanup_simulations_catalog,
)
from backend.src.runs.catalog.simulations import (
    delete_simulation as delete_simulation_catalog,
)
from backend.src.runs.catalog.simulations import (
    list_available_simulations,
    list_simulation_columns,
)
from backend.src.runs.catalog.simulations import (
    purge_all_simulations as purge_all_simulations_catalog,
)
from backend.src.runs.catalog.simulations import (
    rename_simulation as rename_simulation_catalog,
)
from backend.src.infrastructure.errors import (
    SimulationNotFoundError,
    SyntheticDataNotFoundError,
)
from backend.src.domain.id_validation import SimulationId
from backend.src.sessions.configs import resolve_config_path
from backend.src.sessions.simulation import (
    initialize_simulation_session,
    run_simulation_flow_from_model,
)
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import StreamingResponse

_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

router = APIRouter(prefix="/simulations", tags=["Simulations"])


@router.get("/", response_model=list[SimulationSummary])
def get_simulations() -> list[dict]:
    """Returns all simulation runs available in the catalog."""
    return list_available_simulations()


@router.post(
    "/",
    response_model=SimulationJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_simulation(
    request: SimulationCreateRequest,
    background_tasks: BackgroundTasks,
) -> SimulationJob:
    """Launches a new simulation run asynchronously from a trained model.

    The session folder and its ``in_progress`` card are created synchronously
    so the returned ``simulation_id`` is immediately queryable via
    ``GET /simulations/{simulation_id}``. Clients poll that endpoint to observe
    the ``status`` transition to ``completed`` or ``failed``.
    """
    session = initialize_simulation_session(
        model_id=request.model_id,
        synthetic_data_file_format=request.synthetic_data_file_format,
    )
    cancel_event = register_cancel(session.simulation_id)
    background_tasks.add_task(
        run_simulation_flow_from_model,
        model_id=request.model_id,
        sample_size=request.sample_size,
        synthetic_data_file_format=session.synthetic_data_file_format,
        mostly_config_path=str(resolve_config_path("mostly_ai")),
        session=session,
        cancel_event=cancel_event,
        table_sample_sizes=request.table_sample_sizes,
    )
    return SimulationJob(simulation_id=session.simulation_id, status="in_progress")


# NOTE: /cleanup must be defined before /{simulation_id}.
@router.delete("/cleanup", response_model=CleanupResult)
def cleanup_simulations(
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
    """Bulk-deletes simulation folders that are empty or dead (orphaned runs).

    Simulations with linked evaluations are skipped and reported in ``skipped_ids``.
    Use ``DELETE /simulations/{simulation_id}`` to handle those individually.
    """
    deleted_empty, deleted_orphans, skipped = cleanup_simulations_catalog(
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
def purge_simulations() -> CleanupResult:
    """Delete every simulation folder regardless of status (destructive)."""
    deleted = purge_all_simulations_catalog()
    return CleanupResult(deleted_ids=deleted, empty=[], orphans=[])


@router.post("/{simulation_id}/cancel", response_model=CancelResponse)
def cancel_simulation(simulation_id: SimulationId) -> CancelResponse:
    """Request cancellation of an in-progress simulation run.

    Safe to call on a finished simulation — returns the current status with a
    ``"job already finished"`` message instead of an error.
    """
    card_path = os.path.join(SIMULATIONS_DIR, simulation_id, SIM_CARD_FILENAME)
    if not os.path.exists(card_path):
        raise HTTPException(status_code=404, detail=f"Simulation '{simulation_id}' not found.")

    with open(card_path, encoding="utf-8") as fh:
        current_status = json.load(fh).get("status", "unknown")

    if current_status in _TERMINAL_STATUSES:
        return CancelResponse(
            id=simulation_id, status=current_status, message="job already finished"
        )

    update_card_status(card_path, "cancelled")
    request_cancel(simulation_id)
    return CancelResponse(id=simulation_id, status="cancelled", message="cancellation requested")


@router.patch("/{simulation_id}/name", response_model=SimulationSummary)
def rename_simulation(simulation_id: SimulationId, body: RenameRequest) -> dict:
    """Updates the human-readable name stored in the simulation card."""
    if not rename_simulation_catalog(simulation_id, body.name):
        raise HTTPException(status_code=404, detail=f"Simulation '{simulation_id}' not found.")
    for simulation in list_available_simulations():
        if simulation["simulation_id"] == simulation_id:
            return simulation
    raise HTTPException(status_code=404, detail=f"Simulation '{simulation_id}' not found.")


@router.get("/{simulation_id}", response_model=SimulationSummary)
def get_simulation(simulation_id: SimulationId) -> dict:
    """Returns the details of a single simulation run by its ID."""
    for simulation in list_available_simulations():
        if simulation["simulation_id"] == simulation_id:
            return simulation
    raise HTTPException(status_code=404, detail=f"Simulation '{simulation_id}' not found.")


@router.delete("/{simulation_id}", response_model=DeletedSimulation)
def delete_simulation(simulation_id: SimulationId) -> DeletedSimulation:
    """Deletes a simulation run and all its stored artifacts.

    Returns 409 if the simulation has linked evaluations — delete those first.
    """
    outcome = delete_simulation_catalog(simulation_id)
    if outcome.status == "not_found":
        raise HTTPException(status_code=404, detail=f"Simulation '{simulation_id}' not found.")
    if outcome.status == "has_linked_evaluations":
        linked_count = len(outcome.linked_evaluation_ids)
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"Simulation '{simulation_id}' has {linked_count} linked evaluation(s). "
                    "Delete them first."
                ),
                "linked_evaluation_ids": outcome.linked_evaluation_ids,
            },
        )
    return DeletedSimulation(deleted_id=simulation_id)


# NOTE: /{simulation_id}/download/synthetic-dataset must be defined before
# /{simulation_id}/download so FastAPI matches the more specific paths first.
@router.get(
    "/{simulation_id}/download/synthetic-dataset",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_simulation_synthetic_dataset(simulation_id: SimulationId) -> StreamingResponse:
    """Downloads only the synthetic_data/ subfolder of the simulation."""
    try:
        bundle = build_synthetic_data_bundle(simulation_id)
    except SimulationNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Simulation '{simulation_id}' not found."
        ) from None
    except SyntheticDataNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle.archive_name}"'},
    )


@router.get(
    "/{simulation_id}/download",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_simulation_folder(simulation_id: SimulationId) -> StreamingResponse:
    """Downloads the entire simulation folder as a zip archive."""
    try:
        bundle = build_full_simulation_bundle(simulation_id)
    except SimulationNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Simulation '{simulation_id}' not found."
        ) from None

    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle.archive_name}"'},
    )


@router.get("/{simulation_id}/columns", response_model=dict[str, list[str]])
def get_simulation_columns(simulation_id: SimulationId) -> dict[str, list[str]]:
    """Returns a map of {table_name: [column_names]} for the data in this simulation.

    The catalog resolves the source artifacts and fallback order.
    """
    try:
        return list_simulation_columns(simulation_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
