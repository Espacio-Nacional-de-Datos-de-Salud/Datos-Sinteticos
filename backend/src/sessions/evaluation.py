"""Evaluation flow service for the synthetic data tool."""

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

from backend.src.config.evaluation import EVAL_PYTHON_PATH
from backend.src.config.general import (
    EVAL_CARD_FILENAME,
    EVALUATION_RUN_FOLDER_PREFIX,
    EVALUATIONS_DIR,
    MODEL_CARD_FILENAME,
    MODELS_DIR,
    SIM_CARD_FILENAME,
    refresh_run_timestamp,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import (
    EVALUATION_PHASES,
    EvaluationPhase,
    advance_progress,
    initial_progress,
)
from backend.src.runs.card_io import mark_card_failed, read_json, update_card_status, write_json
from backend.src.runs.catalog.simulations import ResolvedSimulationInputs, resolve_simulation_inputs

logger = get_logger(__name__)


@dataclass(frozen=True)
class EvaluationSession:
    """Pre-initialized evaluation session created before the background task runs."""

    evaluation_id: str
    output_directory: str
    card_path: str
    timestamp: str


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_real_data_hashes(model_id: str | None, real_data: list[str]) -> None:
    """Fail early when a real-data file changed since the model was trained."""
    if not model_id:
        return

    model_card_path = Path(MODELS_DIR) / model_id / MODEL_CARD_FILENAME
    if not model_card_path.exists():
        return

    try:
        model_card = read_json(str(model_card_path))
    except Exception as error:
        logger.warning("Could not read model card for hash validation: %s", error)
        return

    expected_by_path = {
        str(Path(source["path"]).resolve()): source.get("sha256")
        for source in model_card.get("data_sources", [])
        if source.get("path") and source.get("sha256")
    }

    for real_path in real_data:
        resolved = str(Path(real_path).resolve())
        expected_hash = expected_by_path.get(resolved)
        if not expected_hash:
            continue
        current_hash = _sha256_file(resolved)
        if current_hash != expected_hash:
            raise ValueError(
                "Real data file changed since training: "
                f"{resolved}. Expected sha256 {expected_hash}, got {current_hash}."
            )


def initialize_evaluation_session(
    simulation_id: str,
    model_id: str,
    pipeline_id: str = "none",
    job_name: str | None = None,
    name: str | None = None,
) -> EvaluationSession:
    """Create the output folder and the ``in_progress`` eval card.

    Refreshes the run timestamp and materializes the session on disk.

    Args:
        simulation_id (str): ID of the simulation to evaluate.
        model_id (str): ID of the model used in the simulation.
        pipeline_id (str): Pipeline ID if part of a pipeline run.
        job_name (str | None): Human-readable job name.

    Returns:
        EvaluationSession: Descriptor of the newly created evaluation session.
    """
    timestamp = refresh_run_timestamp()
    evaluation_id = f"{EVALUATION_RUN_FOLDER_PREFIX}_{timestamp}"
    output_directory = os.path.join(EVALUATIONS_DIR, evaluation_id)
    card_path = os.path.join(output_directory, EVAL_CARD_FILENAME)

    os.makedirs(output_directory, exist_ok=True)
    logger.info("Created evaluation output directory: %s", output_directory)

    write_json(
        card_path,
        {
            "evaluation_id": evaluation_id,
            "evaluation_name": name.strip() if name and name.strip() else evaluation_id,
            "status": "in_progress",
            "simulation_id": simulation_id,
            "model_id": model_id,
            "pipeline_id": pipeline_id,
            "job_name": job_name,
            "timestamp": timestamp,
            "progress": initial_progress(EVALUATION_PHASES),
        },
        indent=4,
    )

    return EvaluationSession(
        evaluation_id=evaluation_id,
        output_directory=output_directory,
        card_path=card_path,
        timestamp=timestamp,
    )


def run_evaluation_flow_from_simulation(
    simulation_id: str,
    pipeline_id: str = "none",
    job_name: str | None = None,
    session: EvaluationSession | None = None,
    real_data: list[str] | None = None,
    cancel_event: threading.Event | None = None,
    training_parameters: dict | None = None,
    table_configs: list[dict] | None = None,
) -> str | None:
    """Run evaluation for a completed simulation, deriving all inputs automatically.

    Traces back through the artifact chain:
    - ``sim_card.json`` → ``model_id``
    - ``model_card.json`` → original ``data_sources`` (real data paths)
    - ``synthetic_data/`` → synthetic files matched by table name

    Results land in ``outputs/evaluations/{evaluation_id}/``.

    Args:
        simulation_id (str): ID of the simulation to evaluate.
        pipeline_id (str): Pipeline grouping reference.
        job_name (str | None): Human readable job name.
        session (EvaluationSession | None): Pre-initialized session.
        real_data (list[str] | None): Optional list of real data file paths.
        cancel_event (threading.Event | None): Optional cancellation signal.

    Returns:
        str | None: The evaluation ID if successful, None otherwise.
    """
    if session:
        evaluation_id = session.evaluation_id
        eval_dir = session.output_directory
    else:
        # Fallback if no session is provided
        logger.error("Session must be provided to run evaluation flow.")
        return None

    if cancel_event is not None and cancel_event.is_set():
        logger.info("Evaluation %s cancelled before execution started.", evaluation_id)
        update_card_status(session.card_path, "cancelled")
        return None

    advance_progress(session.card_path, EVALUATION_PHASES, EvaluationPhase.RESOLVING_INPUTS)
    try:
        inputs: ResolvedSimulationInputs = resolve_simulation_inputs(simulation_id)
    except Exception as error:
        logger.error("Failed to resolve simulation inputs: %s", error, exc_info=True)
        mark_card_failed(session.card_path, error)
        return None

    # Default to the master table when the caller (e.g. CLI/pipeline) didn't pick.
    if not table_configs:
        sim_card = read_json(os.path.join(inputs.simulation_dir, SIM_CARD_FILENAME))
        mother_table = sim_card.get("mother_table") if isinstance(sim_card, dict) else None
        table_configs = [{"table": mother_table}] if mother_table else None

    effective_real_data = real_data if real_data else inputs.real_data_files
    try:
        _validate_real_data_hashes(inputs.model_id, effective_real_data)
    except Exception as error:
        logger.error("Real data validation failed: %s", error, exc_info=True)
        mark_card_failed(session.card_path, error)
        return None

    advance_progress(session.card_path, EVALUATION_PHASES, EvaluationPhase.RUNNING)
    if EVAL_PYTHON_PATH is not None:
        succeeded = _run_subprocess(
            real_data=effective_real_data,
            synthetic_files=inputs.synthetic_files,
            eval_dir=eval_dir,
            simulation_dir=inputs.simulation_dir,
            model_id=inputs.model_id,
            simulation_id=inputs.simulation_id,
            evaluation_id=evaluation_id,
            pipeline_id=pipeline_id,
            job_name=job_name,
            training_parameters=training_parameters,
            table_configs=table_configs,
        )
    else:
        succeeded = _run_inprocess(
            real_data=effective_real_data,
            synthetic_files=inputs.synthetic_files,
            eval_dir=eval_dir,
            simulation_dir=inputs.simulation_dir,
            model_id=inputs.model_id,
            simulation_id=inputs.simulation_id,
            evaluation_id=evaluation_id,
            pipeline_id=pipeline_id,
            job_name=job_name,
            training_parameters=training_parameters,
            table_configs=table_configs,
        )
    return evaluation_id if succeeded else None


def _run_subprocess(
    real_data: list[str],
    synthetic_files: list[str],
    eval_dir: str,
    simulation_dir: str,
    model_id: str | None,
    simulation_id: str,
    evaluation_id: str,
    pipeline_id: str = "none",
    job_name: str | None = None,
    training_parameters: dict | None = None,
    table_configs: list[dict] | None = None,
) -> bool:
    """Run evaluation in a separate subprocess.

    Args:
        real_data (list[str]): List of real data file paths.
        synthetic_files (list[str]): List of synthetic data file paths.
        eval_dir (str): Output directory for evaluation results.
        simulation_dir (str): Directory containing synthetic data.
        model_id (str | None): ID of the model context.
        simulation_id (str): ID of the simulation context.
        evaluation_id (str): ID of the evaluation session.
    """
    import subprocess

    cmd: list[str] = [
        EVAL_PYTHON_PATH,
        "-m",
        "backend.src.domain.evaluation",
        "--real-data",
        *real_data,
        "--synthetic-data",
        *synthetic_files,
        "--eval-dir",
        eval_dir,
        "--simulation-dir",
        simulation_dir,
        "--simulation-id",
        simulation_id,
        "--evaluation-id",
        evaluation_id,
    ]
    if pipeline_id:
        cmd.extend(["--pipeline-id", pipeline_id])

    if job_name:
        cmd.extend(["--job-name", job_name])

    if training_parameters:
        cmd.extend(["--training-parameters", json.dumps(training_parameters)])

    if table_configs:
        cmd.extend(["--table-configs", json.dumps(table_configs)])

    if model_id:
        cmd += ["--model-id", model_id]

    logger.info("Launching evaluation subprocess: %s", " ".join(cmd))
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        ),
    )
    collected: list[str] = []
    assert proc.stdout is not None
    os.makedirs(eval_dir, exist_ok=True)
    subprocess_log_path = os.path.join(eval_dir, "subprocess.log")
    with open(subprocess_log_path, "w", encoding="utf-8") as subprocess_log:
        for raw_line in proc.stdout:
            line = raw_line.rstrip()
            logger.info("[eval] %s", line)
            collected.append(line)
            subprocess_log.write(line + "\n")
            subprocess_log.flush()
    returncode = proc.wait()
    if returncode != 0:
        logger.error("Evaluation subprocess exited with code %d.", returncode)
        card_path = os.path.join(eval_dir, EVAL_CARD_FILENAME)
        stderr_tail = "\n".join(collected[-50:])
        mark_card_failed(
            card_path,
            error_message=(f"Evaluation subprocess exited with code {returncode}."),
        )
        if stderr_tail and os.path.exists(card_path):
            try:
                card = read_json(card_path)
                card["error_traceback"] = stderr_tail
                write_json(card_path, card)
            except Exception as write_error:
                logger.warning(
                    "Could not attach stderr to failed card %s: %s", card_path, write_error
                )
        return False
    return True


def _run_inprocess(
    real_data: list[str],
    synthetic_files: list[str],
    eval_dir: str,
    simulation_dir: str,
    model_id: str | None,
    simulation_id: str,
    evaluation_id: str,
    pipeline_id: str,
    job_name: str | None,
    training_parameters: dict | None = None,
    table_configs: list[dict] | None = None,
) -> bool:
    """Run evaluation in the current process.

    Args:
        real_data (list[str]): List of real data file paths.
        synthetic_files (list[str]): List of synthetic data file paths.
        eval_dir (str): Output directory for evaluation results.
        simulation_dir (str): Directory containing synthetic data.
        model_id (str | None): ID of the model context.
        simulation_id (str): ID of the simulation context.
        evaluation_id (str): ID of the evaluation session.
        pipeline_id (str): Pipeline grouping reference.
        job_name (str | None): Human readable job name.
    """
    from backend.src.domain.evaluation import run_evaluation
    from backend.src.domain.evaluation.utils import setup_synthcity_environment

    setup_synthcity_environment(simulation_dir)
    try:
        run_evaluation(
            real_data_files_path=real_data,
            synthetic_files_path=synthetic_files,
            eval_dir=eval_dir,
            model_id=model_id,
            simulation_id=simulation_id,
            evaluation_id=evaluation_id,
            pipeline_id=pipeline_id,
            job_name=job_name,
            training_parameters=training_parameters,
            table_configs=table_configs,
        )
        return True
    except Exception as error:
        logger.error("In-process evaluation failed: %s", error, exc_info=True)
        card_path = os.path.join(eval_dir, EVAL_CARD_FILENAME)
        mark_card_failed(card_path, error)
        return False
