"""Pydantic schemas for the synthesis-engine discovery endpoint.

These shapes back ``GET /engines``, which enumerates the available synthesis
engines so a future engine-selection control can render its options. The engine
field schema itself is NOT included here: clients map ``EngineInfo.config_id`` to
the matching entry in ``GET /configs/schemas`` to obtain the form fields, reusing
the existing schemas endpoint.
"""

from pydantic import BaseModel


class EngineInfo(BaseModel):
    """One available synthesis engine.

    Attributes:
        name: Stable engine identifier (the value to pass when selecting it).
        label: Human-friendly name for display.
        config_id: Settings-config alias whose schema (see
            ``GET /configs/schemas``) describes this engine's model settings.
        mode_presets_id: Presets-config alias, or ``None`` if the engine has no
            mode presets.
        has_mode_presets: Convenience flag, ``True`` when ``mode_presets_id`` is
            set.
    """

    name: str
    label: str
    config_id: str
    mode_presets_id: str | None = None
    has_mode_presets: bool


class EnginesResponse(BaseModel):
    """Response for ``GET /engines``.

    Attributes:
        default: Engine name the application uses when none is explicitly chosen.
        engines: All registered engines.
    """

    default: str
    engines: list[EngineInfo]
