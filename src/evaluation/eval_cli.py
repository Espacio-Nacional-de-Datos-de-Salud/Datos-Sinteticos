"""CLI entry point for running evaluation in an isolated virtual environment.

Called by the pipeline via subprocess when EVAL_PYTHON_PATH is configured,
so that synthcity and its heavy dependencies (torch, opacus, …) are loaded
from ``venv_eval`` without polluting the main environment.

Usage (called automatically by the pipeline):
    /path/to/venv_eval/bin/python -m src.evaluation.eval_cli \
        --real-data data/person.csv \
        --synthetic-data outputs/simulations/sim_001/synthetic_data/person_synthetic.csv \
        --eval-dir outputs/simulations/sim_001/evaluation \
        --model-id model_20260311_120000 \
        --simulation-id simulation_20260311_120000
"""

import argparse
import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.eval import main_eval
from src.evaluation.mlflow_evaluation_engine import MLflowEvaluationEngine
from src.evaluation.utils import setup_synthcity_environment


def main() -> None:
    """Parse CLI arguments and execute evaluation in the evaluation environment.

    Reads input/output paths and optional run identifiers from CLI flags,
    configures the synthcity workspace when requested, and delegates the
    evaluation logic to ``main_eval`` with an ``MLflowEvaluationEngine`` instance.

    Returns:
        None: Runs evaluation side effects and exits.

    Raises:
        SystemExit: Raised by ``argparse`` on invalid CLI usage.

    Example:
        >>> # Called as module entrypoint by the pipeline
        >>> # python -m src.evaluation.eval_cli --real-data a.csv --synthetic-data b.csv --eval-dir out
    """
    parser = argparse.ArgumentParser(description="Run synthetic data evaluation.")
    parser.add_argument(
        "--real-data",
        nargs="+",
        required=True,
        help="Paths to real data files.",
    )
    parser.add_argument(
        "--synthetic-data",
        nargs="+",
        required=True,
        help="Paths to synthetic data files.",
    )
    parser.add_argument(
        "--eval-dir",
        required=True,
        help="Directory where evaluation results are saved.",
    )
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--simulation-id", default=None)
    parser.add_argument(
        "--simulation-dir",
        default=None,
        help="Simulation root directory (for synthcity environment setup).",
    )
    args = parser.parse_args()

    if args.simulation_dir:
        setup_synthcity_environment(args.simulation_dir)

    os.makedirs(args.eval_dir, exist_ok=True)
    evaluator = MLflowEvaluationEngine(eval_results_dir=args.eval_dir)

    main_eval(
        real_data_files_path=args.real_data,
        synthetic_files_path=args.synthetic_data,
        evaluator=evaluator,
        model_id=args.model_id,
        simulation_id=args.simulation_id,
    )


if __name__ == "__main__":
    main()
