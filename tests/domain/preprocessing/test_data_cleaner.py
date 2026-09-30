import numpy as np
import pandas as pd
import pytest

from backend.src.domain.preprocessing.data_cleaner import DataCleaner

# -----------------------------------------------------------------------------
# Unit Tests
# -----------------------------------------------------------------------------

def test_removes_completely_empty_columns():
    """Columns where every value is NaN should be dropped."""
    raw = {"t": pd.DataFrame({"id": [1, 2], "empty1": [None, None], "empty2": [np.nan, np.nan], "keep": ["a", "b"]})}
    cleaned = DataCleaner(raw).run()
    assert "empty1" not in cleaned["t"].columns
    assert "empty2" not in cleaned["t"].columns
    assert "id" in cleaned["t"].columns
    assert "keep" in cleaned["t"].columns

def test_keeps_partially_filled_columns():
    """Columns with at least one non-null value should be kept."""
    raw = {"t": pd.DataFrame({"id": [1, 2], "partial": [None, "x"]})}
    cleaned = DataCleaner(raw).run()
    assert "partial" in cleaned["t"].columns

def test_strips_whitespace_from_column_names():
    """Leading/trailing whitespace in column names should be stripped."""
    raw = {"t": pd.DataFrame({" name ": ["Alice"], "  age  ": [30]})}
    cleaned = DataCleaner(raw).run()
    assert list(cleaned["t"].columns) == ["name", "age"]

def test_preserves_column_name_case():
    """Column name casing should be preserved (only whitespace is stripped)."""
    raw = {"t": pd.DataFrame({" MyColumn ": [1]})}
    cleaned = DataCleaner(raw).run()
    assert "MyColumn" in cleaned["t"].columns

def test_converts_integer_floats_to_int64():
    """Float columns containing only whole numbers should be converted to Int64."""
    raw = {"t": pd.DataFrame({"score": [1.0, 2.0, 3.0]})}
    cleaned = DataCleaner(raw).run()
    assert str(cleaned["t"]["score"].dtype) == "Int64"

def test_keeps_true_floats_as_float():
    """Float columns with actual fractional values should remain float."""
    raw = {"t": pd.DataFrame({"value": [1.5, 2.3]})}
    cleaned = DataCleaner(raw).run()
    assert pd.api.types.is_float_dtype(cleaned["t"]["value"])

def test_converts_integer_floats_with_nulls():
    """Float columns with NaN + whole numbers should still convert to Int64."""
    raw = {"t": pd.DataFrame({"count": [1.0, None, 3.0]})}
    cleaned = DataCleaner(raw).run()
    assert str(cleaned["t"]["count"].dtype) == "Int64"
    assert cleaned["t"]["count"].isna().sum() == 1

def test_skips_all_null_float_column():
    """A float column that is entirely NaN should be dropped (all-empty rule), not converted."""
    raw = {"t": pd.DataFrame({"id": [1], "empty_float": [np.nan]})}
    cleaned = DataCleaner(raw).run()
    assert "empty_float" not in cleaned["t"].columns

def test_removes_duplicate_rows():
    """Exact duplicate rows should be removed."""
    raw = {"t": pd.DataFrame({"id": [1, 1, 2], "val": ["a", "a", "b"]})}
    cleaned = DataCleaner(raw).run()
    assert len(cleaned["t"]) == 2

def test_skips_empty_table():
    """An empty DataFrame should be skipped entirely and not appear in cleaned output."""
    raw = {"empty_table": pd.DataFrame()}
    cleaned = DataCleaner(raw).run()
    assert "empty_table" not in cleaned

def test_no_changes_needed():
    """A table already clean should pass through unchanged."""
    df = pd.DataFrame({"id": [1, 2], "name": ["Alice", "Bob"]})
    raw = {"t": df.copy()}
    cleaned = DataCleaner(raw).run()
    pd.testing.assert_frame_equal(cleaned["t"].reset_index(drop=True), df)

def test_multiple_tables():
    """All tables in the input dict should be cleaned independently."""
    raw = {
        "users": pd.DataFrame({" id ": [1, 1], "name": ["A", "A"]}),
        "orders": pd.DataFrame({"oid": [10], "empty": [None]}),
    }
    cleaned = DataCleaner(raw).run()
    assert "id" in cleaned["users"].columns
    assert len(cleaned["users"]) == 1
    assert "empty" not in cleaned["orders"].columns


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------

def test_full_pipeline_combined_operations():
    """Integration test exercising all cleaning steps together on a realistic table."""
    raw = {
        "patients": pd.DataFrame({
            " patient_id ": [1, 2, 2, 3],
            "  Age  ": [25.0, 30.0, 30.0, 45.0],
            "weight": [70.5, 80.2, 80.2, 90.1],
            "notes": [None, None, None, None],
        })
    }
    cleaned = DataCleaner(raw).run()
    patients = cleaned["patients"]

    # Whitespace stripped
    assert "patient_id" in patients.columns
    assert "Age" in patients.columns

    # Empty column dropped
    assert "notes" not in patients.columns

    # Integer-like float converted
    assert str(patients["Age"].dtype) == "Int64"

    # True float preserved
    assert pd.api.types.is_float_dtype(patients["weight"])

    # Duplicates removed (row index 1 and 2 were identical)
    assert len(patients) == 3

def test_pipeline_with_string_and_mixed_types():
    """Integration test with mixed dtypes ensuring no unintended type coercion."""
    raw = {
        "records": pd.DataFrame({
            "code": ["A01", "B02", "A01"],
            "value": [100.0, 200.0, 100.0],
            "ratio": [0.5, 0.75, 0.5],
            "flag": [True, False, True],
        })
    }
    cleaned = DataCleaner(raw).run()
    records = cleaned["records"]

    # Duplicates removed
    assert len(records) == 2

    # Integer-like float converted
    assert str(records["value"].dtype) == "Int64"

    # True float kept
    assert pd.api.types.is_float_dtype(records["ratio"])

    # String and bool columns untouched
    assert records["code"].dtype == object
    assert records["flag"].dtype == bool
