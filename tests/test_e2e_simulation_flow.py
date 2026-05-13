"""End-to-end test for `run_simulation_flow` and `run_simulation_flow_from_model`.

Stubs the heavy collaborators (``MostlyAIEngine``, ``SimulationTracker``,
``run_general_sanity_checks``, ``extract_synthetic_metadata``) but lets the
service layer drive its own dispatch, sanity-check composition, cancellation,
and error handling for real.
"""

from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from backend.src.sessions import simulation as simulation_service


@pytest.fixture
def fake_engine(monkeypatch: pytest.MonkeyPatch):
    """Replace `MostlyAIEngine` with a mock that returns fixed synthetic data.

    Returns the mock class itself (not an instance); when called, it returns
    a mock instance with `simulate()` returning a dict with one table.
    """
    fake = MagicMock()
    fake.return_value.simulate = MagicMock(
        return_value={"patients": pd.DataFrame({"id": [1, 2], "age": [25, 30]})}
    )
    fake.return_value.load_generator_by_id = MagicMock(return_value=(object(), None))
    monkeypatch.setattr(simulation_service, "MostlyAIEngine", fake)
    return fake


@pytest.fixture
def fake_tracker(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Replace `SimulationTracker` with a spy that captures all method calls.

    Returns a dict (`saved`) that records: `init` (constructor args),
    `sim_config`, `sample_size`, `synthetic_results`, `sanity_report`,
    and `sim_metadata` (from corresponding `save_*` method calls).
    Tests assert on these keys to verify the flow called the right methods.
    """
    saved: dict = {}

    class FakeTracker:
        def __init__(
            self,
            *,
            model_id,
            pipeline_id,
            job_name,
            simulation_id=None,
            synthetic_data_file_format="csv",
        ):
            self.simulation_id = simulation_id or "sim_test_1"
            self.output_directory = str(tmp_path / "sims" / self.simulation_id)
            saved["init"] = {
                "model_id": model_id,
                "pipeline_id": pipeline_id,
                "job_name": job_name,
                "synthetic_data_file_format": synthetic_data_file_format,
            }

        def __enter__(self):
            return self

        def __exit__(self, *exc_info):
            return False

        def save_sim_config(self, cfg):
            saved["sim_config"] = cfg

        def save_sim_card(self, sample_size=None):
            saved["sample_size"] = sample_size

        def save_synthetic_results(self, results):
            saved["synthetic_results"] = results

        def save_sanity_report(self, report):
            saved["sanity_report"] = report

        def save_sim_metadata(self, meta):
            saved["sim_metadata"] = meta

    monkeypatch.setattr(simulation_service, "SimulationTracker", FakeTracker)
    monkeypatch.setattr(
        simulation_service, "extract_synthetic_metadata", lambda _r: {"tables": []}
    )
    return saved


@pytest.fixture
def fake_rule_manager() -> SimpleNamespace:
    return SimpleNamespace(
        apply_all_post=lambda raw: raw,
        run_rules_sanity_checks=lambda _r: pd.DataFrame(),
    )


def test_run_simulation_flow_threads_data_through_pipeline(
    fake_engine, fake_tracker, fake_rule_manager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        simulation_service, "run_general_sanity_checks", lambda **_kw: pd.DataFrame()
    )

    metadata = {"tables": [{"name": "patients"}]}
    sim_id = simulation_service.run_simulation_flow(
        generator=object(),
        metadata=metadata,
        rule_manager=fake_rule_manager,
        model_id="model_1",
        sample_size=2,
        mostly_config_path="/cfg/mostly.yaml",
    )

    assert sim_id == "sim_test_1"
    assert fake_tracker["init"]["model_id"] == "model_1"
    assert fake_tracker["init"]["synthetic_data_file_format"] == "csv"
    assert fake_tracker["sample_size"] == 2
    assert fake_tracker["sim_config"]["tables"][0]["configuration"]["sample_size"] == 2
    assert "patients" in fake_tracker["synthetic_results"]
    # No sanity findings -> save_sanity_report should not have been called.
    assert "sanity_report" not in fake_tracker


def test_run_simulation_flow_persists_sanity_findings_when_present(
    fake_engine, fake_tracker, fake_rule_manager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        simulation_service,
        "run_general_sanity_checks",
        lambda **_kw: pd.DataFrame({"check": ["fk"], "result": ["fail"]}),
    )

    simulation_service.run_simulation_flow(
        generator=object(),
        metadata={"tables": [{"name": "patients"}]},
        rule_manager=fake_rule_manager,
        model_id="model_1",
        sample_size=2,
        mostly_config_path="/cfg/mostly.yaml",
    )

    report = fake_tracker["sanity_report"]
    assert isinstance(report, pd.DataFrame)
    assert "check" in report.columns


def test_run_simulation_flow_returns_none_when_engine_raises(
    fake_tracker, fake_rule_manager, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = MagicMock()
    fake.return_value.simulate = MagicMock(side_effect=RuntimeError("boom"))
    monkeypatch.setattr(simulation_service, "MostlyAIEngine", fake)
    monkeypatch.setattr(
        simulation_service, "run_general_sanity_checks", lambda **_kw: pd.DataFrame()
    )

    sim_id = simulation_service.run_simulation_flow(
        generator=object(),
        metadata={"tables": [{"name": "patients"}]},
        rule_manager=fake_rule_manager,
        model_id="model_1",
        sample_size=2,
        mostly_config_path="/cfg/mostly.yaml",
    )
    assert sim_id is None


def test_run_simulation_flow_short_circuits_on_pre_run_cancel(
    fake_engine, fake_tracker, fake_rule_manager
) -> None:
    cancel = threading.Event()
    cancel.set()

    sim_id = simulation_service.run_simulation_flow(
        generator=object(),
        metadata={"tables": [{"name": "patients"}]},
        rule_manager=fake_rule_manager,
        model_id="model_1",
        sample_size=2,
        mostly_config_path="/cfg/mostly.yaml",
        cancel_event=cancel,
    )
    assert sim_id is None
    fake_engine.assert_not_called()


def test_run_simulation_flow_from_model_loads_artifacts_then_simulates(
    fake_engine, fake_tracker, fake_rule_manager, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        simulation_service, "run_general_sanity_checks", lambda **_kw: pd.DataFrame()
    )

    import backend.src.sessions.artifacts as artifacts_mod

    loader = MagicMock(
        return_value=(object(), {"tables": [{"name": "patients"}]}, fake_rule_manager)
    )
    monkeypatch.setattr(artifacts_mod, "load_generator_artifacts", loader)

    sim_id = simulation_service.run_simulation_flow_from_model(
        model_id="model_1",
        sample_size=2,
        mostly_config_path="/cfg/mostly.yaml",
    )
    assert sim_id == "sim_test_1"
    loader.assert_called_once_with("model_1", "/cfg/mostly.yaml")


def test_run_simulation_flow_from_model_returns_none_when_loader_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.src.sessions.artifacts as artifacts_mod

    monkeypatch.setattr(
        artifacts_mod,
        "load_generator_artifacts",
        MagicMock(side_effect=FileNotFoundError("missing")),
    )
    sim_id = simulation_service.run_simulation_flow_from_model(
        model_id="missing",
        sample_size=2,
        mostly_config_path="/cfg/mostly.yaml",
    )
    assert sim_id is None


# --------------------------------------------------------------------------- #
# Helpers exercised independently
# --------------------------------------------------------------------------- #


def test_run_all_sanity_checks_concatenates_rule_and_general_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rules_report = pd.DataFrame({"source": ["rule_1"]})
    general_report = pd.DataFrame({"source": ["general_1"]})
    rule_manager = SimpleNamespace(run_rules_sanity_checks=lambda _r: rules_report)

    monkeypatch.setattr(
        simulation_service, "run_general_sanity_checks", lambda **_kw: general_report
    )

    combined = simulation_service.run_all_sanity_checks(
        synthetic_results={"t": pd.DataFrame()},
        metadata={},
        rule_manager=rule_manager,
    )
    assert combined is not None
    assert combined["source"].tolist() == ["rule_1", "general_1"]


def test_run_all_sanity_checks_returns_none_when_no_findings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rule_manager = SimpleNamespace(run_rules_sanity_checks=lambda _r: pd.DataFrame())
    monkeypatch.setattr(
        simulation_service, "run_general_sanity_checks", lambda **_kw: pd.DataFrame()
    )
    combined = simulation_service.run_all_sanity_checks(
        synthetic_results={"t": pd.DataFrame()},
        metadata={},
        rule_manager=rule_manager,
    )
    assert combined is None


def test_extract_synthetic_metadata_returns_empty_on_extractor_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BoomExtractor:
        def __init__(self, _data):
            raise RuntimeError("nope")

    monkeypatch.setattr(simulation_service, "MetadataExtractor", BoomExtractor)
    result = simulation_service.extract_synthetic_metadata({"t": pd.DataFrame()})
    assert result == {"tables": []}
