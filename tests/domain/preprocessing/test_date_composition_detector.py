import pandas as pd
import pytest
from unittest.mock import patch

from backend.src.domain.preprocessing.date_composition_detector import (
    _tokenize,
    _name_matches_part,
    _value_coincidence,
    detect_date_composition_candidates,
    build_date_composition_warnings,
    DateCompositionCandidate,
)
from backend.src.infrastructure.utils import ModelEncodingType

# -----------------------------------------------------------------------------
# Unit Tests for internal helpers
# -----------------------------------------------------------------------------

def test_tokenize_handles_camel_and_separators():
    name = "birthDateTime-OfBirth"
    tokens = _tokenize(name)
    # Should split on camel case, hyphens and underscores, lower‑casing everything
    assert tokens == {"birth", "date", "time", "of", "birth"}


def test_name_matches_part_recognises_year_tokens():
    # column names that contain any of the year tokens should match
    assert _name_matches_part("dob_year", "year")
    assert _name_matches_part("anio", "year")
    # false positives should be rejected
    assert not _name_matches_part("age", "month")

def test_repeated_letters_in_part_not_matched():
    assert not _name_matches_part("birth_yeeaar", "year")
    assert not _name_matches_part("birth_year", "yearr")
    assert not _name_matches_part("dday", "day")

@patch("backend.src.domain.preprocessing.date_composition_detector.parse_dates")
def test_value_coincidence_perfect_match(mock_parse_dates):
    # canonical column with datetime strings
    canon = pd.Series(["2020-01-01", "2021-02-03", "2022-03-04"])
    # part column containing the year values
    part = pd.Series([2020, 2021, 2022])
    # mock parse_dates to simply convert to datetime
    mock_parse_dates.return_value = pd.to_datetime(canon)
    confidence = _value_coincidence(canon, part, "year")
    assert confidence == 1.0

@patch("backend.src.domain.preprocessing.date_composition_detector.parse_dates")
def test_value_coincidence_partial_match(mock_parse_dates):
    canon = pd.Series(["2020-01-01", "2021-02-03", None])
    part = pd.Series([2020, 999, None])
    mock_parse_dates.return_value = pd.to_datetime(canon)
    confidence = _value_coincidence(canon, part, "year")
    # Only one matching known value out of two known rows -> 0.5
    assert confidence == 0.5

# -----------------------------------------------------------------------------
# Integration Tests for detection and warning building
# -----------------------------------------------------------------------------

def test_detect_date_composition_candidates_basic():
    # Create a table with a canonical datetime column and its parts
    df = pd.DataFrame({
        "dob": pd.to_datetime(["1990-01-02", "1985-05-06", "2000-12-31"]),
        "dob_year": [1990, 1985, 2000],
        "dob_month": [1, 5, 12],
        "dob_day": [2, 6, 31],
        "other": ["a", "b", "c"],
    })
    data = {"patients": df}
    encoding = {"patients": {"dob": ModelEncodingType.tabular_datetime}}

    candidates = detect_date_composition_candidates(data, encoding)
    assert len(candidates) == 1
    cand: DateCompositionCandidate = candidates[0]
    assert cand.table == "patients"
    assert cand.canonical_col == "dob"
    # All three parts should be detected
    assert set(cand.part_cols.keys()) == {"year", "month", "day"}
    assert cand.confidence == 1.0

def test_detect_date_composition_candidates_no_match_due_to_name():
    # Parts exist but column names do not contain any of the part tokens
    df = pd.DataFrame({
        "event_ts": pd.to_datetime(["2020-01-01", "2021-02-02"]),
        "year": [2020, 2021],  # token "yr" matches year, but we will rename to something unrelated
        "month": [1, 2],
    })
    data = {"events": df}
    encoding = {"events": {"event_ts": ModelEncodingType.tabular_datetime}}
    # Rename columns to avoid token match
    df.rename(columns={"year": "y", "month": "m"}, inplace=True)

    candidates = detect_date_composition_candidates(data, encoding)
    # No candidates because name matching fails
    assert candidates == []

def test_build_date_composition_warnings_structure():
    cand = DateCompositionCandidate(
        table="patients",
        canonical_col="dob",
        part_cols={"year": "dob_year", "month": "dob_month"},
        confidence=0.95,
    )
    warnings = build_date_composition_warnings([cand])
    # One warning for canonical column, two for parts = 3 total
    assert len(warnings) == 3
    # Canonical warning should reference the canonical column
    canonical_warn = next(w for w in warnings if w["column"] == "dob")
    assert canonical_warn["kind"] == "date_composition_candidate"
    assert "dob_year" in canonical_warn["message"] and "dob_month" in canonical_warn["message"]
    # Part warnings should reference the part column names
    for part_col in ["dob_year", "dob_month"]:
        part_warn = next(w for w in warnings if w["column"] == part_col)
        assert part_warn["kind"] == "date_composition_candidate"
        assert "coincide" in part_warn["message"]
        assert part_warn["details"]["canonical_col"] == "dob"
        assert part_warn["details"]["part_cols"]["year"] == "dob_year"
        assert part_warn["details"]["part_cols"]["month"] == "dob_month"
        assert part_warn["details"]["confidence"] == 0.95
