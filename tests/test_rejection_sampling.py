import pandas as pd

from backend.src.domain.preprocessing.logical_rules import (
    LogicalRuleManager,
    NumericThresholdRule,
)
from backend.src.domain.rules_config import extract_rules_and_rejection_config
from backend.src.sessions.simulation import _cascade_delete_tables


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
    aux_col: "is_adult"
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


def test_extract_rules_collects_warnings_for_skipped_rules(tmp_path) -> None:
    config_path = tmp_path / "rules.yaml"
    config_path.write_text(
        """
rules:
  - type: "date_inequality"
    table_target: "patients"
    target_col: "discharge_date"
    # invalid: neither origin_col nor constraint
  - type: "no_such_rule"
    table_target: "patients"
""".lstrip()
    )
    warnings: list[dict] = []

    rules, _ = extract_rules_and_rejection_config(str(config_path), warnings_sink=warnings)

    assert rules == []
    assert len(warnings) == 2
    assert "invalid configuration" in warnings[0]["message"]
    assert warnings[0]["table"] == "patients"
    assert "unrecognized type" in warnings[1]["message"]


def test_collect_rejection_failures() -> None:
    df = pd.DataFrame({"age": [10, 20], "is_adult": [True, False]})
    rule = NumericThresholdRule(
        table_origin="patients",
        origin_col="age",
        table_target="patients",
        aux_col="is_adult",
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
        aux_col="age",
        threshold=18,
        operator=">=",
        rejection_sampling=True,
    )

    manager = LogicalRuleManager()
    manager.add_rule(rule)

    rejected = manager.collect_rejection_failures({"patients": df}, [rule])

    assert rejected["patients"] == {0}


def test_rejection_sampling_age() -> None:
    df = pd.DataFrame(
        {
            "age": [20, 1],
        }
    )


    rejection_rule = NumericThresholdRule(
        table_origin="patients",
        table_target="patients",
        origin_col="age",
        aux_col="age",
        threshold=18,
        operator=">=",
        rejection_sampling=True,
    )

    manager = LogicalRuleManager()
    manager.add_rule(rejection_rule)

    rejected = manager.collect_rejection_failures({"patients": df}, [rejection_rule])
    print(rejected)
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


def test_generate_with_rejection_sampling_saves_attempt_history() -> None:
    from unittest.mock import MagicMock
    from backend.src.sessions.simulation import _generate_with_rejection_sampling

    # Mock engine
    mock_engine = MagicMock()
    mock_engine.simulate.return_value = (
        {"patients": pd.DataFrame({"age": [20, 15]})},
        "sd_test_rejection",
    )

    # Mock rule manager
    mock_rule = MagicMock()
    mock_rule.table_target = "patients"
    type(mock_rule).__name__ = "NumericThresholdRule"

    mock_rule_manager = MagicMock()
    mock_rule_manager.get_rejection_rules.return_value = [mock_rule]
    mock_rule_manager.collect_rejection_failures.return_value = {"patients": {1}}
    mock_rule_manager.apply_all_post = lambda x: x

    # Config mocks
    metadata = {
        "tables": [
            {
                "name": "patients",
                "primary_key": "id",
                "foreign_keys": [],
            }
        ]
    }

    # Mock _resolve_rejection_sampling_config
    import backend.src.sessions.simulation as sim_mod
    original_resolve = sim_mod._resolve_rejection_sampling_config
    sim_mod._resolve_rejection_sampling_config = lambda mgr, overrides=None: {
        "max_attempts": 2,
        "overgenerate_factor": 2.0,
    }

    try:
        results, stats, last_sd, _ = _generate_with_rejection_sampling(
            engine=mock_engine,
            generator=object(),
            metadata=metadata,
            rule_manager=mock_rule_manager,
            subject_targets={"patients": 1},
            training_table_sizes={"patients": 1},
        )

        assert stats["enabled"] is True
        assert stats["max_attempts"] == 2
        assert stats["overgenerate_factor"] == 2.0
        assert stats["attempts"] == 1
        assert "attempt_history" in stats
        assert len(stats["attempt_history"]) == 1
        
        first_attempt = stats["attempt_history"][0]
        assert first_attempt["attempt"] == 1
        assert first_attempt["multiplier"] == 2.0
        assert "patients" in first_attempt["tables"]
        assert first_attempt["tables"]["patients"]["generated"] == 2
        assert first_attempt["tables"]["patients"]["accepted"] == 1
        assert first_attempt["tables"]["patients"]["rejected"] == 1
        
        # Verify best attempt tracking
        assert stats["attempt_history"][0]["is_best"] is True

        # Degraded-reconstruction warnings ride along even when empty so the
        # report shape is stable.
        assert stats["post_reconstruction_warnings"] == []
        assert first_attempt["post_reconstruction_warnings"] == []

    finally:
        sim_mod._resolve_rejection_sampling_config = original_resolve


def test_generate_with_rejection_sampling_uses_constant_multiplier_on_retry() -> None:
    from unittest.mock import MagicMock
    from backend.src.sessions.simulation import _generate_with_rejection_sampling

    # Mock engine - returns 2 rows
    mock_engine = MagicMock()
    mock_engine.simulate.return_value = (
        {"patients": pd.DataFrame({"age": [20, 15]})},
        "sd_test_rejection",
    )

    # Mock rule manager - rejects everything to force all retries
    mock_rule = MagicMock()
    mock_rule.table_target = "patients"
    type(mock_rule).__name__ = "NumericThresholdRule"

    mock_rule_manager = MagicMock()
    mock_rule_manager.get_rejection_rules.return_value = [mock_rule]
    mock_rule_manager.collect_rejection_failures.return_value = {"patients": {0, 1}}
    mock_rule_manager.apply_all_post = lambda x: x

    metadata = {
        "tables": [
            {
                "name": "patients",
                "primary_key": "id",
                "foreign_keys": [],
            }
        ]
    }

    import backend.src.sessions.simulation as sim_mod
    original_resolve = sim_mod._resolve_rejection_sampling_config
    sim_mod._resolve_rejection_sampling_config = lambda mgr, overrides=None: {
        "max_attempts": 3,
        "overgenerate_factor": 2.5,
    }

    try:
        results, stats, last_sd, _ = _generate_with_rejection_sampling(
            engine=mock_engine,
            generator=object(),
            metadata=metadata,
            rule_manager=mock_rule_manager,
            subject_targets={"patients": 1},
            training_table_sizes={"patients": 1},
        )

        assert stats["max_attempts"] == 3
        assert stats["overgenerate_factor"] == 2.5
        assert stats["attempts"] == 3
        assert len(stats["attempt_history"]) == 3
        
        # Verify constant multiplier in all history entries
        for entry in stats["attempt_history"]:
            assert entry["multiplier"] == 2.5

    finally:
        sim_mod._resolve_rejection_sampling_config = original_resolve


def _parent_child_metadata() -> dict:
    return {
        "tables": [
            {"name": "patients", "primary_key": "patient_id", "foreign_keys": []},
            {
                "name": "visits",
                "primary_key": "visit_id",
                "foreign_keys": [
                    {
                        "column": "patient_id",
                        "referenced_table": "patients",
                        "is_context": True,
                    }
                ],
            },
        ]
    }


def test_resolve_fixed_target_mother_walks_context_chain() -> None:
    from backend.src.sessions.simulation import _resolve_fixed_target_mother

    assert _resolve_fixed_target_mother(_parent_child_metadata(), "visits") == "patients"
    assert _resolve_fixed_target_mother(_parent_child_metadata(), "patients") == "patients"


def test_generate_with_fixed_target_sampling_trims_to_exact_target(monkeypatch) -> None:
    from unittest.mock import MagicMock
    import backend.src.sessions.simulation as sim_mod
    from backend.src.sessions.simulation import _generate_with_fixed_target_sampling

    # Each draw of N patients yields 2 visits per patient.
    def fake_simulate(generator, runtime_config, cancel_event=None, progress_copy_dest=None):
        draw = next(
            t["configuration"]["sample_size"]
            for t in runtime_config["tables"]
            if t["name"] == "patients"
        )
        patients = pd.DataFrame({"patient_id": range(draw)})
        visits = pd.DataFrame(
            {
                "visit_id": range(draw * 2),
                "patient_id": [p for p in range(draw) for _ in range(2)],
            }
        )
        return {"patients": patients, "visits": visits}, "sd_fixed"

    mock_engine = MagicMock()
    mock_engine.simulate.side_effect = fake_simulate

    mock_rule_manager = MagicMock()
    mock_rule_manager.get_rejection_rules.return_value = []
    mock_rule_manager.apply_all_post = lambda x: x
    mock_rule_manager.date_formats = {}
    mock_rule_manager.post_warnings = []

    monkeypatch.setattr(
        sim_mod,
        "_resolve_rejection_sampling_config",
        lambda mgr, overrides=None: {"max_attempts": 3, "overgenerate_factor": 2.0},
    )

    results, stats, _, _ = _generate_with_fixed_target_sampling(
        engine=mock_engine,
        generator=object(),
        metadata=_parent_child_metadata(),
        rule_manager=mock_rule_manager,
        target_table="visits",
        target_rows=10,
        mother_table="patients",
        training_table_sizes={"patients": 100, "visits": 200},
    )

    assert stats["selection"] == "fixed_target"
    assert stats["target_table"] == "visits"
    assert stats["target_rows"] == 10
    # ratio 2:1 needs 5 patients; the first draw is always pre-inflated by the
    # overgeneration factor (×2 → 10 patients) and the 20 visits produced are
    # trimmed down to the exact target.
    assert stats["attempts"] == 1
    assert stats["partial_results"] is False
    assert len(results["visits"]) == 10
    assert stats["attempt_history"][0]["subject_draw"] == {"patients": 10}


def test_generate_with_fixed_target_sampling_regrows_draw_with_rules(monkeypatch) -> None:
    from unittest.mock import MagicMock
    import backend.src.sessions.simulation as sim_mod
    from backend.src.sessions.simulation import _generate_with_fixed_target_sampling

    draws: list[int] = []

    def fake_simulate(generator, runtime_config, cancel_event=None, progress_copy_dest=None):
        draw = next(
            t["configuration"]["sample_size"]
            for t in runtime_config["tables"]
            if t["name"] == "patients"
        )
        draws.append(draw)
        patients = pd.DataFrame({"patient_id": range(draw)})
        visits = pd.DataFrame(
            {"visit_id": range(draw), "patient_id": list(range(draw))}
        )
        return {"patients": patients, "visits": visits}, "sd_fixed"

    mock_engine = MagicMock()
    mock_engine.simulate.side_effect = fake_simulate

    mock_rule = MagicMock()
    mock_rule.table_target = "visits"
    type(mock_rule).__name__ = "NumericThresholdRule"

    mock_rule_manager = MagicMock()
    mock_rule_manager.get_rejection_rules.return_value = [mock_rule]
    # Half the visits fail the rule on every attempt.
    mock_rule_manager.collect_rejection_failures.side_effect = lambda results, rules: {
        "visits": set(results["visits"].index[: len(results["visits"]) // 2])
    }
    mock_rule_manager.apply_all_post = lambda x: x
    mock_rule_manager.date_formats = {}
    mock_rule_manager.post_warnings = []

    monkeypatch.setattr(
        sim_mod,
        "_resolve_rejection_sampling_config",
        lambda mgr, overrides=None: {"max_attempts": 4, "overgenerate_factor": 1.0},
    )

    results, stats, _, _ = _generate_with_fixed_target_sampling(
        engine=mock_engine,
        generator=object(),
        metadata=_parent_child_metadata(),
        rule_manager=mock_rule_manager,
        target_table="visits",
        target_rows=10,
        mother_table="patients",
        training_table_sizes={"patients": 100, "visits": 100},
    )

    # First draw (ratio 1:1, factor 1.0) is 10, yielding only 5 compliant
    # visits; the measured-yield re-estimate must grow the next draw.
    assert draws[0] == 10
    assert len(draws) >= 2 and draws[1] > draws[0]
    assert stats["partial_results"] is False
    assert len(results["visits"]) == 10

def test_resolve_rejection_sampling_config_request_overrides_win() -> None:
    from unittest.mock import MagicMock

    from backend.src.sessions.simulation import _resolve_rejection_sampling_config

    manager = MagicMock()
    manager.rejection_sampling_config = {"max_attempts": 5, "overgenerate_factor": 2.0}

    config = _resolve_rejection_sampling_config(
        manager, {"max_attempts": 1, "overgenerate_factor": 4.0}
    )

    assert config["max_attempts"] == 1
    assert config["overgenerate_factor"] == 4.0
