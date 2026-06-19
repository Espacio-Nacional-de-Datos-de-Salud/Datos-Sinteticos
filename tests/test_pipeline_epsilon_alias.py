"""Regression tests for pipeline differential-privacy epsilon aliases."""

from backend.src.domain.pipeline import executor as executor_module
from backend.src.domain.pipeline.config_classes import JobConfigOverrides, PipelineJobConfig
from backend.src.domain.evaluation.reporting.report_artifacts import _extract_training_parameters


def test_resolve_job_config_maps_root_epsilon_to_model_settings(monkeypatch) -> None:
    monkeypatch.setattr(
        executor_module,
        "resolve_config_path",
        lambda name: f"/cfg/{name}.yaml",
    )
    overrides = JobConfigOverrides(
        mostly_ai={
            "model_settings": {"model": "MOSTLY_AI/Small"},
            "differential_privacy": {"epsilon": 20},
        }
    )

    _rules, _mostly, mostly_overrides, _profiling, _delimiter = (
        executor_module._resolve_job_config(overrides)
    )

    assert mostly_overrides == {
        "model_settings": {
            "model": "MOSTLY_AI/Small",
            "differential_privacy": {"max_epsilon": 20},
        }
    }


def test_extract_training_parameters_reads_pipeline_epsilon_alias() -> None:
    job = PipelineJobConfig(
        name="j",
        config=JobConfigOverrides(
            mostly_ai={
                "model_settings": {
                    "model": "MOSTLY_AI/Large",
                    "enable_flexible_generation": False,
                },
                "differential_privacy": {"epsilon": 20},
            }
        ),
    )

    assert executor_module._extract_training_parameters_from_job(job) == {
        "model_type": "TabularARGN",
        "model_type_full_name": "Tabular Auto-Regressive Generative Network",
        "model_size": "Large",
        "epsilon": 20,
        "flexible_generation": False,
        "raw_model": "MOSTLY_AI/Large",
        "modeling_mode": None,
    }


def test_extract_training_parameters_reads_modeling_mode_from_job_config() -> None:
    job = PipelineJobConfig(
        name="j",
        config=JobConfigOverrides(
            mostly_ai={
                "model_settings": {
                    "model": "MOSTLY_AI/Medium",
                    "modeling_mode": "sequential",
                }
            }
        ),
    )

    assert executor_module._extract_training_parameters_from_job(job)["modeling_mode"] == "sequential"


def test_report_training_parameters_fallback_reads_simulation_epsilon_alias(tmp_path) -> None:
    evaluation_dir = tmp_path / "evaluations" / "eval_1"
    simulation_dir = tmp_path / "simulations" / "sim_1"
    evaluation_dir.mkdir(parents=True)
    simulation_dir.mkdir(parents=True)
    (simulation_dir / "simulation_card.json").write_text(
        """
        {
          "mostly_ai": {
            "model_settings": {
              "model": "MOSTLY_AI/Small",
              "enable_flexible_generation": false
            },
            "differential_privacy": {"epsilon": 20}
          }
        }
        """,
        encoding="utf-8",
    )

    params = _extract_training_parameters(
        evaluation_dir,
        {
            "simulation_id": "sim_1",
            "training_parameters": {
                "model_size": "Small",
                "epsilon": None,
                "flexible_generation": False,
                "raw_model": "MOSTLY_AI/Small",
            },
        },
    )

    assert params["epsilon"] == 20
    assert params["model_type"] == "TabularARGN"
    assert params["model_type_full_name"] == "Tabular Auto-Regressive Generative Network"


def test_report_training_parameters_infers_model_type_from_direct_raw_model(tmp_path) -> None:
    params = _extract_training_parameters(
        tmp_path,
        {
            "training_parameters": {
                "model_size": "Medium",
                "epsilon": 10,
                "flexible_generation": True,
                "raw_model": "MOSTLY_AI/Medium",
            },
        },
    )

    assert params["model_type"] == "TabularARGN"
    assert params["model_type_full_name"] == "Tabular Auto-Regressive Generative Network"
    assert params["epsilon"] == 10


def test_report_training_parameters_reads_modeling_mode_from_direct_training_parameters(tmp_path) -> None:
    params = _extract_training_parameters(
        tmp_path,
        {
            "training_parameters": {
                "model_size": "Medium",
                "epsilon": 10,
                "flexible_generation": True,
                "raw_model": "MOSTLY_AI/Medium",
                "modeling_mode": "sequential",
            },
        },
    )

    assert params["modeling_mode"] == "sequential"


def test_report_training_parameters_reads_modeling_mode_from_training_model_card(tmp_path) -> None:
    evaluation_dir = tmp_path / "evaluations" / "eval_1"
    simulation_dir = tmp_path / "simulations" / "sim_1"
    evaluation_dir.mkdir(parents=True)
    simulation_dir.mkdir(parents=True)
    (simulation_dir / "simulation_card.json").write_text(
        "{\n  \"simulation_id\": \"sim_1\",\n  \"training_parameters\": {\n    \"model_size\": \"Small\",\n    \"epsilon\": null,\n    \"flexible_generation\": false,\n    \"raw_model\": \"MOSTLY_AI/Small\"\n  }\n}\n",
        encoding="utf-8",
    )
    training_dir = simulation_dir / "training"
    training_dir.mkdir(parents=True)
    (training_dir / "model_card.json").write_text(
        "{\n  \"mostly_statistics\": {\n    \"detected_modeling_mode\": \"sequential\"\n  }\n}\n",
        encoding="utf-8",
    )

    params = _extract_training_parameters(
        evaluation_dir,
        {
            "simulation_id": "sim_1",
            "training_parameters": {
                "model_size": "Small",
                "epsilon": None,
                "flexible_generation": False,
                "raw_model": "MOSTLY_AI/Small",
            },
        },
    )

    assert params["modeling_mode"] == "sequential"
