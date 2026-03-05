"""Configuración centralizada de logging para el pipeline de datos sintéticos.

Proporciona un logger profesional que escribe simultáneamente a consola y a un
archivo session.log dentro de la carpeta del run activo. Compatible con el modo
CLI actual y preparado para consumo por API.
"""

import logging
import os
import sys

from config.general_config import LOG_DATE_FORMAT, LOG_FORMAT, LOG_LEVEL, SESSION_LOG_FILENAME

_CONFIGURED_RUN_DIRS: set[str] = set()

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
        color = _LEVEL_COLORS.get(record.levelno, "")
        record.levelname = f"{color}{record.levelname}{_RESET}"
        return super().format(record)


def get_logger(name: str) -> logging.Logger:
    """Obtiene un logger con el nombre dado, con handler de consola por defecto.

    Args:
        name: Nombre del logger (típicamente __name__ del módulo).

    Returns:
        logging.Logger: Logger configurado.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        logger.setLevel(LOG_LEVEL)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(LOG_LEVEL)
        console_handler.setFormatter(_ColorFormatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT))
        logger.addHandler(console_handler)
        logger.propagate = False

    return logger


def add_file_handler(logger: logging.Logger, run_directory: str) -> None:
    """Añade un FileHandler al logger para escribir session.log en el directorio del run.

    Idempotente: si ya se configuró un handler para ese directorio, no duplica.

    Args:
        logger: Logger al que añadir el handler.
        run_directory: Ruta al directorio del run donde crear session.log.
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


def setup_run_logger(name: str, run_directory: str) -> logging.Logger:
    """Crea y configura un logger completo para un run específico.

    Combina handler de consola + archivo session.log en el directorio del run.

    Args:
        name: Nombre del logger.
        run_directory: Directorio del run donde persistir logs.

    Returns:
        logging.Logger: Logger listo para usar.
    """
    logger = get_logger(name)
    add_file_handler(logger, run_directory)
    return logger
