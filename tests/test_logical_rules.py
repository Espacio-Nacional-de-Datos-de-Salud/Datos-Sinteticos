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
    InteractionType,
    LogicalRule,
    LogicalRuleManager,
    NumericBucketRule,
    NumericInequalityRule,
    NumericThresholdRule,
    SemanticProportionalConsistencyRule,
    SemanticRankingConsistencyRule,
)
from backend.src.domain.preprocessing.utils import (
    assign_default_context_keys,
    format_relationships,
    infer_foreign_keys_consistency_rules,
)


@dataclass
class _DummyRule(LogicalRule):
    target_col: str = None
    origin_col: str = None
    source_col: str = None
    aux_col: str = None
    interaction_type: InteractionType = InteractionType.ISOLATED

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
                table_target="conditions",
                origin_col="condition_start_date",
                aux_col="age_at_condition",
                reference_date_col="birth_date",
                reference_date_table="patients",
            )
        ]
    )

    processed = manager.apply_all_pre(data, relationships)

    conditions = processed["conditions"]
    # aux_col gains the unit suffix (default "years"); span = origin - reference
    assert conditions["age_at_condition_years"].tolist() == [40.0, 30.0]
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
    assert preprocessed["duration_discharge_date_days"].tolist() == [11, 0]
    assert "discharge_date" not in preprocessed.columns

    # Post-processing: reconstruct dates from durations (clamps negatives to deadline)
    synthetic = pd.DataFrame({"duration_discharge_date_days": [-5, 3]})
    reconstructed = rule.apply_post(synthetic)

    assert reconstructed["discharge_date"].tolist() == [
        pd.Timestamp("2020-01-31"),
        pd.Timestamp("2020-01-28"),
    ]
    assert "duration_discharge_date_days" not in reconstructed.columns

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
                "duration_condition_end_date_days": [5, 3],
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
    # New convention: origin_col is the more recent date (admission), reference
    # is the older anchor (DOB). The dropped/reconstructed column is the origin.
    rule = DateToAgeRule(
        table_target="patients",
        origin_col="admission_date",
        aux_col="age",
        reference_date="2000-01-02",
        drop_origin=True,
        reconstruct_origin=True,
    )
    original = pd.DataFrame({"admission_date": ["2019-01-02", "2040-01-02"]})

    preprocessed = rule.apply_pre(original)
    # span = origin - reference (years). Suffix appended automatically.
    assert preprocessed["age_years"].tolist() == [19.0, 40.0]
    assert "admission_date" not in preprocessed.columns

    reconstructed = rule.apply_post(preprocessed)

    assert "admission_date" in reconstructed.columns
    assert reconstructed["admission_date"].dt.year.tolist() == [2019, 2040]


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


def test_semantic_proportional_rule_round_trips_with_composite_keys(
    monkeypatch,
) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule.add_group_key("age_bucket")

    original = pd.DataFrame(
        {
            "sex": ["F", "F", "M", "M"],
            "age_bucket": ["adult", "adult", "adult", "senior"],
            "diagnosis": ["flu", "flu", "flu", "cancer"],
        }
    )

    preprocessed = rule.apply_pre(original)
    assert "diagnosis" not in preprocessed.columns
    assert "diagnosis_score" in preprocessed.columns

    reconstructed = rule.apply_post(preprocessed)
    assert reconstructed["diagnosis"].tolist() == original["diagnosis"].tolist()


def test_semantic_proportional_rule_composite_keys_flags_invalid_pairs(
    monkeypatch,
) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule.add_group_key("age_bucket")

    original = pd.DataFrame(
        {
            "sex": ["F", "F", "M", "M"],
            "age_bucket": ["adult", "adult", "adult", "senior"],
            "diagnosis": ["flu", "flu", "flu", "cancer"],
        }
    )
    rule.apply_pre(original)

    failures = rule.sanity_check(
        pd.DataFrame(
            {
                "sex": ["F", "M"],
                "age_bucket": ["adult", "adult"],
                "diagnosis": ["flu", "cancer"],
            }
        )
    )

    assert failures.index.tolist() == [1]
    assert failures.loc[1, "error_type"] == "SEMANTIC_INCONSISTENCY"

def test_semantic_proportional_rule_composite_keys_flags_unseen_pairs(
    monkeypatch,
) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule.add_group_key("age_bucket")

    original = pd.DataFrame(
        {
            "sex": ["F", "F", "M", "M"],
            "age_bucket": ["adult", "adult", "adult", "senior"],
            "diagnosis": ["flu", "flu", "flu", "cancer"],
        }
    )
    rule.apply_pre(original)

    failures = rule.sanity_check(
        pd.DataFrame(
            {
                "sex": ["F", "M"],
                "age_bucket": ["adult", "adult"],
                "diagnosis": ["flu", "X"],
            }
        )
    )

    assert failures.index.tolist() == [1]
    assert failures.loc[1, "error_type"] == "SEMANTIC_INCONSISTENCY"


def test_semantic_add_group_key_seeds_origin_col() -> None:
    rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )

    rule.add_group_key("age_bucket")

    assert rule.group_cols == ["sex", "age_bucket"]

def test_single_origin_semantic_proportional_rule_flags_invalid_pairs(
    monkeypatch,
) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule.apply_pre(
        pd.DataFrame(
            {
                "sex": ["F", "F", "M", "M"],
                "diagnosis": ["flu", "flu", "flu", "cancer"],
            }
        )
    )

    failures = rule.sanity_check(
        pd.DataFrame(
            {
                "sex": ["F", "M"],
                "diagnosis": ["cancer", "cancer"],
            }
        )
    )
    assert failures.index.tolist() == [0]

def test_single_origin_semantic_proportional_rule_sets_None_for_unseen_origin(
    monkeypatch,
) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    pre_df = rule.apply_pre(
        pd.DataFrame(
            {
                "sex": ["F", "F"],
                "diagnosis": ["flu", "flu"],
            }
        )
    )

    result = rule.apply_post(
        pre_df.assign(sex=["F", "X"])
    )

    assert result["diagnosis"].tolist() == ["flu", None]
    failures = rule.sanity_check(
        result
    )
    assert failures.empty


def test_composite_origin_semantic_proportional_rule_sets_None_for_unseen_group(
    monkeypatch,
) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule.add_group_key("age_bucket")

    pre_df = rule.apply_pre(
        pd.DataFrame(
            {
                "sex": ["F", "F"],
                "age_bucket": ["adult", "adult"],
                "diagnosis": ["flu", "flu"],
            }
        )
    )

    result = rule.apply_post(
        pre_df.assign(sex=["F", "F"], age_bucket=["adult", "senior"])
    )

    assert result["diagnosis"].tolist() == ["flu", None]
    failures = rule.sanity_check(result)
    assert failures.empty


def test_semantic_concatenation_on_origin_side() -> None:
    data = {
        "patients": pd.DataFrame(
            {
                "person_id": [1, 2],
                "birth_date": ["1980-01-01", "1990-01-01"],
                "as_of_date": ["2020-01-01", "2020-01-01"],
                "diagnosis": ["flu", "cancer"],
            }
        )
    }
    manager = LogicalRuleManager()

    rule_age = DateToAgeRule(
        table_target="patients",
        table_origin="patients",
        origin_col="as_of_date",
        aux_col="age",
        reference_date_col="birth_date",
    )
    # aux_col gains the unit suffix → "age_years"; bucket consumes that name.
    rule_bucket = NumericBucketRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_years",
        aux_col="age_bucket",
        bins=[0, 65, 120],
        labels=["adult", "senior"],
    )
    rule_diagnosis = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="age_bucket",
        target_col="diagnosis",
    )
    
    manager.add_rule(rule_diagnosis)
    manager.add_rule(rule_bucket)
    assert rule_diagnosis.interaction_type == InteractionType.CONCATENATED
    assert rule_bucket.interaction_type == InteractionType.CONCATENATED
    manager.add_rule(rule_age)
    assert rule_age.interaction_type == InteractionType.CONCATENATED

    preprocessed = manager.apply_all_pre(data, relationships={})

    assert "age_bucket" in preprocessed["patients"].columns
    assert "diagnosis" not in preprocessed["patients"].columns
    assert "diagnosis_score" in preprocessed["patients"].columns

    reconstructed = manager.apply_all_post(preprocessed)
    assert reconstructed["patients"]["diagnosis"].tolist() == ["flu", "cancer"]


def test_semantic_concatenation_on_target_side_with_semantic_rule() -> None:
    data = {
        "patients": pd.DataFrame(
            {
                "sex": ["F", "M"],
                "diagnosis": ["flu", "cancer"],
                "risk_band": ["low", "high"],
                "some_other_col": ["hello", "goodbye"],
            }
        )
    }
    manager = LogicalRuleManager()

    rule_diagnosis = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule_risk_band = SemanticRankingConsistencyRule(
        table_target="patients",
        origin_col="diagnosis",
        target_col="risk_band",
    )
    rule_second_same_origin = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="diagnosis",
        target_col="some_other_col",
    )

    manager.add_rule(rule_second_same_origin)
    manager.add_rule(rule_risk_band)
    manager.add_rule(rule_diagnosis)

    preprocessed = manager.apply_all_pre(data, relationships={})

    assert "diagnosis" not in preprocessed["patients"].columns
    assert "risk_band" not in preprocessed["patients"].columns
    assert "diagnosis_score" in preprocessed["patients"].columns
    assert "risk_band_score" in preprocessed["patients"].columns
    assert "some_other_col_score" in preprocessed["patients"].columns

    reconstructed = manager.apply_all_post(preprocessed)
    assert reconstructed["patients"]["diagnosis"].tolist() == ["flu", "cancer"]
    assert reconstructed["patients"]["risk_band"].tolist() == ["low", "high"]

def test_concat_semantic_rule_fails_target_doesnt_exist() -> None:
    data = {
        "patients": pd.DataFrame(
            {
                "sex": ["F", "M"],
                "diagnosis": ["flu", "cancer"],
                "risk_band": ["low", "high"],
            }
        )
    }
    manager = LogicalRuleManager()

    rule_diagnosis = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule_risk_band = SemanticRankingConsistencyRule(
        table_target="patients",
        origin_col="diagnosis",
        target_col="risk_band",
    )
    rule_second_same_origin = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="diagnosis",
        target_col="some_other_col",
    )

    manager.add_rule(rule_diagnosis)
    manager.add_rule(rule_risk_band)
    manager.add_rule(rule_second_same_origin)

    manager.apply_all_pre(data, relationships={})
    assert rule_second_same_origin not in manager.rules

def test_isolated_semantic_rule_fails_target_doesnt_exist() -> None:
    data = {
        "patients": pd.DataFrame(
            {
                "sex": ["F", "M"],
                "diagnosis": ["flu", "cancer"],
                "risk_band": ["low", "high"],
            }
        )
    }
    manager = LogicalRuleManager()

    rule_diagnosis = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule_second_same_origin = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="risk_band",
        target_col="some_other_col",
    )

    manager.add_rule(rule_diagnosis)
    manager.add_rule(rule_second_same_origin)

    manager.apply_all_pre(data, relationships={})
    assert rule_second_same_origin not in manager.rules


def test_isolated_rule_removed_when_origin_column_missing() -> None:
    data = {
        "patients": pd.DataFrame(
            {
                "diagnosis": ["flu"],
                "age": [30],
            }
        )
    }
    manager = LogicalRuleManager()

    rule_missing_origin = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="missing_origin",
        target_col="diagnosis",
    )

    manager.add_rule(rule_missing_origin)

    manager.apply_all_pre(data, relationships={})
    assert rule_missing_origin not in manager.rules


def test_isolated_rule_removed_when_target_column_missing() -> None:
    data = {
        "patients": pd.DataFrame(
            {
                "age": [30],
            }
        )
    }
    manager = LogicalRuleManager()

    rule_missing_target = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        target_col="missing_target",
    )

    manager.add_rule(rule_missing_target)

    manager.apply_all_pre(data, relationships={})
    assert rule_missing_target not in manager.rules


def test_concat_rule_removed_when_target_column_missing() -> None:
    data = {
        "patients": pd.DataFrame(
            {
                "age": [30],
            }
        )
    }
    manager = LogicalRuleManager()

    rule_create_bucket = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        aux_col="age_bucket",
        target_col="missing_target",
    )
    rule_use_bucket = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_bucket",
        aux_col="is_adult",
    )

    manager.add_rule(rule_create_bucket)
    manager.add_rule(rule_use_bucket)

    assert rule_create_bucket.interaction_type == InteractionType.CONCATENATED
    assert rule_use_bucket.interaction_type == InteractionType.CONCATENATED

    manager.apply_all_pre(data, relationships={})
    assert rule_create_bucket not in manager.rules


def test_concat_rule_removed_when_origin_column_missing() -> None:
    data = {
        "patients": pd.DataFrame(
            {
                "age": [30],
            }
        )
    }
    manager = LogicalRuleManager()

    rule_create_bucket = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        aux_col="age_bucket",
        target_col="missing_target",
    )
    rule_use_bucket = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_bucket",
        aux_col="is_adult",
    )

    manager.add_rule(rule_create_bucket)
    manager.add_rule(rule_use_bucket)

    manager.apply_all_pre(data, relationships={})
    assert rule_use_bucket not in manager.rules

def test_single_origin_semantic_proportional_rule_flags_unseen_target_values(
    monkeypatch,
) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule.apply_pre(
        pd.DataFrame(
            {
                "sex": ["F", "F", "M", "M"],
                "diagnosis": ["flu", "flu", "flu", "cancer"],
            }
        )
    )

    failures = rule.sanity_check(
        pd.DataFrame(
            {
                "sex": ["F", "M"],
                "diagnosis": ["X", "cancer"],
            }
        )
    )
    assert failures.index.tolist() == [0]

def test_semantic_proportional_rule_ignores_unseen_group_keys(
    monkeypatch,
) -> None:
    ### DONT KNOW AB THIS ONE
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule.add_group_key("age_bucket")

    rule.apply_pre(
        pd.DataFrame(
            {
                "sex": ["F", "F"],
                "age_bucket": ["adult", "adult"],
                "diagnosis": ["flu", "flu"],
            }
        )
    )

    failures = rule.sanity_check(
        pd.DataFrame(
            {
                "sex": ["F"],
                "age_bucket": ["senior"],
                "diagnosis": ["cancer"],
            }
        )
    )

    assert failures.empty

def test_semantic_proportional_rule_skips_when_group_column_missing(
    monkeypatch,
) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    rule.add_group_key("age_bucket")

    rule.apply_pre(
        pd.DataFrame(
            {
                "sex": ["F", "F"],
                "age_bucket": ["adult", "adult"],
                "diagnosis": ["flu", "flu"],
            }
        )
    )

    failures = rule.sanity_check(
        pd.DataFrame(
            {
                "sex": ["F"],
                "diagnosis": ["flu"],
            }
        )
    )

    assert failures.empty


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


def test_detect_rule_interactions_flips_isolated_date_inequality_rules() -> None:
    manager = LogicalRuleManager(rules=[])

    existing_rule = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_start_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    new_rule = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="admission_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )

    assert manager.add_rule(existing_rule) is True
    assert manager.add_rule(new_rule) is True

    assert existing_rule.interaction_type == InteractionType.SUPERIMPOSED
    assert new_rule.interaction_type == InteractionType.SUPERIMPOSED
    assert new_rule.constraint_operator == ">="
    assert new_rule.origin_col == "visit_end_date"
    assert new_rule.target_col == "admission_date"
    assert existing_rule.constraint_operator == ">="
    assert existing_rule.origin_col == "visit_end_date"
    assert existing_rule.target_col == "visit_start_date"

    sorted_rules = manager._sort_concat_rules(
        {"visits.visit_start_date", "visits.visit_end_date", "visits.admission_date"}
    )
    # doesnt really matter which order they are in
    assert sorted_rules[0] == existing_rule
    assert sorted_rules[1] == new_rule


def test_detect_rule_interactions_raises_when_existing_rule_is_concatenated() -> None:
    manager = LogicalRuleManager(rules=[])

    existing_rule = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_start_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    existing_rule.interaction_type = InteractionType.CONCATENATED
    manager.rules.append(existing_rule)

    new_rule = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="admission_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )

    with pytest.raises(RuleSuperimpositionError):
        manager._detect_rule_interactions(new_rule)


def test_detect_rule_interactions_flips_isolated_numeric_inequality_rules() -> None:
    manager = LogicalRuleManager(rules=[])

    existing_rule = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="min_value",
        target_col="lab_value",
        constraint_operator="<=",
    )
    new_rule = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="max_value",
        target_col="lab_value",
        constraint_operator="<=",
    )

    assert manager.add_rule(existing_rule) is True
    assert manager.add_rule(new_rule) is True

    assert existing_rule.interaction_type == InteractionType.SUPERIMPOSED
    assert new_rule.interaction_type == InteractionType.SUPERIMPOSED
    assert new_rule.constraint_operator == ">="
    assert new_rule.origin_col == "lab_value"
    assert new_rule.target_col == "max_value"
    assert new_rule.aux_col.startswith("max_value_flipped_")
    assert existing_rule.constraint_operator == ">="
    assert existing_rule.origin_col == "lab_value"
    assert existing_rule.target_col == "min_value"

    sorted_rules = manager._sort_concat_rules(
        {"labs.min_value", "labs.lab_value", "labs.max_value"}
    )
    assert sorted_rules[0] == existing_rule
    assert sorted_rules[1] == new_rule


def test_detect_rule_interactions_flips_chained_date_inequality_rules() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_a = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="b_date",
        target_col="a_date",
        constraint_operator="<=",
    )
    rule_b = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="c_date",
        target_col="a_date",
        constraint_operator="<=",
    )
    rule_c = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="d_date",
        target_col="b_date",
        constraint_operator="<=",
    )

    assert manager.add_rule(rule_a) is True
    assert manager.add_rule(rule_c) is True
    assert manager.add_rule(rule_b) is True

    assert rule_a.interaction_type == InteractionType.SUPERIMPOSED
    assert rule_b.interaction_type == InteractionType.SUPERIMPOSED
    assert rule_c.interaction_type == InteractionType.SUPERIMPOSED

    assert rule_a.constraint_operator == ">="
    assert rule_b.constraint_operator == ">="
    assert rule_c.constraint_operator == ">="

    assert rule_a.origin_col == "a_date"
    assert rule_a.target_col == "b_date"
    assert rule_b.origin_col == "a_date"
    assert rule_b.target_col == "c_date"
    assert rule_c.origin_col == "b_date"
    assert rule_c.target_col == "d_date"


def test_detect_rule_interactions_flips_chained_numeric_inequality_rules() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_a = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="b_value",
        target_col="a_value",
        constraint_operator="<=",
    )
    rule_b = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="c_value",
        target_col="a_value",
        constraint_operator="<=",
    )
    rule_c = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="d_value",
        target_col="b_value",
        constraint_operator="<=",
    )

    assert manager.add_rule(rule_a) is True
    assert manager.add_rule(rule_c) is True
    assert manager.add_rule(rule_b) is True

    assert rule_a.interaction_type == InteractionType.SUPERIMPOSED
    assert rule_b.interaction_type == InteractionType.SUPERIMPOSED
    assert rule_c.interaction_type == InteractionType.SUPERIMPOSED

    assert rule_a.constraint_operator == ">="
    assert rule_b.constraint_operator == ">="
    assert rule_c.constraint_operator == ">="

    assert rule_a.origin_col == "a_value"
    assert rule_a.target_col == "b_value"
    assert rule_b.origin_col == "a_value"
    assert rule_b.target_col == "c_value"
    assert rule_c.origin_col == "b_value"
    assert rule_c.target_col == "d_value"


def test_detect_rule_interactions_flips_four_superimposed_numeric_rules() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_a = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="min_value",
        target_col="lab_value",
        constraint_operator="<=",
    )
    rule_b = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="max_value",
        target_col="lab_value",
        constraint_operator="<=",
    )
    rule_c = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="baseline_value",
        target_col="lab_value",
        constraint_operator="<=",
    )
    rule_d = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="limit_value",
        target_col="lab_value",
        constraint_operator="<=",
    )

    assert manager.add_rule(rule_a) is True
    assert manager.add_rule(rule_b) is True
    assert manager.add_rule(rule_c) is True
    assert manager.add_rule(rule_d) is True

    for rule in (rule_a, rule_b, rule_c, rule_d):
        assert rule.interaction_type == InteractionType.SUPERIMPOSED
        assert rule.constraint_operator == ">="
        assert rule.origin_col == "lab_value"

    assert rule_a.target_col == "min_value"
    assert rule_b.target_col == "max_value"
    assert rule_c.target_col == "baseline_value"
    assert rule_d.target_col == "limit_value"

    aux_names = {rule.aux_col for rule in (rule_a, rule_b, rule_c, rule_d)}
    assert len(aux_names) == 4


def test_detect_rule_interactions_raises_when_existing_numeric_rule_is_concatenated() -> (
    None
):
    manager = LogicalRuleManager(rules=[])

    existing_rule = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="min_value",
        target_col="lab_value",
        constraint_operator="<=",
    )
    existing_rule.interaction_type = InteractionType.CONCATENATED
    manager.rules.append(existing_rule)

    new_rule = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="max_value",
        target_col="lab_value",
        constraint_operator="<=",
    )

    with pytest.raises(RuleSuperimpositionError):
        manager._detect_rule_interactions(new_rule)


def test_detect_rule_interactions_merges_semantic_group_keys() -> None:
    manager = LogicalRuleManager(rules=[])

    existing_rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="sex",
        target_col="diagnosis",
    )
    new_rule = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="age_bucket",
        target_col="diagnosis",
    )

    assert manager.add_rule(existing_rule) is True
    assert manager.add_rule(new_rule) is True

    assert len(manager.rules) == 1
    assert manager.rules[0] is existing_rule
    assert set(existing_rule.group_cols) == {"sex", "age_bucket"}


def test_detect_rule_interactions_no_op() -> None:
    manager = LogicalRuleManager(rules=[])

    first = _DummyRule(table_target="visits", table_origin="patients", target_col="visit_id")
    second = _DummyRule(table_target="patients", table_origin="visits", target_col="patient_id")
    manager.rules.append(first)

    manager._detect_rule_interactions(second)

    assert [rule for rule in manager.rules if rule.interaction_type != InteractionType.ISOLATED and not rule.rejection_sampling] == []


def test_sort_concat_rules_orders_by_dependency_chain() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_create_bucket = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        aux_col="age_bucket",
        interaction_type=InteractionType.CONCATENATED,
    )
    rule_use_bucket = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_bucket",
        aux_col="is_adult",
        interaction_type=InteractionType.CONCATENATED,
    )

    manager.rules = [rule_use_bucket, rule_create_bucket]

    sorted_rules = manager._sort_concat_rules(
        {"patients.age", "patients.age_bucket", "patients.is_adult"}
    )

    assert sorted_rules == [rule_create_bucket, rule_use_bucket]


def test_sort_concat_rules_orders_by_target_dependency() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_delete_col = _DummyRule(
        table_target="visits",
        target_col="visit_end_date",
        interaction_type=InteractionType.CONCATENATED,
    )
    rule_use_col = _DummyRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_end_date",
        target_col="stay_class",
        interaction_type=InteractionType.CONCATENATED,
    )

    manager.rules = [rule_delete_col, rule_use_col]

    sorted_rules = manager._sort_concat_rules(
        {"visits.visit_end_date", "visits.stay_class"}
    )

    assert sorted_rules == [rule_use_col, rule_delete_col]

def test_sort_concat_rules_orders_by_target_dependency_no_swap() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_delete_col = _DummyRule(
        table_target="visits",
        target_col="visit_end_date",
        interaction_type=InteractionType.CONCATENATED,
    )
    rule_use_col = _DummyRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_end_date",
        target_col="stay_class",
        interaction_type=InteractionType.CONCATENATED,
    )

    manager.rules = [rule_use_col, rule_delete_col]

    sorted_rules = manager._sort_concat_rules(
        {"visits.visit_end_date", "visits.stay_class"}
    )

    assert sorted_rules == [rule_use_col, rule_delete_col]


def test_sort_concat_rules_handles_derived_rules() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_bucket = NumericBucketRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        aux_col="age_bucket",
        bins=[0, 18, 65],
        labels=["minor", "adult"],
    )
    rule_bucket.interaction_type = InteractionType.CONCATENATED
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
    rule_threshold.interaction_type = InteractionType.CONCATENATED

    manager.rules = [rule_threshold, rule_bucket]

    sorted_rules = manager._sort_concat_rules(
        {
            "patients.age",
        }
    )

    assert sorted_rules == [rule_bucket, rule_threshold]


def test_sort_concat_rules_orders_rejection_sampling_last() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_age_bucket = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        aux_col="age_bucket",
    )
    rule_age_bucket.interaction_type = InteractionType.CONCATENATED

    rule_is_adult_reject = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_bucket",
        aux_col="is_adult",
        rejection_sampling=True,
    )
    rule_is_adult_reject.interaction_type = InteractionType.CONCATENATED

    manager.rules = [rule_is_adult_reject, rule_age_bucket]

    sorted_rules = manager._sort_concat_rules(
        {
            "patients.age",
        }
    )

    assert sorted_rules == [rule_age_bucket, rule_is_adult_reject]


def test_sort_concat_rules_orders_derived_and_numeric_dependency() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_age = DateToAgeRule(
        table_target="patients",
        table_origin="patients",
        origin_col="birth_date",
        aux_col="age",
        reference_date="2020-01-01",
    )
    rule_age.interaction_type = InteractionType.CONCATENATED

    rule_is_adult = NumericThresholdRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_years",
        aux_col="is_adult",
        threshold=18,
        operator=">=",
        true_value=True,
        false_value=False,
    )
    rule_is_adult.interaction_type = InteractionType.CONCATENATED

    manager.rules = [rule_is_adult, rule_age]

    sorted_rules = manager._sort_concat_rules(
        {
            "patients.birth_date",
        }
    )

    assert sorted_rules == [rule_age, rule_is_adult]


def test_sort_concat_rules_orders_three_rule_chain_with_semantic_consistency() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_age = DateToAgeRule(
        table_target="patients",
        table_origin="patients",
        origin_col="birth_date",
        aux_col="age",
        reference_date="2020-01-01",
    )
    rule_age.interaction_type = InteractionType.CONCATENATED

    rule_is_senior = NumericThresholdRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_years",
        aux_col="is_senior",
        threshold=65,
        operator=">=",
        true_value=True,
        false_value=False,
    )
    rule_is_senior.interaction_type = InteractionType.CONCATENATED

    rule_diagnosis = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="is_senior",
        target_col="diagnosis",
    )
    rule_diagnosis.interaction_type = InteractionType.CONCATENATED

    manager.rules = [rule_diagnosis, rule_is_senior, rule_age]

    sorted_rules = manager._sort_concat_rules(
        {
            "patients.birth_date",
            "patients.diagnosis",
        }
    )

    assert sorted_rules == [rule_age, rule_is_senior, rule_diagnosis]


def test_sort_concat_rules_large_integration_all_rule_types() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_age = DateToAgeRule(
        table_target="patients",
        table_origin="patients",
        origin_col="birth_date",
        aux_col="age",
        reference_date="2020-01-01",
    )
    rule_age.interaction_type = InteractionType.CONCATENATED

    rule_is_senior = NumericThresholdRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_years",
        aux_col="is_senior",
        threshold=65,
        operator=">=",
        true_value=True,
        false_value=False,
    )
    rule_is_senior.interaction_type = InteractionType.CONCATENATED

    rule_bucket = NumericBucketRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_years",
        aux_col="age_bucket",
        bins=[0, 18, 65, 120],
        labels=["minor", "adult", "senior"],
    )
    rule_bucket.interaction_type = InteractionType.CONCATENATED

    rule_diagnosis = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="is_senior",
        target_col="diagnosis",
    )
    rule_diagnosis.interaction_type = InteractionType.CONCATENATED

    rule_risk_band = SemanticRankingConsistencyRule(
        table_target="patients",
        origin_col="age_bucket",
        target_col="risk_band",
    )
    rule_risk_band.interaction_type = InteractionType.CONCATENATED

    rule_visit_duration = DateInequalityRule(
        table_target="visits",
        origin_col="visit_start_date",
        target_col="visit_end_date",
        constraint_operator=">=",
    )
    rule_visit_duration.interaction_type = InteractionType.CONCATENATED

    rule_long_stay = NumericThresholdRule(
        table_target="visits",
        table_origin="visits",
        origin_col="duration_visit_end_date_days",
        aux_col="long_stay",
        threshold=10,
        operator=">=",
        true_value=True,
        false_value=False,
    )
    rule_long_stay.interaction_type = InteractionType.CONCATENATED

    rule_lab_value = NumericInequalityRule(
        table_target="labs",
        origin_col="lab_upper",
        target_col="lab_value",
        constraint_operator="<=",
    )
    rule_lab_value.interaction_type = InteractionType.CONCATENATED

    rule_lab_within_range = NumericThresholdRule(
        table_target="labs",
        table_origin="labs",
        origin_col="diff_lab_value",
        aux_col="lab_within_range",
        threshold=0,
        operator=">=",
        true_value=True,
        false_value=False,
    )
    rule_lab_within_range.interaction_type = InteractionType.CONCATENATED

    manager.rules = [
        rule_diagnosis,
        rule_is_senior,
        rule_bucket,
        rule_risk_band,
        rule_age,
        rule_long_stay,
        rule_visit_duration,
        rule_lab_value,
        rule_lab_within_range,
    ]

    sorted_rules = manager._sort_concat_rules(
        {
            "patients.birth_date",
            "patients.diagnosis",
            "patients.risk_band",
            "visits.visit_start_date",
            "visits.visit_end_date",
            "visits.person_id",
            "labs.lab_upper",
            "labs.lab_value",
            "conditions.person_id",
        }
    )

    positions = {id(rule): idx for idx, rule in enumerate(sorted_rules)}

    assert positions[id(rule_age)] < positions[id(rule_is_senior)]
    assert positions[id(rule_is_senior)] < positions[id(rule_diagnosis)]
    assert positions[id(rule_age)] < positions[id(rule_bucket)]
    assert positions[id(rule_bucket)] < positions[id(rule_risk_band)]
    assert positions[id(rule_visit_duration)] < positions[id(rule_long_stay)]
    assert positions[id(rule_lab_value)] < positions[id(rule_lab_within_range)]


def test_full_pipeline_with_add_rule_orders_and_transforms() -> None:
    data = {
        "patients": pd.DataFrame(
            {
                "person_id": [1, 2],
                "birth_date": ["1950-01-01", "1990-06-15"],
                "diagnosis": ["flu", "allergy"],
                "risk_band": ["low", "high"],
            }
        ),
        "visits": pd.DataFrame(
            {
                "visit_id": [10, 20],
                "person_id": [1, 2],
                "visit_start_date": ["2020-01-01", "2020-02-01"],
                "visit_end_date": ["2020-01-05", "2020-02-10"],
            }
        ),
        "conditions": pd.DataFrame(
            {
                "condition_id": [100, 200],
                "visit_id": [10, 20],
                "person_id": [1, 2],
            }
        ),
        "labs": pd.DataFrame(
            {
                "lab_id": [1, 2],
                "lab_upper": [10.0, 5.0],
                "lab_value": [7.0, 4.0],
            }
        ),
    }
    relationships_autodetect = {
        "fks": [
            {
                "child": "conditions",
                "parent": "visits",
                "fk_column": "visit_id",
                "pk_column": "visit_id",
            },
            {
                "child": "visits",
                "parent": "patients",
                "fk_column": "person_id",
                "pk_column": "person_id",
            },
            {
                "child": "conditions",
                "parent": "patients",
                "fk_column": "person_id",
                "pk_column": "person_id",
            },
        ]
    }
    # 3 foreign key consistency rules
    relationships_autodetect = assign_default_context_keys(relationships_autodetect)
    relationships = format_relationships(relationships_autodetect)

    manager = LogicalRuleManager()

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
        origin_col="age_years",
        aux_col="is_senior",
        threshold=65,
        operator=">=",
        true_value=True,
        false_value=False,
    )
    rule_bucket = NumericBucketRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_years",
        aux_col="age_bucket",
        bins=[0, 18, 65, 120],
        labels=["minor", "adult", "senior"],
    )
    rule_diagnosis = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="is_senior",
        target_col="diagnosis",
    )
    rule_risk_band = SemanticRankingConsistencyRule(
        table_target="patients",
        origin_col="age_bucket",
        target_col="risk_band",
    )
    rule_visit_duration = DateInequalityRule(
        table_target="visits",
        origin_col="visit_start_date",
        target_col="visit_end_date",
        constraint_operator=">=",
    )
    rule_long_stay = NumericThresholdRule(
        table_target="visits",
        table_origin="visits",
        origin_col="duration_visit_end_date_days",
        aux_col="long_stay",
        threshold=5,
        operator=">=",
        true_value=True,
        false_value=False,
    )
    rule_lab_value = NumericInequalityRule(
        table_target="labs",
        origin_col="lab_upper",
        target_col="lab_value",
        constraint_operator="<=",
    )
    rule_lab_within_range = NumericThresholdRule(
        table_target="labs",
        table_origin="labs",
        origin_col="diff_lab_value",
        aux_col="lab_within_range",
        threshold=0,
        operator=">=",
        true_value=True,
        false_value=False,
    )
    inferred_fk_rules = infer_foreign_keys_consistency_rules(relationships_autodetect)
    
    for rule in (
        rule_age,
        rule_is_senior,
        rule_bucket,
        rule_diagnosis,
        rule_risk_band,
        rule_visit_duration,
        rule_long_stay,
        rule_lab_value,
        rule_lab_within_range,
    ):
        manager.add_rule(rule)
    for rule in inferred_fk_rules:
        manager.add_rule(rule)

    # pass all of the table columns in data to sort concat rules
    original_columns = set()
    for df in data.values():
        original_columns.update(df.columns)
    prefixed_columns = {f"{table}.{col}" for table, df in data.items() for col in df.columns}

    sorted_rules = manager._sort_concat_rules(prefixed_columns)

    assert len(sorted_rules) == 9 # fk rules are not concat
    positions = {id(rule): idx for idx, rule in enumerate(sorted_rules)}
    assert positions[id(rule_age)] < positions[id(rule_is_senior)]
    assert positions[id(rule_is_senior)] < positions[id(rule_diagnosis)]
    assert positions[id(rule_age)] < positions[id(rule_bucket)]
    assert positions[id(rule_bucket)] < positions[id(rule_risk_band)]
    assert positions[id(rule_visit_duration)] < positions[id(rule_long_stay)]
    assert positions[id(rule_lab_value)] < positions[id(rule_lab_within_range)]

    preprocessed = manager.apply_all_pre(data, relationships)

    assert "age_years" in preprocessed["patients"].columns
    assert "is_senior" in preprocessed["patients"].columns
    assert "age_bucket" in preprocessed["patients"].columns
    assert "diagnosis" not in preprocessed["patients"].columns
    assert "risk_band" not in preprocessed["patients"].columns
    assert "diagnosis_score" in preprocessed["patients"].columns
    assert "risk_band_score" in preprocessed["patients"].columns
    assert "visit_end_date" not in preprocessed["visits"].columns
    assert "duration_visit_end_date_days" in preprocessed["visits"].columns
    assert "long_stay" in preprocessed["visits"].columns
    assert "lab_value" not in preprocessed["labs"].columns
    assert "diff_lab_value" in preprocessed["labs"].columns
    assert "lab_within_range" in preprocessed["labs"].columns
    assert "person_id" not in preprocessed["conditions"].columns

    reconstructed = manager.apply_all_post(preprocessed)

    assert "diagnosis" in reconstructed["patients"].columns
    assert "risk_band" in reconstructed["patients"].columns
    assert "visit_end_date" in reconstructed["visits"].columns
    assert "lab_value" in reconstructed["labs"].columns
    assert "person_id" in reconstructed["conditions"].columns


def test_full_pipeline_with_multiple_flipped_branches(monkeypatch) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    data = {
        "patients": pd.DataFrame(
            {
                "person_id": [1, 2],
                "birth_date": ["1950-01-01", "1990-06-15"],
                "diagnosis": ["flu", "allergy"],
                "risk_band": ["low", "high"],
            }
        ),
        "visits": pd.DataFrame(
            {
                "visit_id": [10, 20],
                "person_id": [1, 2],
                "visit_start_date": ["2020-01-03", "2020-02-05"],
                "admission_date": ["2020-01-02", "2020-02-03"],
                "arrival_date": ["2020-01-04", "2020-02-06"],
                "checkin_date": ["2020-01-01", "2020-02-02"],
                "visit_end_date": ["2020-01-01", "2020-02-01"],
            }
        ),
        "labs": pd.DataFrame(
            {
                "lab_id": [1, 2],
                "lab_value": [5.0, 6.0],
                "min_value": [6.0, 7.0],
                "max_value": [8.0, 9.0],
                "baseline_value": [7.0, 8.0],
                "limit_value": [10.0, 11.0],
            }
        ),
    }

    manager = LogicalRuleManager()

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
        origin_col="age_years",
        aux_col="is_senior",
        threshold=65,
        operator=">=",
        true_value=True,
        false_value=False,
    )
    rule_bucket = NumericBucketRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age_years",
        aux_col="age_bucket",
        bins=[0, 18, 65, 120],
        labels=["minor", "adult", "senior"],
    )
    rule_diagnosis = SemanticProportionalConsistencyRule(
        table_target="patients",
        origin_col="is_senior",
        target_col="diagnosis",
    )
    rule_risk_band = SemanticRankingConsistencyRule(
        table_target="patients",
        origin_col="age_bucket",
        target_col="risk_band",
    )

    # visits table: 4 rules with same target
    visit_rule_start = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_start_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    visit_rule_admission = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="admission_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    visit_rule_arrival = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="arrival_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    visit_rule_checkin = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="checkin_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )

    # labs also has 4 rules with same target
    lab_rule_min = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="min_value",
        target_col="lab_value",
        constraint_operator="<=",
    )
    lab_rule_max = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="max_value",
        target_col="lab_value",
        constraint_operator="<=",
    )
    lab_rule_baseline = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="baseline_value",
        target_col="lab_value",
        constraint_operator="<=",
    )
    lab_rule_limit = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="limit_value",
        target_col="lab_value",
        constraint_operator="<=",
    )

    for rule in (
        rule_age,
        rule_is_senior,
        rule_bucket,
        rule_diagnosis,
        rule_risk_band,
        visit_rule_start,
        visit_rule_admission,
        visit_rule_arrival,
        visit_rule_checkin,
        lab_rule_min,
        lab_rule_max,
        lab_rule_baseline,
        lab_rule_limit,
    ):
        assert manager.add_rule(rule) is True

    for rule in (
        visit_rule_start,
        visit_rule_admission,
        visit_rule_arrival,
        visit_rule_checkin,
    ):
        assert rule.interaction_type == InteractionType.SUPERIMPOSED
        assert rule.constraint_operator == ">="
        assert rule.origin_col == "visit_end_date"
        assert rule.target_col in {
            "visit_start_date",
            "admission_date",
            "arrival_date",
            "checkin_date",
        }

    for rule in (lab_rule_min, lab_rule_max, lab_rule_baseline, lab_rule_limit):
        assert rule.interaction_type == InteractionType.SUPERIMPOSED
        assert rule.constraint_operator == ">="
        assert rule.origin_col == "lab_value"
        assert rule.target_col in {"min_value", "max_value", "baseline_value", "limit_value"}

    visit_aux_names = {
        rule.aux_col
        for rule in (
            visit_rule_start,
            visit_rule_admission,
            visit_rule_arrival,
            visit_rule_checkin,
        )
    }
    lab_aux_names = {rule.aux_col for rule in (lab_rule_min, lab_rule_max, lab_rule_baseline, lab_rule_limit)}
    assert len(visit_aux_names) == 4
    assert len(lab_aux_names) == 4

    preprocessed = manager.apply_all_pre(data, relationships={})

    assert "age_years" in preprocessed["patients"].columns
    assert "is_senior" in preprocessed["patients"].columns
    assert "age_bucket" in preprocessed["patients"].columns
    assert "diagnosis" not in preprocessed["patients"].columns
    assert "risk_band" not in preprocessed["patients"].columns
    assert "diagnosis_score" in preprocessed["patients"].columns
    assert "risk_band_score" in preprocessed["patients"].columns

    for rule in (
        visit_rule_start,
        visit_rule_admission,
        visit_rule_arrival,
        visit_rule_checkin,
    ):
        assert rule.aux_col in preprocessed["visits"].columns
    assert "visit_start_date" not in preprocessed["visits"].columns
    assert "admission_date" not in preprocessed["visits"].columns
    assert "arrival_date" not in preprocessed["visits"].columns
    assert "checkin_date" not in preprocessed["visits"].columns
    assert "visit_end_date" in preprocessed["visits"].columns

    for rule in (lab_rule_min, lab_rule_max, lab_rule_baseline, lab_rule_limit):
        assert rule.aux_col in preprocessed["labs"].columns
    assert "min_value" not in preprocessed["labs"].columns
    assert "max_value" not in preprocessed["labs"].columns
    assert "baseline_value" not in preprocessed["labs"].columns
    assert "limit_value" not in preprocessed["labs"].columns
    assert "lab_value" in preprocessed["labs"].columns

    reconstructed = manager.apply_all_post(preprocessed)

    assert "diagnosis" in reconstructed["patients"].columns
    assert "risk_band" in reconstructed["patients"].columns
    assert "visit_start_date" in reconstructed["visits"].columns
    assert "admission_date" in reconstructed["visits"].columns
    assert "arrival_date" in reconstructed["visits"].columns
    assert "checkin_date" in reconstructed["visits"].columns
    assert "visit_end_date" in reconstructed["visits"].columns
    assert "min_value" in reconstructed["labs"].columns
    assert "max_value" in reconstructed["labs"].columns
    assert "baseline_value" in reconstructed["labs"].columns
    assert "limit_value" in reconstructed["labs"].columns
    assert "lab_value" in reconstructed["labs"].columns


def test_flipping_multiple_layers(monkeypatch) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    data = {
        "visits": pd.DataFrame(
            {
                "visit_id": [10, 20],
                "person_id": [1, 2],
                "visit_start_date": ["2020-01-03", "2020-02-05"],
                "admission_date": ["2020-01-02", "2020-02-03"],
                "arrival_date": ["2020-01-04", "2020-02-06"],
                "checkin_date": ["2020-01-01", "2020-02-02"],
                "visit_end_date": ["2020-01-01", "2020-02-01"],
                "test_date1": ["2002-01-02", "2002-02-02"],
                "test_date2": ["2001-01-01", "2001-02-01"],
                "test_date3": ["2000-01-01", "2000-02-01"],
                "test_date4": ["1999-01-01", "1999-02-01"],
            }
        ),
    }

    manager = LogicalRuleManager()

    # visits table: 4 rules with same target
    visit_rule_start = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_start_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    visit_rule_admission = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="admission_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    visit_rule_arrival = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="arrival_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    visit_rule_checkin = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="checkin_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    
    # now lets build a second set of 4 that have the original 4 origins as targets
    visit_rule_test1 = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="test_date1",
        target_col="visit_start_date",
        constraint_operator="<=",
    )
    visit_rule_test2 = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="test_date2",
        target_col="admission_date",
        constraint_operator="<=",
    )
    visit_rule_test3 = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="test_date3",
        target_col="arrival_date",
        constraint_operator="<=",
    )
    visit_rule_test4 = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="test_date4",
        target_col="checkin_date",
        constraint_operator="<=",
    )

    for rule in (
        visit_rule_start,
        visit_rule_admission,
        visit_rule_arrival,
        visit_rule_checkin,
        visit_rule_test1,
        visit_rule_test2,
        visit_rule_test3,
        visit_rule_test4,
    ):
        assert manager.add_rule(rule) is True

    for rule in (
        visit_rule_start,
        visit_rule_admission,
        visit_rule_arrival,
        visit_rule_checkin,
    ):
        assert rule.interaction_type == InteractionType.SUPERIMPOSED
        assert rule.constraint_operator == ">="
        assert rule.origin_col == "visit_end_date"
        assert rule.target_col in {
            "visit_start_date",
            "admission_date",
            "arrival_date",
            "checkin_date",
        }

    for rule in (
        visit_rule_test1,
        visit_rule_test2,
        visit_rule_test3,
        visit_rule_test4,
    ):
        assert rule.interaction_type == InteractionType.SUPERIMPOSED
        assert rule.constraint_operator == ">="
        assert rule.origin_col in {
            "visit_start_date",
            "admission_date",
            "arrival_date",
            "checkin_date",
        }
        assert rule.target_col in {
            "test_date1",
            "test_date2",
            "test_date3",
            "test_date4",
        }
        
    preprocessed = manager.apply_all_pre(data, relationships={})

    for rule in (
        visit_rule_start,
        visit_rule_admission,
        visit_rule_arrival,
        visit_rule_checkin,
    ):
        assert rule.aux_col in preprocessed["visits"].columns
    assert "visit_start_date" not in preprocessed["visits"].columns
    assert "admission_date" not in preprocessed["visits"].columns
    assert "arrival_date" not in preprocessed["visits"].columns
    assert "checkin_date" not in preprocessed["visits"].columns
    assert "visit_end_date" in preprocessed["visits"].columns


    reconstructed = manager.apply_all_post(preprocessed)

    assert "visit_start_date" in reconstructed["visits"].columns
    assert "admission_date" in reconstructed["visits"].columns
    assert "arrival_date" in reconstructed["visits"].columns
    assert "checkin_date" in reconstructed["visits"].columns
    assert "visit_end_date" in reconstructed["visits"].columns


def test_flipping_multiple_layers_opposite_signs(monkeypatch) -> None:
    monkeypatch.setattr(np.random, "uniform", _midpoint_uniform_series)
    data = {
        "visits": pd.DataFrame(
            {
                "visit_id": [10, 20],
                "person_id": [1, 2],
                "visit_start_date": ["2020-01-03", "2020-02-05"],
                "admission_date": ["2020-01-02", "2020-02-03"],
                "arrival_date": ["2020-01-04", "2020-02-06"],
                "checkin_date": ["2020-01-01", "2020-02-02"],
                "visit_end_date": ["2020-01-01", "2020-02-01"],
                "test_date1": ["2002-01-02", "2002-02-02"],
                "test_date2": ["2001-01-01", "2001-02-01"],
                "test_date3": ["2000-01-01", "2000-02-01"],
                "test_date4": ["1999-01-01", "1999-02-01"],
            }
        ),
    }

    manager = LogicalRuleManager()

    visit_rule_start = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_start_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    visit_rule_admission = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="admission_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    visit_rule_arrival = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="arrival_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    visit_rule_checkin = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="checkin_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )

    visit_rule_test1 = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="test_date1",
        target_col="visit_start_date",
        constraint_operator=">=",
    )
    visit_rule_test2 = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="test_date2",
        target_col="admission_date",
        constraint_operator=">=",
    )
    visit_rule_test3 = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="test_date3",
        target_col="arrival_date",
        constraint_operator=">=",
    )
    visit_rule_test4 = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="test_date4",
        target_col="checkin_date",
        constraint_operator=">=",
    )

    for rule in (
        visit_rule_start,
        visit_rule_admission,
        visit_rule_arrival,
        visit_rule_checkin,
        visit_rule_test1,
        visit_rule_test2,
        visit_rule_test3,
        visit_rule_test4,
    ):
        assert manager.add_rule(rule) is True

    for rule in (
        visit_rule_start,
        visit_rule_admission,
        visit_rule_arrival,
        visit_rule_checkin,
    ):
        assert rule.interaction_type == InteractionType.SUPERIMPOSED
        assert rule.constraint_operator == ">="
        assert rule.origin_col == "visit_end_date"
        assert rule.target_col in {
            "visit_start_date",
            "admission_date",
            "arrival_date",
            "checkin_date",
        }

    for rule in (
        visit_rule_test1,
        visit_rule_test2,
        visit_rule_test3,
        visit_rule_test4,
    ):
        assert rule.interaction_type == InteractionType.SUPERIMPOSED
        assert rule.constraint_operator == "<="
        assert rule.origin_col in {
            "visit_start_date",
            "admission_date",
            "arrival_date",
            "checkin_date",
        }
        assert rule.target_col in {
            "test_date1",
            "test_date2",
            "test_date3",
            "test_date4",
        }

    preprocessed = manager.apply_all_pre(data, relationships={})

    for rule in (
        visit_rule_start,
        visit_rule_admission,
        visit_rule_arrival,
        visit_rule_checkin,
    ):
        assert rule.aux_col in preprocessed["visits"].columns
    assert "visit_start_date" not in preprocessed["visits"].columns
    assert "admission_date" not in preprocessed["visits"].columns
    assert "arrival_date" not in preprocessed["visits"].columns
    assert "checkin_date" not in preprocessed["visits"].columns
    assert "test_date1" not in preprocessed["visits"].columns
    assert "test_date2" not in preprocessed["visits"].columns
    assert "test_date3" not in preprocessed["visits"].columns
    assert "test_date4" not in preprocessed["visits"].columns
    assert "visit_end_date" in preprocessed["visits"].columns

    reconstructed = manager.apply_all_post(preprocessed)

    assert "visit_start_date" in reconstructed["visits"].columns
    assert "admission_date" in reconstructed["visits"].columns
    assert "arrival_date" in reconstructed["visits"].columns
    assert "checkin_date" in reconstructed["visits"].columns
    assert "visit_end_date" in reconstructed["visits"].columns
    assert "test_date1" in reconstructed["visits"].columns
    assert "test_date2" in reconstructed["visits"].columns
    assert "test_date3" in reconstructed["visits"].columns
    assert "test_date4" in reconstructed["visits"].columns



def test_full_pipeline_with_add_rule_valid_and_invalid_flips() -> None:
    manager = LogicalRuleManager()

    existing_date_rule = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_start_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )
    new_date_rule = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="admission_date",
        target_col="visit_end_date",
        constraint_operator="<=",
    )

    assert manager.add_rule(existing_date_rule) is True
    assert manager.add_rule(new_date_rule) is True

    assert existing_date_rule.interaction_type == InteractionType.SUPERIMPOSED
    assert new_date_rule.interaction_type == InteractionType.SUPERIMPOSED
    assert new_date_rule.constraint_operator == ">="
    assert new_date_rule.origin_col == "visit_end_date"
    assert new_date_rule.target_col == "admission_date"
    assert existing_date_rule.constraint_operator == ">="
    assert existing_date_rule.origin_col == "visit_end_date"
    assert existing_date_rule.target_col == "visit_start_date"

    existing_numeric_rule = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="min_value",
        target_col="lab_value",
        constraint_operator="<=",
    )
    new_numeric_rule = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="max_value",
        target_col="lab_value",
        constraint_operator="<=",
    )

    assert manager.add_rule(existing_numeric_rule) is True
    assert manager.add_rule(new_numeric_rule) is True

    assert existing_numeric_rule.interaction_type == InteractionType.SUPERIMPOSED
    assert new_numeric_rule.interaction_type == InteractionType.SUPERIMPOSED
    assert new_numeric_rule.constraint_operator == ">="
    assert new_numeric_rule.origin_col == "lab_value"
    assert new_numeric_rule.target_col == "max_value"
    assert new_numeric_rule.aux_col.startswith("max_value_flipped_")
    assert existing_numeric_rule.constraint_operator == ">="
    assert existing_numeric_rule.origin_col == "lab_value"
    assert existing_numeric_rule.target_col == "min_value"

    valid_concat_ineq_date = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_end_date",
        target_col="discharge_date",
        constraint_operator="<=",
    )
    assert manager.add_rule(valid_concat_ineq_date) is True
    assert valid_concat_ineq_date.interaction_type == InteractionType.ISOLATED
    assert valid_concat_ineq_date.origin_col == "visit_end_date"
    assert valid_concat_ineq_date.target_col == "discharge_date"

    invalid_date = DateInequalityRule(
        table_target="visits",
        table_origin="visits",
        origin_col="admission_date",
        target_col="discharge_date",
        constraint_operator="<=",
    )

    assert manager.add_rule(invalid_date) is False
    assert invalid_date not in manager.rules

    existing_invalid_numeric = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="min_value",
        target_col="range_value",
        constraint_operator="<=",
    )
    existing_invalid_numeric.interaction_type = InteractionType.CONCATENATED
    manager.rules.append(existing_invalid_numeric)

    invalid_numeric = NumericInequalityRule(
        table_target="labs",
        table_origin="labs",
        origin_col="max_value",
        target_col="range_value",
        constraint_operator="<=",
    )

    assert manager.add_rule(invalid_numeric) is False
    assert invalid_numeric not in manager.rules


def test_sort_concat_rules_skips_when_origin_column_missing() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_missing_origin = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="missing_col",
        target_col="derived",
    )

    manager.rules = [rule_missing_origin]

    sorted_rules = manager._sort_concat_rules({"patients.age"})

    assert sorted_rules == []

def test_sort_concat_rules_detects_cycles() -> None:
    manager = LogicalRuleManager(rules=[])

    rule_a = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="b",
        target_col="a",
    )
    rule_a.interaction_type = InteractionType.CONCATENATED

    rule_b = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="a",
        target_col="b",
    )
    rule_b.interaction_type = InteractionType.CONCATENATED

    manager.rules = [rule_a, rule_b]

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
    rule_a.interaction_type = InteractionType.CONCATENATED

    rule_b = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="c",
        aux_col="b",
    )
    rule_b.interaction_type = InteractionType.CONCATENATED

    rule_c = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        aux_col="c",
    )
    rule_c.interaction_type = InteractionType.CONCATENATED

    manager.rules = [rule_b, rule_c, rule_a]

    sorted_rules = manager._sort_concat_rules({"patients.age", "patients.a"})

    assert sorted_rules == [rule_c, rule_b, rule_a]


def test_sort_concat_rules_with_two_independent_chains() -> None:
    manager = LogicalRuleManager()

    rule_a = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="b",
        target_col="a",
    )
    rule_a.interaction_type = InteractionType.CONCATENATED

    rule_b = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="c",
        aux_col="b",
    )
    rule_b.interaction_type = InteractionType.CONCATENATED

    rule_c = _DummyRule(
        table_target="patients",
        table_origin="patients",
        origin_col="age",
        aux_col="c",
    )
    rule_c.interaction_type = InteractionType.CONCATENATED

    rule_x = _DummyRule(
        table_target="visits",
        table_origin="visits",
        origin_col="y",
        aux_col="x",
    )
    rule_x.interaction_type = InteractionType.CONCATENATED

    rule_y = _DummyRule(
        table_target="visits",
        table_origin="visits",
        origin_col="z",
        aux_col="y",
    )
    rule_y.interaction_type = InteractionType.CONCATENATED

    rule_z = _DummyRule(
        table_target="visits",
        table_origin="visits",
        origin_col="visit_date",
        aux_col="z",
    )
    rule_z.interaction_type = InteractionType.CONCATENATED

    manager.rules = [rule_b, rule_x, rule_z, rule_c, rule_y, rule_a]

    sorted_rules = manager._sort_concat_rules(
        {
            "patients.age",
            "patients.a",
            "visits.visit_date",
        }
    )

    assert len(sorted_rules) == 6
    positions = {id(rule): idx for idx, rule in enumerate(sorted_rules)}

    assert positions[id(rule_c)] < positions[id(rule_b)] < positions[id(rule_a)]
    assert positions[id(rule_z)] < positions[id(rule_y)] < positions[id(rule_x)]