import json

import pytest

import backend.src.sessions.training as training


def _write_inspection(tmp_path, inspection_id, tables, fks, model_settings):
    folder = tmp_path / inspection_id
    folder.mkdir()
    config_path = folder / "mostly_ai.yaml"
    config_path.write_text(json.dumps({"model_settings": model_settings}))  # JSON is valid YAML
    (folder / "inspection_card.json").write_text(
        json.dumps({"tables": tables, "mostly_config_path": str(config_path)})
    )
    (folder / "inspection_metadata.json").write_text(
        json.dumps({"relationships": {"pks": {}, "fks": fks}})
    )


THREE_LEVEL_FKS = [
    {"parent": "persons", "child": "visits", "fk_column": "person_id", "is_context": True},
    {"parent": "visits", "child": "drugs", "fk_column": "visit_id", "is_context": True},
]
TABLES = {"persons": 100, "visits": 300, "drugs": 600}
DP = {"delta": 1e-5, "noise_multiplier": 1.5, "max_grad_norm": 1.0}


@pytest.fixture
def inspections_root(tmp_path, monkeypatch):
    monkeypatch.setattr(training, "INSPECTIONS_DIR", str(tmp_path))
    return tmp_path


def test_preflight_reports_dp_context_chain(inspections_root):
    _write_inspection(
        inspections_root,
        "insp_dp",
        TABLES,
        THREE_LEVEL_FKS,
        {"differential_privacy": DP},
    )
    issues = training.collect_training_preflight("insp_dp")
    assert [i["id"] for i in issues] == ["dp_context_chain"]
    assert issues[0]["tables"] == ["drugs", "persons", "visits"]
    assert "per_table" in issues[0]["guidance"]


def test_preflight_clean_when_per_table_disables_deep_dp(inspections_root):
    _write_inspection(
        inspections_root,
        "insp_ok",
        TABLES,
        THREE_LEVEL_FKS,
        {"differential_privacy": DP, "per_table": {"drugs": {"differential_privacy": None}}},
    )
    assert training.collect_training_preflight("insp_ok") == []


def test_preflight_reports_undersized_sequential_parent(inspections_root):
    _write_inspection(
        inspections_root,
        "insp_small",
        {"persons": 3, "visits": 9},
        [THREE_LEVEL_FKS[0]],
        {},
    )
    issues = training.collect_training_preflight("insp_small")
    assert [i["id"] for i in issues] == ["undersized_sequential_table"]
    assert issues[0]["tables"] == ["visits"]


def test_preflight_missing_inspection_raises(inspections_root):
    with pytest.raises(FileNotFoundError):
        training.collect_training_preflight("nope")
