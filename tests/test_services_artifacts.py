"""Tests for `backend.src.sessions.artifacts.load_generator_artifacts`.

The function is a thin coordinator over `MostlyAIEngine` plus two metadata
loaders. Tests mock those collaborators to verify the wiring: the engine is
constructed with the expected config, the model is loaded by ID, and the
returned tuple matches the loader outputs.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.src.sessions import artifacts as artifacts_module


def test_load_generator_artifacts_wires_collaborators(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # --- Arrange ---
    captured: dict = {}

    fake_generator = object()
    fake_metadata = {"tables": ["t1"]}
    fake_rule_manager = object()
    run_folder = "/runs/model_x"

    class FakeEngine:
        def __init__(self, config_path: str) -> None:
            captured["config_path"] = config_path

        def load_generator_by_id(self, model_id: str):
            captured["model_id"] = model_id
            return fake_generator, run_folder

    def fake_load_metadata(path: str) -> dict:
        captured["metadata_path"] = path
        return fake_metadata

    def fake_load_rule_manager(path: str):
        captured["rules_path"] = path
        return fake_rule_manager

    # --- Mock collaborators ---
    monkeypatch.setattr(artifacts_module, "MostlyAIEngine", FakeEngine)
    monkeypatch.setattr(artifacts_module, "load_metadata", fake_load_metadata)
    monkeypatch.setattr(artifacts_module, "load_rule_manager", fake_load_rule_manager)

    # --- Act ---
    generator, metadata, rule_manager = artifacts_module.load_generator_artifacts(
        model_id="model_x", mostly_config_path="/cfg/mostly.yaml"
    )

    # --- Assert ---
    assert generator is fake_generator
    assert metadata is fake_metadata
    assert rule_manager is fake_rule_manager
    assert captured == {
        "config_path": "/cfg/mostly.yaml",
        "model_id": "model_x",
        "metadata_path": run_folder,
        "rules_path": run_folder,
    }


def test_load_generator_artifacts_propagates_engine_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeEngine:
        def __init__(self, config_path: str) -> None:
            pass

        def load_generator_by_id(self, model_id: str):
            raise FileNotFoundError("missing model")

    monkeypatch.setattr(artifacts_module, "MostlyAIEngine", FakeEngine)
    monkeypatch.setattr(
        artifacts_module, "load_metadata", lambda _path: {}
    )
    monkeypatch.setattr(
        artifacts_module, "load_rule_manager", lambda _path: SimpleNamespace()
    )

    with pytest.raises(FileNotFoundError, match="missing model"):
        artifacts_module.load_generator_artifacts("model_x", "/cfg/mostly.yaml")
