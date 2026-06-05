"""Tests for the PyCanon-backed l-diversity privacy metric."""

# ruff: noqa: E402

from __future__ import annotations

import pandas as pd
import pytest

pycanon = pytest.importorskip("pycanon")

from backend.src.config import evaluation as evaluation_config
from backend.src.domain.evaluation.custom_metrics import LDiversityPyCanon
from backend.src.domain.evaluation.custom_metrics.l_diversity_pycanon import (
    LDiversityPyCanon as LDiversityPyCanonClass,
)
from backend.src.domain.evaluation.runner import EvaluationRunner


@pytest.fixture()
def l_diversity_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    real = pd.DataFrame(
        {
            "age_band": ["20s", "20s", "20s", "30s", "30s"],
            "zip3": ["100", "100", "100", "200", "200"],
            "diagnosis": ["A", "B", "C", "A", "B"],
        }
    )
    synthetic = pd.DataFrame(
        {
            "age_band": ["20s", "20s", "20s", "30s", "30s"],
            "zip3": ["100", "100", "100", "200", "200"],
            "diagnosis": ["A", "A", "B", "A", "A"],
        }
    )
    return real, synthetic


def test_registry_exposes_l_diversity_metric() -> None:
    assert LDiversityPyCanon is LDiversityPyCanonClass
    assert LDiversityPyCanonClass.name() == "l_diversity_pycanon"


def test_distinct_l_diversity_routes_to_custom_metric() -> None:
    runner = EvaluationRunner(
        eval_results_dir="/tmp",
        metrics={"privacy": ["k-anonymization", "distinct l-diversity"]},
    )

    synthcity_metrics, custom_metric_names = runner._partition_requested_metrics(None)

    assert synthcity_metrics["privacy"] == []
    assert "k_anonymity" in custom_metric_names
    assert "l_diversity_pycanon" in custom_metric_names


def test_missing_qi_config_skips_without_pairwise_fallback(
    monkeypatch: pytest.MonkeyPatch,
    l_diversity_frames: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    real, synthetic = l_diversity_frames
    monkeypatch.setattr(evaluation_config, "QUASI_IDENTIFIER_SUBSETS", None)
    monkeypatch.setattr(evaluation_config, "SENSITIVE_COLUMNS", ["diagnosis"])

    result = LDiversityPyCanonClass().evaluate(real, synthetic)

    assert result["score"] is None
    assert result["additional"]["skipped"] is True
    assert result["additional"]["skip_reason"] == "missing_quasi_identifier_subsets"


def test_missing_sensitive_columns_skips(
    monkeypatch: pytest.MonkeyPatch,
    l_diversity_frames: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    real, synthetic = l_diversity_frames
    monkeypatch.setattr(
        evaluation_config,
        "QUASI_IDENTIFIER_SUBSETS",
        {"demographic": ["age_band", "zip3"]},
    )
    monkeypatch.setattr(evaluation_config, "SENSITIVE_COLUMNS", None)

    result = LDiversityPyCanonClass().evaluate(real, synthetic)

    assert result["score"] is None
    assert result["additional"]["skip_reason"] == "missing_sensitive_columns"


def test_computes_configured_l_diversity_with_pycanon(
    monkeypatch: pytest.MonkeyPatch,
    l_diversity_frames: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    real, synthetic = l_diversity_frames
    monkeypatch.setattr(
        evaluation_config,
        "QUASI_IDENTIFIER_SUBSETS",
        {"demographic": ["age_band", "zip3"]},
    )
    monkeypatch.setattr(evaluation_config, "SENSITIVE_COLUMNS", ["diagnosis"])

    result = LDiversityPyCanonClass().evaluate(real, synthetic)

    assert result["scores"]["l_diversity.real"]["mean"] == 2.0
    assert result["scores"]["l_diversity.syn"]["mean"] == 1.0
    assert result["additional"]["subsets"]["demographic"]["real_l"] == 2
    assert result["additional"]["subsets"]["demographic"]["syn_l"] == 1
    assert (
        result["additional"]["report_metadata"]["library"]
        == "pycanon.anonymity.l_diversity"
    )


def test_sensitive_columns_are_removed_from_qi_subset(
    monkeypatch: pytest.MonkeyPatch,
    l_diversity_frames: tuple[pd.DataFrame, pd.DataFrame],
) -> None:
    real, synthetic = l_diversity_frames
    monkeypatch.setattr(
        evaluation_config,
        "QUASI_IDENTIFIER_SUBSETS",
        {"mixed": ["age_band", "diagnosis"]},
    )
    monkeypatch.setattr(evaluation_config, "SENSITIVE_COLUMNS", ["diagnosis"])

    result = LDiversityPyCanonClass().evaluate(real, synthetic)

    assert result["additional"]["subsets"]["mixed"]["columns"] == ["age_band"]
