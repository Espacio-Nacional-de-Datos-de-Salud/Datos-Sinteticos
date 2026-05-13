"""Endpoints for discovering data files on the server.

The frontend needs to let users pick input files for inspections without
typing absolute paths (which differ between Docker and local runs). The
actual filesystem walk lives in ``services.files``; this router just
translates query params and delegates.
"""

from backend.src.api.schemas.files import DataFile, FilePreview, FilePreviewRequest
from backend.src.sessions.files import (
    ALLOWED_EXTENSIONS,
    FilePreviewError,
    UploadConflictError,
    UploadExtensionError,
    UploadNameError,
    UploadSizeLimitError,
    delete_all_uploads,
    get_upload_stats,
    list_data_files,
    preview_file,
    save_uploaded_file,
)
from fastapi import APIRouter, File, HTTPException, Query, UploadFile, status

router = APIRouter(prefix="/files", tags=["Files"])


@router.get("/", response_model=list[DataFile])
def get_data_files(
    ext: str = Query(
        default="",
        description="Comma-separated extensions to include (e.g. 'csv,parquet'). "
        "Defaults to all allowed extensions.",
    ),
) -> list[DataFile]:
    """Returns data files under ``backend/data/`` matching the allowed extensions."""
    wanted = {e.strip().lower() for e in ext.split(",") if e.strip()}
    return list_data_files(wanted or None)


@router.post(
    "/upload",
    response_model=list[DataFile],
    status_code=status.HTTP_201_CREATED,
)
async def upload_data_files(files: list[UploadFile] = File(...)) -> list[DataFile]:
    """Saves uploaded files under ``backend/data/uploads/``.

    Returns the saved files in the same shape as ``GET /files``. Rejects
    unsupported extensions (400), unsafe names (400), name collisions (409),
    and payloads that would exceed the storage quota (413).
    """
    saved: list[DataFile] = []
    for upload in files:
        try:
            saved.append(save_uploaded_file(upload.filename or "", upload.file))
        except UploadNameError:
            raise HTTPException(
                status_code=400, detail=f"Invalid filename: {upload.filename!r}."
            ) from None
        except UploadExtensionError as e:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Unsupported extension {str(e)!r}. Allowed: {sorted(ALLOWED_EXTENSIONS)}."
                ),
            ) from None
        except UploadConflictError:
            raise HTTPException(
                status_code=409,
                detail=f"File {upload.filename!r} already exists in uploads.",
            ) from None
        except UploadSizeLimitError as e:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=str(e),
            ) from None
        finally:
            await upload.close()
    return saved


@router.get("/uploads/stats")
def get_uploads_stats() -> dict:
    """Returns ``{used_bytes, limit_bytes}`` for the uploads directory.

    Used by the frontend to render the storage usage counter and enforce
    the quota visually before attempting a file upload.
    """
    return get_upload_stats()


@router.post("/preview", response_model=list[FilePreview])
def preview_files(req: FilePreviewRequest) -> list[FilePreview]:
    """Returns table name + columns for each path, skipping unreadable files.

    Used by the rules editor to populate table/column dropdowns from files
    that have been uploaded but not yet inspected.
    """
    out: list[FilePreview] = []
    for path in req.paths:
        try:
            out.append(
                preview_file(
                    path,
                    sample_rows=req.sample_rows,
                    offset=req.offset,
                    include_total=req.include_total,
                )
            )
        except FilePreviewError:
            continue
    return out


@router.delete("/uploads", response_model=list[str])
def delete_uploaded_files() -> list[str]:
    """Deletes every file under ``backend/data/uploads/`` and returns their names."""
    return delete_all_uploads()
