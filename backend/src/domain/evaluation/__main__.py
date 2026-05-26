"""CLI entry point for the evaluation stage."""

import argparse
import os
import sys
import json

from backend.src.config.execution import get_execution_config
from backend.src.infrastructure.errors import (
    DataSourceNotFoundError,
    ModelCardNotFoundError,
    SimCardNotFoundError,
    SimulationNotFoundError,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.time_profiling import profiler
from backend.src.domain.evaluation.orchestrator import run_evaluation
from backend.src.domain.evaluation.utils import setup_synthcity_environment

logger = get_logger(__name__)


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the CLI parser shared by both invocation modes."""
    parser = argparse.ArgumentParser(description="Run synthetic data evaluation.")
    parser.add_argument("--real-data", nargs="+", help="Paths to real data files.")
    parser.add_argument("--synthetic-data", nargs="+", help="Paths to synthetic data files.")
    parser.add_argument("--eval-dir", help="Directory where evaluation results are saved.")
    parser.add_argument("--model-id", default=None)
    parser.add_argument("--simulation-id", default=None)
    parser.add_argument("--evaluation-id", default=None)
    parser.add_argument("--pipeline-id", default="none")
    parser.add_argument("--job-name", default=None)
    parser.add_argument("--simulation-dir", default=None, help="Simulation root directory (for synthcity environment setup).")
    parser.add_argument("--training-parameters", default=None, help="JSON string with training parameters used to generate the synthetic data.")
    return parser


def _run_with_explicit_paths(args: argparse.Namespace) -> None:
    """Subprocess mode: paths are passed by the pipeline."""
    if args.simulation_dir:
        setup_synthcity_environment(args.simulation_dir)
    os.makedirs(args.eval_dir, exist_ok=True)

    training_parameters = json.loads(args.training_parameters) if args.training_parameters else None

    run_evaluation(
        real_data_files_path=args.real_data,
        synthetic_files_path=args.synthetic_data,
        eval_dir=args.eval_dir,
        model_id=args.model_id,
        simulation_id=args.simulation_id,
        evaluation_id=args.evaluation_id,
        pipeline_id=args.pipeline_id,
        job_name=args.job_name,
        training_parameters=training_parameters
    )


def _run_from_execution_config(simulation_id: str | None = None) -> None:
    """``make eval`` mode: resolve everything from a simulation_id."""
    execution_config = get_execution_config()
    target_simulation_id = simulation_id or execution_config.simulation_id

    if not target_simulation_id:
        sys.exit(
            "No simulation_id provided. Set it in backend/config/general.yaml or use --simulation-id. "
            "Discover available IDs with: "
            "python -m src.core.catalog.simulations --format table"
        )

    from backend.src.runs.catalog.simulations import resolve_simulation_inputs
    from backend.src.sessions.evaluation import (
        initialize_evaluation_session,
        run_evaluation_flow_from_simulation,
    )

    try:
        inputs = resolve_simulation_inputs(target_simulation_id)
        session = initialize_evaluation_session(
            simulation_id=inputs.simulation_id, model_id=inputs.model_id
        )
        run_evaluation_flow_from_simulation(
            simulation_id=inputs.simulation_id,
            session=session,
        )
    except (
        SimulationNotFoundError,
        SimCardNotFoundError,
        ModelCardNotFoundError,
        DataSourceNotFoundError,
    ) as exc:
        logger.error("Failed to resolve simulation inputs: %s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("Evaluation interrupted by user.")


def main() -> None:
    """Dispatch on whether explicit CLI paths were provided."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    explicit = bool(args.real_data and args.synthetic_data and args.eval_dir)
    try:
        if explicit:
            _run_with_explicit_paths(args)
        else:
            _run_from_execution_config(simulation_id=args.simulation_id)
    finally:
        profiler.report("Evaluation timing breakdown")


if __name__ == "__main__":
    main()
