"""Shared helper to attach a per-run file handler to the ``src`` logger tree.

Both ``ModelTracker`` and ``SimulationTracker`` mirror every log line produced
during their run into ``session.log`` inside the run's output directory. The
handler setup was previously duplicated across both classes.
"""

import logging
import os

from config.general_config import SESSION_LOG_FILENAME

from src.core.logging_config import get_logger, setup_run_logger

logger = get_logger(__name__)


def attach_session_file_handler(output_directory: str, logger_name: str) -> logging.Logger:
    """Create ``session.log`` in ``output_directory`` and route ``src.*`` logs to it.

    Args:
        output_directory (str): Run output folder where ``session.log`` lives.
        logger_name (str): Name passed to ``setup_run_logger`` for the per-run
            logger instance (usually the caller's ``__name__``).

    Returns:
        logging.Logger: The per-run logger returned by ``setup_run_logger``.
    """
    log_path = os.path.join(output_directory, SESSION_LOG_FILENAME)
    run_logger = setup_run_logger(logger_name, output_directory)

    root_logger = logging.getLogger("src")
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root_logger.addHandler(handler)
    logger.info("Run logger initialised: %s", log_path)
    return run_logger
