"""CLI and helpers to list evaluations available under ``outputs/evaluations/``.

Scans evaluation folders and reads their ``eval_card.json``.
"""

import argparse
import glob as _glob
import json
import os
import shutil
from typing import Literal

from backend.src.config.general import (
    EVAL_CARD_FILENAME,
    EVALUATION_RUN_FOLDER_PREFIX,
    EVALUATIONS_DIR,
)
from backend.src.runs.catalog._base import (
    delete_run_folders,
    find_run_cleanup_candidates,
    purge_all_runs,
)
from backend.src.runs.card_io import read_json, write_json
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


def list_available_evaluations() -> list[dict]:
    """Lists all evaluation runs with their metadata.

    Scans the evaluations directory for folders and extracts summary
    information from ``eval_card.json`` when available.

    Returns:
        list[dict]: List of evaluation info dicts.
    """
    run_folders = sorted(
        _glob.glob(os.path.join(EVALUATIONS_DIR, EVALUATION_RUN_FOLDER_PREFIX + "_*")),
        reverse=True,
    )

    evaluations = []
    for folder in run_folders:
        eval_card_path = os.path.join(folder, EVAL_CARD_FILENAME)

        has_card = os.path.exists(eval_card_path)

        # Include empty ones? It's fine unless we use cleanup
        eval_info: dict = {
            "evaluation_id": os.path.basename(folder),
            "evaluation_name": None,
            "folder": folder,
            "status": "",
            "timestamp": "",
            "model_id": None,
            "simulation_id": None,
            "pipeline_id": None,
            "progress": None,
        }

        if has_card:
            try:
                with open(eval_card_path, encoding="utf-8") as f:
                    card = json.load(f)
                eval_info["evaluation_name"] = card.get("evaluation_name") or card.get(
                    "evaluation_id"
                )
                eval_info["status"] = card.get("status", "")
                eval_info["timestamp"] = card.get("timestamp", "")
                eval_info["model_id"] = card.get("model_id")
                eval_info["simulation_id"] = card.get("simulation_id")
                eval_info["pipeline_id"] = card.get("pipeline_id")
                eval_info["job_name"] = card.get("job_name")
                eval_info["metrics_evaluated"] = card.get("metrics_evaluated", [])
                eval_info["progress"] = card.get("progress")
            except Exception as exc:
                logger.warning("Error reading eval_card from %s: %s", folder, exc)

        evaluations.append(eval_info)

    return evaluations


def find_cleanup_candidates(stale_hours: int = 24) -> tuple[list[str], list[str]]:
    """Identify evaluation folders eligible for cleanup.

    See ``base.find_run_cleanup_candidates`` for the policy.
    """
    return find_run_cleanup_candidates(
        base_dir=EVALUATIONS_DIR,
        folder_prefix=EVALUATION_RUN_FOLDER_PREFIX,
        card_filename=EVAL_CARD_FILENAME,
        stale_hours=stale_hours,
    )


def cleanup_evaluations(
    mode: Literal["empty", "orphans", "both"] = "both",
    stale_hours: int = 24,
) -> tuple[list[str], list[str]]:
    empty_ids, orphan_ids = find_cleanup_candidates(stale_hours=stale_hours)
    to_delete_empty = empty_ids if mode in ("empty", "both") else []
    to_delete_orphans = orphan_ids if mode in ("orphans", "both") else []
    return (
        delete_run_folders(EVALUATIONS_DIR, to_delete_empty),
        delete_run_folders(EVALUATIONS_DIR, to_delete_orphans),
    )


def delete_evaluation(evaluation_id: str) -> bool:
    if not any(e["evaluation_id"] == evaluation_id for e in list_available_evaluations()):
        return False
    shutil.rmtree(f"{EVALUATIONS_DIR}/{evaluation_id}", ignore_errors=True)
    return True


def purge_all_evaluations() -> list[str]:
    """Delete every evaluation folder regardless of status."""
    return purge_all_runs(EVALUATIONS_DIR)


def rename_evaluation(evaluation_id: str, name: str) -> bool:
    """Update ``evaluation_name`` in the evaluation card. Returns False if not found."""
    card_path = os.path.join(EVALUATIONS_DIR, evaluation_id, EVAL_CARD_FILENAME)
    if not os.path.exists(card_path):
        return False
    card = read_json(card_path)
    card["evaluation_name"] = name
    write_json(card_path, card)
    return True


def format_available_evaluations(evaluations: list[dict], output: str = "json") -> str:
    output_normalized = output.strip().lower()
    if output_normalized == "json":
        return json.dumps(evaluations, indent=2, ensure_ascii=False)

    if output_normalized != "table":
        raise ValueError("output must be either 'json' or 'table'")

    headers = [
        "evaluation_id",
        "simulation_id",
        "pipeline_id",
        "status",
        "metrics count",
        "timestamp",
    ]

    def _pretty_timestamp(raw_value: object) -> str:
        value = str(raw_value or "").strip()
        if not value:
            return "-"
        if len(value) == 15 and value[8] == "_" and value.replace("_", "").isdigit():
            return (
                f"{value[:4]}-{value[4:6]}-{value[6:8]} {value[9:11]}:{value[11:13]}:{value[13:15]}"
            )
        if "T" in value:
            return value.replace("T", " ").replace("Z", "")
        return value

    rows = []
    for eva in evaluations:
        metrics = eva.get("metrics_evaluated", [])
        metrics_count = str(len(metrics)) if isinstance(metrics, list) else "-"

        rows.append(
            [
                str(eva.get("evaluation_id", "")),
                str(eva.get("simulation_id") or "-"),
                str(eva.get("pipeline_id") or "none"),
                str(eva.get("status") or "-"),
                metrics_count,
                _pretty_timestamp(eva.get("timestamp", "")),
            ]
        )

    if not rows:
        return "No evaluations found."

    widths = [len(h) for h in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    max_widths = [24, 24, 20, 15, 13, 19]
    widths = [min(width, max_widths[idx]) for idx, width in enumerate(widths)]

    def _truncate(value: str, max_len: int) -> str:
        if len(value) <= max_len:
            return value
        if max_len <= 3:
            return value[:max_len]
        return value[: max_len - 3] + "..."

    def _fmt(values: list[str]) -> str:
        return " | ".join(
            _truncate(value, widths[idx]).ljust(widths[idx]) for idx, value in enumerate(values)
        )

    sep = "-+-".join("-" * width for width in widths)
    lines = [_fmt(headers), sep]
    lines.extend(_fmt(row) for row in rows)
    return "\n".join(lines)


def list_available_evaluations_output(output: str = "json") -> str:
    return format_available_evaluations(list_available_evaluations(), output=output)


def main() -> None:
    parser = argparse.ArgumentParser(description="List available evaluations")
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="Output format",
    )
    args = parser.parse_args()
    print(list_available_evaluations_output(output=args.format))


if __name__ == "__main__":
    main()
