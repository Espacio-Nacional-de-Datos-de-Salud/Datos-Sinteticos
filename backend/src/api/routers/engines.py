"""Endpoint for discovering available synthesis engines.

Exposes the engine registry so a future engine-selection control can list its
options and map each engine to its config schema (via ``config_id`` →
``GET /configs/schemas``). Today only ``mostly`` is registered, so the response
has a single entry and nothing in the UI consumes it yet.
"""

from fastapi import APIRouter

from backend.src.api.schemas.engines import EngineInfo, EnginesResponse
from backend.src.domain.synthesis import (
    DEFAULT_ENGINE,
    list_engines,
    resolve_active_engine,
)

router = APIRouter(prefix="/engines", tags=["Engines"])


@router.get("", response_model=EnginesResponse)
def get_engines() -> EnginesResponse:
    """List the available synthesis engines and the active default."""
    engines = [
        EngineInfo(
            name=descriptor.name,
            label=descriptor.label,
            config_id=descriptor.config_id,
            mode_presets_id=descriptor.mode_presets_id,
            has_mode_presets=descriptor.mode_presets_id is not None,
        )
        for descriptor in list_engines()
    ]
    return EnginesResponse(default=resolve_active_engine() or DEFAULT_ENGINE, engines=engines)
