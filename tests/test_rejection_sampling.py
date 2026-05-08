import pandas as pd

from backend.src.core.preprocessing.logical_rules import (
    DateToAgeRule,
    LogicalRuleManager,
    NumericThresholdRule,
)
from backend.src.core.rules_config import extract_rules_and_rejection_config
from backend.src.services.simulation import _cascade_delete_tables


def test_extract_rules_and_rejection_config(tmp_path) -> None:
    config_path = tmp_path / "rules.yaml"
    config_path.write_text(
        """
rejection_sampling:
  max_attempts: 3
  overgenerate_factor: 1.5

rules:
  - type: "numeric_threshold"
    table_origin: "patients"
    origin_col: "age"
    table_target: "patients"
    target_col: "is_adult"
    threshold: 18
    operator: ">="
    rejection_sampling: true
""".lstrip()
    )

    rules, rejection_config = extract_rules_and_rejection_config(str(config_path))

    assert rejection_config.max_attempts == 3
    assert rejection_config.overgenerate_factor == 1.5
    assert len(rules) == 1
    assert rules[0].rejection_sampling is True


def test_collect_rejection_failures() -> None:
    df = pd.DataFrame({"age": [10, 20], "is_adult": [True, False]})
    rule = NumericThresholdRule(
        table_origin="patients",
        origin_col="age",
        table_target="patients",
        target_col="is_adult",
        threshold=18,
        operator=">=",
        rejection_sampling=True,
    )

    manager = LogicalRuleManager()
    manager.add_rule(rule)

    rejected = manager.collect_rejection_failures({"patients": df}, [rule])

    assert rejected["patients"] == {0, 1}


def test_collect_rejection_failures_numeric_constraint() -> None:
    df = pd.DataFrame({"age": [10, 20, 18]})
    rule = NumericThresholdRule(
        table_origin="patients",
        origin_col="age",
        table_target="patients",
        target_col="age",
        threshold=18,
        operator=">=",
        rejection_sampling=True,
    )

    manager = LogicalRuleManager()
    manager.add_rule(rule)

    rejected = manager.collect_rejection_failures({"patients": df}, [rule])

    assert rejected["patients"] == {0}


def test_rejection_sampling_uses_derived_age() -> None:
    df = pd.DataFrame(
        {
            "dob": ["2000-01-01", "2010-01-01"],
            "admittime": ["2020-01-01", "2020-01-01"],
            "age": [10, 30],
            "is_adult": [True, True],
        }
    )

    age_rule = DateToAgeRule(
        table_origin="patients",
        origin_col="dob",
        table_target="patients",
        target_col="age",
        reference_date_col="admittime",
    )
    rejection_rule = NumericThresholdRule(
        table_origin="patients",
        origin_col="age",
        table_target="patients",
        target_col="is_adult",
        threshold=18,
        operator=">=",
        rejection_sampling=True,
    )

    manager = LogicalRuleManager()
    manager.add_rule(age_rule)
    manager.add_rule(rejection_rule)

    rejected = manager.collect_rejection_failures({"patients": df}, [rejection_rule])

    assert rejected.get("patients", set()) == {1}


def test_cascade_delete_tables_removes_children() -> None:
    metadata = {
        "tables": [
            {
                "name": "parents",
                "primary_key": "parent_id",
                "foreign_keys": [],
            },
            {
                "name": "children",
                "primary_key": "child_id",
                "foreign_keys": [
                    {"column": "parent_id", "referenced_table": "parents"}
                ],
            },
        ]
    }

    parents = pd.DataFrame(
        {
            "parent_id": [1, 2, 3],
            "value": ["a", "b", "c"],
        }
    )
    children = pd.DataFrame(
        {
            "child_id": [10, 11, 12, 13],
            "parent_id": [1, 1, 2, 3],
            "value": ["x", "y", "z", "w"],
        }
    )

    rejected_indices = {"parents": {1}}

    filtered, _ = _cascade_delete_tables(
        {"parents": parents, "children": children},
        metadata,
        rejected_indices,
    )

    assert filtered["parents"]["parent_id"].tolist() == [1, 3]
    assert filtered["children"]["parent_id"].tolist() == [1, 1, 3]
