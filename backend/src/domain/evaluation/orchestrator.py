"""High-level evaluation orchestration: load → preprocess → run → track.

``run_evaluation`` is the single function called by both the CLI
(``python -m src.evaluation``) and the in-process branch of the pipeline.
It loads real and synthetic CSVs, harmonises their schemas, runs every
configured metric via ``EvaluationRunner``, and persists the report through
``EvaluationTracker``.
"""

import pandas as pd

from backend.src.config.evaluation import TSTR_TARGET_COLUMN, TSTR_TASK_TYPE
from backend.src.domain.evaluation.runner import EvaluationRunner
from backend.src.domain.evaluation.utils import align_datasets_structure_and_types
from backend.src.domain.loader import FileDataLoader
from backend.src.domain.preprocessing.preprocessor import DataPreprocessor
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import ProfilerPhase
from backend.src.infrastructure.time_profiling import profiler
from backend.src.runs.tracking import EvaluationTracker

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
    training_parameters: dict | None = None,
) -> pd.DataFrame:
    """Load both datasets, evaluate them, and write all outputs.

    Args:
        real_data_files_path (list[str]): Paths to the real-data CSV files.
        synthetic_files_path (list[str]): Paths to the synthetic CSV files.
        eval_dir (str): Directory where evaluation outputs are written.
        model_id (str | None): Parent model ID, recorded on the eval card.
        simulation_id (str | None): Parent simulation ID, recorded on the eval card.
        metadata_path (str | None): Path to ``metadata.json`` for ID columns.

    Returns:
        pd.DataFrame: The evaluation report (also persisted by the tracker).
    """
    try:
        data_loader = FileDataLoader()
        with profiler.phase(ProfilerPhase.LOAD_REAL_DATA):
            raw_real = data_loader.load(real_data_files_path)
        with profiler.phase(ProfilerPhase.LOAD_SYNTHETIC_DATA):
            raw_synthetic = data_loader.load(synthetic_files_path)

        with profiler.phase(ProfilerPhase.PREPROCESS_REAL_DATA):
            processed_real = DataPreprocessor(raw_real).run(run_data_profiling=False).processed_data
        with profiler.phase(ProfilerPhase.PREPROCESS_SYNTHETIC_DATA):
            processed_synthetic = (
                DataPreprocessor(raw_synthetic).run(run_data_profiling=False).processed_data
            )

        with profiler.phase(ProfilerPhase.ALIGN_DATASETS):
            cured_real, cured_synthetic = align_datasets_structure_and_types(
                processed_real, processed_synthetic
            )

        with EvaluationTracker(
            simulation_id=simulation_id or "unknown",
            model_id=model_id or "unknown",
            pipeline_id=pipeline_id,
            job_name=job_name or "",
            evaluation_id=evaluation_id,
            training_parameters=training_parameters,
        ) as tracker:
            runner = EvaluationRunner(eval_results_dir=eval_dir)
            with profiler.phase(ProfilerPhase.RUN_METRICS):
                report = runner.run(
                    real_data_dict=cured_real,
                    synthetic_data_dict=cured_synthetic,
                    target_column=TSTR_TARGET_COLUMN,
                    task_type=TSTR_TASK_TYPE,
                    metadata_path=metadata_path,
                )

            assert not report.empty, "Evaluation report is empty."
            with profiler.phase(ProfilerPhase.SAVE_REPORT):
                tracker.save_report(report)

        return report
    finally:
        import os

        from backend.src.config.general import TIME_PROFILING_REPORT_FILENAME

        timing_report_path = os.path.join(eval_dir, TIME_PROFILING_REPORT_FILENAME)
        profiler.report("Evaluation timing breakdown", output_path=timing_report_path)
