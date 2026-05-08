"""Tests for `backend.src.core.preprocessing.logical_rules` domain logic.

Each logical rule class implements three phases: `apply_pre` (encode before
synthesis), `apply_post` (decode after synthesis), and `sanity_check` (validate
original data against rule constraints). Tests verify round-trip encode/decode
behavior, domain-specific edge cases, and violation detection. Also tests
`LogicalRuleManager` multi-hop join dispatch and aggregated sanity reports.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from backend.src.core.errors import RelationshipNotDefinedError
from backend.src.core.preprocessing.logical_rules import (
    DateInequalityRule,
    DateToAgeRule,
    ForeignKeysConsistencyRule,
    LogicalRuleManager,
    NumericBucketRule,
    NumericInequalityRule,
    SemanticProportionalConsistencyRule,
)


def _midpoint_uniform_scalar(lower: float, upper: float) -> float:
    """Return the midpoint between lower and upper (for np.random.uniform mocking)."""
    return (lower + upper) / 2


def _midpoint_uniform_series(lower: pd.Series, upper: pd.Series) -> pd.Series:
    """Return the midpoint between lower and upper Series (for np.random.uniform mocking)."""
    return (lower + upper) / 2


def test_manager_applies_rule_through_multihop_join_and_strips_origin_columns() -> None:
    data = {
        "conditions": pd.DataFrame(
            {
                "condition_id": [1, 2],
                "visit_id": [10, 20],
                "condition_start_date": ["2020-01-10", "2020-02-05"],
            }
        ),
        "visits": pd.DataFrame(
            {
                "visit_id": [10, 20],
                "patient_id": [100, 200],
                "visit_start_date": ["2020-01-01", "2020-02-01"],
            }
        ),
        "patients": pd.DataFrame(
            {
                "patient_id": [100, 200],
                "birth_date": ["1980-01-01", "1990-02-01"],
            }
        ),
    }
    relationships = {
        ("conditions", "visits"): [("visit_id", "visit_id")],
        ("visits", "patients"): [("patient_id", "patient_id")],
    }
    manager = LogicalRuleManager(
        rules=[
            DateToAgeRule(
                table_origin="patients",
                table_target="conditions",
                origin_col="birth_date",
                target_col="age_at_condition",
                reference_date_col="condition_start_date",
            )
        ]
    )

    processed = manager.apply_all_pre(data, relationships)

    conditions = processed["conditions"]
    assert conditions["age_at_condition"].tolist() == [40.0, 30.0]
    assert "birth_date" not in conditions.columns
    assert "visit_start_date" not in conditions.columns
    assert "patient_id_origin" not in conditions.columns


def test_foreign_key_consistency_reconstructs_from_joined_parent_and_reports_failures() -> (
    None
):
    data = {
        "conditions": pd.DataFrame(
            {
                "condition_id": [1, 2],
                "visit_id": [10, 20],
                "person_id": [999, 200],
            }
        ),
        "visits": pd.DataFrame(
            {
                "visit_id": [10, 20],
                "person_id": [100, 200],
            }
        ),
    }
    manager = LogicalRuleManager(
        rules=[
            ForeignKeysConsistencyRule(
                table_origin="visits",
                table_target="conditions",
                target_col="person_id",
            )
        ],
        relationships={("conditions", "visits"): [("visit_id", "visit_id")]},
    )

    # Phase 1: preprocessing removes target column (person_id will be reconstructed from parent)
    preprocessed = manager.apply_all_pre(
        data,
        relationships={("conditions", "visits"): [("visit_id", "visit_id")]},
    )
    assert "person_id" not in preprocessed["conditions"].columns

    # Phase 2: post-processing reconstructs target column from joined parent
    reconstructed = manager.apply_all_post(preprocessed)
    assert reconstructed["conditions"]["person_id"].tolist() == [100, 200]

    # Phase 3: sanity check detects original data violations (condition_id=1 had person_id=999 != 100)
    report = manager.run_rules_sanity_checks(data)
    assert report.loc[0, "status"] == "FAIL"
    assert report.loc[0, "failed_rows"] == 1


def test_date_inequality_with_constant_reconstructs_from_non_negative_duration() -> (
    None
):
    rule = DateInequalityRule(
        table_target="admissions",
        target_col="discharge_date",
        constraint="2020-01-31",
        constraint_operator="<=",
    )
    original = pd.DataFrame({"discharge_date": ["2020-01-20", "2020-01-31"]})

    # Pre-processing: encode as days since deadline (must be >= 0)
    preprocessed = rule.apply_pre(original)
    assert preprocessed["duration_discharge_date"].tolist() == [11, 0]
    assert "discharge_date" not in preprocessed.columns

    # Post-processing: reconstruct dates from durations (clamps negatives to deadline)
    synthetic = pd.DataFrame({"duration_discharge_date": [-5, 3]})
    reconstructed = rule.apply_post(synthetic)

    assert reconstructed["discharge_date"].tolist() == [
        pd.Timestamp("2020-01-31"),
        pd.Timestamp("2020-01-28"),
    ]
    assert "duration_discharge_date" not in reconstructed.columns

    # Sanity check: flag dates that violate the constraint
    failures = rule.sanity_check(pd.DataFrame({"discharge_date": ["2020-02-01"]}))
    assert failures["error_type"].tolist() == ["TEMPORAL_INCONSISTENCY"]


def test_date_inequality_with_invalid_origin_date_coerces_to_nat() -> None:
    rule = DateInequalityRule(
        table_target="condition_occurrence",
        origin_col="condition_start_date",
        target_col="condition_end_date",
        constraint_operator=">=",
    )

    reconstructed = rule.apply_post(
        pd.DataFrame(
            {
                "condition_start_date": ["-- 00", "2020-01-10"],
                "duration_condition_end_date": [5, 3],
            }
        )
    )

    assert pd.isna(reconstructed.loc[0, "condition_end_date"])
    assert reconstructed.loc[1, "condition_end_date"] == pd.Timestamp("2020-01-13")


def test_numeric_inequality_with_column_reconstructs_and_validates_less_than_rule() -> (
    None
):
    rule = NumericInequalityRule(
        table_target="measurements",
        origin_col="upper_bound",
        target_col="value",
        constraint_operator="<=",
    )
    original = pd.DataFrame({"upper_bound": [10, 20], "value": [7, 20]})

    # Pre-processing: encode as difference from upper bound (must be >= 0)
    preprocessed = rule.apply_pre(original)
    assert preprocessed["diff_value"].tolist() == [3, 0]

    # Post-processing: reconstruct value from difference (clamps negatives to upper bound)
    synthetic = pd.DataFrame({"upper_bound": [10, 20], "diff_value": [-2, 5]})
    reconstructed = rule.apply_post(synthetic)

    assert reconstructed["value"].tolist() == [10, 15]
    assert "diff_value" not in reconstructed.columns

    # Sanity check: flag values that violate the constraint
    failures = rule.sanity_check(
        pd.DataFrame({"upper_bound": [10, 20], "value": [11, 19]})
    )
    assert failures.index.tolist() == [0]
    assert failures.loc[0, "error_type"] == "NUMERIC_INEQUALITY_VIOLATION"


def test_date_to_age_can_drop_and_reconstruct_origin_column() -> None:
    rule = DateToAgeRule(
        table_target="patients",
        origin_col="birth_date",
        target_col="age",
        reference_date="2020-01-01",
        drop_origin=True,
        reconstruct_origin=True,
    )
    original = pd.DataFrame({"birth_date": ["2000-01-02", "1980-01-01"]})

    preprocessed = rule.apply_pre(original)
    assert preprocessed["age"].tolist() == [19.0, 40.0]
    assert "birth_date" not in preprocessed.columns

    reconstructed = rule.apply_post(preprocessed)

    assert "birth_date" in reconstructed.columns
    assert reconstructed["birth_date"].dt.year.tolist() == [2000, 1980]


def test_numeric_bucket_can_drop_and_reconstruct_origin_within_bucket(
    monkeypatch,
) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_scalar)
    rule = NumericBucketRule(
        table_target="patients",
        origin_col="age",
        target_col="age_bucket",
        bins=[0, 18, 65],
        labels=["minor", "adult"],
        drop_origin=True,
        reconstruct_origin=True,
    )

    preprocessed = rule.apply_pre(pd.DataFrame({"age": [7, 42]}))
    assert preprocessed["age_bucket"].astype(str).tolist() == ["minor", "adult"]
    assert "age" not in preprocessed.columns

    reconstructed = rule.apply_post(pd.DataFrame({"age_bucket": ["minor", "adult"]}))
    np.testing.assert_allclose(reconstructed["age"].to_numpy(), [9.0, 41.5])


def test_semantic_proportional_rule_round_trips_scores_and_flags_invalid_pairs(
    monkeypatch,
) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    rule = SemanticProportionalConsistencyRule(
        table_target="diagnoses",
        origin_col="sex",
        target_col="diagnosis",
    )
    original = pd.DataFrame(
        {
            "sex": ["F", "F", "F", "M"],
            "diagnosis": ["flu", "flu", "pregnancy", "flu"],
        }
    )

    preprocessed = rule.apply_pre(original)
    assert "diagnosis" not in preprocessed.columns
    assert "diagnosis_score" in preprocessed.columns

    reconstructed = rule.apply_post(preprocessed)
    assert reconstructed["diagnosis"].tolist() == original["diagnosis"].tolist()

    failures = rule.sanity_check(
        pd.DataFrame(
            {"sex": ["F", "M", "X"], "diagnosis": ["flu", "pregnancy", "anything"]}
        )
    )

    assert failures.index.tolist() == [1]
    assert failures.loc[1, "error_type"] == "SEMANTIC_INCONSISTENCY"


def test_rules_sanity_checks_reports_skipped_pass_and_fail_rows() -> None:
    passing_rule = NumericInequalityRule(
        table_target="measurements",
        target_col="value",
        constraint=0,
    )
    failing_rule = NumericInequalityRule(
        table_target="measurements",
        target_col="value",
        constraint=5,
    )
    skipped_rule = NumericInequalityRule(
        table_target="missing_table",
        target_col="value",
        constraint=0,
    )
    manager = LogicalRuleManager(rules=[passing_rule, failing_rule, skipped_rule])

    report = manager.run_rules_sanity_checks(
        {"measurements": pd.DataFrame({"value": [1, 2, 10]})}
    )

    assert report["status"].tolist() == ["PASS", "FAIL", "SKIPPED"]
    assert report["failed_rows"].tolist() == [0, 2, 0]
    assert report["total_rows"].tolist() == [3, 3, 0]


def test_manager_raises_relationship_error_when_join_rule_has_no_relationships() -> (
    None
):
    manager = LogicalRuleManager(
        rules=[
            ForeignKeysConsistencyRule(
                table_origin="visits",
                table_target="conditions",
                target_col="person_id",
            )
        ]
    )

    with pytest.raises(RelationshipNotDefinedError):
        manager.apply_all_post(
            {
                "conditions": pd.DataFrame({"condition_id": [1], "visit_id": [10]}),
                "visits": pd.DataFrame({"visit_id": [10], "person_id": [100]}),
            }
        )
