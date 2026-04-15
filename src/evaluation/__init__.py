"""Evaluation package: runner + the high-level ``run_evaluation`` orchestration."""

from src.evaluation.orchestrator import run_evaluation
from src.evaluation.runner import EvaluationRunner

__all__ = ["EvaluationRunner", "run_evaluation"]
