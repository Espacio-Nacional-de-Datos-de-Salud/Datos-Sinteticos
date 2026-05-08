"""Tests for `backend.src.pipeline.executor`.

The executor wires the train/simulate/evaluate services into a sequential
pipeline. These tests mock the underlying service flows to verify:

- per-job override resolution merges user config with defaults
- each step dispatcher passes the right arguments to its service
- step failures short-circuit the rest of the job
- a missing precondition (no model_id, no simulation_id) is reported
- artifacts produced by the train step are threaded into simulate
- cancellation events are honored between steps and between jobs
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.src.pipeline import executor as executor_module
from backend.src.pipeline.config_classes import (
    EvaluateStepConfig,
    JobConfigOverrides,
    PipelineConfig,
    PipelineJobConfig,
    SimulateStepConfig,
    TrainStepConfig,
)

# --------------------------------------------------------------------------- #
# _resolve_job_config
# --------------------------------------------------------------------------- #


@pytest.fixture
def stub_resolve_config_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        executor_module,
        "resolve_config_path",
        lambda name: f"/cfg/{name}.yaml",
    )


def test_resolve_job_config_returns_defaults_when_no_overrides(
    stub_resolve_config_path: None,
) -> None:
    rules, mostly, mostly_overrides, profiling, delim = (
        executor_module._resolve_job_config(None)
    )
    assert rules == "/cfg/rules.yaml"
    assert mostly == "/cfg/mostly_ai.yaml"
    assert mostly_overrides is None
    assert isinstance(profiling, bool)
    assert isinstance(delim, str)


def test_resolve_job_config_applies_each_override_kind(
    stub_resolve_config_path: None,
) -> None:
    overrides = JobConfigOverrides(
        rules_config="/custom/rules.yaml",
        mostly_ai={"epochs": 7},
        general={"enable_data_profiling": False, "csv_delimiter": ";"},
    )
    rules, mostly, mostly_overrides, profiling, delim = (
        executor_module._resolve_job_config(overrides)
    )
    assert rules == "/custom/rules.yaml"
    assert mostly == "/cfg/mostly_ai.yaml"
    assert mostly_overrides == {"epochs": 7}
    assert profiling is False
    assert delim == ";"


def test_resolve_job_config_ignores_partial_general_keys(
    stub_resolve_config_path: None,
) -> None:
    overrides = JobConfigOverrides(general={"csv_delimiter": "|"})
    _, _, _, profiling, delim = executor_module._resolve_job_config(overrides)
    # csv_delimiter overridden but enable_data_profiling kept at module default
    assert delim == "|"
    assert isinstance(profiling, bool)


# --------------------------------------------------------------------------- #
# _run_train_step
# --------------------------------------------------------------------------- #


def _patch_run_training_flow(monkeypatch: pytest.MonkeyPatch, return_value):
    """Replace `run_training_flow` with a mock returning a fixed result."""
    fake = MagicMock(return_value=return_value)
    import backend.src.services.training as training_mod

    monkeypatch.setattr(training_mod, "run_training_flow", fake)
    return fake


def test_run_train_step_returns_none_when_service_returns_no_model_id(
    stub_resolve_config_path: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_run_training_flow(monkeypatch, (None, None, None, None))
    result = executor_module._run_train_step(TrainStepConfig(files=["/x.csv"]))
    assert result is None


def test_run_train_step_returns_full_artifact_tuple_on_success(
    stub_resolve_config_path: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _patch_run_training_flow(
        monkeypatch, ("model_1", "GEN", {"meta": True}, "RM")
    )
    result = executor_module._run_train_step(
        TrainStepConfig(files=["/x.csv"]),
        pipeline_id="pid",
        job_name="job_a",
    )
    assert result == ("model_1", "GEN", {"meta": True}, "RM")
    fake.assert_called_once()
    kwargs = fake.call_args.kwargs
    assert kwargs["file_paths"] == ["/x.csv"]
    assert kwargs["mostly_config_path"] == "/cfg/mostly_ai.yaml"
    assert kwargs["pipeline_id"] == "pid"
    assert kwargs["job_name"] == "job_a"


# --------------------------------------------------------------------------- #
# _run_simulate_step
# --------------------------------------------------------------------------- #


def _patch_simulation_flow(monkeypatch: pytest.MonkeyPatch, return_value):
    """Replace `run_simulation_flow` with a mock returning a fixed result."""
    fake = MagicMock(return_value=return_value)
    import backend.src.services.simulation as simulation_mod

    monkeypatch.setattr(simulation_mod, "run_simulation_flow", fake)
    return fake


def test_run_simulate_step_uses_existing_artifacts_when_available(
    stub_resolve_config_path: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_sim = _patch_simulation_flow(monkeypatch, "sim_1")

    sim_id = executor_module._run_simulate_step(
        step=SimulateStepConfig(sample_size=100, synthetic_data_file_format="parquet"),
        generator="GEN",
        metadata={"meta": True},
        rule_manager="RM",
        model_id="model_1",
    )

    assert sim_id == "sim_1"
    fake_sim.assert_called_once()
    kwargs = fake_sim.call_args.kwargs
    assert kwargs["generator"] == "GEN"
    assert kwargs["model_id"] == "model_1"
    assert kwargs["sample_size"] == 100
    assert kwargs["synthetic_data_file_format"] == "parquet"


def test_run_simulate_step_loads_artifacts_when_no_inline_generator(
    stub_resolve_config_path: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_sim = _patch_simulation_flow(monkeypatch, "sim_2")

    import backend.src.services.artifacts as artifacts_mod

    fake_loader = MagicMock(return_value=("GEN_LOADED", {"m": 1}, "RM_LOADED"))
    monkeypatch.setattr(artifacts_mod, "load_generator_artifacts", fake_loader)

    sim_id = executor_module._run_simulate_step(
        step=SimulateStepConfig(sample_size=10, model_id="model_x"),
        generator=None,
        metadata=None,
        rule_manager=None,
        model_id=None,
    )

    assert sim_id == "sim_2"
    fake_loader.assert_called_once_with("model_x", "/cfg/mostly_ai.yaml")
    assert fake_sim.call_args.kwargs["generator"] == "GEN_LOADED"


def test_run_simulate_step_returns_none_when_no_model_or_generator(
    stub_resolve_config_path: None,
) -> None:
    sim_id = executor_module._run_simulate_step(
        step=SimulateStepConfig(),
        generator=None,
        metadata=None,
        rule_manager=None,
        model_id=None,
    )
    assert sim_id is None


def test_run_simulate_step_returns_none_when_artifact_loading_fails(
    stub_resolve_config_path: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    import backend.src.services.artifacts as artifacts_mod

    monkeypatch.setattr(
        artifacts_mod,
        "load_generator_artifacts",
        MagicMock(side_effect=FileNotFoundError("no model")),
    )
    sim_id = executor_module._run_simulate_step(
        step=SimulateStepConfig(model_id="missing"),
        generator=None,
        metadata=None,
        rule_manager=None,
        model_id=None,
    )
    assert sim_id is None


# --------------------------------------------------------------------------- #
# _run_evaluate_step
# --------------------------------------------------------------------------- #


def _patch_evaluation_service(monkeypatch: pytest.MonkeyPatch, eval_id: str | None):
    """Replace evaluation service functions with mocks. Returns (init_mock, flow_mock)."""
    import backend.src.services.evaluation as evaluation_mod

    fake_session = SimpleNamespace(evaluation_id="eval_pre")
    init = MagicMock(return_value=fake_session)
    flow = MagicMock(return_value=eval_id)
    monkeypatch.setattr(evaluation_mod, "initialize_evaluation_session", init)
    monkeypatch.setattr(evaluation_mod, "run_evaluation_flow_from_simulation", flow)
    return init, flow


def test_run_evaluate_step_threads_simulation_and_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init, flow = _patch_evaluation_service(monkeypatch, "eval_ok")

    result = executor_module._run_evaluate_step(
        step=EvaluateStepConfig(real_data=["/r.csv"]),
        simulation_id="sim_1",
        model_id="model_1",
        pipeline_id="pid",
        job_name="job_a",
    )
    assert result == "eval_ok"
    init.assert_called_once_with(simulation_id="sim_1", model_id="model_1")
    assert flow.call_args.kwargs["real_data"] == ["/r.csv"]
    assert flow.call_args.kwargs["pipeline_id"] == "pid"


def test_run_evaluate_step_prefers_explicit_overrides_over_threaded_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    init, flow = _patch_evaluation_service(monkeypatch, "eval_ok")

    executor_module._run_evaluate_step(
        step=EvaluateStepConfig(
            real_data=["/r.csv"],
            simulation_id="explicit_sim",
            model_id="explicit_model",
        ),
        simulation_id="threaded_sim",
        model_id="threaded_model",
        pipeline_id="pid",
        job_name="job_a",
    )
    init.assert_called_once_with(
        simulation_id="explicit_sim", model_id="explicit_model"
    )


def test_run_evaluate_step_requires_simulation_id() -> None:
    result = executor_module._run_evaluate_step(
        step=EvaluateStepConfig(real_data=["/r.csv"]),
        simulation_id=None,
        model_id="model_1",
        pipeline_id="pid",
        job_name="job_a",
    )
    assert result is None


def test_run_evaluate_step_requires_model_id() -> None:
    result = executor_module._run_evaluate_step(
        step=EvaluateStepConfig(real_data=["/r.csv"], simulation_id="sim_1"),
        simulation_id=None,
        model_id=None,
        pipeline_id="pid",
        job_name="job_a",
    )
    assert result is None


def test_run_evaluate_step_returns_none_on_service_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import backend.src.services.evaluation as evaluation_mod

    monkeypatch.setattr(
        evaluation_mod,
        "initialize_evaluation_session",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    result = executor_module._run_evaluate_step(
        step=EvaluateStepConfig(real_data=["/r.csv"]),
        simulation_id="sim_1",
        model_id="model_1",
        pipeline_id="pid",
        job_name="job_a",
    )
    assert result is None


# --------------------------------------------------------------------------- #
# _run_job orchestration
# --------------------------------------------------------------------------- #


def _stub_step_runners(
    monkeypatch: pytest.MonkeyPatch,
    *,
    train_result=("model_1", "GEN", {"m": 1}, "RM"),
    simulate_result="sim_1",
    evaluate_result="eval_1",
):
    """Replace step runners with mocks. Returns (train_mock, simulate_mock, evaluate_mock)."""
    train_mock = MagicMock(return_value=train_result)
    simulate_mock = MagicMock(return_value=simulate_result)
    evaluate_mock = MagicMock(return_value=evaluate_result)
    monkeypatch.setattr(executor_module, "_run_train_step", train_mock)
    monkeypatch.setattr(executor_module, "_run_simulate_step", simulate_mock)
    monkeypatch.setattr(executor_module, "_run_evaluate_step", evaluate_mock)
    return train_mock, simulate_mock, evaluate_mock


def test_run_job_threads_train_artifacts_into_simulate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_mock, simulate_mock, evaluate_mock = _stub_step_runners(monkeypatch)

    job = PipelineJobConfig(
        name="j",
        train=TrainStepConfig(files=["/x.csv"]),
        simulate=SimulateStepConfig(),
        evaluate=EvaluateStepConfig(real_data=["/r.csv"]),
    )
    model_id, simulation_id, _evaluation_id = executor_module._run_job(
        job, pipeline_id="pid"
    )

    assert model_id == "model_1"
    assert simulation_id == "sim_1"

    sim_kwargs = simulate_mock.call_args.kwargs
    assert sim_kwargs["generator"] == "GEN"
    assert sim_kwargs["metadata"] == {"m": 1}
    assert sim_kwargs["rule_manager"] == "RM"
    assert sim_kwargs["model_id"] == "model_1"

    eval_args = evaluate_mock.call_args
    assert eval_args.kwargs["simulation_id"] == "sim_1"
    assert eval_args.kwargs["model_id"] == "model_1"


def test_run_job_skips_simulate_and_evaluate_when_train_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    train_mock, simulate_mock, evaluate_mock = _stub_step_runners(
        monkeypatch, train_result=None
    )
    job = PipelineJobConfig(
        name="j",
        train=TrainStepConfig(files=["/x.csv"]),
        simulate=SimulateStepConfig(),
        evaluate=EvaluateStepConfig(real_data=["/r.csv"]),
    )
    model_id, simulation_id, _evaluation_id = executor_module._run_job(
        job, pipeline_id="pid"
    )
    assert model_id is None and simulation_id is None
    train_mock.assert_called_once()
    simulate_mock.assert_not_called()
    evaluate_mock.assert_not_called()


def test_run_job_skips_evaluate_when_simulate_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, simulate_mock, evaluate_mock = _stub_step_runners(
        monkeypatch, simulate_result=None
    )
    job = PipelineJobConfig(
        name="j",
        train=TrainStepConfig(files=["/x.csv"]),
        simulate=SimulateStepConfig(),
        evaluate=EvaluateStepConfig(real_data=["/r.csv"]),
    )
    _, simulation_id, _ = executor_module._run_job(job, pipeline_id="pid")
    assert simulation_id is None
    simulate_mock.assert_called_once()
    evaluate_mock.assert_not_called()


def test_run_job_honors_cancellation_after_train(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, simulate_mock, evaluate_mock = _stub_step_runners(monkeypatch)
    cancel_event = threading.Event()
    cancel_event.set()

    job = PipelineJobConfig(
        name="j",
        train=TrainStepConfig(files=["/x.csv"]),
        simulate=SimulateStepConfig(),
        evaluate=EvaluateStepConfig(real_data=["/r.csv"]),
    )
    executor_module._run_job(job, pipeline_id="pid", cancel_event=cancel_event)
    simulate_mock.assert_not_called()
    evaluate_mock.assert_not_called()


# --------------------------------------------------------------------------- #
# run_pipeline
# --------------------------------------------------------------------------- #


@contextmanager
def _fake_tracker(pipeline_id: str = "pid", output_directory: str = "/tmp/out"):
    """Provide a mock PipelineTracker with tracked methods for assertions."""
    yield SimpleNamespace(
        pipeline_id=pipeline_id,
        output_directory=output_directory,
        register_job_result=MagicMock(),
        mark_cancelled=MagicMock(),
        set_progress=MagicMock(),
    )


def _fake_pipeline_tracker_factory(monkeypatch: pytest.MonkeyPatch, tmp_path):
    """Create a fake PipelineTracker factory and return (factory, captured_dict).

    The captured dict stores the tracker instance under key 't' for assertions.
    """
    captured: dict = {}

    def fake_tracker_factory(config_path, pipeline_id=None):
        @contextmanager
        def _cm():
            tracker = SimpleNamespace(
                pipeline_id="pid",
                output_directory=str(tmp_path),
                register_job_result=MagicMock(),
                mark_cancelled=MagicMock(),
                set_progress=MagicMock(),
            )
            captured["t"] = tracker
            yield tracker

        return _cm()

    monkeypatch.setattr(executor_module, "PipelineTracker", fake_tracker_factory)
    return captured


def test_run_pipeline_runs_each_job_and_registers_results(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_runner = MagicMock(side_effect=[("m1", "s1", None), ("m2", "s2", None)])
    monkeypatch.setattr(executor_module, "_run_job", job_runner)

    captured_tracker = _fake_pipeline_tracker_factory(monkeypatch, tmp_path)

    config = PipelineConfig(
        jobs=[PipelineJobConfig(name="a"), PipelineJobConfig(name="b")]
    )
    executor_module.run_pipeline(config, config_path="/cfg/p.yaml")

    assert job_runner.call_count == 2
    register = captured_tracker["t"].register_job_result
    assert register.call_count == 2
    assert {call.kwargs["job_name"] for call in register.call_args_list} == {"a", "b"}


def test_run_pipeline_cancellation_skips_remaining_jobs(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_runner = MagicMock(return_value=("m", "s", None))
    monkeypatch.setattr(executor_module, "_run_job", job_runner)

    cancel_event = threading.Event()
    cancel_event.set()

    captured = _fake_pipeline_tracker_factory(monkeypatch, tmp_path)

    config = PipelineConfig(
        jobs=[PipelineJobConfig(name="a"), PipelineJobConfig(name="b")]
    )
    executor_module.run_pipeline(
        config, config_path="/cfg/p.yaml", cancel_event=cancel_event
    )

    job_runner.assert_not_called()
    captured["t"].mark_cancelled.assert_called_once()
