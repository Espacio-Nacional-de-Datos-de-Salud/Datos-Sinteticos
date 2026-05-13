"""Artifact loading service for the synthetic data tool."""

from backend.src.domain.synthesis import MostlyAIEngine
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.utils import load_metadata, load_rule_manager

logger = get_logger(__name__)


def load_generator_artifacts(
    model_id: str,
    mostly_config_path: str,
) -> tuple[object, object, object]:
    """Loads a trained generator and its associated metadata/rules.

    This function abstracts the complexity of restoring a previously trained model
    from the filesystem, keeping the simulation flows clean.

    Args:
        model_id (str): The folder name containing the model (e.g., model_2026...).
        mostly_config_path (str): Path to the Mostly AI configuration file.

    Returns:
        tuple[object, object, object]: (generator, metadata, rule_manager).

    Raises:
        FileNotFoundError: If the generator file cannot be found.
        MetadataNotFoundError: If the metadata.json is missing or corrupted.
        RuleManagerNotFoundError: If the rules manager file is missing or corrupted.
    """
    logger.info("Loading artifacts for model '%s'...", model_id)
    engine = MostlyAIEngine(config_path=mostly_config_path)

    # Resolving artifact paths using the engine's built-in helper
    generator, path_run_folder = engine.load_generator_by_id(model_id)

    metadata = load_metadata(path_run_folder)
    rule_manager = load_rule_manager(path_run_folder)

    return generator, metadata, rule_manager
