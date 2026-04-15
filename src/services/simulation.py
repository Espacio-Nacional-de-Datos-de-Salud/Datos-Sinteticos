"""Simulation flow service for the synthetic data tool."""

from pathlib import Path

import pandas as pd

from src.core.general_sanity_checks import run_general_sanity_checks
from src.core.logging_config import get_logger
from src.core.synthesis import MostlyAIEngine
from src.core.tracking import SimulationTracker
from src.core.utils import create_simulation_config, delete_empty_folders

logger = get_logger(__name__)


def run_all_sanity_checks(
    synthetic_results: dict[str, pd.DataFrame],
    metadata: dict | object,
    rule_manager: object,
) -> pd.DataFrame | None:
    """Runs all sanity checks (logical rules + general structural checks).

    Args:
        synthetic_results (dict): Generated synthetic data dataframes.
        metadata (dict | object): Model metadata definitions.
        rule_manager (object): The RuleManager instance loaded from training.

    Returns:
        pd.DataFrame | None: Target combined DataFrame of validation reports,
                             or None if there are no checks.
    """
    sanity_checks: list[pd.DataFrame] = []

    rules_report = rule_manager.run_rules_sanity_checks(synthetic_results)
    if not rules_report.empty:
        sanity_checks.append(rules_report)

    general_report = run_general_sanity_checks(
        synthetic_data=synthetic_results,
        metadata=metadata,
        rule_manager=rule_manager,
    )
    if not general_report.empty:
        sanity_checks.append(general_report)

    if sanity_checks:
        return pd.concat(sanity_checks, ignore_index=True)
    return None


def run_simulation_flow(
    generator: object,
    metadata: dict | object,
    rule_manager: object,
    model_id: str,
    sample_size: int | None,
    mostly_config_path: str,
    mostly_ai_overrides: dict | None = None,
    pipeline_id: str = "none",
    job_name: str | None = None,
) -> str | None:
    """Execute the core simulation workflow entirely isolated from callers.

    Instantiates a SimulationTracker, builds execution cards, requests generation
    from the Engine, applies post-processing logic, and conducts sanity checks.

    Args:
        generator (object): The previously restored Mostly AI Generator.
        metadata (dict | object): Restored model schema metadata from training.
        rule_manager (object): Restored applied rules to use in post-processing.
        model_id (str): The unique ID or folder name for the model context.
        sample_size (int | None): Expected bounds for produced samples.
        mostly_config_path (str): Mostly AI configuration bindings.
        mostly_ai_overrides (dict | None, optional): Real-time parameter overlaps.
        pipeline_id (str, optional): ID grouping this run optionally.
        job_name (str | None, optional): Explicit nomenclature for job logging.

    Returns:
        str | None: The simulation tracking ID if successful. None on failure.
    """
    try:
        with SimulationTracker(
            model_id=model_id, pipeline_id=pipeline_id, job_name=job_name
        ) as sim_tracker:
            engine = MostlyAIEngine(
                config_path=mostly_config_path,
                config_overrides=mostly_ai_overrides,
                run_dir=sim_tracker.output_directory,
            )

            simulation_config = create_simulation_config(metadata, sample_size)
            sim_tracker.save_sim_config(simulation_config)
            sim_tracker.save_sim_card(sample_size=sample_size)

            raw_synthetic_results = engine.simulate(generator, simulation_config)
            synthetic_results = rule_manager.apply_all_post(raw_synthetic_results)
            sim_tracker.save_synthetic_results(synthetic_results)

            combined_report = run_all_sanity_checks(synthetic_results, metadata, rule_manager)
            if combined_report is not None:
                sim_tracker.save_sanity_report(combined_report)

            logger.info("Simulación finalizada exitosamente (ID: %s).", sim_tracker.simulation_id)
            delete_empty_folders(Path(sim_tracker.output_directory).parent.parent)

            return sim_tracker.simulation_id

    except Exception as error:
        logger.error("Simulation flow failed: %s", error)
        return None
