"""Run synthcity's built-in metrics on a (real, synthetic) pair.

Wraps the boilerplate of building ``GenericDataLoader`` instances and calling
``synthcity.metrics.Metrics.evaluate``. To attribute time to individual
metrics in the profiling report, the wrapper invokes synthcity once per
``(group, metric)`` pair under its own profiler phase and concatenates the
resulting rows.
"""

from pathlib import Path

import pandas as pd
from synthcity.metrics import Metrics
from synthcity.plugins.core.dataloader import GenericDataLoader

from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import synthcity_metric_phase_label
from backend.src.infrastructure.time_profiling import profiler

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
    """Run synthcity once per requested metric and return the combined report.

    Each ``(group, metric_name)`` pair runs in its own ``profiler.phase`` so
    the timing report attributes seconds to individual metrics. Calling
    ``Metrics.evaluate`` per metric repeats some encoder setup (concat +
    encode of the two frames), but that overhead is a fraction of a second
    on typical datasets and is the price for per-metric attribution.
    """
    workspace = Path(workspace_path)
    frames: list[pd.DataFrame] = []
    for group, metric_names in metrics.items():
        for metric_name in metric_names:
            phase_label = synthcity_metric_phase_label(group, metric_name)
            try:
                with profiler.phase(phase_label):
                    sub_report = Metrics.evaluate(
                        loader_real,
                        loader_syn,
                        metrics={group: [metric_name]},
                        task_type=task_type,
                        workspace=workspace,
                        X_train=loader_real,
                        X_ref_syn=loader_syn,
                    )
                frames.append(sub_report)
            except Exception:
                logger.error("Synthcity metric %s/%s failed.", group, metric_name, exc_info=True)

    if not frames:
        return pd.DataFrame()
    return pd.concat(frames)
