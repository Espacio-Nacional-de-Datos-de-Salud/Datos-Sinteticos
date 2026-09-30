"""Tests for composite primary key support in `MetadataExtractor`.

The extractor accepts an optional ``composite_pk_config`` mapping
``{table_name: [col, ...]}``. For each listed table it synthesizes a single
unique PK column by concatenating the named columns, instead of relying on
heuristic single-column detection. Invalid configs (missing columns or a
non-unique key) fall back to the heuristics.
"""

from __future__ import annotations

import pandas as pd

from backend.src.domain.preprocessing.metadata_extractor import MetadataExtractor


def _patients() -> pd.DataFrame:
    """A table whose natural key is (patient_id, year), neither unique alone."""
    return pd.DataFrame(
        {
            "patient_id": ["p1", "p1", "p2", "p2"],
            "year": [2020, 2021, 2020, 2021],
            "weight": [70, 71, 60, 62],
        }
    )


def test_composite_pk_is_synthesized_and_unique() -> None:
    df = _patients()
    extractor = MetadataExtractor(
        {"patients": df},
        composite_pk_config={"patients": ["patient_id", "year"]},
    )
    pks = extractor.extract_primary_keys()

    pk_col = pks["patients"]
    sep = MetadataExtractor.COMPOSITE_PK_SEP
    assert pk_col == f"patient_id{sep}year"
    # The synthesized column is added to the table in-place and is unique.
    assert pk_col in extractor.data["patients"].columns
    assert extractor.data["patients"][pk_col].is_unique
    assert extractor.data["patients"][pk_col].iloc[0] == f"p1{sep}2020"


def test_composite_pk_falls_back_when_columns_missing() -> None:
    df = _patients()
    extractor = MetadataExtractor(
        {"patients": df},
        composite_pk_config={"patients": ["patient_id", "nonexistent"]},
    )
    pks = extractor.extract_primary_keys()
    # No column named with the separator was synthesized.
    assert MetadataExtractor.COMPOSITE_PK_SEP not in pks.get("patients", "")


def test_composite_pk_falls_back_when_not_unique() -> None:
    # patient_id alone is NOT unique -> a composite of just [patient_id]
    # must be rejected and detection must fall back.
    df = _patients()
    extractor = MetadataExtractor(
        {"patients": df},
        composite_pk_config={"patients": ["patient_id"]},
    )
    pks = extractor.extract_primary_keys()
    assert MetadataExtractor.COMPOSITE_PK_SEP not in pks.get("patients", "")


def test_composite_pk_matches_columns_case_insensitively() -> None:
    # Config uses lowercase; the table has UPPERCASE headers (the data cleaner
    # preserves source casing). Matching must still succeed.
    df = _patients().rename(columns={"patient_id": "PATIENT_ID", "year": "YEAR"})
    extractor = MetadataExtractor(
        {"patients": df},
        composite_pk_config={"patients": ["patient_id", "year"]},
    )
    pks = extractor.extract_primary_keys()
    pk_col = pks["patients"]
    sep = MetadataExtractor.COMPOSITE_PK_SEP
    # Synthesized name uses the table's actual column casing.
    assert pk_col == f"PATIENT_ID{sep}YEAR"
    assert extractor.data["patients"][pk_col].is_unique


def test_empty_list_synthesizes_surrogate_key() -> None:
    # An event-style table with no natural unique key: an empty config list
    # requests a 0..N-1 surrogate PK.
    df = pd.DataFrame(
        {
            "patient_id": ["p1", "p1", "p1"],
            "drug": ["x", "x", "x"],
            "date": [1, 1, 1],  # genuinely no unique key
        }
    )
    extractor = MetadataExtractor({"events": df}, composite_pk_config={"events": []})
    pks = extractor.extract_primary_keys()

    pk_col = pks["events"]
    assert pk_col == MetadataExtractor.SURROGATE_PK_COL
    col = extractor.data["events"][pk_col]
    assert col.is_unique
    assert list(col) == [0, 1, 2]


def test_no_config_uses_heuristics() -> None:
    # A genuinely unique single column is still detected with no config.
    df = pd.DataFrame({"id": [1, 2, 3], "v": [9, 8, 7]})
    extractor = MetadataExtractor({"t": df})
    pks = extractor.extract_primary_keys()
    assert pks["t"] == "id"
