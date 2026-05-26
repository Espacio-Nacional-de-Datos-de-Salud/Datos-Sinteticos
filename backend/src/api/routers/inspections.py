"""Endpoints for inspection sessions."""

import json
from pathlib import Path
from typing import Literal

from backend.src.api.schemas import CancelResponse, TimeProfilingReport, load_time_profiling_report
from backend.src.api.schemas.inspections import (
    Autodetect,
    CleanupResult,
    DeletedInspection,
    InspectionCreateRequest,
    InspectionJob,
    InspectionSummary,
    ProfilingReport,
    ProfilingReports,
    Relationships,
    RenameRequest,
)
from backend.src.config.general import (
    AUTODETECTED_INSPECTION_METADATA_FILENAME,
    INSPECTION_CARD_FILENAME,
    INSPECTION_METADATA_FILENAME,
    INSPECTIONS_DIR,
    PROCESSED_DATA_DIRNAME,
    PROFILING_REPORT_PATTERN,
    PROFILING_REPORTS_DIRNAME,
)
from backend.src.infrastructure.cancellation import register as register_cancel
from backend.src.infrastructure.cancellation import request_cancel
from backend.src.runs.card_io import update_card_status
from backend.src.runs.catalog.downloads import (
    build_full_inspection_bundle,
    build_inspection_processed_data_bundle,
    build_inspection_profiling_bundle,
    build_zip_stream,
)
from backend.src.api.schemas.files import FilePreview
from backend.src.sessions.files import FilePreviewError, read_file_preview
from backend.src.runs.catalog.inspections import (
    cleanup_inspections as cleanup_inspections_catalog,
)
from backend.src.runs.catalog.inspections import (
    delete_inspection as delete_inspection_catalog,
)
from backend.src.runs.catalog.inspections import (
    list_available_inspections,
)
from backend.src.runs.catalog.inspections import (
    purge_all_inspections as purge_all_inspections_catalog,
)
from backend.src.runs.catalog.inspections import (
    rename_inspection as rename_inspection_catalog,
)
from backend.src.infrastructure.errors import (
    InspectionNotFoundError,
    InspectionProcessedDataNotFoundError,
    InspectionProfilingNotFoundError,
)
from backend.src.domain.id_validation import InspectionId
from backend.src.sessions.configs import resolve_config_path
from backend.src.sessions.inspection import (
    RULES_SNAPSHOT_FILENAME,
    initialize_inspection_session,
    run_inspection_flow,
)
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse
from pydantic import BaseModel

_TERMINAL_STATUSES = {"completed", "failed", "cancelled"}

router = APIRouter(prefix="/inspections", tags=["Inspections"])


@router.get("/", response_model=list[InspectionSummary])
def get_inspections() -> list[dict]:
    """Returns all inspection sessions available in the catalog."""
    return list_available_inspections()


@router.post(
    "/",
    response_model=InspectionJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_inspection(
    request: InspectionCreateRequest,
    background_tasks: BackgroundTasks,
) -> InspectionJob:
    """Launches a new inspection run asynchronously.

    The session folder and its ``in_progress`` card are created synchronously so
    the returned ``inspection_id`` is immediately queryable via
    ``GET /inspections/{id}``. The actual load + preprocessing + autodetect
    work runs in the background; clients poll the GET endpoint to observe the
    ``status`` transition to ``completed`` or ``failed``.
    """
    session = initialize_inspection_session(name=request.name)
    cancel_event = register_cancel(session.inspection_id)
    background_tasks.add_task(
        run_inspection_flow,
        file_paths=request.file_paths,
        mostly_config_path=request.mostly_config_path or str(resolve_config_path("mostly_ai")),
        rules_config_path=request.rules_config_path or str(resolve_config_path("rules")),
        enable_data_profiling=request.enable_data_profiling,
        csv_delimiter=request.csv_delimiter,
        excluded_columns=request.excluded_columns,
        composite_pks=request.composite_pks,
        session=session,
        cancel_event=cancel_event,
    )
    return InspectionJob(inspection_id=session.inspection_id, status="in_progress")


@router.post("/{inspection_id}/cancel", response_model=CancelResponse)
def cancel_inspection(inspection_id: InspectionId) -> CancelResponse:
    """Request cancellation of an in-progress inspection.

    Safe to call on a finished inspection — returns the current status with a
    ``"job already finished"`` message instead of an error.
    """
    card_path = Path(INSPECTIONS_DIR) / inspection_id / INSPECTION_CARD_FILENAME
    if not card_path.exists():
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")

    with open(card_path, encoding="utf-8") as fh:
        current_status = json.load(fh).get("status", "unknown")

    if current_status in _TERMINAL_STATUSES:
        return CancelResponse(
            id=inspection_id, status=current_status, message="job already finished"
        )

    update_card_status(str(card_path), "cancelled")
    request_cancel(inspection_id)
    return CancelResponse(id=inspection_id, status="cancelled", message="cancellation requested")


# NOTE: /cleanup must be defined before /{inspection_id}.
@router.delete("/cleanup", response_model=CleanupResult)
def cleanup_inspections(
    mode: Literal["empty", "orphans", "duplicates", "both", "all"] = Query(
        default="all",
        description=(
            "**empty** — completely empty folders (no files at all). "
            "**orphans** — folders with content but dead: status='failed', "
            "no card but started more than stale_hours ago, "
            "or status='in_progress' started more than stale_hours ago. "
            "**duplicates** — completed runs with identical file_paths; keeps the most recent. "
            "**both** — empty + orphans. "
            "**all** — empty + orphans + duplicates (default)."
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
    """Bulk-deletes inspection folders that are empty, dead (orphaned), or exact duplicates.

    Inspections with linked trained models are skipped and reported in
    ``skipped_ids``. Use ``DELETE /inspections/{inspection_id}`` to handle them
    individually after the linked models are deleted.
    """
    deleted_empty, deleted_orphans, deleted_duplicates, skipped = cleanup_inspections_catalog(
        mode=mode, stale_hours=stale_hours
    )

    all_deleted = deleted_empty + deleted_orphans + deleted_duplicates
    return CleanupResult(
        deleted_ids=all_deleted,
        empty=deleted_empty,
        orphans=deleted_orphans,
        duplicates=deleted_duplicates,
        skipped_ids=skipped,
    )


@router.delete("/purge", response_model=CleanupResult)
def purge_inspections() -> CleanupResult:
    """Delete every inspection folder regardless of status (destructive)."""
    deleted = purge_all_inspections_catalog()
    return CleanupResult(deleted_ids=deleted, empty=[], orphans=[], duplicates=[], skipped_ids=[])


@router.get("/{inspection_id}", response_model=InspectionSummary)
def get_inspection(inspection_id: InspectionId) -> dict:
    """Returns the details of a single inspection session by its ID."""
    for inspection in list_available_inspections():
        if inspection["inspection_id"] == inspection_id:
            return inspection
    raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")


@router.get("/{inspection_id}/time-profiling", response_model=TimeProfilingReport)
def get_inspection_time_profiling(inspection_id: InspectionId) -> TimeProfilingReport:
    """Returns the structured per-phase timing breakdown of an inspection run."""
    folder = Path(INSPECTIONS_DIR) / inspection_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")
    report = load_time_profiling_report(str(folder))
    if report is None:
        raise HTTPException(
            status_code=404,
            detail=f"No time profiling report for inspection '{inspection_id}'.",
        )
    return report


# NOTE: /{id}/autodetect must be declared before any bare /{id}/… catch-all.
# It's placed after GET /{id} so FastAPI's longest-prefix match picks it up.
@router.get("/{inspection_id}/autodetect", response_model=Autodetect)
def get_inspection_autodetect(inspection_id: InspectionId) -> Autodetect:
    """Returns the current schema (PKs, FKs, per-column encoding types).

    This is whatever ``inspection_metadata.json`` currently holds — either the
    auto-detected values or the user's last edit via ``PUT``. The pristine
    auto-detected snapshot is preserved separately in
    ``autodetected_inspection_metadata.json``. Returns 404 if the inspection is
    still ``in_progress`` or ``failed``.
    """
    path = Path(INSPECTIONS_DIR) / inspection_id / INSPECTION_METADATA_FILENAME
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"inspection_metadata.json not found for inspection '{inspection_id}'. "
                "It may still be in progress or the run failed."
            ),
        )
    with open(path) as f:
        data = json.load(f)
    return Autodetect.model_validate(data)


@router.get("/{inspection_id}/autodetect/original", response_model=Autodetect)
def get_inspection_autodetect_original(inspection_id: InspectionId) -> Autodetect:
    """Returns the pristine auto-detected schema captured at inspection time.

    Reads ``autodetected_inspection_metadata.json``, the frozen snapshot that is
    written once when the inspection runs and is never overwritten by user
    edits. Used by the UI's "reset to autodetected" action.
    """
    path = Path(INSPECTIONS_DIR) / inspection_id / AUTODETECTED_INSPECTION_METADATA_FILENAME
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(
                f"autodetected_inspection_metadata.json not found for inspection '{inspection_id}'."
            ),
        )
    with open(path) as f:
        data = json.load(f)
    return Autodetect.model_validate(data)


@router.get("/{inspection_id}/rules", response_class=PlainTextResponse)
def get_inspection_rules(inspection_id: InspectionId) -> str:
    """Return the rules YAML snapshot captured at inspection time.

    This is the exact ``rules.yaml`` content used to preprocess the dataset,
    independent of any later edits to the live config. Returns 404 when the
    snapshot does not exist (older inspections, or run before snapshotting
    was added).
    """
    path = Path(INSPECTIONS_DIR) / inspection_id / RULES_SNAPSHOT_FILENAME
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Rules snapshot not found for inspection '{inspection_id}'.",
        )
    return path.read_text(encoding="utf-8")


def _load_inspection_metadata(inspection_id: InspectionId) -> tuple[Path, Autodetect]:
    """Returns the on-disk metadata path and parsed contents for an inspection.

    Args:
        inspection_id (str): The inspection identifier.

    Returns:
        tuple[Path, Autodetect]: (file_path, parsed_metadata).

    Raises:
        HTTPException: 404 if the folder or metadata file is missing.
    """
    folder = Path(INSPECTIONS_DIR) / inspection_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")
    path = folder / INSPECTION_METADATA_FILENAME
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail=(f"inspection_metadata.json not found for inspection '{inspection_id}'."),
        )
    with open(path) as f:
        data = json.load(f)
    return path, Autodetect.model_validate(data)


def _write_inspection_metadata(path: Path, payload: Autodetect) -> None:
    """Persists the merged metadata back to ``inspection_metadata.json``.

    Args:
        path (Path): Destination file path.
        payload (Autodetect): Metadata object to persist.

    Returns:
        None
    """
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload.model_dump(), f, indent=2, ensure_ascii=False, default=str)


def _validate_single_context_per_child(payload: Relationships) -> None:
    """Rejects payloads that mark more than one FK as context for the same child.

    MostlyAI accepts at most one context FK per child table.

    Args:
        payload (Relationships): Relationship definitions to validate.

    Returns:
        None

    Raises:
        HTTPException: 400 if validation fails.
    """
    seen: set[str] = set()
    for fk in payload.fks:
        if not fk.is_context:
            continue
        if fk.child in seen:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Table '{fk.child}' has more than one context FK. "
                    "MostlyAI accepts at most one context FK per child table."
                ),
            )
        seen.add(fk.child)


@router.put("/{inspection_id}/autodetect/relationships", response_model=Autodetect)
def put_inspection_autodetect_relationships(
    inspection_id: InspectionId, payload: Relationships
) -> Autodetect:
    """Overwrites only the ``relationships`` section of ``inspection_metadata.json``.

    The encoding-types section is preserved untouched. Training consumes the merged
    metadata file, so edits here take effect on the next training run.
    """
    _validate_single_context_per_child(payload)
    path, current = _load_inspection_metadata(inspection_id)
    current.relationships = payload
    _write_inspection_metadata(path, current)
    return current


@router.put("/{inspection_id}/autodetect/encoding-types", response_model=Autodetect)
def put_inspection_autodetect_encoding_types(
    inspection_id: InspectionId, payload: dict[str, dict[str, str]]
) -> Autodetect:
    """Overwrites only the ``encoding_types`` section of ``inspection_metadata.json``.

    The relationships section is preserved untouched. Training consumes the merged
    metadata file, so edits here take effect on the next training run.
    """
    path, current = _load_inspection_metadata(inspection_id)
    current.encoding_types = payload
    _write_inspection_metadata(path, current)
    return current


class ExcludeColumnsRequest(BaseModel):
    """Body of ``PUT /{id}/autodetect/excluded-columns``: columns to remove per table."""

    excluded_columns: dict[str, list[str]]


@router.put("/{inspection_id}/autodetect/excluded-columns", response_model=Autodetect)
def put_inspection_excluded_columns(
    inspection_id: InspectionId, body: ExcludeColumnsRequest
) -> Autodetect:
    """Remove specific columns from an inspection's metadata **and** from the cached
    processed parquet files in a single atomic operation.

    Use this endpoint (instead of the generic ``PUT /autodetect/encoding-types``) when
    the user explicitly excludes columns post-inspection, so that the cached data and
    the schema stay in sync. Excluded columns are:

    * Removed from ``encoding_types`` in ``inspection_metadata.json``.
    * Removed from any FK/PK relationships that reference them.
    * Physically dropped from the matching ``processed_data/<table>.parquet`` files.

    The changes are irreversible on disk; use "Restaurar autodetectado" only for the
    schema — the parquet files are not restored by that action.
    """
    import pandas as pd
    from backend.src.config.general import PROCESSED_DATA_DIRNAME

    folder = Path(INSPECTIONS_DIR) / inspection_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")

    path, current = _load_inspection_metadata(inspection_id)

    excluded = {t: set(cols) for t, cols in body.excluded_columns.items() if cols}
    if not excluded:
        return current

    # ---- Update encoding_types ----
    for tbl, drop_cols in excluded.items():
        if tbl not in current.encoding_types:
            continue
        for col in drop_cols:
            current.encoding_types[tbl].pop(col, None)

    # ---- Update relationships ----
    current.relationships.fks = [
        fk
        for fk in current.relationships.fks
        if not (
            (fk.child in excluded and fk.fk_column in excluded[fk.child])
            or (fk.parent in excluded and fk.pk_column in excluded[fk.parent])
        )
    ]
    for tbl, drop_cols in excluded.items():
        if current.relationships.pks.get(tbl) in drop_cols:
            del current.relationships.pks[tbl]

    _write_inspection_metadata(path, current)

    # ---- Drop columns from cached parquet files ----
    processed_dir = folder / PROCESSED_DATA_DIRNAME
    for tbl, drop_cols in excluded.items():
        parquet_path = processed_dir / f"{tbl}.parquet"
        if not parquet_path.exists():
            continue
        try:
            df = pd.read_parquet(parquet_path)
            cols_to_drop = [c for c in drop_cols if c in df.columns]
            if cols_to_drop:
                df = df.drop(columns=cols_to_drop)
                df.to_parquet(parquet_path)
        except Exception as exc:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update parquet for table '{tbl}': {exc}",
            ) from exc

    return current


@router.patch("/{inspection_id}/name", response_model=InspectionSummary)
def rename_inspection(inspection_id: InspectionId, body: RenameRequest) -> dict:
    """Updates the human-readable name stored in the inspection card."""
    if not rename_inspection_catalog(inspection_id, body.name):
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")
    for inspection in list_available_inspections():
        if inspection["inspection_id"] == inspection_id:
            return inspection
    raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")


@router.delete("/{inspection_id}", response_model=DeletedInspection)
def delete_inspection(
    inspection_id: InspectionId,
    mode: Literal["safe", "force", "cascade"] = Query(
        default="safe",
        description=(
            "**safe** — refuse (409) when linked models exist. "
            "**force** — delete the inspection only, leaving its models orphaned. "
            "**cascade** — delete the inspection and every downstream model, "
            "simulation, and evaluation."
        ),
    ),
) -> DeletedInspection:
    """Deletes an inspection session and all its stored artifacts.

    With ``mode=safe`` (default), returns 409 if the inspection has linked
    trained models. Use ``mode=force`` or ``mode=cascade`` to delete anyway.
    """
    outcome = delete_inspection_catalog(inspection_id, mode=mode)
    if outcome.status == "not_found":
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")
    if outcome.status == "has_linked_models":
        linked_count = len(outcome.linked_model_ids)
        raise HTTPException(
            status_code=409,
            detail={
                "message": (
                    f"La inspección '{inspection_id}' tiene {linked_count} "
                    "modelo(s) asociado(s)."
                ),
                "linked_model_ids": outcome.linked_model_ids,
            },
        )
    return DeletedInspection(
        deleted_id=inspection_id,
        deleted_model_ids=outcome.deleted_model_ids,
        deleted_simulation_ids=outcome.deleted_simulation_ids,
        deleted_evaluation_ids=outcome.deleted_evaluation_ids,
    )


@router.get(
    "/{inspection_id}/download",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_inspection_folder(inspection_id: InspectionId) -> StreamingResponse:
    """Downloads the entire inspection folder as a zip archive."""
    try:
        bundle = build_full_inspection_bundle(inspection_id)
    except InspectionNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Inspection '{inspection_id}' not found."
        ) from None

    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle.archive_name}"'},
    )


@router.get("/{inspection_id}/profiling", response_model=ProfilingReports)
def list_inspection_profiling(inspection_id: InspectionId) -> ProfilingReports:
    """Lists the per-table ydata-profiling HTML reports for an inspection.

    Returns an empty ``reports`` list if the inspection was run without
    ``enable_data_profiling=True``. Returns 404 if the inspection folder
    itself does not exist.
    """
    inspection_folder = Path(INSPECTIONS_DIR) / inspection_id
    if not inspection_folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")

    profiling_folder = inspection_folder / PROFILING_REPORTS_DIRNAME
    reports: list[ProfilingReport] = []
    if profiling_folder.is_dir():
        suffix = PROFILING_REPORT_PATTERN.format(name="")
        for entry in sorted(profiling_folder.iterdir()):
            if entry.is_file() and entry.name.endswith(suffix):
                table = entry.name[: -len(suffix)] if suffix else entry.stem
                reports.append(ProfilingReport(table=table, filename=entry.name))
    return ProfilingReports(inspection_id=inspection_id, reports=reports)


@router.get(
    "/{inspection_id}/profiling/{table}",
    response_class=FileResponse,
    responses={200: {"content": {"text/html": {}}}},
)
def get_inspection_profiling_report(inspection_id: InspectionId, table: str) -> FileResponse:
    """Serves the raw HTML profiling report for a single table.

    The frontend embeds this in an ``<iframe>``. Returns 404 if the inspection
    or the specific table's report file is missing.
    """
    if "/" in table or "\\" in table or table.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid table name.")

    inspection_folder = Path(INSPECTIONS_DIR) / inspection_id
    if not inspection_folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")

    report_path = (
        inspection_folder / PROFILING_REPORTS_DIRNAME / PROFILING_REPORT_PATTERN.format(name=table)
    )
    if not report_path.is_file():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Profiling report for table '{table}' not found in inspection "
                f"'{inspection_id}'. Was the inspection run with enable_data_profiling=True?"
            ),
        )
    return FileResponse(report_path, media_type="text/html")


def _resolve_inspection_processed_dir(inspection_id: InspectionId) -> Path:
    folder = Path(INSPECTIONS_DIR) / inspection_id
    if not folder.is_dir():
        raise HTTPException(status_code=404, detail=f"Inspection '{inspection_id}' not found.")
    processed = folder / PROCESSED_DATA_DIRNAME
    if not processed.is_dir():
        raise HTTPException(
            status_code=404,
            detail=(
                f"Processed data not found for inspection '{inspection_id}'. "
                "It may still be in progress or the run failed."
            ),
        )
    return processed


@router.get("/{inspection_id}/preprocessed", response_model=list[str])
def list_inspection_preprocessed_tables(inspection_id: InspectionId) -> list[str]:
    """Lists table names present in the inspection's ``processed_data/`` folder."""
    processed = _resolve_inspection_processed_dir(inspection_id)
    return sorted(p.stem for p in processed.iterdir() if p.is_file() and p.suffix == ".parquet")


@router.get("/{inspection_id}/preprocessed/{table}", response_model=FilePreview)
def get_inspection_preprocessed_preview(
    inspection_id: InspectionId,
    table: str,
    sample_rows: int = Query(default=50, ge=0, le=1000),
    offset: int = Query(default=0, ge=0),
    include_total: bool = Query(default=False),
) -> FilePreview:
    """Returns preview rows for one preprocessed table.

    Mirrors the ``/files/preview`` shape so the frontend can reuse the same
    table-explorer UI for both raw and preprocessed views.
    """
    if "/" in table or "\\" in table or table.startswith("."):
        raise HTTPException(status_code=400, detail="Invalid table name.")
    processed = _resolve_inspection_processed_dir(inspection_id)
    target = processed / f"{table}.parquet"
    if not target.is_file():
        raise HTTPException(
            status_code=404,
            detail=f"Preprocessed table '{table}' not found for inspection '{inspection_id}'.",
        )
    try:
        return read_file_preview(
            target,
            sample_rows=sample_rows,
            offset=offset,
            include_total=include_total,
        )
    except FilePreviewError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from None


@router.get(
    "/{inspection_id}/download/preprocessed",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_inspection_preprocessed(inspection_id: InspectionId) -> StreamingResponse:
    """Downloads the ``processed_data/`` subfolder as a zip archive."""
    try:
        bundle = build_inspection_processed_data_bundle(inspection_id)
    except InspectionNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Inspection '{inspection_id}' not found."
        ) from None
    except InspectionProcessedDataNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle.archive_name}"'},
    )


@router.get(
    "/{inspection_id}/download/profiling",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}}},
)
def download_inspection_profiling(inspection_id: InspectionId) -> StreamingResponse:
    """Downloads the profiling_reports/ subfolder as a zip archive.

    Returns 404 if the inspection doesn't exist, or if the inspection was run
    without ``enable_data_profiling=True`` (no reports were produced).
    """
    try:
        bundle = build_inspection_profiling_bundle(inspection_id)
    except InspectionNotFoundError:
        raise HTTPException(
            status_code=404, detail=f"Inspection '{inspection_id}' not found."
        ) from None
    except InspectionProfilingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None

    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{bundle.archive_name}"'},
    )
