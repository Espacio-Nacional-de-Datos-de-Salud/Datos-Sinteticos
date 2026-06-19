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


SUPERSEDED_FAILURE_MESSAGE = (
    "Ejecución interrumpida: quedó en progreso sin finalizar y se inició otra "
    "ejecución después, por lo que se marcó como fallida automáticamente "
    "(no se produjo un error explícito durante su ejecución)."
)


def fail_superseded_in_progress_runs(
    base_dir: str,
    card_filename: str,
    current_run_id: str | None = None,
) -> list[str]:
    """Flip every other ``in_progress`` card under ``base_dir`` to ``failed``.

    Runs of a given category execute one at a time, so when a new run starts any
    sibling card still reading ``in_progress`` belongs to a run that died without
    ever updating its status (crash, killed worker, lost connection). Left alone
    it shows a perpetual spinner in the UI. This sweep, invoked as a new run
    starts, marks those orphans as failed so only the freshly started run keeps
    spinning.

    ``current_run_id`` (the run just started) is skipped. Returns the ids
    flipped to failed. Errors are logged but never raised: failing to tidy up a
    stale sibling must not block the new run.
    """
    if not os.path.isdir(base_dir):
        return []
    failed: list[str] = []
    for entry in os.listdir(base_dir):
        if entry == current_run_id:
            continue
        card_path = os.path.join(base_dir, entry, card_filename)
        if not os.path.exists(card_path):
            continue
        try:
            if read_json(card_path).get("status") != "in_progress":
                continue
        except Exception:
            continue
        mark_card_failed(card_path, error_message=SUPERSEDED_FAILURE_MESSAGE)
        failed.append(entry)
    if failed:
        logger.info("Marked superseded in_progress runs as failed: %s", failed)
    return failed


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
