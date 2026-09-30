"""Tests for DateCompositionRule and its opt-in candidate detector."""

import pandas as pd
import pytest

from backend.src.domain.preprocessing.date_composition_detector import (
    DateCompositionCandidate,
    build_date_composition_warnings,
    detect_date_composition_candidates,
)
from backend.src.domain.preprocessing.logical_rules import DateCompositionRule
from backend.src.infrastructure.date_parsing import clear_cache
from backend.src.infrastructure.utils import ModelEncodingType


@pytest.fixture(autouse=True)
def _reset_cache():
    clear_cache()
    yield
    clear_cache()


# --- Rule mechanics ---


def _sample_df():
    return pd.DataFrame(
        {
            "dob": ["1990-03-25", "1985-07-13", "2001-11-20"],
            "dob_year": [1990, 1985, 2001],
            "dob_month": [3, 7, 11],
            "dob_day": [25, 13, 20],
            "other": ["a", "b", "c"],
        }
    )


def test_rule_requires_canonical_and_parts():
    with pytest.raises(ValueError):
        DateCompositionRule(table_target="t", part_cols={"year": "dob_year"})
    with pytest.raises(ValueError):
        DateCompositionRule(table_target="t", canonical_col="dob")
    with pytest.raises(ValueError):
        DateCompositionRule(
            table_target="t", canonical_col="dob", part_cols={"century": "dob_century"}
        )


def test_apply_pre_drops_only_part_columns():
    rule = DateCompositionRule(
        table_target="t",
        canonical_col="dob",
        part_cols={"year": "dob_year", "month": "dob_month", "day": "dob_day"},
    )
    out = rule.apply_pre(_sample_df())
    assert "dob" in out.columns
    assert "other" in out.columns
    assert {"dob_year", "dob_month", "dob_day"}.isdisjoint(out.columns)


def test_apply_post_reconstructs_parts_from_canonical():
    rule = DateCompositionRule(
        table_target="t",
        canonical_col="dob",
        part_cols={"year": "dob_year", "month": "dob_month", "day": "dob_day"},
    )
    synthetic = pd.DataFrame({"dob": ["1991-04-12", "1986-08-30"], "other": ["x", "y"]})
    out = rule.apply_post(synthetic)
    assert list(out["dob_year"]) == [1991, 1986]
    assert list(out["dob_month"]) == [4, 8]
    assert list(out["dob_day"]) == [12, 30]


def test_apply_post_missing_canonical_logs_and_returns():
    rule = DateCompositionRule(
        table_target="t", canonical_col="dob", part_cols={"year": "dob_year"}
    )
    df = pd.DataFrame({"other": ["x"]})
    out = rule.apply_post(df)
    assert list(out.columns) == ["other"]


def test_sanity_check_flags_mismatched_rows():
    rule = DateCompositionRule(
        table_target="t",
        canonical_col="dob",
        part_cols={"year": "dob_year"},
    )
    df = pd.DataFrame({"dob": ["1990-03-25", "1985-07-13"], "dob_year": [1990, 1999]})
    failing = rule.sanity_check(df)
    assert len(failing) == 1
    assert failing.iloc[0]["error_type"] == "DATE_COMPOSITION_MISMATCH"


# --- Candidate detector ---


def test_detector_finds_matching_split_columns():
    df = _sample_df()
    encoding_types = {"t": {"dob": ModelEncodingType.tabular_datetime}}
    candidates = detect_date_composition_candidates({"t": df}, encoding_types)
    assert len(candidates) == 1
    cand = candidates[0]
    assert cand.canonical_col == "dob"
    assert cand.part_cols == {"year": "dob_year", "month": "dob_month", "day": "dob_day"}
    assert cand.confidence >= 0.99


def test_detector_ignores_split_when_values_disagree():
    df = pd.DataFrame(
        {
            "dob": ["1990-03-25", "1985-07-13", "2001-11-20"],
            "dob_year": [9999, 9999, 9999],
        }
    )
    encoding_types = {"t": {"dob": ModelEncodingType.tabular_datetime}}
    candidates = detect_date_composition_candidates({"t": df}, encoding_types)
    assert candidates == []


def test_detector_picks_up_spanish_part_names():
    df = pd.DataFrame(
        {
            "fecha_nac": ["1990-03-25", "1985-07-13"],
            "fecha_nac_anio": [1990, 1985],
            "fecha_nac_mes": [3, 7],
            "fecha_nac_dia": [25, 13],
        }
    )
    encoding_types = {"t": {"fecha_nac": ModelEncodingType.tabular_datetime}}
    candidates = detect_date_composition_candidates({"t": df}, encoding_types)
    assert len(candidates) == 1
    assert candidates[0].part_cols == {
        "year": "fecha_nac_anio",
        "month": "fecha_nac_mes",
        "day": "fecha_nac_dia",
    }


def test_detector_skips_when_canonical_not_datetime_encoded():
    df = _sample_df()
    encoding_types = {"t": {"dob": ModelEncodingType.tabular_categorical}}
    candidates = detect_date_composition_candidates({"t": df}, encoding_types)
    assert candidates == []


def test_warnings_fan_out_to_canonical_and_each_part():
    cand = DateCompositionCandidate(
        table="t",
        canonical_col="dob",
        part_cols={"year": "dob_year", "month": "dob_month"},
        confidence=1.0,
    )
    warnings = build_date_composition_warnings([cand])
    columns = {w["column"] for w in warnings}
    assert columns == {"dob", "dob_year", "dob_month"}
    for w in warnings:
        assert w["kind"] == "date_composition_candidate"
        assert w["default_excluded"] is False
        assert w["details"]["rule_type"] == "date_composition"
        assert w["details"]["canonical_col"] == "dob"


def test_detector_finds_omop_person_style_columns():
    df = pd.DataFrame(
        {
            "birth_datetime": ["1996-07-13", "1951-03-30"],
            "year_of_birth": [1996, 1951],
            "month_of_birth": [7, 3],
            "day_of_birth": [13, 30],
        }
    )
    encoding_types = {"person": {"birth_datetime": ModelEncodingType.tabular_datetime}}
    cands = detect_date_composition_candidates({"person": df}, encoding_types)
    assert len(cands) == 1
    assert cands[0].part_cols == {
        "year": "year_of_birth",
        "month": "month_of_birth",
        "day": "day_of_birth",
    }
