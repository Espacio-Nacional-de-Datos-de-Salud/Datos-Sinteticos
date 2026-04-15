"""Run synthcity's built-in metrics on a (real, synthetic) pair.

Wraps the boilerplate of building ``GenericDataLoader`` instances and calling
``synthcity.metrics.Metrics.evaluate`` so the runner stays focused on
orchestration.
"""

from pathlib import Path

import pandas as pd
from synthcity.metrics import Metrics
from synthcity.plugins.core.dataloader import GenericDataLoader

from src.core.logging_config import get_logger

logger = get_logger(__name__)


def build_data_loaders(
    real_data: pd.DataFrame, synthetic_data: pd.DataFrame, target_column: str | None
) -> tuple[GenericDataLoader, GenericDataLoader]:
    """Wrap the real and synthetic frames in synthcity ``GenericDataLoader`` objects."""
    try:
        loader_real = GenericDataLoader(
            real_data, target_column=target_column, sensitive_features=[]
        )
        loader_syn = GenericDataLoader(
            synthetic_data, target_column=target_column, sensitive_features=[]
        )
    except Exception:
        logger.error("Failed to create synthcity DataLoaders.", exc_info=True)
        raise
    return loader_real, loader_syn


def evaluate_synthcity_metrics(
    loader_real: GenericDataLoader,
    loader_syn: GenericDataLoader,
    metrics: dict[str, list[str]],
    task_type: str,
    workspace_path: str,
) -> pd.DataFrame:
    """Run ``synthcity.metrics.Metrics.evaluate`` and return its DataFrame report."""
    return Metrics.evaluate(
        loader_real,
        loader_syn,
        metrics=metrics,
        task_type=task_type,
        workspace=Path(workspace_path),
        X_train=loader_real,
        X_ref_syn=loader_syn,
    )
