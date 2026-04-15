"""CLI entry point for the evaluation stage.

Two ways to invoke:

- ``make eval`` reads ``execution_config.simulation_id`` and resolves all
  paths from the simulation card, then runs the evaluation.
- ``python -m src.evaluation --real-data ... --synthetic-data ... --eval-dir ...``
  runs against explicit paths; this is what the pipeline launches as a
  subprocess in the ``.venv_eval`` interpreter.

Both modes converge on ``run_evaluation``.
"""

import argparse
import os
import sys

from config.execution_config import get_execution_config

from src.core.errors import (
    DataSourceNotFoundError,
    ModelCardNotFoundError,
    SimCardNotFoundError,
    SimulationNotFoundError,
)
from src.core.list_available_simulations import resolve_simulation_inputs
from src.core.logging_config import get_logger, log_run_header
from src.evaluation.orchestrator import run_evaluation
from src.evaluation.utils import setup_synthcity_environment

logger = get_logger(__name__)


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser shared by both invocation modes."""
    parser = argparse.ArgumentParser(description="Run synthetic data evaluation.")
    parser.add_argument("--real-data", nargs="+", help="Paths to real data files.")
    parser.add_argument("--synthetic-data", nargs="+", help="Paths to synthetic data files.")
    parser.add_argument("--eval-dir", help="Directory where evaluation results are saved.")
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--simulation-id", default=None)
    parser.add_argument(
        "--simulation-dir",
        default=None,
        help="Simulation root directory (for synthcity environment setup).",
    )
    return parser


def _run_with_explicit_paths(args: argparse.Namespace) -> None:
    """Subprocess mode: paths are passed by the pipeline."""
    if args.simulation_dir:
        setup_synthcity_environment(args.simulation_dir)
    os.makedirs(args.eval_dir, exist_ok=True)

    run_evaluation(
        real_data_files_path=args.real_data,
        synthetic_files_path=args.synthetic_data,
        eval_dir=args.eval_dir,
        model_id=args.model_id,
        simulation_id=args.simulation_id,
    )


def _run_from_execution_config() -> None:
    """``make eval`` mode: resolve everything from ``execution_config.simulation_id``."""
    execution_config = get_execution_config()
    if not execution_config.simulation_id:
        sys.exit(
            "SIMULATION_ID is not set in config/execution_config.py. "
            "Discover available IDs with: "
            "python -m src.core.list_available_simulations --format table"
        )

    try:
        inputs = resolve_simulation_inputs(execution_config.simulation_id)
    except (
        SimulationNotFoundError,
        SimCardNotFoundError,
        ModelCardNotFoundError,
        DataSourceNotFoundError,
    ) as exc:
        logger.error("Failed to resolve simulation inputs: %s", exc)
        sys.exit(1)

    log_run_header(
        logger,
        "e",
        subtitle="comparing synthetic vs real",
        simulation_id=inputs.simulation_id,
        model_id=inputs.model_id,
        real_data=inputs.real_data_files,
        synthetic_data=inputs.synthetic_files,
    )

    eval_dir = os.path.join(inputs.simulation_dir, "evaluation")
    setup_synthcity_environment(inputs.simulation_dir)

    metadata_path = inputs.metadata_path if os.path.exists(inputs.metadata_path) else None

    try:
        run_evaluation(
            real_data_files_path=inputs.real_data_files,
            synthetic_files_path=inputs.synthetic_files,
            eval_dir=eval_dir,
            model_id=inputs.model_id,
            simulation_id=inputs.simulation_id,
            metadata_path=metadata_path,
        )
    except KeyboardInterrupt:
        logger.info("Evaluation interrupted by user.")


def main() -> None:
    """Dispatch on whether explicit CLI paths were provided."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    explicit = bool(args.real_data and args.synthetic_data and args.eval_dir)
    if explicit:
        _run_with_explicit_paths(args)
    else:
        _run_from_execution_config()


if __name__ == "__main__":
    main()
