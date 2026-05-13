"""Synthetic data pipeline execution module.

This module provides the functional orchestration to run the standard
pipelines defined in YAML config files.
"""

from backend.src.domain.pipeline.config_classes import PipelineConfig
from backend.src.domain.pipeline.executor import run_pipeline
from backend.src.domain.pipeline.loader import load_pipeline_config

__all__ = [
    "run_pipeline",
    "load_pipeline_config",
    "PipelineConfig",
]
