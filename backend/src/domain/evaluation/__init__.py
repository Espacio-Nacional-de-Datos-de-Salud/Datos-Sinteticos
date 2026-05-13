"""Evaluation package: runner + the high-level ``run_evaluation`` orchestration."""

from backend.src.domain.evaluation.orchestrator import run_evaluation
from backend.src.domain.evaluation.runner import EvaluationRunner

__all__ = ["EvaluationRunner", "run_evaluation"]
