"""Endpoints for discovering and editing config files.

The frontend lets users pick AND edit config files (pipeline / evaluation /
rules / runtime settings) without typing absolute paths. Config files can be
YAML, Python, JSON, or TOML. Committed templates live beside their real
counterparts as ``*.example.yaml``; edits go to the real gitignored ``*.yaml``
file — ``*.example.yaml`` is never modified by the API. Filesystem work lives
in ``services.configs``; this router just translates query params and handles
HTTP status codes.
"""

from backend.src.api.schemas.configs import (
    ConfigBulkResult,
    ConfigContent,
    ConfigFile,
    ConfigScope,
    ConfigUpdate,
)
from backend.src.services.configs import (
    ConfigMissingError,
    ConfigNotFoundError,
    ConfigParseError,
    bootstrap_configs,
    clean_configs,
    config_exists,
    determine_config_scope,
    determine_editor_format_for_file_path,
    example_path_for,
    list_configs,
    read_config_text,
    real_path_for,
    reset_config,
    write_config,
)
from fastapi import APIRouter, HTTPException, Path, Query, Response

router = APIRouter(prefix="/configs", tags=["Configs"])


@router.post("/bootstrap", response_model=ConfigBulkResult)
def bootstrap_configs_endpoint() -> ConfigBulkResult:
    """Create all missing real config files from their committed templates.

    Non-destructive: already-existing files are skipped. Equivalent to
    ``make config``.
    """
    result = bootstrap_configs()
    return ConfigBulkResult(**result)


@router.delete("/", response_model=ConfigBulkResult)
def clean_configs_endpoint() -> ConfigBulkResult:
    """Delete all real config yaml files, leaving templates untouched.

    Equivalent to ``make clean-config``.
    """
    result = clean_configs()
    return ConfigBulkResult(**result)


@router.post("/reset", response_model=ConfigBulkResult)
def reset_configs_endpoint() -> ConfigBulkResult:
    """Reset all configs: delete real yamls then recreate from templates.

    Equivalent to ``make clean-config && make config``.
    """
    clean_result = clean_configs()
    bootstrap_result = bootstrap_configs()
    return ConfigBulkResult(
        removed=clean_result["removed"],
        created=bootstrap_result["created"],
        skipped=bootstrap_result["skipped"],
    )


@router.get("/", response_model=list[ConfigFile])
def get_configs(
    scope: ConfigScope = Query(
        default=ConfigScope.ALL,
        description="Which subset of configs to return.",
    ),
) -> list[ConfigFile]:
    """List editable config files filtered by functional area."""
    return list_configs(scope)


@router.get("/{config_id:path}", response_model=ConfigContent)
def get_config(
    config_id: str = Path(
        ...,
        description=(
            "Alias (``rules``, ``mostly_ai``, ``statistics``, ``general``) or "
            "relative path under ``backend/config/`` (e.g. "
            "``pipelines/example_pipeline.yaml``)."
        ),
    ),
) -> ConfigContent:
    """Return complete metadata and text for one config file.

    Returns 409 when the real file does not exist yet so the client can
    prompt the user to bootstrap it (``make config`` or POST via this API).
    """
    try:
        example_path = example_path_for(config_id)
        path = real_path_for(config_id)
        config_scope = determine_config_scope(config_id)
        content = read_config_text(config_id)
    except ConfigNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown config: {config_id}") from exc
    except ConfigMissingError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    example_content = example_path.read_text(encoding="utf-8")
    return ConfigContent(
        id=config_id,
        scope=config_scope,
        exists=True,
        example_path=str(example_path),
        path=str(path),
        content=content,
        example_content=example_content,
        format=determine_editor_format_for_file_path(str(path)),
    )


@router.put("/{config_id:path}", response_model=ConfigContent)
def put_config(config_id: str, payload: ConfigUpdate) -> ConfigContent:
    """Create or replace the real config file content for one config id.

    YAML and JSON are syntax-validated before writing. On validation errors,
    this endpoint returns HTTP 400 and preserves any existing file.
    """
    try:
        write_config(config_id, payload.content)
    except ConfigNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown config: {config_id}") from exc
    except ConfigParseError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid config content: {exc}") from exc
    return get_config(config_id)


@router.delete("/{config_id:path}", status_code=204)
def reset_config_endpoint(config_id: str) -> Response:
    """Reset the real config file by restoring the committed template."""
    try:
        reset_config(config_id)
    except ConfigNotFoundError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown config: {config_id}") from exc
    return Response(status_code=204)


__all__ = ["router", "config_exists"]
