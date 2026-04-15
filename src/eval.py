"""Standalone evaluation entry point.

Runs the evaluation stage in isolation against an existing simulation,
comparing synthetic data to real data using the fidelity, privacy, and
detection metrics configured in ``config/evaluation/evaluation_config.py``.

Expects the evaluation-specific virtual environment (``.venv_eval``) since
it depends on heavy packages (``synthcity``, ``torch``) that are not part
of the core training environment.

Usage:
    make eval                           # reads parameters from execution_config
    .venv_eval/bin/python -m src.eval   # equivalent direct invocation
"""

import os
import sys

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from config.evaluation.evaluation_config import TSTR_TARGET_COLUMN, TSTR_TASK_TYPE
from config.execution_config import get_execution_config

from src.core.errors import (
    DataSourceNotFoundError,
    ModelCardNotFoundError,
    SimCardNotFoundError,
    SimulationNotFoundError,
)
from src.core.list_available_simulations import resolve_simulation_inputs
from src.core.loader import FileDataLoader
from src.core.logging_config import get_logger, log_run_header
from src.core.preprocessing.preprocessor import DataPreprocessor
from src.evaluation.abstract_evaluation_engine import AbstractEvaluationEngine
from src.evaluation.mlflow_evaluation_engine import MLflowEvaluationEngine
from src.evaluation.utils import align_datasets_structure_and_types, setup_synthcity_environment

logger = get_logger(__name__)


def main_eval(
    real_data_files_path: list[str],
    synthetic_files_path: list[str],
    evaluator: AbstractEvaluationEngine,
    model_id: str | None = None,
    simulation_id: str | None = None,
    metadata_path: str | None = None,
) -> pd.DataFrame:
    """Runs the complete evaluation of synthetic data against real data.

    Loads real and synthetic data, preprocesses them, aligns their structures and types,
    runs evaluation using the provided engine, and saves the results.

    Args:
        real_data_files_path (list[str]): List of real-data file paths.
        synthetic_files_path (list[str]): List of synthetic-data file paths.
        eval_dir (str): Directory where evaluation results will be saved.
        evaluator (AbstractEvaluationEngine): Evaluation engine used to run
            the metrics.
        model_id (str | None): Model ID.
        simulation_id (str | None): Simulation ID.
        metadata_path (str | None): Path to the metadata.json file.

    Returns:
        pd.DataFrame: DataFrame with evaluation results.

    Raises:
        AssertionError: If the evaluation report is empty.
    """
    data_loader = FileDataLoader()
    raw_real = data_loader.load(real_data_files_path)
    raw_synthetic = data_loader.load(synthetic_files_path)

    processed_real, _, _, _ = DataPreprocessor(raw_real).run(run_data_profiling=False)
    processed_synthetic, _, _, _ = DataPreprocessor(raw_synthetic).run(run_data_profiling=False)

    cured_real, cured_synthetic = align_datasets_structure_and_types(
        processed_real, processed_synthetic
    )

    eval_report = evaluator.run(
        real_data_dict=cured_real,
        synthetic_data_dict=cured_synthetic,
        target_column=TSTR_TARGET_COLUMN,
        task_type=TSTR_TASK_TYPE,
        model_id=model_id,
        simulation_id=simulation_id,
        metadata_path=metadata_path,
    )

    assert not eval_report.empty, "El reporte de evaluación está vacío."

    return


if __name__ == "__main__":
    execution_config = get_execution_config()

    if not execution_config.simulation_id:
        sys.exit(
            "SIMULATION_ID is not set in config/execution_config.py. "
            "Discover available IDs with: "
            "python -m src.core.list_available_simulations --format table"
        )

    try:
        resolved_simulation_inputs = resolve_simulation_inputs(execution_config.simulation_id)
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
        simulation_id=resolved_simulation_inputs.simulation_id,
        model_id=resolved_simulation_inputs.model_id,
        real_data=resolved_simulation_inputs.real_data_files,
        synthetic_data=resolved_simulation_inputs.synthetic_files,
    )

    eval_dir = os.path.join(resolved_simulation_inputs.simulation_dir, "evaluation")
    os.makedirs(eval_dir, exist_ok=True)

    setup_synthcity_environment(resolved_simulation_inputs.simulation_dir)

    evaluator = MLflowEvaluationEngine(eval_results_dir=eval_dir)

    metadata_path = (
        resolved_simulation_inputs.metadata_path
        if os.path.exists(resolved_simulation_inputs.metadata_path)
        else None
    )

    try:
        main_eval(
            real_data_files_path=resolved_simulation_inputs.real_data_files,
            synthetic_files_path=resolved_simulation_inputs.synthetic_files,
            evaluator=evaluator,
            model_id=resolved_simulation_inputs.model_id,
            simulation_id=resolved_simulation_inputs.simulation_id,
            metadata_path=metadata_path,
        )
    except KeyboardInterrupt:
        logger.info("Evaluation interrupted by user.")
