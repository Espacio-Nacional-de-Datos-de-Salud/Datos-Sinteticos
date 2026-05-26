"""Shared primitives for the per-domain catalog modules.

The five run-type catalogs (inspections, models, simulations, evaluations,
pipelines) all share the same on-disk layout: one timestamped folder per run
under a base directory, each holding a ``*_card.json`` descriptor. The helpers
below capture the parts of that contract that were copy-pasted across modules:

- ``folder_has_files``      — detect totally empty run folders.
- ``parse_folder_start_time`` — recover the run timestamp from the folder name.
- ``find_run_cleanup_candidates`` — apply the standard policy
  (empty folder vs. dead/stale orphan) to a run directory.
- ``purge_all_runs``        — wipe every immediate subdirectory of a base dir.
- ``delete_run_folders``    — small helper to delete a list of run ids.

Modules with quirks (pipelines: legacy summary card + artifact check; models:
skip when linked simulations exist) still reuse the low-level helpers and only
keep their domain-specific orchestration locally.
"""

import glob
import json
import os
import shutil
from datetime import datetime, timedelta, timezone


def folder_started_at_ms(folder: str, folder_prefix: str) -> int | None:
    """Parse the UTC start time encoded in a ``<prefix>_YYYYMMDD_HHMMSS`` folder
    and return it as epoch milliseconds.

    This is the single source of truth for the "in-progress elapsed time"
    counter shown by the UI: the folder name is set once at run creation, is
    always UTC (``pd.Timestamp.utcnow``), and is never rewritten — unlike the
    card's ``timestamp`` / ``timestamp_ms`` which can be refreshed mid-run.
    """
    folder_name = os.path.basename(folder)
    start_time = parse_folder_start_time(folder_name, folder_prefix)
    if start_time is None:
        return None
    return int(start_time.replace(tzinfo=timezone.utc).timestamp() * 1000)


def read_total_run_duration_seconds(folder: str) -> float | None:
    """Return the total duration recorded in ``time_profiling_report.json``.

    Returns ``None`` if the file is missing, unreadable, or has no recorded total.
    Imported lazily to avoid a circular import on ``config.general``.
    """
    from backend.src.config.general import TIME_PROFILING_REPORT_FILENAME

    path = os.path.join(folder, TIME_PROFILING_REPORT_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    total = payload.get("total_seconds")
    if isinstance(total, (int, float)) and total > 0:
        return float(total)
    return None


def folder_has_files(folder: str) -> bool:
    """Returns True if the folder tree contains at least one file."""
    for _, _, files in os.walk(folder):
        if files:
            return True
    return False


def parse_folder_start_time(folder_name: str, prefix: str) -> datetime | None:
    """Parse the run start time encoded in a ``<prefix>_YYYYMMDD_HHMMSS`` folder name.

    Returns ``None`` if the suffix doesn't match the expected pattern.
    """
    suffix = folder_name[len(prefix) + 1 :]
    try:
        return datetime.strptime(suffix, "%Y%m%d_%H%M%S")
    except ValueError:
        return None


def find_run_cleanup_candidates(
    base_dir: str,
    folder_prefix: str,
    card_filename: str,
    stale_hours: int = 24,
) -> tuple[list[str], list[str]]:
    """Identify run folders eligible for cleanup using the standard policy.

    Two categories are returned:

    - **empty**: the folder tree contains no files at all.
    - **orphans**: the folder has content but is definitively dead:
        - card status ``"failed"``
        - card missing or unreadable AND folder is older than ``stale_hours``
        - card status ``"in_progress"`` AND folder is older than ``stale_hours``

    Returns ``(empty_ids, orphan_ids)``.
    """
    cutoff = datetime.now() - timedelta(hours=stale_hours)
    run_folders = sorted(glob.glob(os.path.join(base_dir, folder_prefix + "_*")))

    empty_ids: list[str] = []
    orphan_ids: list[str] = []

    for folder in run_folders:
        run_id = os.path.basename(folder)
        card_path = os.path.join(folder, card_filename)

        if not folder_has_files(folder):
            empty_ids.append(run_id)
            continue

        if not os.path.exists(card_path):
            start_time = parse_folder_start_time(run_id, folder_prefix)
            if start_time is not None and start_time < cutoff:
                orphan_ids.append(run_id)
            continue

        try:
            with open(card_path, encoding="utf-8") as handle:
                card = json.load(handle)
        except Exception:
            start_time = parse_folder_start_time(run_id, folder_prefix)
            if start_time is not None and start_time < cutoff:
                orphan_ids.append(run_id)
            continue

        status = card.get("status")
        if status in ("failed", "cancelled"):
            orphan_ids.append(run_id)
        elif status == "in_progress":
            start_time = parse_folder_start_time(run_id, folder_prefix)
            if start_time is not None and start_time < cutoff:
                orphan_ids.append(run_id)

    return empty_ids, orphan_ids


def delete_run_folders(base_dir: str, run_ids: list[str]) -> list[str]:
    """``shutil.rmtree`` each ``base_dir/run_id`` and return the ones processed."""
    deleted: list[str] = []
    for run_id in run_ids:
        shutil.rmtree(os.path.join(base_dir, run_id), ignore_errors=True)
        deleted.append(run_id)
    return deleted


def purge_all_runs(base_dir: str) -> list[str]:
    """Delete every immediate subdirectory of ``base_dir``. Returns deleted ids."""
    deleted: list[str] = []
    if not os.path.isdir(base_dir):
        return deleted
    for entry in os.listdir(base_dir):
        path = os.path.join(base_dir, entry)
        if os.path.isdir(path):
            shutil.rmtree(path, ignore_errors=True)
            deleted.append(entry)
    return deleted
