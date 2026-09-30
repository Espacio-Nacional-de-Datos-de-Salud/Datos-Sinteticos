"""Shared helper to attach a per-run file handler to every project logger.

Both ``ModelTracker``, ``SimulationTracker``, and ``EvaluationTracker`` mirror
every log line produced during their run into ``session.log`` inside the run's
output directory.
"""

import logging
import os

from backend.src.config.general import SESSION_LOG_FILENAME
from backend.src.infrastructure.logging_config import (
    clear_session_handler,
    get_logger,
    set_session_handler,
)

logger = get_logger(__name__)


def attach_session_file_handler(output_directory: str, logger_name: str) -> logging.Logger:
    """Create ``session.log`` in ``output_directory`` and route project logs to it.

    A single ``FileHandler`` is attached to every project logger via
    ``set_session_handler``. (We deliberately do **not** also call
    ``setup_run_logger`` here: it would add a *second* FileHandler on the same
    file to the caller's module logger, making every one of that module's lines
    appear twice in ``session.log``.)

    Args:
        output_directory (str): Run output folder where ``session.log`` lives.
        logger_name (str): Logger name returned for the caller's convenience
            (usually the caller's ``__name__``).

    Returns:
        logging.Logger: The project logger for ``logger_name``.
    """
    log_path = os.path.join(output_directory, SESSION_LOG_FILENAME)

    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    set_session_handler(handler)
    logger.info("Run logger initialised: %s", log_path)
    return get_logger(logger_name)


def detach_session_file_handler() -> None:
    """Remove the active session file handler from every project logger."""
    clear_session_handler()
