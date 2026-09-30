"""End-to-end test for `run_simulation_flow` and `run_simulation_flow_from_model`.

Stubs the heavy collaborators (the engine via ``create_engine``, ``SimulationTracker``,
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
    """Replace the engine factory with a mock that returns fixed synthetic data.

    Returns the mock class itself (not an instance); when called, it returns
    a mock instance with `simulate()` returning a dict with one table.
    """
    fake = MagicMock()
    fake.return_value.simulate = MagicMock(
        return_value=(
            {"patients": pd.DataFrame({"id": [1, 2], "age": [25, 30]})},
            "sd_test_1",
        )
    )
    fake.return_value.load_generator_by_id = MagicMock(return_value=(object(), None))
    monkeypatch.setattr(simulation_service, "create_engine", fake)
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

        def save_sim_card(
            self,
            sample_size=None,
            mother_table=None,
            mother_table_size=None,
            target_table=None,
            target_table_rows=None,
        ):
            saved["sample_size"] = sample_size
            saved["mother_table"] = mother_table
            saved["mother_table_size"] = mother_table_size
            saved["target_table"] = target_table
            saved["target_table_rows"] = target_table_rows

        def save_synthetic_results(self, results):
            saved["synthetic_results"] = results

        def save_sanity_report(self, report):
            saved["sanity_report"] = report

        def save_auxiliary_columns(self, raw_results, final_results, metadata):
            saved["auxiliary_columns"] = {
                "raw": raw_results,
                "final": final_results,
                "metadata": metadata,
            }

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
        run_rules_sanity_checks=lambda _r, **_kw: pd.DataFrame(),
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
    monkeypatch.setattr(simulation_service, "create_engine", fake)
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
    rule_manager = SimpleNamespace(run_rules_sanity_checks=lambda _r, **_kw: rules_report)

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
    rule_manager = SimpleNamespace(run_rules_sanity_checks=lambda _r, **_kw: pd.DataFrame())
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


def test_resolve_subject_targets_uses_table_sizes_and_skips_children() -> None:
    """Only subject tables get a target; children cascade and are excluded.

    Regression for the gate bug: a per-table size on the subject (``person``)
    must produce a target even when the global ``sample_size`` is None, so
    rejection sampling engages instead of dropping into the destructive
    single-pass fallback. Context children (with an ``is_context`` FK) never get
    a target — the engine cascades their counts.
    """
    metadata = {
        "tables": [
            {"name": "person", "foreign_keys": []},
            {
                "name": "condition_occurrence",
                "foreign_keys": [
                    {"column": "person_id", "referenced_table": "person", "is_context": True}
                ],
            },
        ]
    }

    # Per-table size on the subject, no global size: still yields a target.
    targets = simulation_service._resolve_subject_targets(
        metadata, sample_size=None, table_sample_sizes={"person": 1000}
    )
    assert targets == {"person": 1000}

    # A child size is ignored even if supplied.
    targets = simulation_service._resolve_subject_targets(
        metadata, sample_size=None, table_sample_sizes={"condition_occurrence": 5000}
    )
    assert targets == {}

    # Global fallback applies to the subject only.
    targets = simulation_service._resolve_subject_targets(
        metadata, sample_size=250, table_sample_sizes=None
    )
    assert targets == {"person": 250}

    # No size anywhere ⇒ no targets ⇒ rejection sampling cannot run.
    assert simulation_service._resolve_subject_targets(metadata, None, None) == {}


def _omop_like_metadata() -> dict:
    return {
        "tables": [
            {"name": "person", "primary_key": "person_id", "foreign_keys": []},
            {
                "name": "condition_occurrence",
                "primary_key": "condition_occurrence_id",
                "foreign_keys": [
                    {"column": "person_id", "referenced_table": "person", "is_context": True}
                ],
            },
        ]
    }


def test_resolve_child_targets_scales_by_real_ratio() -> None:
    """Child target = (real child:subject ratio) × subject target.

    Training had 167 conditions for 12 persons; a 1000-person request should aim
    for ~13917 compliant conditions. The engine can't enforce this — it's only
    used to decide how hard rejection sampling retries and to report the gap.
    """
    targets = simulation_service._resolve_child_targets(
        metadata=_omop_like_metadata(),
        rejection_child_tables={"condition_occurrence"},
        subject_targets={"person": 1000},
        training_table_sizes={"person": 12, "condition_occurrence": 167},
    )
    assert targets == {"condition_occurrence": round(167 / 12 * 1000)}

    # Without training sizes there is no target (no extra retries forced).
    assert (
        simulation_service._resolve_child_targets(
            _omop_like_metadata(), {"condition_occurrence"}, {"person": 1000}, {}
        )
        == {}
    )


def test_select_best_subjects_keeps_exact_count_maximizing_compliant_children() -> None:
    """Subjects stay exactly at target; the ones with the most child rows are kept."""
    results = {
        "person": pd.DataFrame({"person_id": [1, 2, 3]}),
        # person 1 has 3 conditions, person 2 has 1, person 3 has none.
        "condition_occurrence": pd.DataFrame(
            {
                "condition_occurrence_id": [10, 11, 12, 13],
                "person_id": [1, 1, 1, 2],
            }
        ),
    }
    selected = simulation_service._select_best_subjects(
        results,
        metadata=_omop_like_metadata(),
        subject_targets={"person": 2},
        rejection_child_tables={"condition_occurrence"},
    )
    # Exactly the requested number of subjects, and the two highest contributors.
    assert len(selected["person"]) == 2
    assert set(selected["person"]["person_id"]) == {1, 2}
    # Person 3 (no children) was dropped; person 1's children all survive.
    assert set(selected["condition_occurrence"]["person_id"]) == {1, 2}
    assert len(selected["condition_occurrence"]) == 4


def test_save_auxiliary_columns(tmp_path) -> None:
    from backend.src.runs.tracking.simulation_tracker import SimulationTracker
    import os

    tracker = SimulationTracker(model_id="model_1", simulation_id="sim_1")
    tracker.output_directory = str(tmp_path / "sims" / "sim_1")
    tracker.synthetic_data_directory = os.path.join(tracker.output_directory, "synthetic_data")

    # Setup raw and final results
    # patients table has raw auxiliary column 'duration_days' which is dropped in final_df
    raw_results = {
        "patients": pd.DataFrame({
            "id": [1, 2, 3],
            "age": [25, 30, 35],
            "duration_days": [100, 200, 300]
        })
    }
    # final_results has only id and age (reconstructed dates, but duration_days is dropped)
    # Rejection sampling dropped row with id=2 (index 1)
    final_results = {
        "patients": pd.DataFrame({
            "id": [1, 3],
            "age": [25, 35]
        }, index=[0, 2])
    }

    metadata = {
        "tables": [
            {
                "name": "patients",
                "primary_key": "id"
            }
        ]
    }

    # Save auxiliary columns
    tracker.save_auxiliary_columns(raw_results, final_results, metadata)

    # Check that the file was created and contains correct data
    aux_file_path = os.path.join(tracker.output_directory, "auxiliary_columns", "patients.csv")
    assert os.path.exists(aux_file_path)

    saved_df = pd.read_csv(aux_file_path)
    # Check columns: primary key 'id' and auxiliary column 'duration_days' should be there
    assert list(saved_df.columns) == ["id", "duration_days"]
    # Check values: only rows 1 and 3 (index 0 and 2) should remain
    assert saved_df["id"].tolist() == [1, 3]
    assert saved_df["duration_days"].tolist() == [100, 300]

