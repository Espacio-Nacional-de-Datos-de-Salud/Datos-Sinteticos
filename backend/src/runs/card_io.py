"""Shared JSON I/O helpers for session-layer card files.

Centralizes the read/write/status-update patterns that were duplicated across
inspection, training, simulation, evaluation, and pipeline services.
"""

import json
import os
import traceback

from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


def read_json(path: str) -> dict:
    """Load a JSON file as a dict."""
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: str, payload: dict, indent: int = 2) -> None:
    """Write ``payload`` as JSON to ``path``.

    Uses ``ensure_ascii=False`` and ``default=str`` so timestamps and other
    non-serializable values fall back to their string representation.
    """
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=indent, ensure_ascii=False, default=str)


def update_card_status(card_path: str, status: str, indent: int = 2) -> None:
    """Overwrite the ``status`` field on an existing card JSON file.

    No-op if the card does not exist. Errors are logged but swallowed so that
    failure-handling code paths cannot themselves raise.
    """
    if not os.path.exists(card_path):
        return
    try:
        card = read_json(card_path)
        card["status"] = status
        write_json(card_path, card, indent=indent)
    except Exception as error:
        logger.warning("Could not update status on card %s: %s", card_path, error)


def mark_card_failed(
    card_path: str,
    error: BaseException | None = None,
    error_message: str | None = None,
    indent: int = 2,
) -> None:
    """Set ``status='failed'`` and persist error details on the card.

    Captures ``error_message`` and ``error_traceback`` so the client can show
    a meaningful failure reason instead of a bare ``failed`` card. Falls back
    to a no-op when the card does not exist. Designed to be safe inside
    failure-handling paths: own exceptions are logged and swallowed.
    """
    if not os.path.exists(card_path):
        return
    try:
        card = read_json(card_path)
        card["status"] = "failed"
        if error is not None:
            card["error_message"] = error_message or f"{type(error).__name__}: {error}"
            card["error_traceback"] = "".join(
                traceback.format_exception(type(error), error, error.__traceback__)
            )
        elif error_message is not None:
            card["error_message"] = error_message
        write_json(card_path, card, indent=indent)
    except Exception as write_error:
        logger.warning("Could not mark card failed %s: %s", card_path, write_error)
