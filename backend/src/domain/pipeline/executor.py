"""Pipeline executor for automating sequential synthetic data generation."""

import threading

from backend.src.config.general import (
    DEFAULT_CSV_DELIMITER,
    ENABLE_DATA_PROFILING,
    TIME_PROFILING_REPORT_FILENAME,
    refresh_run_timestamp,
)
from backend.src.infrastructure.logging_config import get_logger, log_run_header
from backend.src.infrastructure.progress import ProfilerPhase, job_phase_label
from backend.src.infrastructure.time_profiling import profiler
from backend.src.runs.tracking import PipelineTracker
from backend.src.domain.pipeline.config_classes import (
    EvaluateStepConfig,
    JobConfigOverrides,
    PipelineConfig,
    PipelineJobConfig,
    SimulateStepConfig,
    TrainStepConfig,
)
from backend.src.sessions.configs import resolve_config_path

logger = get_logger(__name__)


def _resolve_job_config(
    overrides: JobConfigOverrides | None,
) -> tuple[str, str, dict | None, bool, str]:
    """Resolve effective configuration values for a job.

    Args:
        overrides (JobConfigOverrides | None): User-defined overrides for the job.

    Returns:
        tuple[str, str, dict | None, bool, str]: A tuple containing:
            - rules_path (str): Path to the logical rules config.
            - mostly_ai_path (str): Path to the Mostly AI config.
            - mostly_ai_overrides (dict | None): Engine-specific overrides.
            - enable_profiling (bool): Whether data profiling is enabled.
            - csv_delimiter (str): The CSV parsing delimiter.
    """
    rules_path = str(resolve_config_path("rules"))
    mostly_ai_path = str(resolve_config_path("mostly_ai"))
    mostly_ai_overrides: dict | None = None
    enable_profiling = ENABLE_DATA_PROFILING
    csv_delimiter = DEFAULT_CSV_DELIMITER

    if overrides is not None:
        if overrides.rules_config:
            rules_path = overrides.rules_config
        if overrides.mostly_ai:
            mostly_ai_overrides = overrides.mostly_ai
        if overrides.general:
            general = overrides.general
            if "enable_data_profiling" in general:
                enable_profiling = bool(general["enable_data_profiling"])
            if "csv_delimiter" in general:
                csv_delimiter = str(general["csv_delimiter"])

    return rules_path, mostly_ai_path, mostly_ai_overrides, enable_profiling, csv_delimiter


def _run_train_step(
    step: TrainStepConfig,
    pipeline_id: str = "none",
    job_config: JobConfigOverrides | None = None,
    job_name: str = "",
) -> tuple[str, object, dict, object] | None:
    """Execute a training step and return the resulting artifacts.

    Args:
        step (TrainStepConfig): Training step configuration.
        pipeline_id (str): ID of the parent pipeline run.
        job_config (JobConfigOverrides | None): Overrides for this job.
        job_name (str): Human-readable name of the job.

    Returns:
        tuple[str, object, dict, object] | None: (model_id, generator, metadata, rule_manager)
            if successful, None otherwise.
    """
    (
        rules_path,
        mostly_ai_path,
        mostly_ai_overrides,
        enable_profiling,
        csv_delimiter,
    ) = _resolve_job_config(job_config)

    # Resume-from-inspection takes priority when set: it lets the user run a
    # job whose train step uses a manually-edited inspection (relationships /
    # encoding-type tweaks) without re-preprocessing raw files.
    if step.inspection_id:
        from backend.src.sessions.training import run_training_flow_from_inspection

        model_id, generator, metadata, rule_manager = run_training_flow_from_inspection(
            inspection_id=step.inspection_id,
            mostly_ai_overrides=mostly_ai_overrides,
            pipeline_id=pipeline_id,
            job_name=job_name,
        )
    else:
        from backend.src.sessions.training import run_training_flow

        model_id, generator, metadata, rule_manager = run_training_flow(
            file_paths=step.files,
            mostly_config_path=mostly_ai_path,
            rules_config_path=rules_path,
            enable_data_profiling=enable_profiling,
            csv_delimiter=csv_delimiter,
            mostly_ai_overrides=mostly_ai_overrides,
            pipeline_id=pipeline_id,
            job_name=job_name,
        )

    if model_id is None:
        return None
    return model_id, generator, metadata, rule_manager


def _run_simulate_step(
    step: SimulateStepConfig,
    generator: object | None,
    metadata: dict | None,
    rule_manager: object | None,
    model_id: str | None,
    pipeline_id: str = "none",
    job_config: JobConfigOverrides | None = None,
    job_name: str = "",
) -> str | None:
    """Execute a simulation step and return the resulting simulation ID.

    Args:
        step (SimulateStepConfig): Simulation step configuration.
        generator (object | None): Trained generator instance.
        metadata (dict | None): Model metadata.
        rule_manager (object | None): Logical rule manager.
        model_id (str | None): ID of the model to simulate from.
        pipeline_id (str): ID of the parent pipeline run.
        job_config (JobConfigOverrides | None): Overrides for this job.
        job_name (str): Human-readable name of the job.

    Returns:
        str | None: The simulation ID if successful, None otherwise.
    """
    (
        _rules_path,
        mostly_ai_path,
        mostly_ai_overrides,
        _enable_profiling,
        _csv_delimiter,
    ) = _resolve_job_config(job_config)

    effective_model_id = model_id or step.model_id
    active_generator = generator
    active_metadata = metadata
    active_rule_manager = rule_manager

    if active_generator is None:
        if effective_model_id is None:
            logger.error(
                "Simulate step requires either a preceding train step or an explicit model_id."
            )
            return None

        from backend.src.sessions.artifacts import load_generator_artifacts

        try:
            result = load_generator_artifacts(effective_model_id, mostly_ai_path)
            active_generator, active_metadata, active_rule_manager = result
        except Exception as e:
            logger.error("Failed to load artifacts for simulation: %s", e)
            return None

    from backend.src.sessions.simulation import run_simulation_flow

    simulation_id = run_simulation_flow(
        generator=active_generator,
        metadata=active_metadata,
        rule_manager=active_rule_manager,
        model_id=effective_model_id,
        sample_size=step.sample_size,
        mostly_config_path=mostly_ai_path,
        synthetic_data_file_format=step.synthetic_data_file_format,
        mostly_ai_overrides=mostly_ai_overrides,
        pipeline_id=pipeline_id,
        job_name=job_name,
    )

    return simulation_id


def _run_evaluate_step(
    step: EvaluateStepConfig,
    simulation_id: str | None,
    model_id: str | None,
    pipeline_id: str,
    job_name: str,
) -> str | None:
    """Execute an evaluation step using the unified evaluation flow service.

    Args:
        step (EvaluateStepConfig): Evaluation step configuration.
        simulation_id (str | None): ID of the simulation to evaluate.
        model_id (str | None): ID of the model context.
        pipeline_id (str): ID of the parent pipeline run.
        job_name (str): Human-readable name of the job.

    Returns:
        str | None: The evaluation ID if successful, None otherwise.
    """
    effective_simulation_id = step.simulation_id or simulation_id
    effective_model_id = step.model_id or model_id

    if effective_simulation_id is None:
        logger.error(
            "Evaluate step requires either a preceding simulate step or an explicit simulation_id."
        )
        return None

    if effective_model_id is None:
        logger.error("Evaluate step requires an explicit model_id.")
        return None

    from backend.src.sessions.evaluation import (
        initialize_evaluation_session,
        run_evaluation_flow_from_simulation,
    )

    try:
        session = initialize_evaluation_session(
            simulation_id=effective_simulation_id, model_id=effective_model_id
        )
        evaluation_id = run_evaluation_flow_from_simulation(
            simulation_id=effective_simulation_id,
            pipeline_id=pipeline_id,
            job_name=job_name,
            session=session,
            # Pass explicit real_data if provided via step config
            real_data=step.real_data,
        )
        return evaluation_id
    except Exception as error:
        logger.error("Evaluate step failed: %s", error)
        return None


def _run_job(
    job: PipelineJobConfig,
    pipeline_id: str,
    cancel_event: threading.Event | None = None,
) -> tuple[str | None, str | None, str | None]:
    """Execute all steps of a single pipeline job.

    Artifacts are threaded through the steps within the job.
    If a step fails, subsequent steps in that job are skipped.

    Args:
        job (PipelineJobConfig): Job to execute.
        pipeline_id (str): Pipeline ID shared by all jobs in this pipeline run.

    Returns:
        tuple[str | None, str | None, str | None]: ``(model_id, simulation_id,
        evaluation_id)`` produced by the job. Any element is ``None`` when the
        corresponding step did not run or failed.
    """
    generator = None
    metadata = None
    rule_manager = None
    model_id: str | None = None
    simulation_id: str | None = None
    evaluation_id: str | None = None

    if job.train is not None:
        logger.info("[%s] Running train step...", job.name)
        with profiler.phase(job_phase_label(job.name, ProfilerPhase.TRAIN)):
            result = _run_train_step(
                job.train, pipeline_id=pipeline_id, job_config=job.config, job_name=job.name
            )
        if result is None:
            logger.error("[%s] Train step failed — skipping remaining steps.", job.name)
            return model_id, simulation_id, evaluation_id
        model_id, generator, metadata, rule_manager = result
        logger.info("[%s] Train step complete. model_id=%s", job.name, model_id)

    if cancel_event is not None and cancel_event.is_set():
        logger.info(
            "[%s] Cancellation detected after train step — skipping simulate/evaluate.", job.name
        )
        return model_id, simulation_id, evaluation_id

    if job.simulate is not None:
        logger.info("[%s] Running simulate step...", job.name)
        with profiler.phase(job_phase_label(job.name, ProfilerPhase.SIMULATE)):
            simulation_id = _run_simulate_step(
                step=job.simulate,
                generator=generator,
                metadata=metadata,
                rule_manager=rule_manager,
                model_id=model_id,
                pipeline_id=pipeline_id,
                job_config=job.config,
                job_name=job.name,
            )
        if simulation_id is None:
            logger.error("[%s] Simulate step failed — skipping evaluate step.", job.name)
            return model_id, simulation_id, evaluation_id
        logger.info("[%s] Simulate step complete. simulation_id=%s", job.name, simulation_id)

    if cancel_event is not None and cancel_event.is_set():
        logger.info("[%s] Cancellation detected after simulate step — skipping evaluate.", job.name)
        return model_id, simulation_id, evaluation_id

    if job.evaluate is not None:
        logger.info("[%s] Running evaluate step...", job.name)
        with profiler.phase(job_phase_label(job.name, ProfilerPhase.EVALUATE)):
            evaluation_id = _run_evaluate_step(
                step=job.evaluate,
                simulation_id=simulation_id,
                model_id=model_id,
                pipeline_id=pipeline_id,
                job_name=job.name,
            )
        if evaluation_id:
            logger.info("[%s] Evaluate step complete. evaluation_id=%s", job.name, evaluation_id)
        else:
            logger.error("[%s] Evaluate step failed.", job.name)

    return model_id, simulation_id, evaluation_id


def run_pipeline(
    config: PipelineConfig,
    config_path: str,
    pipeline_id: str | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Execute all jobs in the pipeline sequentially.

    Each job's steps run in order: train → simulate → evaluate.
    Artifacts (model_id, generator, metadata, rule_manager) produced by
    earlier steps are passed automatically to later steps in the same job.
    A PipelineTracker collects the combined log and a summary of all job outputs.

    Args:
        config (PipelineConfig): Parsed pipeline configuration.
        config_path (str): Path to the pipeline config file (used for tracking).
        pipeline_id (str | None): Optional ID to reuse for the pipeline.
        cancel_event (threading.Event | None): Optional cancellation signal.

    Returns:
        None
    """
    total = len(config.jobs)
    log_run_header(
        logger,
        "p",
        subtitle="multi-job YAML pipeline",
        config=config_path,
        jobs=total,
        job_names=[job.name for job in config.jobs],
    )

    with PipelineTracker(config_path, pipeline_id=pipeline_id) as pipeline_tracker:
        try:
            for index, job in enumerate(config.jobs, start=1):
                if cancel_event is not None and cancel_event.is_set():
                    logger.info(
                        "Pipeline cancelled — stopping before job %d/%d: '%s'.",
                        index,
                        total,
                        job.name,
                    )
                    pipeline_tracker.mark_cancelled()
                    break
                pipeline_tracker.set_progress(step=index - 1, total=total, label=job.name)
                refresh_run_timestamp()
                logger.info("-" * 100)
                logger.info(
                    "----------------------------- Job %d/%d: '%s' ------------------------------",
                    index,
                    total,
                    job.name,
                )
                logger.info("-" * 100)
                model_id, simulation_id, evaluation_id = _run_job(
                    job, pipeline_tracker.pipeline_id, cancel_event
                )
                pipeline_tracker.register_job_result(
                    job_name=job.name,
                    model_id=model_id,
                    simulation_id=simulation_id,
                    evaluation_id=evaluation_id,
                )
        finally:
            import os

            timing_report_path = os.path.join(
                pipeline_tracker.output_directory, TIME_PROFILING_REPORT_FILENAME
            )
            profiler.report("Pipeline timing breakdown", output_path=timing_report_path)

    logger.info("Pipeline completed: %d job(s) finished.", total)
