"""Pipeline runner for automated sequential synthetic data generation.

Supports running any combination of train, simulate, and evaluate steps
across multiple jobs defined in a YAML configuration file. Jobs run
sequentially in definition order; steps within a job pass artifacts
(generator, metadata, rule manager) automatically between them.

Usage:
    python -m src.pipeline --config config/pipelines/my_pipeline.yaml
"""

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field

import yaml

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from config.evaluation.evaluation_config import EVAL_PYTHON_PATH
from config.general_config import (
    DEFAULT_CSV_DELIMITER,
    DEFAULT_SAMPLE_SIZE,
    ENABLE_DATA_PROFILING,
    MOSTLYAI_CONFIG_PATH,
    RULES_CONFIG_PATH,
    SIMULATIONS_DIR,
    refresh_run_timestamp,
)

from src.core.logging_config import get_logger, log_run_header
from src.core.tracking import PipelineTracker
from src.core.utils import get_files_from_directory

logger = get_logger(__name__)


@dataclass
class TrainStepConfig:
    """Configuration for a training step.

    Attributes:
        files (list[str]): Paths to input data files or directories.
    """

    files: list[str]


@dataclass
class SimulateStepConfig:
    """Configuration for a simulation step.

    Attributes:
        sample_size (int): Number of synthetic records to generate.
        model_id (str | None): Explicit model ID to use. If None and a train step
            precedes this in the same job, the trained model is used automatically.
    """

    sample_size: int = DEFAULT_SAMPLE_SIZE
    model_id: str | None = None


@dataclass
class EvaluateStepConfig:
    """Configuration for an evaluation step.

    Attributes:
        real_data (list[str]): Paths to real data files for comparison.
        simulation_id (str | None): Explicit simulation ID to evaluate. If None and
            a simulate step precedes this in the same job, that simulation is used.
        model_id (str | None): Explicit model ID. If None, inferred from job context.
    """

    real_data: list[str]
    simulation_id: str | None = None
    model_id: str | None = None


@dataclass
class JobConfigOverrides:
    """Per-job configuration overrides.

    Allows each pipeline job to customise rules, Mostly AI hyperparameters,
    and general settings independently, instead of relying only on the
    global defaults.

    Attributes:
        rules_config (str | None): Path to a job-specific rules YAML file.
            When None the global ``RULES_CONFIG_PATH`` is used.
        mostly_ai (dict | None): Deep-merge overrides applied on top of the
            base ``mostly_ai_config.yaml``.  Only the keys you specify are
            changed; everything else keeps its default value.
        general (dict | None): Overrides for selected ``general_config``
            values (e.g. ``enable_data_profiling``, ``csv_delimiter``).
    """

    rules_config: str | None = None
    mostly_ai: dict | None = None
    general: dict | None = None


@dataclass
class PipelineJobConfig:
    """Configuration for a single pipeline job.

    A job can contain any combination of train, simulate, and evaluate steps.
    Steps execute in order: train → simulate → evaluate. Artifacts produced
    by earlier steps are passed automatically to later ones in the same job.

    Attributes:
        name (str): Human-readable job name used in log messages.
        config (JobConfigOverrides | None): Per-job configuration overrides.
        train (TrainStepConfig | None): Training step config, or None to skip.
        simulate (SimulateStepConfig | None): Simulation step config, or None to skip.
        evaluate (EvaluateStepConfig | None): Evaluation step config, or None to skip.
    """

    name: str
    config: JobConfigOverrides | None = None
    train: TrainStepConfig | None = None
    simulate: SimulateStepConfig | None = None
    evaluate: EvaluateStepConfig | None = None


@dataclass
class PipelineConfig:
    """Top-level pipeline configuration.

    Attributes:
        jobs (list[PipelineJobConfig]): Ordered list of jobs to execute.
    """

    jobs: list[PipelineJobConfig] = field(default_factory=list)


def load_pipeline_config(config_path: str) -> PipelineConfig:
    """Load and parse a pipeline configuration YAML file.

    Args:
        config_path (str): Path to the YAML pipeline configuration file.

    Returns:
        PipelineConfig: Parsed pipeline configuration.

    Raises:
        FileNotFoundError: If the config file does not exist.
        ValueError: If the config is missing the required top-level 'jobs' key.

    Example:
        >>> config = load_pipeline_config("config/pipelines/my_pipeline.yaml")
        3
    """
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Pipeline config not found: {config_path}")

    with open(config_path, encoding="utf-8") as file_handle:
        raw = yaml.safe_load(file_handle)

    if not isinstance(raw, dict) or "jobs" not in raw:
        raise ValueError("Pipeline config must have a top-level 'jobs' key.")

    jobs: list[PipelineJobConfig] = []
    for raw_job in raw["jobs"]:
        train_config = None
        simulate_config = None
        evaluate_config = None

        if "train" in raw_job:
            raw_train = raw_job["train"]
            files = raw_train.get("files", [])
            if len(files) == 1 and os.path.isdir(files[0]):
                files = get_files_from_directory(files[0])
            train_config = TrainStepConfig(
                files=files,
            )

        if "simulate" in raw_job:
            raw_sim = raw_job["simulate"]
            simulate_config = SimulateStepConfig(
                sample_size=raw_sim.get("sample_size", DEFAULT_SAMPLE_SIZE),
                model_id=raw_sim.get("model_id"),
            )

        if "evaluate" in raw_job:
            raw_eval = raw_job["evaluate"]
            evaluate_config = EvaluateStepConfig(
                real_data=raw_eval.get("real_data", []),
                simulation_id=raw_eval.get("simulation_id"),
                model_id=raw_eval.get("model_id"),
            )

        job_config_overrides = None
        if "config" in raw_job:
            raw_cfg = raw_job["config"]
            job_config_overrides = JobConfigOverrides(
                rules_config=raw_cfg.get("rules_config"),
                mostly_ai=raw_cfg.get("mostly_ai"),
                general=raw_cfg.get("general"),
            )

        jobs.append(
            PipelineJobConfig(
                name=raw_job.get("name", f"job_{len(jobs) + 1}"),
                config=job_config_overrides,
                train=train_config,
                simulate=simulate_config,
                evaluate=evaluate_config,
            )
        )

    return PipelineConfig(jobs=jobs)


def _resolve_job_config(
    overrides: JobConfigOverrides | None,
) -> tuple[str, str, dict | None, bool, str]:
    """Resolve effective configuration values for a job.

    Merges per-job overrides with global defaults for rules path,
    Mostly AI config path, Mostly AI overrides, profiling flag,
    and CSV delimiter.

    Args:
        overrides (JobConfigOverrides | None): Per-job configuration overrides.

    Returns:
        tuple: (rules_config_path, mostly_ai_config_path, mostly_ai_overrides,
                enable_data_profiling, csv_delimiter).
    """
    rules_path = RULES_CONFIG_PATH
    mostly_ai_path = MOSTLYAI_CONFIG_PATH
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
        pipeline_id (str): Pipeline ID grouping this run, or ``"none"`` for standalone.
        job_config (JobConfigOverrides | None): Per-job configuration overrides.

    Returns:
        tuple[str, object, dict, object] | None: Tuple of
            (model_id, generator, metadata, rule_manager), or None on failure.
    """
    (
        rules_path,
        mostly_ai_path,
        mostly_ai_overrides,
        enable_profiling,
        csv_delimiter,
    ) = _resolve_job_config(job_config)

    from src.services.training import run_training_flow

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

    If generator/metadata/rule_manager are not provided (i.e., there was no
    preceding train step), they are loaded from disk using the resolved model_id.

    Args:
        step (SimulateStepConfig): Simulation step configuration.
        generator: Pre-loaded generator from a preceding train step, or None.
        metadata: Pre-loaded metadata from a preceding train step, or None.
        rule_manager: Pre-loaded rule manager from a preceding train step, or None.
        model_id (str | None): Model ID from the job context (preceding train step).
        pipeline_id (str): Pipeline ID grouping this run, or ``"none"`` for standalone.
        job_config (JobConfigOverrides | None): Per-job configuration overrides.

    Returns:
        str | None: The simulation_id of the completed run, or None on failure.
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

        from src.services.artifacts import load_generator_artifacts

        try:
            result = load_generator_artifacts(effective_model_id, mostly_ai_path)
            active_generator, active_metadata, active_rule_manager = result
        except Exception as e:
            logger.error("Failed to load artifacts for simulation: %s", e)
            return None

    from src.services.simulation import run_simulation_flow

    simulation_id = run_simulation_flow(
        generator=active_generator,
        metadata=active_metadata,
        rule_manager=active_rule_manager,
        model_id=effective_model_id,
        sample_size=step.sample_size,
        mostly_config_path=mostly_ai_path,
        mostly_ai_overrides=mostly_ai_overrides,
        pipeline_id=pipeline_id,
        job_name=job_name,
    )

    return simulation_id


def _resolve_evaluate_paths(
    step: EvaluateStepConfig,
    simulation_id: str | None,
    model_id: str | None,
) -> tuple[str, str, str, list[str], str | None, str | None] | None:
    """Resolve and validate all paths needed for an evaluation step.

    Returns:
        Tuple of (simulation_dir, synthetic_data_dir, eval_dir, synthetic_files,
        effective_model_id, effective_simulation_id) or None on validation failure.
    """
    effective_simulation_id = step.simulation_id or simulation_id
    effective_model_id = step.model_id or model_id

    if effective_simulation_id is None:
        logger.error(
            "Evaluate step requires either a preceding simulate step or an explicit simulation_id."
        )
        return None

    simulation_dir = os.path.join(SIMULATIONS_DIR, effective_simulation_id)
    if not os.path.exists(simulation_dir):
        logger.error("Simulation directory not found: %s", simulation_dir)
        return None

    synthetic_data_dir = os.path.join(simulation_dir, "synthetic_data")
    if not os.path.exists(synthetic_data_dir):
        logger.error("Synthetic data directory not found: %s", synthetic_data_dir)
        return None

    real_table_names = [os.path.basename(real_file) for real_file in step.real_data]
    synthetic_files: list[str] = []
    for table_filename in real_table_names:
        table_name, ext = os.path.splitext(table_filename)
        candidate = os.path.join(synthetic_data_dir, f"{table_name}_synthetic{ext}")
        if not os.path.exists(candidate):
            candidate = os.path.join(synthetic_data_dir, f"{table_name}_synthetic.csv")
        if os.path.exists(candidate):
            synthetic_files.append(candidate)
        else:
            logger.warning("Synthetic file not found for table '%s'.", table_name)

    if not synthetic_files:
        logger.error("No synthetic files found in '%s'.", synthetic_data_dir)
        return None

    eval_dir = os.path.join(simulation_dir, "evaluation")
    return (
        simulation_dir,
        synthetic_data_dir,
        eval_dir,
        synthetic_files,
        effective_model_id,
        effective_simulation_id,
    )


def _run_evaluate_step(
    step: EvaluateStepConfig,
    simulation_id: str | None,
    model_id: str | None,
) -> None:
    """Execute an evaluation step.

    When ``EVAL_PYTHON_PATH`` is configured, the evaluation runs as a
    subprocess using the specified interpreter (typically from *venv_eval*),
    avoiding dependency conflicts with the main virtual environment.
    Otherwise, evaluation runs in-process (requires synthcity in the active env).

    Args:
        step (EvaluateStepConfig): Evaluation step configuration.
        simulation_id (str | None): Simulation ID from a preceding simulate step.
            Takes precedence over step.simulation_id if both are set.
        model_id (str | None): Model ID from the job context.
    """
    resolved = _resolve_evaluate_paths(step, simulation_id, model_id)
    if resolved is None:
        return

    simulation_dir, _, eval_dir, synthetic_files, effective_model_id, effective_simulation_id = (
        resolved
    )

    if EVAL_PYTHON_PATH is not None:
        _run_evaluate_subprocess(
            step=step,
            synthetic_files=synthetic_files,
            eval_dir=eval_dir,
            simulation_dir=simulation_dir,
            model_id=effective_model_id,
            simulation_id=effective_simulation_id,
        )
    else:
        _run_evaluate_inprocess(
            step=step,
            synthetic_files=synthetic_files,
            eval_dir=eval_dir,
            simulation_dir=simulation_dir,
            model_id=effective_model_id,
            simulation_id=effective_simulation_id,
        )


def _run_evaluate_subprocess(
    step: EvaluateStepConfig,
    synthetic_files: list[str],
    eval_dir: str,
    simulation_dir: str,
    model_id: str | None,
    simulation_id: str | None,
) -> None:
    """Run evaluation as a subprocess using the ``EVAL_PYTHON_PATH`` interpreter."""
    cmd: list[str] = [
        EVAL_PYTHON_PATH,
        "-m",
        "src.evaluation.eval_cli",
        "--real-data",
        *step.real_data,
        "--synthetic-data",
        *synthetic_files,
        "--eval-dir",
        eval_dir,
        "--simulation-dir",
        simulation_dir,
    ]
    if model_id:
        cmd += ["--model-id", model_id]
    if simulation_id:
        cmd += ["--simulation-id", simulation_id]

    logger.info("Launching evaluation subprocess: %s", " ".join(cmd))

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=os.path.dirname(os.path.dirname(__file__)),
    )

    if result.stdout:
        for line in result.stdout.strip().splitlines():
            logger.info("[eval] %s", line)
    if result.stderr:
        for line in result.stderr.strip().splitlines():
            logger.warning("[eval] %s", line)

    if result.returncode != 0:
        logger.error("Evaluate subprocess exited with code %d.", result.returncode)


def _run_evaluate_inprocess(
    step: EvaluateStepConfig,
    synthetic_files: list[str],
    eval_dir: str,
    simulation_dir: str,
    model_id: str | None,
    simulation_id: str | None,
) -> None:
    """Run evaluation in the current process (requires synthcity in the active env)."""
    from src.eval import main_eval
    from src.evaluation.mlflow_evaluation_engine import MLflowEvaluationEngine
    from src.evaluation.utils import setup_synthcity_environment

    os.makedirs(eval_dir, exist_ok=True)
    setup_synthcity_environment(simulation_dir)

    evaluator = MLflowEvaluationEngine(eval_results_dir=eval_dir)
    try:
        main_eval(
            real_data_files_path=step.real_data,
            synthetic_files_path=synthetic_files,
            evaluator=evaluator,
            model_id=model_id,
            simulation_id=simulation_id,
        )
    except Exception as error:
        logger.error("Evaluate step failed: %s", error)


class PipelineRunner:
    """Orchestrates sequential execution of pipeline jobs.

    Reads a PipelineConfig and runs each job in order, automatically
    propagating model and simulation artifacts between steps within each job.

    Args:
        config (PipelineConfig): Parsed pipeline configuration.

    Example:
        >>> config = load_pipeline_config("config/pipelines/my_pipeline.yaml")
        >>> PipelineRunner(config).run()
    """

    def __init__(self, config: PipelineConfig, config_path: str) -> None:
        self.config = config
        self.config_path = config_path

    def run(self) -> None:
        """Execute all jobs in the pipeline sequentially.

        Each job's steps run in order: train → simulate → evaluate.
        Artifacts (model_id, generator, metadata, rule_manager) produced by
        earlier steps are passed automatically to later steps in the same job.
        A PipelineTracker collects the combined log and a summary of all job outputs.
        """
        total = len(self.config.jobs)
        log_run_header(
            logger,
            "p",
            subtitle="multi-job YAML pipeline",
            config=self.config_path,
            jobs=total,
            job_names=[job.name for job in self.config.jobs],
        )

        with PipelineTracker(self.config_path) as pipeline_tracker:
            for index, job in enumerate(self.config.jobs, start=1):
                refresh_run_timestamp()
                logger.info("-" * 100)
                logger.info(
                    "----------------------------- Job %d/%d: '%s' ------------------------------",
                    index,
                    total,
                    job.name,
                )
                logger.info("-" * 100)
                model_id, simulation_id = self._run_job(job, pipeline_tracker.pipeline_id)
                pipeline_tracker.register_job_result(
                    job_name=job.name,
                    model_id=model_id,
                    simulation_id=simulation_id,
                )

        logger.info("Pipeline completed: %d job(s) finished.", total)

    def _run_job(self, job: PipelineJobConfig, pipeline_id: str) -> tuple[str | None, str | None]:
        """Execute all steps of a single pipeline job.

        Artifacts are threaded through the steps within the job.
        If a step fails, subsequent steps in that job are skipped.

        Args:
            job (PipelineJobConfig): Job to execute.
            pipeline_id (str): Pipeline ID shared by all jobs in this pipeline run.

        Returns:
            tuple[str | None, str | None]: (model_id, simulation_id) produced by the job.
        """
        generator = None
        metadata = None
        rule_manager = None
        model_id: str | None = None
        simulation_id: str | None = None

        if job.train is not None:
            logger.info("[%s] Running train step...", job.name)
            result = _run_train_step(
                job.train, pipeline_id=pipeline_id, job_config=job.config, job_name=job.name
            )
            if result is None:
                logger.error("[%s] Train step failed — skipping remaining steps.", job.name)
                return model_id, simulation_id
            model_id, generator, metadata, rule_manager = result
            logger.info("[%s] Train step complete. model_id=%s", job.name, model_id)

        if job.simulate is not None:
            logger.info("[%s] Running simulate step...", job.name)
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
                return model_id, simulation_id
            logger.info("[%s] Simulate step complete. simulation_id=%s", job.name, simulation_id)

        if job.evaluate is not None:
            logger.info("[%s] Running evaluate step...", job.name)
            _run_evaluate_step(
                step=job.evaluate,
                simulation_id=simulation_id,
                model_id=model_id,
            )
            logger.info("[%s] Evaluate step complete.", job.name)

        return model_id, simulation_id


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an automated synthetic data pipeline.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the pipeline YAML configuration file.",
    )
    args = parser.parse_args()

    try:
        pipeline_config = load_pipeline_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        sys.exit(f"Failed to load pipeline config: {exc}")

    try:
        PipelineRunner(pipeline_config, config_path=args.config).run()
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user.")
