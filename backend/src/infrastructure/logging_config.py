"""Centralized logging configuration for the synthetic data pipeline.

Provides a production-style logger that writes simultaneously to console and to a
session.log file inside the active run folder. Compatible with the current CLI mode
and ready for API consumption.
"""

import logging
import os
import sys

from backend.src.config.general import (
    LOG_DATE_FORMAT,
    LOG_FORMAT,
    LOG_LEVEL,
    SESSION_LOG_FILENAME,
)

_CONFIGURED_RUN_DIRS: set[str] = set()

_pipeline_handler: logging.Handler | None = None
_session_handler: logging.Handler | None = None

_PROJECT_LOGGER_PREFIX = "backend.src."

_LEVEL_COLORS = {
    logging.DEBUG: "\033[36m",  # cyan
    logging.INFO: "\033[32m",  # green
    logging.WARNING: "\033[33m",  # yellow
    logging.ERROR: "\033[31m",  # red
    logging.CRITICAL: "\033[1;31m",  # bold red
}
_RESET = "\033[0m"


class _ColorFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        original_levelname = record.levelname
        color = _LEVEL_COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{_RESET}"
        try:
            return super().format(record)
        finally:
            record.levelname = original_levelname


def get_logger(name: str) -> logging.Logger:
    """Gets a logger with the given name, with a default console handler.

    Args:
        name: Logger name (typically the module's __name__).

    Returns:
        logging.Logger: Configured logger.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(LOG_LEVEL)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(LOG_LEVEL)
        console_handler.setFormatter(_ColorFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        logger.addHandler(console_handler)
        logger.propagate = False

    if _pipeline_handler is not None and _pipeline_handler not in logger.handlers:
        logger.addHandler(_pipeline_handler)

    if _session_handler is not None and _session_handler not in logger.handlers:
        logger.addHandler(_session_handler)

    return logger


def set_session_handler(handler: logging.Handler) -> None:
    """Activate ``handler`` for every existing and future project logger.

    Mirrors how ``_pipeline_handler`` works: stored on a module global so that
    ``get_logger`` attaches it to newly created loggers, and immediately added
    to every already-instantiated ``backend.src.*`` logger so logs from modules
    imported earlier in the process also flow into it.

    What is a handler? In logging terms, it's a destination for log records.
    By setting a session handler, you can ensure that all logs from the project
    are also written to a specific file or other output, in addition to the console.

    What is a sesssion? In this context, a session typically corresponds to a single
    run of the pipeline, with its own directory and logs. By configuring a session
    handler, you can have all logs for that run neatly organized in one place,
    making it easier to review and debug specific executions of the pipeline.

    Args:
        handler: Handler to add to all project loggers.
    """
    global _session_handler
    if _session_handler is not None:
        clear_session_handler()
    _session_handler = handler
    for name, item in list(logging.Logger.manager.loggerDict.items()):
        if not isinstance(item, logging.Logger):
            continue
        if name.startswith(_PROJECT_LOGGER_PREFIX) or name == "backend.src":
            if handler not in item.handlers:
                item.addHandler(handler)


def clear_session_handler() -> None:
    """Detach the active session handler from every project logger and close it."""
    global _session_handler
    if _session_handler is None:
        return
    handler = _session_handler
    for _name, item in list(logging.Logger.manager.loggerDict.items()):
        if not isinstance(item, logging.Logger):
            continue
        if handler in item.handlers:
            item.removeHandler(handler)
    try:
        handler.close()
    except Exception:
        pass
    _session_handler = None


def add_file_handler(logger: logging.Logger, run_directory: str) -> None:
    """Adds a FileHandler to the logger to write session.log in the run directory.

    Idempotent: if a handler was already configured for that directory, it is not duplicated.

    Args:
        logger: Logger to which the handler is added.
        run_directory: Path to the run directory where session.log is created.
    """
    log_path = os.path.join(run_directory, SESSION_LOG_FILENAME)

    # Evitar duplicados
    if log_path in _CONFIGURED_RUN_DIRS:
        return

    os.makedirs(run_directory, exist_ok=True)
    file_handler = logging.FileHandler(log_path, encoding="utf-8")
    file_handler.setLevel(LOG_LEVEL)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
    logger.addHandler(file_handler)
    _CONFIGURED_RUN_DIRS.add(log_path)


_MODE_LABELS = {
    "i": "INSPECCION",
    "t": "ENTRENAMIENTO",
    "s": "SIMULACION",
    "e": "EVALUACION",
    "p": "PIPELINE",
}


def log_run_header(
    logger: logging.Logger,
    mode: str,
    subtitle: str | None = None,
    **fields: object,
) -> None:
    """Log a consistent banner announcing the selected mode and its key inputs.

    ``mode`` accepts the single-letter codes used by ``execution_config`` (``i``,
    ``t``, ``s``, ``e``, ``p``) or any free-form label. ``subtitle`` is meant for
    the provenance line (e.g. ``"from inspection"`` vs ``"from raw files"``).
    ``fields`` are rendered as aligned ``key : value`` pairs below the title.
    """
    label = _MODE_LABELS.get(mode, mode.upper())
    title = f"EJECUCION: {label}"
    if subtitle:
        title += f"  —  {subtitle}"

    bar = "=" * 80
    logger.info(bar)
    logger.info(title)
    if fields:
        width = max(len(key) for key in fields)
        for key, value in fields.items():
            logger.info("  %-*s : %s", width, key, value)
    logger.info(bar)


def setup_run_logger(name: str, run_directory: str) -> logging.Logger:
    """Creates and configures a full logger for a specific run.

    Combines a console handler + session.log file in the run directory.

    Args:
        name: Logger name.
        run_directory: Run directory where logs are persisted.

    Returns:
        logging.Logger: Logger ready to use.
    """
    logger = get_logger(name)
    add_file_handler(logger, run_directory)
    return logger
