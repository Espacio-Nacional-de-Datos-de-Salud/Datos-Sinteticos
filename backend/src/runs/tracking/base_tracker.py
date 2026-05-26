"""Shared scaffolding for per-run trackers.

Every step-level tracker (model training, simulation, evaluation, inspection)
shares the same on-disk lifecycle:

- a timestamped output folder under ``outputs/<step>/``;
- a ``*_card.json`` written with ``status: "in_progress"`` on entry and
  flipped to ``completed`` / ``failed`` / ``cancelled`` on exit;
- a per-run ``session.log`` capturing every project log line produced
  inside the context;
- a final ``cancellation.unregister`` call on the run id.

``BaseRunTracker`` absorbs that mechanical layer so each concrete tracker
only has to declare its run id, its card filename, and the step-specific
``save_*`` methods. ``PipelineTracker`` does **not** inherit from this base
class — it manages a different session-log setup (a single shared file
handler attached to every logger across multiple sub-job runs) and a
status semantic computed from sub-job outcomes rather than from a single
exception type.
"""

import logging
import os
from types import TracebackType

from backend.src.runs.card_io import read_json, update_card_status, write_json
from backend.src.infrastructure.logging_config import get_logger
from backend.src.runs.tracking._session_logger import (
    attach_session_file_handler,
    detach_session_file_handler,
)

logger = get_logger(__name__)


class BaseRunTracker:
    """Common context-manager lifecycle for step trackers.

    Subclasses must set ``run_id`` and ``output_directory`` before
    ``__enter__`` runs, and set the class attribute ``card_filename``.
    Override ``_on_enter`` for any extra setup (e.g. archiving configs,
    writing the initial card payload) and ``_on_exit`` for any teardown
    that should happen before the status is flipped (e.g. report
    generation).
    """

    #: Name of the card JSON file written inside ``output_directory``.
    card_filename: str = ""

    #: Short label used in log messages ("model", "simulation", ...).
    run_kind: str = "run"

    # Subclasses must assign these in their ``__init__``.
    run_id: str
    output_directory: str

    def __init__(self) -> None:
        self._run_logger: logging.Logger | None = None

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------
    def __enter__(self):
        os.makedirs(self.output_directory, exist_ok=True)
        logger.info("Created %s output directory: %s", self.run_kind, self.output_directory)
        self._run_logger = attach_session_file_handler(self.output_directory, type(self).__module__)
        self._on_enter()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        try:
            self._on_exit(exc_type, exc_val, exc_tb)
        finally:
            from backend.src.infrastructure.cancellation import JobCancelled, unregister

            if exc_type is JobCancelled:
                status = "cancelled"
            elif exc_type is not None:
                status = "failed"
            else:
                status = "completed"

            self.update_card_status(status)
            unregister(self.run_id)
            detach_session_file_handler()

    # ------------------------------------------------------------------
    # Subclass hooks
    # ------------------------------------------------------------------
    def _on_enter(self) -> None:
        """Optional setup hook called after folder + session log are ready."""

    def _on_exit(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Optional teardown hook called before the card status is updated."""

    # ------------------------------------------------------------------
    # Card helpers
    # ------------------------------------------------------------------
    @property
    def card_path(self) -> str:
        return os.path.join(self.output_directory, self.card_filename)

    def write_initial_card(self, payload: dict, *, preserve_progress: bool = True) -> None:
        """Write the run's card with ``status: "in_progress"``.

        When ``preserve_progress`` is True and a card already exists on disk
        (e.g. when an API endpoint pre-created it to expose the run id
        synchronously), its ``progress`` field is kept so polling clients
        see a continuous bar.
        """
        payload = {**payload}
        payload.setdefault("status", "in_progress")
        if preserve_progress and os.path.exists(self.card_path):
            try:
                existing = read_json(self.card_path)
                if "progress" in existing and "progress" not in payload:
                    payload["progress"] = existing["progress"]
                # Preserve any user-assigned functional name written by the API
                # before the background task started (e.g. via PATCH /{id}/name).
                for key in ("model_name", "simulation_name", "inspection_name", "evaluation_name"):
                    if key in existing and key not in payload:
                        payload[key] = existing[key]
            except Exception:
                pass
        write_json(self.card_path, payload, indent=4)
        logger.info("%s card saved to '%s'.", self.run_kind.capitalize(), self.card_path)

    def update_card_status(self, status: str) -> None:
        """Overwrite the ``status`` field on the run's card (no-op if absent)."""
        update_card_status(self.card_path, status, indent=4)

    def patch_card(self, **fields) -> None:
        """Read-modify-write helper to add or overwrite card fields."""
        if not os.path.exists(self.card_path):
            return
        card = read_json(self.card_path)
        card.update(fields)
        write_json(self.card_path, card, indent=4)
