"""Pipeline flow service needed to wrap the core pipeline logic for the API.

This module acts as a service layer (facade) specifically designed to wrap the core
pipeline execution engine (located in `src/pipeline/`).

Why does this exist alongside `src/pipeline/`?
- `src/pipeline/` contains the actual execution engine: parsing YAMLs, resolving configs,
  and orchestrating the steps. It is stateless and unaware of the web API context.
- `src/services/pipeline.py` (this file) orchestrates the state management needed by the API.
  It creates the `pipeline_card.json` in an `in_progress` state BEFORE background jobs begin,
  manages the `PipelineSession`, and catches high-level exceptions to update the card
  to a `failed` state if the engine crashes.

In short: `src/pipeline/` is the engine, `src/services/pipeline.py` is the stateful API wrapper.
"""

import os
import threading
from dataclasses import dataclass

from backend.src.config.general import (
    PIPELINE_CARD_FILENAME,
    PIPELINE_RUN_FOLDER_PREFIX,
    PIPELINES_DIR,
    refresh_run_timestamp,
)
from backend.src.core.card_io import mark_card_failed, write_json
from backend.src.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class PipelineSession:
    """Pre-initialized pipeline session created before the background task runs."""

    pipeline_id: str
    output_directory: str
    card_path: str
    timestamp: str


def initialize_pipeline_session(config_path: str) -> PipelineSession:
    """Create the output folder and the ``in_progress`` pipeline card.

    Refreshes the run timestamp and materializes the session on disk.

    Args:
        config_path (str): Path to the pipeline YAML configuration file.

    Returns:
        PipelineSession: Descriptor of the newly created pipeline session.
    """
    timestamp = refresh_run_timestamp()
    pipeline_id = f"{PIPELINE_RUN_FOLDER_PREFIX}_{timestamp}"
    output_directory = os.path.join(PIPELINES_DIR, pipeline_id)
    configs_directory = os.path.join(output_directory, "configs")
    card_path = os.path.join(output_directory, PIPELINE_CARD_FILENAME)

    os.makedirs(configs_directory, exist_ok=True)
    logger.info("Created pipeline output directory: %s", output_directory)

    write_json(
        card_path,
        {
            "pipeline_id": pipeline_id,
            "status": "in_progress",
            "timestamp": timestamp,
            "config_path": config_path,
            "jobs": [],
            # Coarse placeholder so the UI can render a progress bar from the
            # first poll; the executor refines step/total/label as jobs run.
            "progress": {"step": 0, "total": 0, "label": "Initializing"},
        },
        indent=4,
    )

    return PipelineSession(
        pipeline_id=pipeline_id,
        output_directory=output_directory,
        card_path=card_path,
        timestamp=timestamp,
    )


def run_pipeline_from_config(
    config_path: str,
    session: PipelineSession | None = None,
    cancel_event: threading.Event | None = None,
) -> None:
    """Load a pipeline YAML and execute all its jobs.

    Wraps ``load_pipeline_config`` + ``run_pipeline`` so the API background
    task only needs a config path and an optional pre-initialized session.

    Args:
        config_path (str): Path to the pipeline YAML configuration file.
        session (PipelineSession | None): Pre-initialized session.
        cancel_event (threading.Event | None): Optional cancellation event.

    Returns:
        None
    """
    if cancel_event is not None and cancel_event.is_set():
        logger.info(
            "Pipeline %s cancelled before execution started.",
            session.pipeline_id if session else "",
        )
        return

    try:
        from backend.src.pipeline.executor import run_pipeline
        from backend.src.pipeline.loader import load_pipeline_config

        config = load_pipeline_config(config_path)
        run_pipeline(
            config,
            config_path,
            pipeline_id=session.pipeline_id if session else None,
            cancel_event=cancel_event,
        )
    except Exception as error:
        logger.error("Pipeline flow failed: %s", error, exc_info=True)
        if session:
            mark_card_failed(session.card_path, error)
