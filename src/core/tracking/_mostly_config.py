"""Helpers for loading and logging the Mostly AI configuration to MLflow.

Shared between ``ModelTracker`` (logs the config that will drive a training
run) and ``SimulationTracker`` (logs the parent model's training config with
a ``train.`` prefix so the simulation MLflow run carries training lineage).
"""

import mlflow
import yaml

from src.core.logging_config import get_logger
from src.core.utils import deep_merge

logger = get_logger(__name__)


def load_mostly_config(config_path: str, overrides: dict | None = None) -> dict:
    """Load a Mostly AI YAML config and optionally apply overrides.

    Args:
        config_path (str): Path to the Mostly AI YAML configuration file.
        overrides (dict | None): Deep-merged on top of the loaded config.

    Returns:
        dict: Parsed (and merged) configuration dictionary.
    """
    with open(config_path, encoding="utf-8") as fh:
        config = yaml.safe_load(fh)
    if overrides:
        logger.debug("Applying mostly_ai overrides: %s", overrides)
        config = deep_merge(config, overrides)
    else:
        logger.debug("No mostly_ai overrides to apply.")
    return config


def log_mostly_config_params(
    mostly_config: dict, data_file_paths: list[str], prefix: str = ""
) -> None:
    """Log Mostly AI configuration as MLflow params.

    Shared between the model and simulation trackers so both the training run
    and the downstream simulation run carry comparable, filterable parameters.

    Args:
        mostly_config (dict): Parsed Mostly AI YAML configuration.
        data_file_paths (list[str]): Paths to the original data files used for training.
        prefix (str): Optional prefix prepended to every param key (e.g. ``"train."``).
    """
    _log_generator_params(mostly_config, prefix)
    _log_model_settings_params(mostly_config, prefix)
    _log_differential_privacy_params(mostly_config, prefix)
    _log_model_type(mostly_config, prefix)
    _log_training_file_params(data_file_paths, prefix)


def _log_generator_params(mostly_config: dict, prefix: str) -> None:
    """Log ``generator``-section params from the Mostly AI config."""
    generator_params = mostly_config.get("generator", {})
    mlflow.log_params(
        {f"{prefix}mostly.{key}": str(value) for key, value in generator_params.items()}
    )


def _log_model_settings_params(mostly_config: dict, prefix: str) -> None:
    """Log scalar entries from ``model_settings`` (nested dicts are handled separately)."""
    model_settings = mostly_config.get("model_settings", {})
    mlflow.log_params(
        {
            f"{prefix}mostly.model.{key}": str(value)
            for key, value in model_settings.items()
            if not isinstance(value, dict)
        }
    )


def _log_differential_privacy_params(mostly_config: dict, prefix: str) -> None:
    """Log the ``differential_privacy`` subsection, plus a boolean enabled flag."""
    dp_config = mostly_config.get("model_settings", {}).get("differential_privacy", {})
    mlflow.log_param(f"{prefix}mostly.model.dp.enabled", bool(dp_config))
    if dp_config:
        mlflow.log_params(
            {f"{prefix}mostly.model.dp.{key}": str(value) for key, value in dp_config.items()}
        )


def _log_model_type(mostly_config: dict, prefix: str) -> None:
    """Log the model type, defaulting to ``MOSTLY_AI/Medium`` when not provided."""
    model_settings = mostly_config.get("model_settings", {})
    mlflow.log_param(f"{prefix}mostly.model.type", model_settings.get("model", "MOSTLY_AI/Medium"))


def _log_training_file_params(data_file_paths: list[str], prefix: str) -> None:
    """Log each training data file path as its own indexed MLflow param."""
    for idx, file_path in enumerate(data_file_paths):
        mlflow.log_param(f"{prefix}.file.{idx}", file_path)
