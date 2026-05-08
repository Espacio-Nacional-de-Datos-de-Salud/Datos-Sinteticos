"""Evaluation package: runner + the high-level ``run_evaluation`` orchestration."""

from backend.src.evaluation.orchestrator import run_evaluation
from backend.src.evaluation.runner import EvaluationRunner

__all__ = ["EvaluationRunner", "run_evaluation"]
