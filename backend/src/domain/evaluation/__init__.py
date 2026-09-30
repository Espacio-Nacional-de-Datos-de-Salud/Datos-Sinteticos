"""Evaluation package public API.

The heavy evaluation dependencies live behind lazy imports so lightweight
submodules (for example custom metrics) can be imported without loading
SynthCity and the full orchestration stack.
"""

__all__ = ["EvaluationRunner", "run_evaluation"]


def __getattr__(name: str):
    if name == "EvaluationRunner":
        from backend.src.domain.evaluation.runner import EvaluationRunner

        return EvaluationRunner
    if name == "run_evaluation":
        from backend.src.domain.evaluation.orchestrator import run_evaluation

        return run_evaluation
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
