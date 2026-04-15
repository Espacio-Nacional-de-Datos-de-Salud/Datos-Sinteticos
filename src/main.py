"""Entry point for synthetic data generation with train/simulation mode.

Orchestrates the full flow: data loading, preprocessing, model training,
and synthetic data generation. Supports two execution modes:

- 'train': Processes raw data, extracts metadata, trains the model with Mostly AI,
    and saves artifacts (generator, metadata, rules).
- 'simulation': Loads a trained generator, generates new synthetic data, and applies
    post-processing through logical rules.

"""

import os
import sys

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from config.execution_config import get_execution_config
from config.general_config import (
    DEFAULT_CSV_DELIMITER,
    ENABLE_DATA_PROFILING,
    MOSTLYAI_CONFIG_PATH,
    RULES_CONFIG_PATH,
)

from src.core.logging_config import get_logger, log_run_header
from src.services.artifacts import load_generator_artifacts
from src.services.inspection import run_inspection_flow
from src.services.simulation import run_simulation_flow
from src.services.training import run_training_flow, run_training_flow_from_inspection

logger = get_logger(__name__)


def main(
    mode: str,
    file_paths: list[str] | None,
    sample_size: int | None = None,
    model_id: str | None = None,
    inspection_id: str | None = None,
) -> None:
    """Runs the full training and/or synthetic data generation pipeline.

    Orchestrates the entire process: inspects raw data (mode 'i'), trains a
    model (mode 't') or loads an existing one (mode 's'), and runs simulation
    to generate synthetic data with validations.

    Args:
        mode (str): Execution mode: 'i' for inspect, 't' for train, 's' for simulation.
        file_paths (list[str] | None): Paths to CSV/Excel/Parquet files to process.
            Applies in inspect and (raw) train modes.
        sample_size (int | None): Number of synthetic records to generate.
            Defaults to None (train-only, no simulation after training).
        model_id (str | None): Model identifier for simulation mode.
            Required when mode is 's'.
        inspection_id (str | None): When set in train mode, training consumes the
            inspection session instead of re-running preprocessing on raw files.
    """
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
            mostly_config_path=MOSTLYAI_CONFIG_PATH,
            rules_config_path=RULES_CONFIG_PATH,
            enable_data_profiling=ENABLE_DATA_PROFILING,
            csv_delimiter=DEFAULT_CSV_DELIMITER,
        )
        if result is None:
            logger.error("Inspection flow failed.")
            return
        logger.info(
            "Inspection ready at '%s'.\n"
            "  Review / edit: autodetect.json  (source of truth for PKs, FKs, encoding types)\n"
            "  To assign a custom name, edit the 'inspection_name' field in inspection_card.json.\n"
            "  To train: set INSPECTION_ID='%s' + EXECUTION_MODE='t' in"
            " config/execution_config.py, then execute the tool.",
            result.output_directory,
            result.inspection_id,
        )
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
            resolved_model_id, generator, metadata, rule_manager = run_training_flow(
                file_paths=file_paths,
                mostly_config_path=MOSTLYAI_CONFIG_PATH,
                rules_config_path=RULES_CONFIG_PATH,
                enable_data_profiling=ENABLE_DATA_PROFILING,
                csv_delimiter=DEFAULT_CSV_DELIMITER,
            )

        if not resolved_model_id:
            logger.error("Training flow failed to produce a model. Exiting.")
            return

        if sample_size is None:
            logger.info("Entrenamiento finalizado. No sample_size provided for simulation.")
            return

    if mode == "s":
        if not model_id:
            raise ValueError("model_id is required for simulation mode ('s').")

        log_run_header(
            logger,
            mode,
            subtitle="loading existing model",
            model_id=model_id,
            sample_size=sample_size,
        )
        try:
            generator, metadata, rule_manager = load_generator_artifacts(
                model_id=model_id, mostly_config_path=MOSTLYAI_CONFIG_PATH
            )
            resolved_model_id = model_id
        except Exception as e:
            logger.error("Failed to initialize artifacts for simulation mode: %s", e)
            return

    if generator and metadata and rule_manager and resolved_model_id:
        simulation_id = run_simulation_flow(
            generator=generator,
            metadata=metadata,
            rule_manager=rule_manager,
            model_id=resolved_model_id,
            sample_size=sample_size,
            mostly_config_path=MOSTLYAI_CONFIG_PATH,
        )
        if not simulation_id:
            logger.error("Simulation flow execution failed.")


if __name__ == "__main__":
    execution_config = get_execution_config()

    try:
        main(
            mode=execution_config.mode,
            file_paths=execution_config.file_paths,
            sample_size=execution_config.sample_size,
            model_id=execution_config.model_id,
            inspection_id=execution_config.inspection_id,
        )
    except KeyboardInterrupt:
        logger.info("Herramienta interrumpida por el usuario.")
