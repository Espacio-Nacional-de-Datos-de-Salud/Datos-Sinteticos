from __future__ import annotations
import pandas as pd
import pytest
from backend.src.domain.evaluation.custom_metrics.exact_match_rows import ExactMatchRows
from backend.src.domain.evaluation.dtype_alignment import align_dtypes


@pytest.fixture
def real_data() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "age": [25, 30, 35, 40, 45],
            "gender": ["M", "F", "M", "F", "M"],
            "diagnosis": ["A", "B", "C", "A", "B"],
            "score": [0.1, 0.5, 0.9, 0.3, 0.7],
        }
    )


@pytest.fixture
def clean_synthetic() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "age": [27, 32, 38, 42, 47],
            "gender": ["F", "M", "F", "M", "F"],
            "diagnosis": ["B", "C", "A", "B", "C"],
            "score": [0.2, 0.6, 0.8, 0.4, 0.6],
        }
    )


@pytest.fixture
def contaminated_synthetic(real_data, clean_synthetic) -> pd.DataFrame:
    """Synthetic dataset with 2 rows copied verbatim from real_data."""
    copied = real_data.iloc[[1, 3]].copy()
    return pd.concat([clean_synthetic, copied], ignore_index=True)


class TestExactMatchRowsNoMatches:
    def test_score_is_zero(self, real_data, clean_synthetic):
        result = ExactMatchRows().evaluate(real_data, clean_synthetic)
        assert result["score"] == 0.0

    def test_no_additional_payload(self, real_data, clean_synthetic):
        result = ExactMatchRows().evaluate(real_data, clean_synthetic)
        assert "additional" not in result

    def test_empty_real_returns_zero(self, clean_synthetic):
        result = ExactMatchRows().evaluate(pd.DataFrame(), clean_synthetic)
        assert result["score"] == 0.0

    def test_empty_synthetic_returns_zero(self, real_data):
        result = ExactMatchRows().evaluate(real_data, pd.DataFrame())
        assert result["score"] == 0.0


class TestAlignDtypes:
    """align_dtypes runs in the runner before every metric — covers the MostlyAI bool→int case."""

    def test_bool_real_cast_to_int_to_match_syn(self):
        real = pd.DataFrame({"flag": [True, False]})
        syn = pd.DataFrame({"flag": [1, 0]})
        real_out, _ = align_dtypes(real, syn)
        assert real_out["flag"].dtype != bool
        assert list(real_out["flag"]) == [1, 0]

    def test_int_real_cast_to_float_to_match_syn(self):
        real = pd.DataFrame({"x": [1, 2]})
        syn = pd.DataFrame({"x": [1.0, 2.0]})
        real_out, _ = align_dtypes(real, syn)
        assert pd.api.types.is_float_dtype(real_out["x"])

    def test_same_dtype_untouched(self):
        real = pd.DataFrame({"x": [1, 2]})
        syn = pd.DataFrame({"x": [3, 4]})
        real_out, _ = align_dtypes(real, syn)
        assert real_out["x"].dtype == real["x"].dtype

    def test_after_alignment_emr_detects_bool_copies(self):
        """End-to-end: bool real + int syn — after alignment ExactMatchRows must find the match."""
        real = pd.DataFrame({"name": ["A", "B"], "flag": [True, False]})
        syn = pd.DataFrame({"name": ["A", "B"], "flag": [1, 0]})
        real_aligned, syn_aligned = align_dtypes(real, syn)
        result = ExactMatchRows().evaluate(real_aligned, syn_aligned)
        assert result["additional"]["full_match"]["count"] == 2


class TestExactMatchRowsFullMatch:
    def test_detects_correct_count(self, real_data, contaminated_synthetic):
        result = ExactMatchRows().evaluate(real_data, contaminated_synthetic)
        assert result["additional"]["full_match"]["count"] == 2

    def test_proportion_matches_count(self, real_data, contaminated_synthetic):
        result = ExactMatchRows().evaluate(real_data, contaminated_synthetic)
        expected = 2 / len(contaminated_synthetic)
        assert result["score"] == pytest.approx(expected)
        assert result["additional"]["full_match"]["proportion"] == pytest.approx(
            expected
        )

    def test_detected_rows_match_real_source(self, real_data, contaminated_synthetic):
        result = ExactMatchRows(show_filtered_rows=True).evaluate(
            real_data, contaminated_synthetic
        )
        rows = pd.DataFrame(result["additional"]["full_match"]["rows"])
        assert set(rows["age"].tolist()) == {"30", "40"}

    def test_synthetic_indices_are_valid(self, real_data, contaminated_synthetic):
        result = ExactMatchRows(show_filtered_rows=True).evaluate(
            real_data, contaminated_synthetic
        )
        indices = result["additional"]["full_match"]["synthetic_indices"]
        assert len(indices) == 2
        for idx in indices:
            assert 0 <= idx < len(contaminated_synthetic)

    def test_full_dataset_duplicate_detects_all(self, real_data):
        result = ExactMatchRows().evaluate(real_data, real_data.copy())
        assert result["additional"]["full_match"]["count"] == len(real_data)
        assert result["score"] == pytest.approx(1.0)


class TestExactMatchRowsLeaveOneOut:
    def test_loo_entries_for_every_column(self, real_data, contaminated_synthetic):
        result = ExactMatchRows().evaluate(real_data, contaminated_synthetic)
        loo = result["additional"]["leave_one_out"]
        assert set(loo.keys()) == {"age", "diagnosis", "score", "gender"}
        for v in loo.values():
            assert "count" in v and "proportion" in v

    def test_loo_catches_row_with_one_bad_column(self, real_data):
        """Synthetic row that matches real on all columns except one should appear in loo."""
        syn = real_data.copy()
        syn.loc[0, "score"] = 999.0
        result = ExactMatchRows(show_filtered_rows=True).evaluate(real_data, syn)
        assert result["additional"]["full_match"]["count"] == 4
        loo = result["additional"]["leave_one_out"]
        assert loo["score"]["count"] == 5
        assert "rows" in loo["score"]

    def test_loo_no_rows_when_count_zero(self, real_data, clean_synthetic):
        """Even when run, loo entries with count=0 must not include the heavy 'rows' field."""
        syn = clean_synthetic.copy()
        result = ExactMatchRows().evaluate(real_data, syn)
        assert "additional" not in result

    def test_single_column_df_skips_loo(self):
        """Leave-one-out requires at least 2 columns — single-column df must not crash."""
        real = pd.DataFrame({"x": [1, 2, 3]})
        syn = pd.DataFrame({"x": [1, 2, 3]})
        result = ExactMatchRows().evaluate(real, syn)
        assert result["additional"]["full_match"]["count"] == 3
        assert result["additional"]["leave_one_out"] == {}
