"""Endpoints for business-rules-configuration (BRC) runs.

A BRC run materialises a snapshot of the rules YAML applied (PRE phase
only) on top of an upload's preprocessed data. Each run lives in its
own folder so the user can keep a history of attempts per upload and
the original upload parquet is never mutated.
"""

import os
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse, StreamingResponse

from backend.src.api.schemas.business_rules_configurations import (
    BRCCreateRequest,
    BRCDeletedResponse,
    BRCJob,
    BRCProfilingReport,
    BRCProfilingReports,
    BRCRenameRequest,
    BRCSummary,
)
from backend.src.api.schemas.files import FilePreview
from backend.src.config.general import INSPECTION_METADATA_FILENAME, INSPECTIONS_DIR
from backend.src.runs.card_io import read_json
from backend.src.runs.catalog.downloads import (
    build_brc_dataset_bundle,
    build_brc_full_bundle,
    build_brc_profiling_bundle,
    build_zip_stream,
)
from backend.src.sessions.business_rules_configurations import (
    brc_dataset_paths,
    brc_new_columns,
    brc_profiling_report_path,
    brc_profiling_reports,
    brc_rules_snapshot_path,
    delete_brc_run,
    initialize_brc_session,
    list_brc_runs,
    load_brc_card,
    rename_brc_run,
    run_brc_flow,
)
from backend.src.sessions.configs import resolve_config_path
from backend.src.sessions.files import FilePreviewError, read_file_preview

router = APIRouter(
    prefix="/business-rules-configurations",
    tags=["BusinessRulesConfigurations"],
)


@router.get("/", response_model=list[BRCSummary])
def list_brcs(
    inspection_id: str | None = Query(
        default=None,
        description="If set, returns only runs whose source upload matches this id.",
    ),
) -> list[dict]:
    return list_brc_runs(inspection_id=inspection_id)


@router.post(
    "/",
    response_model=BRCJob,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_brc(request: BRCCreateRequest, background_tasks: BackgroundTasks) -> BRCJob:
    """Launch a new BRC run asynchronously.

    The folder + ``in_progress`` card are written synchronously so the
    returned ``brc_id`` is immediately queryable; the actual rule
    application runs in the background.
    """
    session = initialize_brc_session(inspection_id=request.inspection_id, name=request.name)
    rules_path = request.rules_config_path or str(resolve_config_path("rules"))
    background_tasks.add_task(
        run_brc_flow,
        inspection_id=request.inspection_id,
        rules_config_path=rules_path,
        enable_profiling=request.enable_profiling,
        session=session,
    )
    return BRCJob(brc_id=session.brc_id)


@router.get("/{brc_id}", response_model=BRCSummary)
def get_brc(brc_id: str) -> dict:
    for run in list_brc_runs():
        if run.get("brc_id") == brc_id:
            return run
    raise HTTPException(status_code=404, detail=f"BRC run '{brc_id}' not found.")


@router.patch("/{brc_id}/name", response_model=BRCSummary)
def patch_brc_name(brc_id: str, body: BRCRenameRequest) -> dict:
    try:
        rename_brc_run(brc_id, body.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return get_brc(brc_id)


@router.delete("/{brc_id}", response_model=BRCDeletedResponse)
def delete_brc(brc_id: str) -> BRCDeletedResponse:
    try:
        delete_brc_run(brc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return BRCDeletedResponse(brc_id=brc_id)


@router.get("/{brc_id}/rules-snapshot", response_class=PlainTextResponse)
def get_brc_rules_snapshot(brc_id: str) -> str:
    try:
        path = brc_rules_snapshot_path(brc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Path(path).read_text(encoding="utf-8")


@router.get("/{brc_id}/new-columns")
def get_brc_new_columns(brc_id: str) -> dict[str, list[str]]:
    try:
        return brc_new_columns(brc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{brc_id}/preview", response_model=list[FilePreview])
def get_brc_preview(
    brc_id: str,
    sample_rows: int = Query(default=50, ge=0, le=2000),
    offset: int = Query(default=0, ge=0),
    only_new_columns: bool = Query(
        default=False,
        description="If true, projects each table to the columns produced by the rules.",
    ),
    include_total: bool = Query(default=True),
) -> list[FilePreview]:
    """Return a per-table preview of the BRC run's preprocessed parquet.

    The route mirrors ``POST /files/preview`` but is scoped to a single
    BRC run's processed_data and supports filtering to "new" columns
    only (the aux/diff/duration columns produced by the rules).
    """
    try:
        paths = brc_dataset_paths(brc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not paths:
        raise HTTPException(
            status_code=404,
            detail=f"BRC run '{brc_id}' has no preprocessed data yet.",
        )

    new_cols_by_table = brc_new_columns(brc_id) if only_new_columns else {}
    # When projecting to "new columns only", the PK of each table is also
    # kept so the user can identify rows in the preview. PKs come from the
    # source upload's inspection_metadata.json (single-column PKs).
    pks_by_table: dict[str, str] = {}
    if only_new_columns:
        card = load_brc_card(brc_id)
        inspection_id = card.get("inspection_id")
        if inspection_id:
            md_path = os.path.join(INSPECTIONS_DIR, inspection_id, INSPECTION_METADATA_FILENAME)
            if os.path.exists(md_path):
                try:
                    md = read_json(md_path)
                    pks_by_table = md.get("relationships", {}).get("pks", {}) or {}
                except Exception:
                    pks_by_table = {}
    previews: list[FilePreview] = []
    for table, parquet_path in paths.items():
        try:
            preview = read_file_preview(
                Path(parquet_path),
                sample_rows=sample_rows,
                offset=offset,
                include_total=include_total,
            )
        except FilePreviewError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        if only_new_columns:
            keep_set: set[str] = set(new_cols_by_table.get(table, []))
            pk_col = pks_by_table.get(table)
            if pk_col:
                keep_set.add(pk_col)
            if keep_set:
                # Keep column order from the source so it matches the parquet
                # schema; PK ends up wherever it lives in the parquet.
                kept_idx = [i for i, c in enumerate(preview.columns) if c in keep_set]
                preview = FilePreview(
                    path=preview.path,
                    table=preview.table,
                    columns=[preview.columns[i] for i in kept_idx],
                    rows=[[row[i] for i in kept_idx] for row in preview.rows],
                    total_rows=preview.total_rows,
                )
            else:
                preview = FilePreview(
                    path=preview.path,
                    table=preview.table,
                    columns=[],
                    rows=[],
                    total_rows=preview.total_rows,
                )
        # Normalise table name to the parquet's stem so the frontend can
        # key previews by table.
        preview = FilePreview(
            path=preview.path,
            table=table,
            columns=preview.columns,
            rows=preview.rows,
            total_rows=preview.total_rows,
        )
        previews.append(preview)
    return previews


@router.get("/{brc_id}/profiling", response_model=BRCProfilingReports)
def get_brc_profiling(brc_id: str) -> BRCProfilingReports:
    try:
        load_brc_card(brc_id)  # 404 if missing
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    tables = brc_profiling_reports(brc_id)
    reports = [
        BRCProfilingReport(
            table=t,
            filename=os.path.basename(brc_profiling_report_path(brc_id, t)),
        )
        for t in tables
    ]
    return BRCProfilingReports(brc_id=brc_id, reports=reports)


@router.get("/{brc_id}/profiling/{table}")
def get_brc_profiling_report(brc_id: str, table: str) -> FileResponse:
    try:
        path = brc_profiling_report_path(brc_id, table)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type="text/html")


@router.get("/{brc_id}/download")
def download_brc_folder(brc_id: str) -> StreamingResponse:
    try:
        bundle = build_brc_full_bundle(brc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={bundle.archive_name}"},
    )


@router.get("/{brc_id}/download/dataset")
def download_brc_dataset(brc_id: str) -> StreamingResponse:
    try:
        bundle = build_brc_dataset_bundle(brc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={bundle.archive_name}"},
    )


@router.get("/{brc_id}/download/profiling")
def download_brc_profiling(brc_id: str) -> StreamingResponse:
    try:
        bundle = build_brc_profiling_bundle(brc_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return StreamingResponse(
        build_zip_stream(bundle),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={bundle.archive_name}"},
    )
