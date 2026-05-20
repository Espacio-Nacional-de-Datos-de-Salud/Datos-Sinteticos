"""Tests for custom-statistics discovery and the `create_statistic` factory.

The custom-statistics loader is what wires user-defined metrics (age,
null_proportion, etc.) into ``ConfidenceIntervalOverlap``. A wrong default
module path silently degrades the metric to built-ins only — the symptom is
a missing row in the report rather than a crash, which is hard to spot.
"""

from __future__ import annotations

import importlib
import logging

import pytest

from backend.src.config.evaluation import CONFIDENCE_INTERVAL_LEVEL
from backend.src.domain.evaluation.custom_metrics.confidence_interval_overlap import (
    ConfidenceIntervalOverlap,
)
from backend.src.domain.evaluation.statistics import (
    MeanStatistic,
    Statistic,
    create_statistic,
    statistic_map,
)


def _bind_loader(module_path: str | None) -> dict | None:
    """Call `_load_custom_statistics` without instantiating the full evaluator."""
    stub = ConfidenceIntervalOverlap.__new__(ConfidenceIntervalOverlap)
    stub.custom_statistics_module = module_path
    return ConfidenceIntervalOverlap._load_custom_statistics(stub)


def test_default_module_resolves_and_exposes_expected_statistics() -> None:
    module = importlib.import_module(
        "backend.src.domain.evaluation.custom_metrics.custom_statistics"
    )
    assert hasattr(module, "CUSTOM_STATISTIC_MAP")

    custom_map = module.CUSTOM_STATISTIC_MAP
    for op_name in ("age", "null_proportion", "coefficient_of_variation", "interquartile_range"):
        assert op_name in custom_map, f"{op_name} missing from CUSTOM_STATISTIC_MAP"
        assert issubclass(custom_map[op_name], Statistic)


def test_loader_returns_map_when_module_path_is_valid() -> None:
    custom_map = _bind_loader("backend.src.domain.evaluation.custom_metrics.custom_statistics")

    assert custom_map is not None
    assert "age" in custom_map and "null_proportion" in custom_map


def test_loader_returns_none_and_logs_on_bad_module_path() -> None:
    records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _ListHandler(level=logging.ERROR)
    target_logger = logging.getLogger(
        "backend.src.domain.evaluation.custom_metrics.confidence_interval_overlap"
    )
    target_logger.addHandler(handler)
    try:
        custom_map = _bind_loader("backend.src.domain.evaluation.this_module_does_not_exist")
    finally:
        target_logger.removeHandler(handler)

    assert custom_map is None
    assert any("does_not_exist" in record.getMessage() for record in records)


def test_create_statistic_with_builtin_op_returns_builtin_class() -> None:
    stat = create_statistic(
        CONFIDENCE_INTERVAL_LEVEL,
        {"operation": "mean", "table": "t", "col": "c"},
    )
    assert isinstance(stat, MeanStatistic)
    assert stat.table == "t" and stat.column == "c"


def test_create_statistic_with_custom_op_uses_custom_map() -> None:
    custom_map = importlib.import_module(
        "backend.src.domain.evaluation.custom_metrics.custom_statistics"
    ).CUSTOM_STATISTIC_MAP

    stat = create_statistic(
        CONFIDENCE_INTERVAL_LEVEL,
        {"operation": "null_proportion", "table": "t", "col": "c"},
        custom_statistic_map=custom_map,
    )
    assert type(stat) is custom_map["null_proportion"]


def test_create_statistic_with_unknown_op_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown statistic operation"):
        create_statistic(
            CONFIDENCE_INTERVAL_LEVEL,
            {"operation": "totally_made_up", "table": "t", "col": "c"},
        )


def test_create_statistic_unknown_op_not_rescued_by_empty_custom_map() -> None:
    # Defensive: passing an empty custom map must not silently swallow unknown ops.
    assert "totally_made_up" not in statistic_map
    with pytest.raises(ValueError):
        create_statistic(
            CONFIDENCE_INTERVAL_LEVEL,
            {"operation": "totally_made_up", "table": "t", "col": "c"},
            custom_statistic_map={},
        )
