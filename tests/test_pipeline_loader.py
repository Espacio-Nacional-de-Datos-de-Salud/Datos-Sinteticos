"""Tests for `backend.src.pipeline.loader.load_pipeline_config`.

The loader translates YAML pipeline configs into typed dataclasses. These
tests cover schema validation (missing top-level key, missing file), per-step
parsing (train / simulate / evaluate / config overrides), default job names,
and the directory-expansion shortcut for train inputs.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from backend.src.config.general import DEFAULT_SAMPLE_SIZE
from backend.src.pipeline.loader import load_pipeline_config


def _write_yaml(path: Path, payload: dict) -> Path:
    path.write_text(yaml.safe_dump(payload), encoding="utf-8")
    return path


def test_missing_file_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="Pipeline config not found"):
        load_pipeline_config(str(tmp_path / "missing.yaml"))


def test_missing_jobs_key_raises_value_error(tmp_path: Path) -> None:
    cfg = _write_yaml(tmp_path / "p.yaml", {"not_jobs": []})
    with pytest.raises(ValueError, match="top-level 'jobs' key"):
        load_pipeline_config(str(cfg))


def test_non_dict_root_raises_value_error(tmp_path: Path) -> None:
    cfg = tmp_path / "p.yaml"
    cfg.write_text("- just a list\n", encoding="utf-8")
    with pytest.raises(ValueError, match="top-level 'jobs' key"):
        load_pipeline_config(str(cfg))


def test_full_three_step_job_parses_all_fields(tmp_path: Path) -> None:
    cfg = _write_yaml(
        tmp_path / "p.yaml",
        {
            "jobs": [
                {
                    "name": "alpha",
                    "train": {"files": ["/data/a.csv", "/data/b.csv"]},
                    "simulate": {
                        "sample_size": 1234,
                        "model_id": "m1",
                        "synthetic_data_file_format": "parquet",
                    },
                    "evaluate": {
                        "real_data": ["/data/a.csv"],
                        "simulation_id": "s1",
                        "model_id": "m1",
                    },
                    "config": {
                        "rules_config": "/cfg/rules.yaml",
                        "mostly_ai": {"epochs": 5},
                        "general": {"csv_delimiter": ";"},
                    },
                }
            ]
        },
    )
    parsed = load_pipeline_config(str(cfg))

    assert len(parsed.jobs) == 1
    job = parsed.jobs[0]
    assert job.name == "alpha"
    assert job.train is not None and job.train.files == ["/data/a.csv", "/data/b.csv"]
    assert job.simulate is not None
    assert job.simulate.sample_size == 1234 and job.simulate.model_id == "m1"
    assert job.simulate.synthetic_data_file_format == "parquet"
    assert job.evaluate is not None
    assert job.evaluate.real_data == ["/data/a.csv"]
    assert job.evaluate.simulation_id == "s1" and job.evaluate.model_id == "m1"
    assert job.config is not None
    assert job.config.rules_config == "/cfg/rules.yaml"
    assert job.config.mostly_ai == {"epochs": 5}
    assert job.config.general == {"csv_delimiter": ";"}


def test_simulate_defaults_use_sample_size_and_no_model_id(tmp_path: Path) -> None:
    cfg = _write_yaml(
        tmp_path / "p.yaml",
        {"jobs": [{"name": "j", "simulate": {}}]},
    )
    parsed = load_pipeline_config(str(cfg))
    sim = parsed.jobs[0].simulate
    assert sim is not None
    assert sim.sample_size == DEFAULT_SAMPLE_SIZE
    assert sim.model_id is None
    assert sim.synthetic_data_file_format is None


def test_missing_step_keys_default_to_none(tmp_path: Path) -> None:
    cfg = _write_yaml(
        tmp_path / "p.yaml",
        {"jobs": [{"name": "only-train", "train": {"files": ["/x.csv"]}}]},
    )
    job = load_pipeline_config(str(cfg)).jobs[0]
    assert job.simulate is None
    assert job.evaluate is None
    assert job.config is None


def test_default_job_name_is_assigned_when_missing(tmp_path: Path) -> None:
    cfg = _write_yaml(
        tmp_path / "p.yaml",
        {"jobs": [{"train": {"files": ["/x.csv"]}}, {"train": {"files": ["/y.csv"]}}]},
    )
    parsed = load_pipeline_config(str(cfg))
    assert [job.name for job in parsed.jobs] == ["job_1", "job_2"]


def test_train_files_is_expanded_when_single_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "a.csv").write_text("x")
    (data_dir / "b.csv").write_text("y")

    cfg = _write_yaml(
        tmp_path / "p.yaml",
        {"jobs": [{"name": "j", "train": {"files": [str(data_dir)]}}]},
    )

    import backend.src.pipeline.loader as loader_module

    monkeypatch.setattr(
        loader_module,
        "get_files_from_directory",
        lambda d: [f"{d}/a.csv", f"{d}/b.csv"],
    )

    job = load_pipeline_config(str(cfg)).jobs[0]
    assert job.train is not None
    assert job.train.files == [f"{data_dir}/a.csv", f"{data_dir}/b.csv"]


def test_train_files_list_with_multiple_paths_is_left_untouched(tmp_path: Path) -> None:
    a = tmp_path / "a.csv"
    a.write_text("x")
    b = tmp_path / "b.csv"
    b.write_text("y")
    cfg = _write_yaml(
        tmp_path / "p.yaml",
        {"jobs": [{"name": "j", "train": {"files": [str(a), str(b)]}}]},
    )
    job = load_pipeline_config(str(cfg)).jobs[0]
    assert job.train is not None and job.train.files == [str(a), str(b)]
