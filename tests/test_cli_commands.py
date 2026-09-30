"""Tests for `backend.src.cli.commands.run_workflow` — the CLI dispatcher.

The function dispatches on execution mode (``i`` / ``t`` / ``s``) and threads
artifacts between training and simulation when both run in one invocation.
Service flows are stubbed so we cover the dispatch logic without touching
mostlyai or any heavy dependency.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import backend.src.cli.commands as commands_module


@pytest.fixture
def stub_resolve(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(commands_module, "resolve_config_path", lambda name: f"/cfg/{name}.yaml")


def test_main_inspect_mode_invokes_inspection_flow(
    stub_resolve: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = MagicMock(
        return_value=SimpleNamespace(
            inspection_id="insp_1", output_directory="/runs/insp_1"
        )
    )
    monkeypatch.setattr(commands_module, "run_inspection_flow", fake)

    commands_module.run_workflow(mode="i", file_paths=["/data/a.csv"])

    fake.assert_called_once()
    kwargs = fake.call_args.kwargs
    assert kwargs["file_paths"] == ["/data/a.csv"]
    assert kwargs["mostly_config_path"] == "/cfg/mostly_ai.yaml"
    assert kwargs["rules_config_path"] == "/cfg/rules.yaml"


def test_main_inspect_mode_returns_silently_when_flow_returns_none(
    stub_resolve: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(commands_module, "run_inspection_flow", MagicMock(return_value=None))
    # Should not raise; just logs an error and returns.
    commands_module.run_workflow(mode="i", file_paths=[])


def test_main_train_mode_from_inspection_skips_simulation_when_no_sample_size(
    stub_resolve: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    train_from = MagicMock(return_value=("model_1", "GEN", {"m": 1}, "RM"))
    train_raw = MagicMock()
    sim = MagicMock()
    monkeypatch.setattr(commands_module, "run_training_flow_from_inspection", train_from)
    monkeypatch.setattr(commands_module, "run_training_flow", train_raw)
    monkeypatch.setattr(commands_module, "run_simulation_flow", sim)

    commands_module.run_workflow(mode="t", file_paths=None, inspection_id="insp_1")

    train_from.assert_called_once_with(inspection_id="insp_1")
    train_raw.assert_not_called()
    sim.assert_not_called()  # no sample_size provided -> training only


def test_main_train_mode_from_raw_files_threads_into_simulation(
    stub_resolve: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        commands_module,
        "run_training_flow",
        MagicMock(return_value=("model_1", "GEN", {"m": 1}, "RM")),
    )
    sim = MagicMock(return_value="sim_1")
    monkeypatch.setattr(commands_module, "run_simulation_flow", sim)

    commands_module.run_workflow(mode="t", file_paths=["/data/a.csv"], sample_size=100)

    sim.assert_called_once()
    kwargs = sim.call_args.kwargs
    assert kwargs["model_id"] == "model_1"
    assert kwargs["sample_size"] == 100
    assert kwargs["generator"] == "GEN"


def test_main_train_mode_returns_when_training_fails(
    stub_resolve: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        commands_module,
        "run_training_flow",
        MagicMock(return_value=(None, None, None, None)),
    )
    sim = MagicMock()
    monkeypatch.setattr(commands_module, "run_simulation_flow", sim)

    commands_module.run_workflow(mode="t", file_paths=["/data/a.csv"], sample_size=100)
    sim.assert_not_called()


def test_main_simulation_mode_loads_artifacts_then_simulates(
    stub_resolve: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        commands_module,
        "load_generator_artifacts",
        MagicMock(return_value=("GEN", {"m": 1}, "RM")),
    )
    sim = MagicMock(return_value="sim_1")
    monkeypatch.setattr(commands_module, "run_simulation_flow", sim)

    commands_module.run_workflow(mode="s", file_paths=None, sample_size=50, model_id="model_1")

    sim.assert_called_once()
    assert sim.call_args.kwargs["model_id"] == "model_1"
    assert sim.call_args.kwargs["sample_size"] == 50


def test_main_rules_mode_invokes_rules_flow(
    stub_resolve: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    apply_rules = MagicMock(return_value={
        "inspection_id": "insp_1",
        "rules_config_path": "/cfg/rules.yaml",
        "rules_count": 1,
    })
    monkeypatch.setattr(commands_module, "apply_inspection_rules", apply_rules)

    commands_module.run_workflow(mode="r", file_paths=None, inspection_id="insp_1")

    apply_rules.assert_called_once_with(inspection_id="insp_1")


def test_main_simulation_mode_requires_model_id(stub_resolve: None) -> None:
    with pytest.raises(ValueError, match="model_id es obligatorio"):
        commands_module.run_workflow(mode="s", file_paths=None, sample_size=50)


def test_main_simulation_mode_returns_when_artifact_loading_fails(
    stub_resolve: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        commands_module,
        "load_generator_artifacts",
        MagicMock(side_effect=FileNotFoundError("missing")),
    )
    sim = MagicMock()
    monkeypatch.setattr(commands_module, "run_simulation_flow", sim)

    commands_module.run_workflow(mode="s", file_paths=None, sample_size=50, model_id="missing")
    sim.assert_not_called()
