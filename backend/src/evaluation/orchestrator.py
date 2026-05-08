"""High-level evaluation orchestration: load → preprocess → run → track.

``run_evaluation`` is the single function called by both the CLI
(``python -m src.evaluation``) and the in-process branch of the pipeline.
It loads real and synthetic CSVs, harmonises their schemas, runs every
configured metric via ``EvaluationRunner``, and persists the report through
``EvaluationTracker`` (which also pushes metrics to the parent simulation's
MLflow run).
"""

import pandas as pd
from backend.src.config.evaluation import TSTR_TARGET_COLUMN, TSTR_TASK_TYPE
from backend.src.core.loader import FileDataLoader
from backend.src.core.logging_config import get_logger
from backend.src.core.preprocessing.preprocessor import DataPreprocessor
from backend.src.core.time_profiling import profiler
from backend.src.core.tracking import EvaluationTracker
from backend.src.evaluation.runner import EvaluationRunner
from backend.src.evaluation.utils import align_datasets_structure_and_types

logger = get_logger(__name__)


def run_evaluation(
    real_data_files_path: list[str],
    synthetic_files_path: list[str],
    eval_dir: str,
    model_id: str | None = None,
    simulation_id: str | None = None,
    evaluation_id: str | None = None,
    pipeline_id: str = "none",
    job_name: str | None = None,
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
    try:
        data_loader = FileDataLoader()
        with profiler.phase("load real data"):
            raw_real = data_loader.load(real_data_files_path)
        with profiler.phase("load synthetic data"):
            raw_synthetic = data_loader.load(synthetic_files_path)

        with profiler.phase("preprocess real data"):
            processed_real = DataPreprocessor(raw_real).run(run_data_profiling=False).processed_data
        with profiler.phase("preprocess synthetic data"):
            processed_synthetic = (
                DataPreprocessor(raw_synthetic).run(run_data_profiling=False).processed_data
            )

        with profiler.phase("align datasets"):
            cured_real, cured_synthetic = align_datasets_structure_and_types(
                processed_real, processed_synthetic
            )

        with EvaluationTracker(
            simulation_id=simulation_id or "unknown",
            model_id=model_id or "unknown",
            pipeline_id=pipeline_id,
            job_name=job_name or "",
            evaluation_id=evaluation_id,
        ) as tracker:
            runner = EvaluationRunner(eval_results_dir=eval_dir)
            with profiler.phase("run metrics"):
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

            assert not report.empty, "Evaluation report is empty."
            with profiler.phase("save report"):
                tracker.save_report(report)

        return report
    finally:
        import os

        from backend.src.config.general import TIME_PROFILING_REPORT_FILENAME

        timing_report_path = os.path.join(eval_dir, TIME_PROFILING_REPORT_FILENAME)
        profiler.report("Evaluation timing breakdown", output_path=timing_report_path)
