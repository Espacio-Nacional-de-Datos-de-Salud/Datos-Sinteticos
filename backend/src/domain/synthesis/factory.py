"""Factory for constructing synthesis engines by name.

Call sites use ``create_engine`` instead of instantiating a concrete engine, so
adding a new backend later is a localized change in the engine registry rather
than across every training/simulation flow. Today only ``"mostly"`` is
registered (see :mod:`backend.src.domain.synthesis.registry`).
"""

from backend.src.domain.synthesis.base import SynthesisEngine
from backend.src.domain.synthesis.registry import DEFAULT_ENGINE, get_engine_descriptor


def create_engine(
    engine_name: str = DEFAULT_ENGINE,
    *,
    config_path: str,
    run_dir: str | None = None,
    local: bool = True,
    config_overrides: dict | None = None,
    local_dir: str | None = None,
) -> SynthesisEngine:
    """Construct a synthesis engine by name.

    Args:
        engine_name: Identifier of the engine to build. Currently only
            ``"mostly"`` is supported.
        config_path: Path to the engine's YAML configuration file.
        run_dir: Directory for session logging. Defaults to None.
        local: Whether to run the engine locally. Defaults to True.
        config_overrides: Deep-merge overrides applied on top of the base config.
        local_dir: Where the engine persists its results. Defaults to the
            engine's own default.

    Returns:
        SynthesisEngine: An engine instance satisfying the synthesis contract.

    Raises:
        ValueError: If ``engine_name`` is not a registered engine.
    """
    descriptor = get_engine_descriptor(engine_name)
    return descriptor.builder(
        config_path=config_path,
        run_dir=run_dir,
        local=local,
        config_overrides=config_overrides,
        local_dir=local_dir,
    )
