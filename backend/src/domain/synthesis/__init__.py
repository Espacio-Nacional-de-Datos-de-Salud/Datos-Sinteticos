"""Synthesis engine package.

Public surface:
    - ``SynthesisEngine``: engine-agnostic contract (Protocol).
    - ``create_engine``: factory that builds an engine by name.
    - ``MostlyAIEngine``: the Mostly AI implementation (lazily loaded).
    - Engine registry helpers (``list_engines``, ``get_engine_descriptor``,
      ``resolve_active_engine``, ``EngineDescriptor``, ``DEFAULT_ENGINE``): the
      single place engines and their config surface are declared.

Prefer ``create_engine`` over importing a concrete engine directly so call
sites stay engine-agnostic.

``MostlyAIEngine`` is exposed lazily (PEP 562): ``from
backend.src.domain.synthesis import MostlyAIEngine`` still works, but merely
importing this package does NOT import the Mostly AI SDK. That keeps the
SDK-free seam (the factory, registry, and ``resolve_active_engine``) importable
in environments without ``mostlyai`` installed (e.g. the evaluation venv).
"""

from typing import TYPE_CHECKING

from backend.src.domain.synthesis.base import SynthesisEngine
from backend.src.domain.synthesis.factory import create_engine
from backend.src.domain.synthesis.registry import (
    DEFAULT_ENGINE,
    EngineDescriptor,
    get_engine_descriptor,
    list_engines,
    resolve_active_engine,
)

if TYPE_CHECKING:
    from backend.src.domain.synthesis.mostly import MostlyAIEngine

__all__ = [
    "DEFAULT_ENGINE",
    "EngineDescriptor",
    "MostlyAIEngine",
    "SynthesisEngine",
    "create_engine",
    "get_engine_descriptor",
    "list_engines",
    "resolve_active_engine",
]


def __getattr__(name: str) -> object:
    """Lazily resolve ``MostlyAIEngine`` so the SDK loads only when accessed."""
    if name == "MostlyAIEngine":
        from backend.src.domain.synthesis.mostly import MostlyAIEngine

        return MostlyAIEngine
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
