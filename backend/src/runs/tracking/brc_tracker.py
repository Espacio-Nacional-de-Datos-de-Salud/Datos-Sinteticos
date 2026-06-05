"""Business-rules-configuration (BRC) run tracker.

A BRC run materialises the inspection's preprocessed data after applying
the PRE phase of the rule manager, so the user can preview and profile
the dataset the model will see before training. Folder layout:

    outputs/brc/brc_<ts>/
        brc_card.json                       Session descriptor + status + progress.
        rules_snapshot.yaml                 Frozen copy of rules.yaml at launch time.
        processed_data/<table>.parquet      Preprocessed tables after apply_all_pre.
        profiling_reports/<table>_profiling_report.html
                                            ydata-profiling reports (only for the
                                            new aux/diff/duration columns produced
                                            by the rules).
        new_columns.json                    Per-table list of columns produced by
                                            the rules (drives the dev badges in the
                                            preview and the profiling subset).
"""

import os
from dataclasses import dataclass

import pandas as pd

from backend.src.config.general import (
    BRC_CARD_FILENAME,
    BRC_DIR,
    BRC_RUN_FOLDER_PREFIX,
    PROCESSED_DATA_DIRNAME,
    refresh_run_timestamp,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import BRC_PHASES, initial_progress
from backend.src.runs.card_io import mark_card_failed, write_json
from backend.src.runs.tracking.base_tracker import BaseRunTracker

logger = get_logger(__name__)


@dataclass(frozen=True)
class BRCSession:
    """Descriptor for a BRC run pre-initialised on disk."""

    brc_id: str
    inspection_id: str
    output_directory: str
    card_path: str
    timestamp: str


class BRCTracker(BaseRunTracker):
    """Per-run lifecycle for a business-rules-configuration job."""

    card_filename = BRC_CARD_FILENAME
    run_kind = "business_rules_configuration"

    def __init__(
        self,
        brc_id: str | None = None,
        output_directory: str | None = None,
        timestamp: str | None = None,
    ) -> None:
        super().__init__()
        if brc_id is None:
            timestamp = timestamp or refresh_run_timestamp()
            brc_id = f"{BRC_RUN_FOLDER_PREFIX}_{timestamp}"
        if output_directory is None:
            output_directory = os.path.join(BRC_DIR, brc_id)

        self.brc_id = brc_id
        self.run_id = brc_id
        self.output_directory = output_directory
        self.timestamp = timestamp or ""

    @classmethod
    def initialize_session(
        cls,
        inspection_id: str,
        name: str | None = None,
    ) -> BRCSession:
        """Create the output folder and an ``in_progress`` card synchronously.

        The API endpoint that launches the job creates the session first so
        it can return ``brc_id`` immediately; the background task picks it
        up via :meth:`from_session`.
        """
        timestamp = refresh_run_timestamp()
        tracker = cls(timestamp=timestamp)
        processed_data_dir = os.path.join(tracker.output_directory, PROCESSED_DATA_DIRNAME)
        os.makedirs(processed_data_dir, exist_ok=True)
        logger.info("Created BRC output directory: %s", tracker.output_directory)

        brc_name = name.strip() if name and name.strip() else tracker.brc_id
        write_json(
            tracker.card_path,
            {
                "brc_id": tracker.brc_id,
                "brc_name": brc_name,
                "inspection_id": inspection_id,
                "status": "in_progress",
                "timestamp": tracker.timestamp,
                "timestamp_ms": int(pd.Timestamp.utcnow().timestamp() * 1000),
                "progress": initial_progress(BRC_PHASES),
            },
        )

        return BRCSession(
            brc_id=tracker.brc_id,
            inspection_id=inspection_id,
            output_directory=tracker.output_directory,
            card_path=tracker.card_path,
            timestamp=timestamp,
        )

    @classmethod
    def from_session(cls, session: BRCSession) -> "BRCTracker":
        return cls(
            brc_id=session.brc_id,
            output_directory=session.output_directory,
            timestamp=session.timestamp,
        )

    def finalize_card(self, payload: dict) -> None:
        payload.setdefault("status", "in_progress")
        write_json(self.card_path, payload)

    def mark_failed(self, error: BaseException) -> None:
        mark_card_failed(self.card_path, error)
