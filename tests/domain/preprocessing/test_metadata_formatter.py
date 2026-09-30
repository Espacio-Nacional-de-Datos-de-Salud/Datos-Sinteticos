"""Tests for MetadataFormatter encoding fallback and detect_series_encoding.

Regression context: rule-created aux columns (e.g. ``duration_*_days``) are not
in the inspection's encoding map. They used to default to TABULAR_CATEGORICAL,
which turned every value of a high-cardinality numeric into a rare category —
the engine's rare-category protection then generated the column 100% null and
every datetime reconstructed from it came back empty.
"""

import pandas as pd

from backend.src.domain.encoding_types import ModelEncodingType
from backend.src.domain.preprocessing.metadata_formatter import MetadataFormatter
from backend.src.infrastructure.utils import detect_series_encoding


def _column_types(metadata: dict, table: str) -> dict[str, str]:
    table_def = next(t for t in metadata["tables"] if t["name"] == table)
    return {c["name"]: c["model_encoding_type"] for c in table_def["columns"]}


class TestDetectSeriesEncoding:
    def test_integer_durations_are_numeric(self):
        series = pd.Series([6846, 7959, 9072, 14, 230], dtype="Int64")
        assert detect_series_encoding(series) == ModelEncodingType.tabular_numeric_auto

    def test_floats_are_numeric(self):
        series = pd.Series([1.5, 2.25, 3.75, 4.0])
        assert detect_series_encoding(series) == ModelEncodingType.tabular_numeric_auto

    def test_bool_is_categorical(self):
        series = pd.Series([True, False, True])
        assert detect_series_encoding(series) == ModelEncodingType.tabular_categorical

    def test_two_value_numeric_flag_is_categorical(self):
        series = pd.Series([0, 1, 0, 1, 1])
        assert detect_series_encoding(series) == ModelEncodingType.tabular_categorical

    def test_strings_refine_to_datetime(self):
        series = pd.Series(["2023-01-01", "2023-02-01", "2023-03-01"])
        assert detect_series_encoding(series) == ModelEncodingType.tabular_datetime

    def test_refine_false_keeps_categorical(self):
        series = pd.Series(["2023-01-01", "2023-02-01", "2023-03-01"])
        assert (
            detect_series_encoding(series, refine=False)
            == ModelEncodingType.tabular_categorical
        )


class TestMetadataFormatterEncodingFallback:
    def test_rule_created_numeric_column_not_defaulted_to_categorical(self):
        df = pd.DataFrame(
            {
                "person_id": [1, 2, 3, 4],
                "duration_condition_start_datetime_days": pd.array(
                    [6846, 7959, 9072, 10500], dtype="Int64"
                ),
            }
        )
        types_data = {
            "condition_occurrence": {"person_id": ModelEncodingType.tabular_numeric_auto}
        }

        metadata = MetadataFormatter().format({"condition_occurrence": df}, None, types_data)

        col_types = _column_types(metadata, "condition_occurrence")
        assert col_types["duration_condition_start_datetime_days"] == "TABULAR_NUMERIC_AUTO"

    def test_known_columns_keep_mapped_encoding(self):
        df = pd.DataFrame({"code": [101, 102, 103, 104, 105]})
        types_data = {"events": {"code": ModelEncodingType.tabular_categorical}}

        metadata = MetadataFormatter().format({"events": df}, None, types_data)

        assert _column_types(metadata, "events")["code"] == "TABULAR_CATEGORICAL"

    def test_unknown_string_column_falls_back_to_detection(self):
        df = pd.DataFrame({"created_at": ["2024-05-01", "2024-05-02", "2024-05-03"]})

        metadata = MetadataFormatter().format({"events": df}, None, {})

        assert _column_types(metadata, "events")["created_at"] == "TABULAR_DATETIME"
