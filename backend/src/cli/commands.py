"""Command handlers behind the backend CLI."""

from __future__ import annotations

import os

from backend.src.cli.summaries import print_run_summary
from backend.src.config.general import DEFAULT_CSV_DELIMITER, ENABLE_DATA_PROFILING
from backend.src.core.logging_config import get_logger, log_run_header
from backend.src.core.time_profiling import profiler
from backend.src.services.artifacts import load_generator_artifacts
from backend.src.services.configs import resolve_config_path
from backend.src.services.inspection import run_inspection_flow
from backend.src.services.simulation import run_simulation_flow
from backend.src.services.training import run_training_flow, run_training_flow_from_inspection

logger = get_logger(__name__)


def run_workflow(
    mode: str,
    file_paths: list[str] | None,
    sample_size: int | None = None,
    model_id: str | None = None,
    inspection_id: str | None = None,
) -> None:
    """Run a single inspect, train, or simulation workflow."""
    generator = None
    metadata = None
    rule_manager = None
    resolved_model_id = None

    if mode == "i":
        log_run_header(
            logger,
            mode,
            subtitle="autodetect only, no training",
            files=len(file_paths or []),
            file_paths=file_paths or [],
        )
        result = run_inspection_flow(
            file_paths=file_paths or [],
            mostly_config_path=str(resolve_config_path("mostly_ai")),
            rules_config_path=str(resolve_config_path("rules")),
            enable_data_profiling=ENABLE_DATA_PROFILING,
            csv_delimiter=DEFAULT_CSV_DELIMITER,
        )
        if result is None:
            logger.error("Inspection flow failed.")
            return
        logger.info(
            "Inspection ready at '%s'.\n"
            "  Review / edit: inspection_metadata.json  "
            "(source of truth for PKs, FKs, encoding types)\n"
            "  To assign a custom name, edit the 'inspection_name' field in inspection_card.json.\n"
            "  To train: use --inspection-id %s and --mode t",
            result.output_directory,
            result.inspection_id,
        )
        print_run_summary("i", result.inspection_id, result.output_directory)
        return

    if mode == "t":
        if inspection_id:
            log_run_header(
                logger,
                mode,
                subtitle="resuming from inspection",
                inspection_id=inspection_id,
                sample_size=sample_size,
            )
            with profiler.phase("train (from inspection)"):
                resolved_model_id, generator, metadata, rule_manager = (
                    run_training_flow_from_inspection(inspection_id=inspection_id)
                )
        else:
            log_run_header(
                logger,
                mode,
                subtitle="from raw files (no inspection)",
                files=len(file_paths or []),
                file_paths=file_paths or [],
                sample_size=sample_size,
            )
            with profiler.phase("train"):
                resolved_model_id, generator, metadata, rule_manager = run_training_flow(
                    file_paths=file_paths,
                    mostly_config_path=str(resolve_config_path("mostly_ai")),
                    rules_config_path=str(resolve_config_path("rules")),
                    enable_data_profiling=ENABLE_DATA_PROFILING,
                    csv_delimiter=DEFAULT_CSV_DELIMITER,
                )

        if not resolved_model_id:
            logger.error("Training flow failed to produce a model. Exiting.")
            return

        print_run_summary(
            "t", resolved_model_id, os.path.join("backend/outputs/models", resolved_model_id)
        )

        if sample_size is None:
            logger.info("Entrenamiento finalizado. No sample_size provided for simulation.")
            return

    if mode == "s":
        if not model_id:
            raise ValueError("model_id is required for simulation mode ('s'). Use --model-id.")

        log_run_header(
            logger,
            mode,
            subtitle="loading existing model",
            model_id=model_id,
            sample_size=sample_size,
        )
        try:
            with profiler.phase("load generator artifacts"):
                generator, metadata, rule_manager = load_generator_artifacts(
                    model_id=model_id, mostly_config_path=str(resolve_config_path("mostly_ai"))
                )
            resolved_model_id = model_id
        except Exception as exc:
            logger.error("Failed to initialize artifacts for simulation mode: %s", exc)
            return

    if generator and metadata and rule_manager and resolved_model_id:
        with profiler.phase("simulate"):
            simulation_id = run_simulation_flow(
                generator=generator,
                metadata=metadata,
                rule_manager=rule_manager,
                model_id=resolved_model_id,
                sample_size=sample_size,
                mostly_config_path=str(resolve_config_path("mostly_ai")),
            )
        if simulation_id:
            print_run_summary(
                "s", simulation_id, os.path.join("backend/outputs/simulations", simulation_id)
            )
        else:
            logger.error("Simulation flow execution failed.")
