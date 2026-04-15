"""High-level evaluation orchestration: load → preprocess → run → track.

``run_evaluation`` is the single function called by both the CLI
(``python -m src.evaluation``) and the in-process branch of the pipeline.
It loads real and synthetic CSVs, harmonises their schemas, runs every
configured metric via ``EvaluationRunner``, and persists the report through
``EvaluationTracker`` (which also pushes metrics to the parent simulation's
MLflow run).
"""

import pandas as pd
from config.evaluation.evaluation_config import TSTR_TARGET_COLUMN, TSTR_TASK_TYPE

from src.core.loader import FileDataLoader
from src.core.logging_config import get_logger
from src.core.preprocessing.preprocessor import DataPreprocessor
from src.core.tracking import EvaluationTracker
from src.evaluation.runner import EvaluationRunner
from src.evaluation.utils import align_datasets_structure_and_types

logger = get_logger(__name__)


def run_evaluation(
    real_data_files_path: list[str],
    synthetic_files_path: list[str],
    eval_dir: str,
    model_id: str | None = None,
    simulation_id: str | None = None,
    metadata_path: str | None = None,
) -> pd.DataFrame:
    """Load both datasets, evaluate them, and write all outputs.

    Args:
        real_data_files_path (list[str]): Paths to the real-data CSV files.
        synthetic_files_path (list[str]): Paths to the synthetic CSV files.
        eval_dir (str): Directory where evaluation outputs are written.
        model_id (str | None): Parent model ID, used as MLflow tag.
        simulation_id (str | None): Parent simulation ID; the tracker will
            attach to this MLflow run if found.
        metadata_path (str | None): Path to ``metadata.json`` for ID columns.

    Returns:
        pd.DataFrame: The evaluation report (also persisted by the tracker).
    """
    data_loader = FileDataLoader()
    raw_real = data_loader.load(real_data_files_path)
    raw_synthetic = data_loader.load(synthetic_files_path)

    processed_real, _, _, _ = DataPreprocessor(raw_real).run(run_data_profiling=False)
    processed_synthetic, _, _, _ = DataPreprocessor(raw_synthetic).run(run_data_profiling=False)

    cured_real, cured_synthetic = align_datasets_structure_and_types(
        processed_real, processed_synthetic
    )

    with EvaluationTracker(simulation_id, eval_dir) as tracker:
        runner = EvaluationRunner(eval_results_dir=eval_dir)
        report = runner.run(
            real_data_dict=cured_real,
            synthetic_data_dict=cured_synthetic,
            target_column=TSTR_TARGET_COLUMN,
            task_type=TSTR_TASK_TYPE,
            metadata_path=metadata_path,
        )

        if model_id is not None:
            import mlflow

            mlflow.set_tag("model_id", model_id)

        assert not report.empty, "El reporte de evaluación está vacío."
        tracker.save_report(report)

    return report
