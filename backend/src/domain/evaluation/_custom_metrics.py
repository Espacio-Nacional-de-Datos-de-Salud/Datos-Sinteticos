"""Run our in-house metric classes and inject results into the synthcity report.

The custom metrics defined in ``src.evaluation.metrics`` are not part of the
synthcity registry, so we execute them ourselves here and append their rows
to the report DataFrame returned by synthcity. Two result shapes are
supported:

- single-row metrics, returning ``{"score": ..., "min": ..., "max": ...}``
- multi-row metrics, returning ``{"scores": {row_name: {"mean": ..., ...}}}``

Either may also carry a ``figure`` and an ``additional`` dict, which are
attached to the first row only to avoid duplication in the report.
"""

import pandas as pd

from backend.src.domain.evaluation.custom_metrics import (
    DCR,
    NNDR,
    ConfidenceIntervalOverlap,
    CorrelationMatrixDistance,
    DistributionComparisonReport,
    ExactMatchRows,
    KAnonymity,
    LDiversityPyCanon,
    UtilityTests,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import custom_metric_phase_label
from backend.src.infrastructure.time_profiling import profiler

logger = get_logger(__name__)

CUSTOM_METRIC_CLASSES = [
    DCR,
    NNDR,
    CorrelationMatrixDistance,
    ConfidenceIntervalOverlap,
    DistributionComparisonReport,
    ExactMatchRows,
    KAnonymity,
    UtilityTests,
]

if LDiversityPyCanon is not None:
    CUSTOM_METRIC_CLASSES.append(LDiversityPyCanon)


def run_custom_metrics(
    real: pd.DataFrame,
    syn: pd.DataFrame,
    report: pd.DataFrame,
    requested_metrics: list[str],
    real_data_dict: dict[str, pd.DataFrame] | None = None,
    synthetic_data_dict: dict[str, pd.DataFrame] | None = None,
) -> pd.DataFrame:
    """Append rows for each requested custom metric to ``report``.

    Args:
        real (pd.DataFrame): First real dataset, used by single-table metrics.
        syn (pd.DataFrame): First synthetic dataset, used by single-table metrics.
        report (pd.DataFrame): Report from the synthcity stage; rows are appended.
        requested_metrics (list[str]): Names (per ``MetricClass.name()``) to run.
        real_data_dict: All real tables, used by multitable metrics.
        synthetic_data_dict: All synthetic tables, used by multitable metrics.

    Returns:
        pd.DataFrame: The same report with custom-metric rows appended.
    """
    logger.info("Running custom metrics: %s", requested_metrics)

    real_data_dict = real_data_dict or {}
    synthetic_data_dict = synthetic_data_dict or {}

    for MetricClass in CUSTOM_METRIC_CLASSES:
        metric_name = MetricClass.name()
        if metric_name not in requested_metrics:
            continue

        try:
            with profiler.phase(custom_metric_phase_label(metric_name)):
                metric = MetricClass()
                if getattr(metric, "supports_multitable", False):
                    results = metric.evaluate(real_data_dict, synthetic_data_dict)
                else:
                    results = metric.evaluate(real, syn)

            logger.debug("Successfully executed custom metric %s", metric_name)
            report = _append_metric_rows(report, metric_name, results)
        except Exception as exc:
            logger.error("Failed to run custom metric %s: %s", metric_name, exc)

    return report


def _append_metric_rows(report: pd.DataFrame, metric_name: str, results: dict) -> pd.DataFrame:
    """Dispatch on result shape and append the resulting rows to ``report``."""
    figure = results.get("figure")
    additional = results.get("additional")

    if "scores" in results:
        return _append_multi_row_result(report, results["scores"], figure, additional)
    return _append_single_row_result(report, metric_name, results, figure, additional)


def _append_multi_row_result(
    report: pd.DataFrame,
    scores: dict[str, dict],
    figure: object,
    additional: dict | None,
) -> pd.DataFrame:
    """Append one row per ``scores`` entry; attach ``figure``/``additional`` to first row only."""
    first = True
    for row_name, row_scores in scores.items():
        row_data = dict(row_scores)
        row_data["figure"] = figure if first else None
        row_data["additional"] = additional if first else None
        first = False
        report = pd.concat([report, pd.DataFrame([row_data], index=[row_name])])
    return report


def _append_single_row_result(
    report: pd.DataFrame,
    metric_name: str,
    results: dict,
    figure: object,
    additional: dict | None,
) -> pd.DataFrame:
    """Append a single row for a metric returning ``score``/``min``/``max``."""
    row_data: dict = {}
    score = results.get("score")
    if score is not None:
        row_data["mean"] = score
        row_data["min"] = results.get("min")
        row_data["max"] = results.get("max")
    row_data["figure"] = figure
    row_data["additional"] = additional
    return pd.concat([report, pd.DataFrame([row_data], index=[metric_name])])
