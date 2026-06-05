"""Business-rules-configuration (BRC) flow.

A BRC run takes the preprocessed data from a completed upload (inspection),
applies the PRE phase of the rule manager on top, and persists the
result in its own session folder so the user can review and profile the
dataset that will actually feed the model. Each run snapshots the
rules.yaml that was in effect at launch time so the history stays
reproducible even if the global rules file is edited later.

The flow re-uses building blocks from ``sessions.rules`` (rule manager
construction, snapshot helper) and from the inspection session
(processed-data discovery, profiling writer) so behaviour stays in sync.
"""

import json
import os
import shutil
import threading
from dataclasses import dataclass

import pandas as pd

from backend.src.config.general import (
    BRC_CARD_FILENAME,
    BRC_DIR,
    INSPECTION_METADATA_FILENAME,
    INSPECTIONS_DIR,
    PROCESSED_DATA_DIRNAME,
    PROFILING_REPORT_PATTERN,
    PROFILING_REPORTS_DIRNAME,
)
from backend.src.domain.preprocessing.logical_rules import LogicalRuleManager
from backend.src.domain.preprocessing.logical_rules_serialization import (
    serialize_logical_rule_manager_to_dict,
)
from backend.src.domain.preprocessing.profiling import generate_profile_report
from backend.src.domain.preprocessing.utils import format_relationships
from backend.src.domain.rules_config import extract_rules_and_rejection_config
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import (
    BRC_PHASES,
    BRC_PHASES_NO_PROFILING,
    BRCPhase,
    advance_progress,
)
from backend.src.runs.card_io import mark_card_failed, read_json, write_json
from backend.src.runs.tracking.brc_tracker import BRCSession, BRCTracker
from backend.src.sessions import rules as rules_session

logger = get_logger(__name__)

BRC_RULES_SNAPSHOT_FILENAME = rules_session.RULES_SNAPSHOT_FILENAME
BRC_RULE_MANAGER_FILENAME = rules_session.INSPECTION_RULE_MANAGER_FILENAME
NEW_COLUMNS_FILENAME = "new_columns.json"


@dataclass(frozen=True)
class BRCResult:
    brc_id: str
    brc_name: str
    inspection_id: str
    output_directory: str
    tables: dict[str, int]
    new_columns: dict[str, list[str]]
    rules_count: int


def initialize_brc_session(inspection_id: str, name: str | None = None) -> BRCSession:
    """Create the BRC folder + ``in_progress`` card synchronously."""
    return BRCTracker.initialize_session(inspection_id=inspection_id, name=name)


def run_brc_flow(
    inspection_id: str,
    rules_config_path: str,
    enable_profiling: bool = True,
    session: BRCSession | None = None,
    cancel_event: threading.Event | None = None,
) -> BRCResult | None:
    """Apply the rules' PRE phase to the inspection's preprocessed data.

    Args:
        inspection_id: Folder name of the source upload/inspection.
        rules_config_path: Path to the rules YAML to apply. The file is
            snapshotted into the run folder so subsequent edits to the
            global file don't change what this run represents.
        enable_profiling: Whether to run ydata-profiling on the new columns.
        session: Pre-initialised BRCSession from
            :func:`initialize_brc_session`. When ``None`` it is created on
            the fly (the run id is then only available after the call returns).
        cancel_event: Optional event the caller can set to abort early.

    Returns:
        BRCResult on success, ``None`` on failure.
    """
    session = session or initialize_brc_session(inspection_id)
    phases = BRC_PHASES if enable_profiling else BRC_PHASES_NO_PROFILING

    if cancel_event is not None and cancel_event.is_set():
        logger.info("BRC run %s cancelled before execution.", session.brc_id)
        from backend.src.runs.card_io import update_card_status

        update_card_status(session.card_path, "cancelled")
        return None

    try:
        with BRCTracker.from_session(session) as tracker:
            inspection_dir = os.path.join(INSPECTIONS_DIR, inspection_id)
            if not os.path.isdir(inspection_dir):
                raise FileNotFoundError(f"Upload not found: {inspection_dir}")

            advance_progress(tracker.card_path, phases, BRCPhase.LOADING)
            source_processed_dir = os.path.join(inspection_dir, PROCESSED_DATA_DIRNAME)
            if not os.path.isdir(source_processed_dir):
                raise FileNotFoundError(
                    f"Processed data missing for upload {inspection_id}: {source_processed_dir}"
                )

            inspection_metadata_path = os.path.join(
                inspection_dir, INSPECTION_METADATA_FILENAME
            )
            inspection_metadata = read_json(inspection_metadata_path)
            relationships = inspection_metadata.get("relationships", {"pks": {}, "fks": []})

            processed_data: dict[str, pd.DataFrame] = {}
            for filename in sorted(os.listdir(source_processed_dir)):
                if filename.endswith(".parquet"):
                    table_name = os.path.splitext(filename)[0]
                    processed_data[table_name] = pd.read_parquet(
                        os.path.join(source_processed_dir, filename)
                    )

            original_columns = {tbl: list(df.columns) for tbl, df in processed_data.items()}

            # Snapshot rules.yaml *before* applying so the history is
            # reproducible even if the user edits the global file later.
            snapshot_path = os.path.join(
                tracker.output_directory, BRC_RULES_SNAPSHOT_FILENAME
            )
            try:
                shutil.copyfile(rules_config_path, snapshot_path)
            except OSError as copy_error:
                logger.warning("Could not snapshot rules file: %s", copy_error)
                snapshot_path = rules_config_path

            advance_progress(tracker.card_path, phases, BRCPhase.APPLYING_RULES)
            formatted_relationships = format_relationships(relationships)
            rule_manager = LogicalRuleManager()
            rule_manager.relationships = formatted_relationships
            extracted_rules, rejection_config = extract_rules_and_rejection_config(snapshot_path)
            for rule in extracted_rules:
                rule_manager.add_rule(rule)
            rule_manager.rejection_sampling_config = rejection_config.as_dict()

            processed_with_rules = rule_manager.apply_all_pre(
                processed_data, relationships=formatted_relationships
            )

            advance_progress(tracker.card_path, phases, BRCPhase.SAVING_PROCESSED)
            dest_processed_dir = os.path.join(tracker.output_directory, PROCESSED_DATA_DIRNAME)
            os.makedirs(dest_processed_dir, exist_ok=True)
            for table_name, df in processed_with_rules.items():
                df.to_parquet(os.path.join(dest_processed_dir, f"{table_name}.parquet"))

            # Persist the rule manager alongside the parquets so the training
            # flow can pick it up and skip re-applying PRE when it reads from
            # this BRC run. Mirrors what `sessions.rules.apply_inspection_rules`
            # writes inside the inspection folder.
            from backend.src.runs.card_io import write_json as _write_json

            _write_json(
                os.path.join(tracker.output_directory, BRC_RULE_MANAGER_FILENAME),
                serialize_logical_rule_manager_to_dict(rule_manager),
                indent=2,
            )

            # Identify columns that did not exist in the source upload's
            # processed data — these are the ones produced by the rules
            # (aux_col, duration_*, diff_*, derived-column outputs, …). The
            # frontend uses this list to drive the dev badges in the preview
            # and to subset the profiling reports.
            new_columns: dict[str, list[str]] = {}
            for table_name, df in processed_with_rules.items():
                src = set(original_columns.get(table_name, []))
                novel = [c for c in df.columns if c not in src]
                if novel:
                    new_columns[table_name] = novel

            with open(
                os.path.join(tracker.output_directory, NEW_COLUMNS_FILENAME),
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(new_columns, handle, indent=2, ensure_ascii=False)

            if enable_profiling:
                advance_progress(tracker.card_path, phases, BRCPhase.PROFILING_REPORTS)
                # ydata-profiling on a subset: only the new columns per
                # table. If a table has no new columns we skip it entirely.
                profiling_input = {
                    tbl: df[new_columns[tbl]]
                    for tbl, df in processed_with_rules.items()
                    if tbl in new_columns
                }
                if profiling_input:
                    profiles = generate_profile_report(profiling_input) or {}
                    profiling_dir = os.path.join(
                        tracker.output_directory, PROFILING_REPORTS_DIRNAME
                    )
                    os.makedirs(profiling_dir, exist_ok=True)
                    for name, profile in profiles.items():
                        report_path = os.path.join(
                            profiling_dir, PROFILING_REPORT_PATTERN.format(name=name)
                        )
                        profile.to_file(report_path)

            tables = {tbl: int(len(df)) for tbl, df in processed_with_rules.items()}

            existing_card = read_json(session.card_path)
            brc_name = existing_card.get("brc_name") or session.brc_id

            tracker.finalize_card(
                {
                    "brc_id": session.brc_id,
                    "brc_name": brc_name,
                    "step_name": brc_name,
                    "inspection_id": inspection_id,
                    "timestamp": session.timestamp,
                    "tables": tables,
                    "new_columns": new_columns,
                    "rules_count": len(rule_manager.rules),
                    "rules_snapshot_path": snapshot_path,
                    "source_rules_config_path": rules_config_path,
                    "enable_profiling": enable_profiling,
                }
            )

            logger.info(
                "BRC run saved: %s (tables=%s, new_cols=%s).",
                session.brc_id,
                list(tables),
                {t: len(c) for t, c in new_columns.items()},
            )

            return BRCResult(
                brc_id=session.brc_id,
                brc_name=brc_name,
                inspection_id=inspection_id,
                output_directory=tracker.output_directory,
                tables=tables,
                new_columns=new_columns,
                rules_count=len(rule_manager.rules),
            )

    except Exception as error:
        logger.error("BRC flow failed: %s", error, exc_info=True)
        mark_card_failed(session.card_path, error)
        return None


# ----------------------------------------------------------------------
# Read-side helpers used by the API layer
# ----------------------------------------------------------------------


def list_brc_runs(inspection_id: str | None = None) -> list[dict]:
    """Return every BRC card on disk, optionally filtered by upload.

    Cards are enriched with ``duration_seconds`` and ``started_at_ms``
    derived from the folder timestamp, mirroring how the inspections
    catalogue exposes that data to the API layer.
    """
    from backend.src.runs.catalog._base import (
        folder_started_at_ms,
        read_total_run_duration_seconds,
    )

    if not os.path.isdir(BRC_DIR):
        return []
    out: list[dict] = []
    for entry in sorted(os.listdir(BRC_DIR), reverse=True):
        folder = os.path.join(BRC_DIR, entry)
        card_path = os.path.join(folder, BRC_CARD_FILENAME)
        if not os.path.exists(card_path):
            continue
        try:
            card = read_json(card_path)
        except Exception as exc:
            logger.warning("Skipping unreadable BRC card '%s': %s", card_path, exc)
            continue
        if inspection_id and card.get("inspection_id") != inspection_id:
            continue
        card.setdefault("duration_seconds", read_total_run_duration_seconds(folder))
        card.setdefault(
            "started_at_ms", folder_started_at_ms(folder, "brc")
        )
        out.append(card)
    return out


def load_brc_card(brc_id: str) -> dict:
    card_path = os.path.join(BRC_DIR, brc_id, BRC_CARD_FILENAME)
    if not os.path.exists(card_path):
        raise FileNotFoundError(f"BRC run not found: {brc_id}")
    return read_json(card_path)


def rename_brc_run(brc_id: str, new_name: str) -> dict:
    card = load_brc_card(brc_id)
    card["brc_name"] = new_name.strip() or brc_id
    write_json(os.path.join(BRC_DIR, brc_id, BRC_CARD_FILENAME), card)
    return card


def delete_brc_run(brc_id: str) -> None:
    target = os.path.join(BRC_DIR, brc_id)
    if not os.path.isdir(target):
        raise FileNotFoundError(f"BRC run not found: {brc_id}")
    shutil.rmtree(target)


def brc_run_dir(brc_id: str) -> str:
    target = os.path.join(BRC_DIR, brc_id)
    if not os.path.isdir(target):
        raise FileNotFoundError(f"BRC run not found: {brc_id}")
    return target


def brc_dataset_paths(brc_id: str) -> dict[str, str]:
    """Return ``{table: parquet_path}`` for the run's preprocessed data."""
    processed_dir = os.path.join(brc_run_dir(brc_id), PROCESSED_DATA_DIRNAME)
    if not os.path.isdir(processed_dir):
        return {}
    out: dict[str, str] = {}
    for filename in sorted(os.listdir(processed_dir)):
        if filename.endswith(".parquet"):
            out[os.path.splitext(filename)[0]] = os.path.join(processed_dir, filename)
    return out


def brc_new_columns(brc_id: str) -> dict[str, list[str]]:
    path = os.path.join(brc_run_dir(brc_id), NEW_COLUMNS_FILENAME)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def brc_profiling_reports(brc_id: str) -> list[str]:
    """Return the list of table names that have a profiling report on disk."""
    profiling_dir = os.path.join(brc_run_dir(brc_id), PROFILING_REPORTS_DIRNAME)
    if not os.path.isdir(profiling_dir):
        return []
    suffix = PROFILING_REPORT_PATTERN.format(name="")
    out: list[str] = []
    for filename in sorted(os.listdir(profiling_dir)):
        if filename.endswith(suffix):
            out.append(filename[: -len(suffix)])
    return out


def brc_profiling_report_path(brc_id: str, table: str) -> str:
    path = os.path.join(
        brc_run_dir(brc_id),
        PROFILING_REPORTS_DIRNAME,
        PROFILING_REPORT_PATTERN.format(name=table),
    )
    if not os.path.exists(path):
        raise FileNotFoundError(f"Profiling report not found: {brc_id}/{table}")
    return path


def brc_rules_snapshot_path(brc_id: str) -> str:
    path = os.path.join(brc_run_dir(brc_id), BRC_RULES_SNAPSHOT_FILENAME)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Rules snapshot not found for BRC run: {brc_id}")
    return path
