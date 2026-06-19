"""Inspection-run tracker.

``InspectionTracker`` is the counterpart to ``ModelTracker`` /
``SimulationTracker`` / ``EvaluationTracker`` for the inspection step
(load + preprocess + autodetect). Previously the inspection service
managed its own folder, card, and status transitions inline in
``services/inspection.py``; this class moves that mechanical lifecycle into
``core/tracking/`` so every step is consistent.

The inspection step is special in two ways the API still relies on:

- The session folder and the initial ``in_progress`` card are written
  *synchronously* by ``InspectionTracker.initialize_session``, so that the
  API endpoint can return the ``inspection_id`` to the caller before the
  background task that actually runs the work has started.
- The card is built up progressively (the final payload — table sizes,
  rules paths, profiling flag — is only known once the flow has finished),
  so the tracker exposes ``finalize_card`` for the flow to call before
  exiting.
"""

import os
from dataclasses import dataclass

import pandas as pd

from backend.src.config.general import (
    INSPECTION_CARD_FILENAME,
    INSPECTION_RUN_FOLDER_PREFIX,
    INSPECTIONS_DIR,
    PROCESSED_DATA_DIRNAME,
    refresh_run_timestamp,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import INSPECTION_PHASES, initial_progress
from backend.src.runs.card_io import (
    fail_superseded_in_progress_runs,
    mark_card_failed,
    write_json,
)
from backend.src.runs.tracking.base_tracker import BaseRunTracker

logger = get_logger(__name__)


@dataclass(frozen=True)
class InspectionSession:
    """Bookkeeping for a session created on disk but not yet executed.

    The API layer calls ``InspectionTracker.initialize_session`` to
    materialize the folder + ``in_progress`` card synchronously, then hands
    this descriptor to a background task that opens an ``InspectionTracker``
    context manager around the actual flow. Keeping the inspection id,
    output directory and timestamp on this object means the background task
    is independent of any ``ContextVar`` that might not propagate across
    threads (FastAPI ``BackgroundTasks`` may run in a different context
    than the request that scheduled it).
    """

    inspection_id: str
    output_directory: str
    card_path: str
    timestamp: str


class InspectionTracker(BaseRunTracker):
    """Manages folder, card, and session logging for one inspection run.

    Use as a context manager wrapping the load + preprocess + autodetect
    flow. The folder and initial card are usually pre-created by
    :meth:`initialize_session` so the API can expose the inspection id
    immediately; the context manager then preserves the existing
    ``progress`` field and updates the card status on exit.

    Example:
        >>> session = InspectionTracker.initialize_session()
        >>> with InspectionTracker.from_session(session) as tracker:
        ...     # run flow, calling tracker.finalize_card(...) on success
        ...     ...
    """

    card_filename = INSPECTION_CARD_FILENAME
    run_kind = "inspection"

    def __init__(
        self,
        inspection_id: str | None = None,
        output_directory: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        super().__init__()
        if inspection_id is None:
            timestamp = timestamp or refresh_run_timestamp()
            inspection_id = f"{INSPECTION_RUN_FOLDER_PREFIX}_{timestamp}"
        if output_directory is None:
            output_directory = os.path.join(INSPECTIONS_DIR, inspection_id)

        self.inspection_id = inspection_id
        self.run_id = inspection_id
        self.output_directory = output_directory
        self.timestamp = timestamp or ""

    # ------------------------------------------------------------------
    # Session pre-initialization (synchronous; used by the API layer)
    # ------------------------------------------------------------------
    @classmethod
    def initialize_session(cls, name: str | None = None) -> InspectionSession:
        """Create the output folder and the ``in_progress`` inspection card.

        Refreshes the run timestamp and writes the initial card so callers
        can immediately query the inspection by id. Returns a descriptor that
        can later be passed to :meth:`from_session` inside a background task.
        """
        timestamp = refresh_run_timestamp()
        tracker = cls(timestamp=timestamp)
        processed_data_dir = os.path.join(tracker.output_directory, PROCESSED_DATA_DIRNAME)
        os.makedirs(processed_data_dir, exist_ok=True)
        logger.info("Created inspection output directory: %s", tracker.output_directory)

        # Supersede any earlier inspection/upload still stuck in_progress: it
        # died without updating its status and would otherwise spin forever.
        fail_superseded_in_progress_runs(
            INSPECTIONS_DIR,
            INSPECTION_CARD_FILENAME,
            current_run_id=tracker.inspection_id,
        )

        inspection_name = name.strip() if name and name.strip() else tracker.inspection_id
        write_json(
            tracker.card_path,
            {
                "inspection_id": tracker.inspection_id,
                "inspection_name": inspection_name,
                "status": "in_progress",
                "timestamp": tracker.timestamp,
                "timestamp_ms": int(pd.Timestamp.utcnow().timestamp() * 1000),
                # The flow patches the total once profiling is known (it
                # may drop the trailing phase). Default to the full list so
                # the initial poll already shows a sensible bar.
                "progress": initial_progress(INSPECTION_PHASES),
            },
        )

        return InspectionSession(
            inspection_id=tracker.inspection_id,
            output_directory=tracker.output_directory,
            card_path=tracker.card_path,
            timestamp=timestamp,
        )

    @classmethod
    def from_session(cls, session: InspectionSession) -> "InspectionTracker":
        """Build a tracker bound to a pre-initialized session."""
        return cls(
            inspection_id=session.inspection_id,
            output_directory=session.output_directory,
            timestamp=session.timestamp,
        )

    # ------------------------------------------------------------------
    # Public API used by the inspection flow
    # ------------------------------------------------------------------
    def finalize_card(self, payload: dict) -> None:
        """Replace the card with the final summary payload.

        Called by the flow once preprocessing + autodetection have finished
        successfully. The base class will still flip ``status`` to
        ``completed`` (or ``failed`` / ``cancelled``) on context exit, so
        callers should not set it here.
        """
        payload.setdefault("status", "in_progress")
        write_json(self.card_path, payload)

    def mark_failed(self, error: BaseException) -> None:
        """Persist a failure reason on the card (status flip handled on exit)."""
        mark_card_failed(self.card_path, error)
