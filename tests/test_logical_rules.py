"""Tests for `backend.src.domain.preprocessing.logical_rules` domain logic.

Each logical rule class implements three phases: `apply_pre` (encode before
synthesis), `apply_post` (decode after synthesis), and `sanity_check` (validate
original data against rule constraints). Tests verify round-trip encode/decode
behavior, domain-specific edge cases, and violation detection. Also tests
`LogicalRuleManager` multi-hop join dispatch and aggregated sanity reports.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from backend.src.infrastructure.errors import RelationshipNotDefinedError
from backend.src.infrastructure.errors import RuleConcatenationError, RuleSuperimpositionError
from backend.src.domain.preprocessing.logical_rules import (
    DateInequalityRule,
    DateToAgeRule,
    ForeignKeysConsistencyRule,
    LogicalRule,
    LogicalRuleManager,
    NumericBucketRule,
    NumericInequalityRule,
    NumericThresholdRule,
    SemanticProportionalConsistencyRule,
)


@dataclass
class _DummyRule(LogicalRule):
    target_col: str = None
    origin_col: str = None
    source_col: str = None
    aux_col: str = None

    def apply_pre(self, df: pd.DataFrame) -> pd.DataFrame:
        return df


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
                aux_col="age_at_condition",
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
        aux_col="age",
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
        aux_col="age_bucket",
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


def test_detect_rule_interactions_raises_on_superimposition() -> None:
    manager = LogicalRuleManager(rules=[_DummyRule(table_target="patients", target_col="age")])

    with pytest.raises(RuleSuperimpositionError):
        manager._detect_rule_interactions(
            _DummyRule(table_target="patients", target_col="age")
        )


def test_detect_rule_interactions_no_op() -> None:
    manager = LogicalRuleManager(rules=[])
    manager.concat_rules = []

    first = _DummyRule(table_target="visits", table_origin="patients", target_col="visit_id")
    second = _DummyRule(table_target="patients", table_origin="visits", target_col="patient_id")
    manager.rules.append(first)

    manager._detect_rule_interactions(second)

    assert manager.concat_rules == []


def test_sort_concat_rules_orders_by_dependency_chain() -> None:
    manager = LogicalRuleManager(rules=[])
    manager.concat_rules = []

    rule_create_bucket = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        target_col="age_bucket",
    )
    rule_use_bucket = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_bucket",
        target_col="is_adult",
    )

    manager.concat_rules = [rule_use_bucket, rule_create_bucket]

    sorted_rules = manager._sort_concat_rules(
        {"patients.age", "patients.age_bucket", "patients.is_adult"}
    )

    assert sorted_rules == [rule_create_bucket, rule_use_bucket]


def test_sort_concat_rules_orders_by_aux_dependency() -> None:
    manager = LogicalRuleManager(rules=[])
    manager.concat_rules = []

    rule_create_aux = _DummyRule(
        table_target="visits",
        target_col="visit_end_date",
        aux_col="duration_visit_end_date",
    )
    rule_use_aux = _DummyRule(
        table_target="visits",
        table_origin="visits",
        origin_col="duration_visit_end_date",
        target_col="stay_class",
    )

    manager.concat_rules = [rule_use_aux, rule_create_aux]

    sorted_rules = manager._sort_concat_rules(
        {"visits.visit_end_date", "visits.stay_class"}
    )

    assert sorted_rules == [rule_create_aux, rule_use_aux]


def test_sort_concat_rules_handles_derived_rules() -> None:
    manager = LogicalRuleManager(rules=[])
    manager.concat_rules = []

    rule_bucket = NumericBucketRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        aux_col="age_bucket",
        bins=[0, 18, 65],
        labels=["minor", "adult"],
    )
    rule_threshold = NumericThresholdRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_bucket",
        aux_col="is_adult",
        threshold=1,
        operator=">=",
        true_value=True,
        false_value=False,
    )

    manager.concat_rules = [rule_threshold, rule_bucket]

    sorted_rules = manager._sort_concat_rules(
        {
            "patients.age",
        }
    )

    assert sorted_rules == [rule_bucket, rule_threshold]


def test_sort_concat_rules_orders_derived_and_numeric_dependency() -> None:
    manager = LogicalRuleManager(rules=[])
    manager.concat_rules = []

    rule_age = DateToAgeRule(
        table_target="patients",
        table_origin="patients",
        origin_col="birth_date",
        aux_col="age",
        reference_date="2020-01-01",
    )
    rule_is_adult = NumericThresholdRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        aux_col="is_adult",
        threshold=18,
        operator=">=",
        true_value=True,
        false_value=False,
    )

    manager.concat_rules = [rule_is_adult, rule_age]

    sorted_rules = manager._sort_concat_rules(
        {
            "patients.birth_date",
        }
    )

    assert sorted_rules == [rule_age, rule_is_adult]


def test_sort_concat_rules_orders_three_rule_chain_with_semantic_consistency() -> None:
    manager = LogicalRuleManager(rules=[])
    manager.concat_rules = []

    rule_age = DateToAgeRule(
        table_target="patients",
        table_origin="patients",
        origin_col="birth_date",
        aux_col="age",
        reference_date="2020-01-01",
    )
    rule_is_senior = NumericThresholdRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        aux_col="is_senior",
        threshold=65,
        operator=">=",
        true_value=True,
        false_value=False,
    )
    rule_diagnosis = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="is_senior",
        target_col="diagnosis",
    )

    manager.concat_rules = [rule_diagnosis, rule_is_senior, rule_age]

    sorted_rules = manager._sort_concat_rules(
        {
            "patients.birth_date",
            "patients.diagnosis",
        }
    )

    assert sorted_rules == [rule_age, rule_is_senior, rule_diagnosis]


def test_sort_concat_rules_skips_when_origin_column_missing() -> None:
    manager = LogicalRuleManager(rules=[])
    manager.concat_rules = []

    rule_missing_origin = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="missing_col",
        target_col="derived",
    )

    manager.concat_rules = [rule_missing_origin]

    sorted_rules = manager._sort_concat_rules({"patients.age"})

    assert sorted_rules == []

def test_sort_concat_rules_detects_cycles() -> None:
    manager = LogicalRuleManager(rules=[])
    manager.concat_rules = []

    rule_a = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="b",
        target_col="a",
    )
    rule_b = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="a",
        target_col="b",
    )

    manager.concat_rules = [rule_a, rule_b]

    with pytest.raises(RuleConcatenationError):
        manager._sort_concat_rules({"patients.a", "patients.b"})

def test_multiple_concat_rules() -> None:
    manager = LogicalRuleManager()

    rule_a = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="b",
        target_col="a",
    )
    rule_b = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="c",
        target_col="b",
    )
    rule_c = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        target_col="c",
    )
    manager.concat_rules = [rule_b, rule_c, rule_a]

    sorted_rules = manager._sort_concat_rules({"patients.age", "patients.a", "patients.b", "patients.c"})

    assert sorted_rules == [rule_c, rule_b, rule_a]


def test_sort_concat_rules_with_two_independent_chains() -> None:
    manager = LogicalRuleManager()

    rule_a = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="b",
        target_col="a",
    )
    rule_b = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="c",
        target_col="b",
    )
    rule_c = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        target_col="c",
    )
    rule_x = _DummyRule(
        table_target="visits",
        table_origin="visits",
        origin_col="y",
        target_col="x",
    )
    rule_y = _DummyRule(
        table_target="visits",
        table_origin="visits",
        origin_col="z",
        target_col="y",
    )
    rule_z = _DummyRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_date",
        target_col="z",
    )

    manager.concat_rules = [rule_b, rule_x, rule_z, rule_c, rule_y, rule_a]

    sorted_rules = manager._sort_concat_rules(
        {
            "patients.age",
            "patients.a",
            "patients.b",
            "patients.c",
            "visits.visit_date",
            "visits.x",
            "visits.y",
            "visits.z",
        }
    )

    assert len(sorted_rules) == 6
    positions = {id(rule): idx for idx, rule in enumerate(sorted_rules)}

    assert positions[id(rule_c)] < positions[id(rule_b)] < positions[id(rule_a)]
    assert positions[id(rule_z)] < positions[id(rule_y)] < positions[id(rule_x)]