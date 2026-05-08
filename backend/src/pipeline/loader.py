"""Configuration loader for the synthetic data pipeline."""

import os
from pathlib import Path

import yaml
from backend.src.config.general import DEFAULT_SAMPLE_SIZE
from backend.src.pipeline.config_classes import (
    EvaluateStepConfig,
    JobConfigOverrides,
    PipelineConfig,
    PipelineJobConfig,
    SimulateStepConfig,
    TrainStepConfig,
)
from backend.src.services.files import get_files_from_directory

# Repository roots used to resolve relative paths in pipeline YAMLs.
# Authors typically write ``data/foo.csv`` or ``config/...`` expecting those to
# be evaluated from the backend folder (where the CLI was traditionally run).
# When the API server starts from the project root, those literal paths break
# because CWD differs. We accept either — see ``_resolve_relative_path``.
_BACKEND_ROOT = Path(__file__).resolve().parents[2]  # .../backend
_PROJECT_ROOT = _BACKEND_ROOT.parent


def _resolve_relative_path(raw: str) -> str:
    """Best-effort absolutize a path read from a pipeline YAML.

    Args:
        raw (str): A file path that may be relative or absolute.

    Returns:
        str: The original string when it's already absolute or already exists
            relative to CWD. Otherwise tries the backend folder, then the project
            root. If nothing matches, returns the original — downstream code will
            surface the FileNotFoundError with the user's literal path so the message
            stays familiar.
    """
    if not raw or os.path.isabs(raw):
        return raw
    if os.path.exists(raw):
        return raw
    for base in (_BACKEND_ROOT, _PROJECT_ROOT):
        candidate = base / raw
        if candidate.exists():
            return str(candidate)
    return raw


def load_pipeline_config(config_path: str) -> PipelineConfig:
    """Load and parse a pipeline configuration YAML file.

    Args:
        config_path (str): Path to the YAML pipeline configuration file.

    Returns:
        PipelineConfig: Parsed pipeline configuration.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the config is missing the required top-level 'jobs' key.

    Example:
        >>> config = load_pipeline_config("config/pipelines/my_pipeline.yaml")
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Pipeline config not found: {config_path}")

    with open(config_path, encoding="utf-8") as file_handle:
        raw = yaml.safe_load(file_handle)

    if not isinstance(raw, dict) or "jobs" not in raw:
        raise ValueError("Pipeline config must have a top-level 'jobs' key.")

    jobs: list[PipelineJobConfig] = []
    for raw_job in raw["jobs"]:
        train_config = None
        simulate_config = None
        evaluate_config = None

        if "train" in raw_job:
            raw_train = raw_job["train"]
            files = [_resolve_relative_path(f) for f in raw_train.get("files", [])]
            if len(files) == 1 and os.path.isdir(files[0]):
                files = get_files_from_directory(files[0])
            train_config = TrainStepConfig(
                files=files,
                inspection_id=raw_train.get("inspection_id"),
            )

        if "simulate" in raw_job:
            raw_sim = raw_job["simulate"]
            simulate_config = SimulateStepConfig(
                sample_size=raw_sim.get("sample_size", DEFAULT_SAMPLE_SIZE),
                model_id=raw_sim.get("model_id"),
                synthetic_data_file_format=raw_sim.get("synthetic_data_file_format"),
            )

        if "evaluate" in raw_job:
            raw_eval = raw_job["evaluate"]
            real_data = None
            if "real_data" in raw_eval:
                real_data = [_resolve_relative_path(f) for f in raw_eval["real_data"]]
            evaluate_config = EvaluateStepConfig(
                real_data=real_data,
                simulation_id=raw_eval.get("simulation_id"),
                model_id=raw_eval.get("model_id"),
            )

        job_config_overrides = None
        if "config" in raw_job:
            raw_cfg = raw_job["config"]
            rules_cfg = raw_cfg.get("rules_config")
            job_config_overrides = JobConfigOverrides(
                rules_config=_resolve_relative_path(rules_cfg) if rules_cfg else None,
                mostly_ai=raw_cfg.get("mostly_ai"),
                general=raw_cfg.get("general"),
            )

        jobs.append(
            PipelineJobConfig(
                name=raw_job.get("name", f"job_{len(jobs) + 1}"),
                config=job_config_overrides,
                train=train_config,
                simulate=simulate_config,
                evaluate=evaluate_config,
            )
        )

    return PipelineConfig(jobs=jobs)
