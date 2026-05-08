"""CLI and helpers to list inspection sessions awaiting training."""

import argparse
import glob
import json
import os
import shutil
from typing import Literal

from backend.src.config.general import (
    INSPECTION_CARD_FILENAME,
    INSPECTION_RUN_FOLDER_PREFIX,
    INSPECTIONS_DIR,
)
from backend.src.core.catalog._base import (
    delete_run_folders,
    find_run_cleanup_candidates,
    purge_all_runs,
)
from backend.src.core.card_io import read_json, write_json
from backend.src.core.logging_config import get_logger

logger = get_logger(__name__)


def list_available_inspections() -> list[dict]:
    """Scan the inspections directory and return one entry per session.

    Returns:
        List of dicts with ``inspection_id``, ``inspection_name``, ``folder``, ``timestamp``,
        ``tables`` (comma-separated with row counts), and ``file_paths``.
    """
    run_folders = sorted(
        glob.glob(os.path.join(INSPECTIONS_DIR, INSPECTION_RUN_FOLDER_PREFIX + "_*")),
        reverse=True,
    )

    inspections: list[dict] = []
    for folder in run_folders:
        card_path = os.path.join(folder, INSPECTION_CARD_FILENAME)
        if not os.path.exists(card_path):
            continue

        info: dict = {
            "inspection_id": os.path.basename(folder),
            "inspection_name": "",
            "status": "",
            "folder": folder,
            "timestamp": "",
            "tables": {},
            "file_paths": [],
            "progress": None,
        }

        try:
            with open(card_path, encoding="utf-8") as handle:
                card = json.load(handle)

            info["inspection_name"] = card.get("inspection_name", "") or info["inspection_id"]
            info["status"] = card.get("status", "")
            info["timestamp"] = card.get("timestamp", "")
            info["tables"] = card.get("tables", {}) or {}
            info["file_paths"] = card.get("file_paths", []) or []
            info["progress"] = card.get("progress")
        except Exception as exc:
            logger.warning("Error reading inspection card from %s: %s", folder, exc)

        inspections.append(info)

    return inspections


def find_duplicate_candidates() -> list[str]:
    """Find completed inspections that are exact duplicates of a newer run.

    Two inspections are duplicates when their ``file_paths`` sets are identical
    (order-insensitive). For each such group, the most recent run (highest
    folder timestamp) is kept; all older ones are returned as candidates.

    Only ``completed`` inspections are compared — failed/in-progress runs are
    never deleted this way.
    """
    completed = [i for i in list_available_inspections() if i.get("status") == "completed"]

    from collections import defaultdict

    groups: dict[tuple, list[dict]] = defaultdict(list)
    for inspection in completed:
        paths = inspection.get("file_paths") or []
        key = tuple(sorted(os.path.basename(p) for p in paths))
        if key:
            groups[key].append(inspection)

    duplicate_ids: list[str] = []
    for group in groups.values():
        if len(group) <= 1:
            continue
        # Sort ascending by folder name (timestamp encoded), keep the last.
        sorted_group = sorted(group, key=lambda i: i["inspection_id"])
        for inspection in sorted_group[:-1]:
            duplicate_ids.append(inspection["inspection_id"])

    return duplicate_ids


def find_cleanup_candidates(stale_hours: int = 24) -> tuple[list[str], list[str]]:
    """Identify inspection folders eligible for cleanup.

    See ``base.find_run_cleanup_candidates`` for the policy.
    """
    return find_run_cleanup_candidates(
        base_dir=INSPECTIONS_DIR,
        folder_prefix=INSPECTION_RUN_FOLDER_PREFIX,
        card_filename=INSPECTION_CARD_FILENAME,
        stale_hours=stale_hours,
    )


def cleanup_inspections(
    mode: Literal["empty", "orphans", "duplicates", "both", "all"] = "both",
    stale_hours: int = 24,
) -> tuple[list[str], list[str], list[str]]:
    """Delete inspection folders selected by the catalog cleanup policy.

    ``both`` covers empty + orphans (backward-compatible default).
    ``all`` additionally removes exact duplicate completed runs.
    ``duplicates`` removes only duplicate runs.
    """
    empty_ids, orphan_ids = find_cleanup_candidates(stale_hours=stale_hours)
    duplicate_ids = find_duplicate_candidates() if mode in ("duplicates", "all") else []

    to_delete_empty = empty_ids if mode in ("empty", "both", "all") else []
    to_delete_orphans = orphan_ids if mode in ("orphans", "both", "all") else []
    to_delete_duplicates = duplicate_ids if mode in ("duplicates", "all") else []

    return (
        delete_run_folders(INSPECTIONS_DIR, to_delete_empty),
        delete_run_folders(INSPECTIONS_DIR, to_delete_orphans),
        delete_run_folders(INSPECTIONS_DIR, to_delete_duplicates),
    )


def delete_inspection(inspection_id: str) -> bool:
    """Delete a single inspection folder. Returns False if the id is unknown."""
    if not any(i["inspection_id"] == inspection_id for i in list_available_inspections()):
        return False
    shutil.rmtree(f"{INSPECTIONS_DIR}/{inspection_id}", ignore_errors=True)
    return True


def purge_all_inspections() -> list[str]:
    """Delete every inspection folder regardless of status. Returns deleted ids."""
    return purge_all_runs(INSPECTIONS_DIR)


def rename_inspection(inspection_id: str, name: str) -> bool:
    """Update ``inspection_name`` in the inspection card. Returns False if not found."""
    card_path = os.path.join(INSPECTIONS_DIR, inspection_id, INSPECTION_CARD_FILENAME)
    if not os.path.exists(card_path):
        return False
    card = read_json(card_path)
    card["inspection_name"] = name
    write_json(card_path, card)
    return True


def format_available_inspections(inspections: list[dict], output: str = "json") -> str:
    """Render the inspections list as JSON or as an ASCII table."""
    output_normalized = output.strip().lower()
    if output_normalized == "json":
        return json.dumps(inspections, indent=2, ensure_ascii=False)

    if output_normalized != "table":
        raise ValueError("output must be either 'json' or 'table'")

    headers = ["inspection_name", "inspection_id", "tables (size)", "timestamp"]

    def _pretty_timestamp(raw_value: object) -> str:
        value = str(raw_value or "").strip()
        if not value:
            return "-"
        if len(value) == 15 and value[8] == "_" and value.replace("_", "").isdigit():
            return (
                f"{value[:4]}-{value[4:6]}-{value[6:8]} {value[9:11]}:{value[11:13]}:{value[13:15]}"
            )
        return value

    rows: list[list[str]] = []
    for inspection in inspections:
        tables = inspection.get("tables", {})
        if isinstance(tables, dict) and tables:
            tables_text = ", ".join(f"{name} ({size})" for name, size in sorted(tables.items()))
        else:
            tables_text = "-"
        rows.append(
            [
                str(inspection.get("inspection_name", "")),
                str(inspection.get("inspection_id", "")),
                tables_text,
                _pretty_timestamp(inspection.get("timestamp", "")),
            ]
        )

    if not rows:
        return "No inspections found."

    widths = [len(h) for h in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    def _fmt(values: list[str]) -> str:
        return " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(values))

    sep = "-+-".join("-" * width for width in widths)
    lines = [_fmt(headers), sep]
    lines.extend(_fmt(row) for row in rows)
    return "\n".join(lines)


def list_available_inspections_output(output: str = "json") -> str:
    """Return available inspections formatted as JSON or table."""
    return format_available_inspections(list_available_inspections(), output=output)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="List inspection sessions awaiting training")
    parser.add_argument("--format", choices=["json", "table"], default="json")
    args = parser.parse_args()
    print(list_available_inspections_output(output=args.format))


if __name__ == "__main__":
    main()
