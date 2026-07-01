"""High-level evaluation orchestration: load → preprocess → run → track.

``run_evaluation`` is the single function called by both the CLI
(``python -m src.evaluation``) and the in-process branch of the pipeline.
It loads real and synthetic CSVs, harmonises their schemas, runs every
configured metric via ``EvaluationRunner``, and persists the report through
``EvaluationTracker``.
"""

import os
from pathlib import Path

import pandas as pd

from backend.src.domain.evaluation.reporting.report_artifacts import (
    build_report_data,
    generate_combined_report_artifacts,
    load_json,
)
from backend.src.domain.evaluation.runner import EvaluationRunner
from backend.src.domain.evaluation.table_settings import (
    TableEvalSettings,
    build_table_settings,
)
from backend.src.domain.evaluation.utils import align_datasets_structure_and_types
from backend.src.domain.loader import FileDataLoader
from backend.src.domain.preprocessing.preprocessor import DataPreprocessor
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import ProfilerPhase
from backend.src.infrastructure.time_profiling import profiler
from backend.src.runs.tracking import EvaluationTracker

logger = get_logger(__name__)


def _resolve_table_settings(
    requested: list[dict] | None,
    real_data: dict[str, pd.DataFrame],
    synthetic_data: dict[str, pd.DataFrame],
) -> list[TableEvalSettings]:
    """Resolve the effective per-table settings.

    Each request entry is ``{"table": str, "config": dict | None}`` where
    ``config`` is a full evaluation-config object (``evaluation.yaml`` shape).
    Keeps only tables present in both datasets; per-table settings fall back to
    the global config for any omitted key. Defaults to the first available table
    with global settings when the request is empty or invalid.
    """
    available = [name for name in real_data if name in synthetic_data]
    if not available:
        raise ValueError("No common tables between real and synthetic datasets.")

    requested = requested or [{"table": available[0]}]
    resolved: list[TableEvalSettings] = []
    for cfg in requested:
        table = cfg.get("table")
        if table not in available:
            logger.warning("Requested table '%s' not available (%s); skipping.", table, available)
            continue
        resolved.append(build_table_settings(table, cfg.get("config")))

    if not resolved:
        logger.warning("No valid requested tables; evaluating first table '%s'.", available[0])
        resolved = [build_table_settings(available[0], None)]
    return resolved


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
    table_configs: list[dict] | None = None,
) -> pd.DataFrame:
    """Load both datasets, evaluate them per selected table, and write all outputs.

    The evaluation is single-table (synthcity operates on one table at a time):
    each entry in ``table_configs`` is evaluated independently with its own
    metrics / TSTR target / sensitive columns / quasi-identifiers, and gets its
    own report under ``<eval_dir>/tables/<table>/``. Defaults to the first
    available table with global settings when none are requested.

    Args:
        real_data_files_path (list[str]): Paths to the real-data CSV files.
        synthetic_files_path (list[str]): Paths to the synthetic CSV files.
        eval_dir (str): Directory where evaluation outputs are written.
        model_id (str | None): Parent model ID, recorded on the eval card.
        simulation_id (str | None): Parent simulation ID, recorded on the eval card.
        metadata_path (str | None): Path to ``metadata.json`` for ID columns.
        table_configs (list[dict] | None): Per-table evaluation configs.

    Returns:
        pd.DataFrame: The evaluation report of the last evaluated table.
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

        settings = _resolve_table_settings(table_configs, cured_real, cured_synthetic)
        tables = [s.table for s in settings]
        logger.info("Evaluating tables: %s", tables)

        report = pd.DataFrame()
        with EvaluationTracker(
            simulation_id=simulation_id or "unknown",
            model_id=model_id or "unknown",
            pipeline_id=pipeline_id,
            job_name=job_name or "",
            evaluation_id=evaluation_id,
            training_parameters=training_parameters,
            evaluation_parameters={
                "target_column": settings[0].target_column,
                "task_type": settings[0].task_type,
            },
            evaluated_tables=tables,
        ) as tracker:
            eval_card = load_json(Path(tracker.card_path))
            # The card on disk is still "in_progress" (it's finalized on tracker
            # exit, after this loop). Per-table reports are generated here, once
            # their metrics have finished, so stamp them "completed" — otherwise
            # every report shows a stale in-progress banner.
            eval_card["status"] = "completed"
            # Per-table metrics still run independently (synthcity is single-table),
            # but instead of one HTML report per table we collect each table's
            # structured report data and emit a single unified report at the eval
            # root: headline scores are the per-axis mean across tables, and the
            # per-metric detail is switchable by table from a dropdown.
            per_table_report_data: dict[str, dict] = {}
            for table_settings in settings:
                table = table_settings.table
                table_dir = os.path.join(eval_dir, "tables", table)
                os.makedirs(table_dir, exist_ok=True)
                runner = EvaluationRunner(
                    eval_results_dir=table_dir, metrics=table_settings.metrics
                )
                with profiler.phase(ProfilerPhase.RUN_METRICS):
                    report = runner.run(
                        real_data_dict=cured_real,
                        synthetic_data_dict=cured_synthetic,
                        metadata_path=metadata_path,
                        settings=table_settings,
                    )

                assert not report.empty, f"Evaluation report for table '{table}' is empty."
                with profiler.phase(ProfilerPhase.SAVE_REPORT):
                    tracker.save_report(report, output_dir=table_dir)
                per_table_report_data[table] = build_report_data(
                    Path(table_dir),
                    eval_card=eval_card,
                    evaluated_table=table,
                    base_dir=Path(eval_dir),
                    evaluation_parameters={
                        "target_column": table_settings.target_column,
                        "task_type": table_settings.task_type,
                    },
                )

            generate_combined_report_artifacts(Path(eval_dir), per_table_report_data)

        return report
    finally:
        from backend.src.config.general import TIME_PROFILING_REPORT_FILENAME

        timing_report_path = os.path.join(eval_dir, TIME_PROFILING_REPORT_FILENAME)
        profiler.report("Evaluation timing breakdown", output_path=timing_report_path)
