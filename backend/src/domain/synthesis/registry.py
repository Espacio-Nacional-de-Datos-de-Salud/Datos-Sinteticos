"""Registry of available synthesis engines and their config surface.

A single source of truth that binds each ``engine_name`` to everything the rest
of the application needs to know about it *without* importing the engine's SDK:

- ``label``: human-friendly name for a future engine-selection dropdown.
- ``config_id``: the settings-yaml alias whose schema (served by
  ``GET /configs/schemas``) describes that engine's model settings.
- ``mode_presets_id``: the presets-yaml alias, or ``None`` if the engine ships
  no presets.
- ``builder``: constructs the concrete :class:`SynthesisEngine`. Imports the
  engine module lazily so merely enumerating engines never forces an SDK import.

Today only ``"mostly"`` is registered, so every value resolves to the literals
used before this registry existed — behavior is unchanged. Adding an engine
later is a localized edit here (plus a ``_format_for_<engine>`` in
``MetadataFormatter`` and an entry in ``_ENCODING_TYPE_MAPPERS``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from backend.src.domain.synthesis.base import SynthesisEngine

DEFAULT_ENGINE = "mostly"


@dataclass(frozen=True)
class EngineDescriptor:
    """Static description of one synthesis engine.

    Attributes:
        name: Stable engine identifier (matches the ``create_engine`` key and the
            ``MetadataFormatter`` / ``_ENCODING_TYPE_MAPPERS`` engine name).
        label: Human-friendly name for UI (e.g. an engine dropdown).
        config_id: Settings-config alias whose schema describes this engine's
            model settings (e.g. ``"mostly_ai"``).
        mode_presets_id: Presets-config alias, or ``None`` if the engine has no
            mode presets.
        builder: Callable that constructs the concrete engine. Keyword args mirror
            :func:`backend.src.domain.synthesis.factory.create_engine`.
    """

    name: str
    label: str
    config_id: str
    mode_presets_id: str | None
    builder: Callable[..., SynthesisEngine]


def _build_mostly(
    *,
    config_path: str,
    run_dir: str | None = None,
    local: bool = True,
    config_overrides: dict | None = None,
    local_dir: str | None = None,
) -> SynthesisEngine:
    """Construct the Mostly AI engine.

    The import is deferred to call time so that listing engines (and importing
    this registry) does not pull in the Mostly AI SDK.
    """
    from backend.src.domain.synthesis.mostly import MostlyAIEngine

    return MostlyAIEngine(
        config_path=config_path,
        run_dir=run_dir,
        local=local,
        config_overrides=config_overrides,
        local_dir=local_dir,
    )


ENGINE_REGISTRY: dict[str, EngineDescriptor] = {
    "mostly": EngineDescriptor(
        name="mostly",
        label="Mostly AI",
        config_id="mostly_ai",
        mode_presets_id="mode_presets",
        builder=_build_mostly,
    ),
}


def list_engines() -> list[EngineDescriptor]:
    """Return all registered engine descriptors."""
    return list(ENGINE_REGISTRY.values())


def get_engine_descriptor(engine_name: str) -> EngineDescriptor:
    """Return the descriptor for ``engine_name``.

    Raises:
        ValueError: If ``engine_name`` is not a registered engine.
    """
    try:
        return ENGINE_REGISTRY[engine_name]
    except KeyError as exc:
        supported = ", ".join(repr(n) for n in ENGINE_REGISTRY)
        raise ValueError(
            f"Unknown synthesis engine: {engine_name!r}. Supported: {supported}."
        ) from exc


def resolve_active_engine() -> str:
    """Return the engine name the application should use right now.

    Single seam for engine selection. Today it always returns
    :data:`DEFAULT_ENGINE`; when a persisted/user-chosen engine is introduced,
    only this function changes and every call site follows automatically.
    """
    return DEFAULT_ENGINE
