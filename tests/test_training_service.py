from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from backend.src.domain.preprocessing.logical_rules_serialization import (
    reconstruct_logical_rule_manager_from_dict,
    serialize_logical_rule_manager_to_dict,
)
from backend.src.sessions import training as training_module


def test_run_training_flow_from_inspection_persists_relationships_without_rules(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    relationships = {
        "pks": {"visits": "visit_id", "conditions": "condition_id"},
        "fks": [
            {
                "child": "conditions",
                "parent": "visits",
                "fk_column": "visit_id",
                "pk_column": "visit_id",
            }
        ],
    }
    inspection_metadata = {"relationships": relationships, "encoding_types": {}}
    processed_data = {
        "visits": pd.DataFrame({"visit_id": [10]}),
        "conditions": pd.DataFrame({"condition_id": [1], "visit_id": [10]}),
    }
    card = {
        "mostly_config_path": "/cfg/mostly.yaml",
        "rules_config_path": "/cfg/rules.yaml",
        "mostly_ai_overrides": None,
        "file_paths": [],
    }
    captured: dict[str, object] = {}

    class FakeRejectionConfig:
        def as_dict(self) -> dict:
            return {}

    class FakeFormatter:
        def __init__(self, engine_name: str) -> None:
            assert engine_name == "mostly"

        def format(
            self, data_dfs: dict, relationships_data: dict, types_data: dict
        ) -> dict:
            captured["formatted_relationships"] = relationships_data
            return {
                "tables": [
                    {
                        "name": name,
                        "primary_key": relationships["pks"].get(name),
                        "foreign_keys": [],
                    }
                    for name in data_dfs
                ]
            }

    class FakeTracker:
        def __init__(self, **_kwargs) -> None:
            self.model_id = "model_test_1"
            self.output_directory = str(tmp_path / "model_test_1")
            Path(self.output_directory).mkdir(parents=True, exist_ok=True)

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def save_training_table_sizes(self, _processed_data) -> None:
            return None

        def save_rule_manager(self, rule_manager) -> None:
            captured["serialized_rule_manager"] = (
                serialize_logical_rule_manager_to_dict(rule_manager)
            )

        def save_metadata(self, _metadata) -> None:
            return None

        def save_generator(self, _generator) -> None:
            return None

        def save_qa_reports(self, _generator_id) -> None:
            return None

        def save_mostly_statistics(self, _generator_id) -> None:
            return None

    class FakeEngine:
        def __init__(self, **_kwargs) -> None:
            return None

        def train(self, _processed_data, _metadata, cancel_event=None):
            assert cancel_event is None
            return SimpleNamespace(id="generator_test_1")

    monkeypatch.setattr(
        training_module,
        "load_inspection_artifacts",
        lambda _inspection_id: (card, processed_data, inspection_metadata),
    )
    monkeypatch.setattr(
        training_module,
        "resolve_inspection_rules_config_path",
        lambda _inspection_id, _card=None: "/cfg/rules.yaml",
    )
    monkeypatch.setattr(
        training_module,
        "extract_rules_and_rejection_config",
        lambda _path: ([], FakeRejectionConfig()),
    )
    monkeypatch.setattr(training_module, "MetadataFormatter", FakeFormatter)
    monkeypatch.setattr(training_module, "ModelTracker", FakeTracker)
    monkeypatch.setattr(training_module, "create_engine", FakeEngine)

    model_id, _generator, _metadata, rule_manager = (
        training_module.run_training_flow_from_inspection(inspection_id="inspection_1")
    )

    assert model_id == "model_test_1"
    assert rule_manager is not None
    assert rule_manager.rules == []
    assert rule_manager.relationships == {
        ("conditions", "visits"): [("visit_id", "visit_id")]
    }
    assert captured["formatted_relationships"] == relationships

    persisted = reconstruct_logical_rule_manager_from_dict(
        captured["serialized_rule_manager"]
    )
    assert persisted.rules == []
    assert persisted.relationships == {
        ("conditions", "visits"): [("visit_id", "visit_id")]
    }
