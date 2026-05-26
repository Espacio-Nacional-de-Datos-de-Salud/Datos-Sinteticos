"""Helpers to list pipeline sessions."""

import glob
import json
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal

from backend.src.config.general import (
    MODELS_DIR,
    PIPELINE_CARD_FILENAME,
    PIPELINE_RUN_FOLDER_PREFIX,
    PIPELINES_DIR,
    SIMULATIONS_DIR,
)
from backend.src.runs.catalog._base import (
    delete_run_folders,
    folder_has_files,
    folder_started_at_ms,
    parse_folder_start_time,
    read_total_run_duration_seconds,
)
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


def list_available_pipelines() -> list[dict]:
    """Scan the pipelines directory and return one entry per session.

    Returns:
        List of dicts with ``pipeline_id``, ``folder``, ``status``, ``timestamp``,
        ``config_path``, and ``jobs``.
    """
    run_folders = sorted(
        glob.glob(os.path.join(PIPELINES_DIR, PIPELINE_RUN_FOLDER_PREFIX + "_*")),
        reverse=True,
    )

    pipelines: list[dict] = []
    for folder in run_folders:
        card_path = os.path.join(folder, PIPELINE_CARD_FILENAME)
        if not os.path.exists(card_path):
            continue

        info: dict = {
            "pipeline_id": os.path.basename(folder),
            "folder": folder,
            "status": "unknown",
            "timestamp": "",
            "config_path": "",
            "jobs": [],
            "progress": None,
            "started_at_ms": folder_started_at_ms(folder, PIPELINE_RUN_FOLDER_PREFIX),
            "duration_seconds": read_total_run_duration_seconds(folder),
        }

        try:
            with open(card_path, encoding="utf-8") as handle:
                card = json.load(handle)

            info["pipeline_id"] = card.get("pipeline_id", "") or info["pipeline_id"]
            info["status"] = card.get("status", "unknown")
            info["timestamp"] = card.get("timestamp", "")
            info["config_path"] = card.get("config_path", "")
            info["jobs"] = card.get("jobs", []) or []
            info["progress"] = card.get("progress")
        except Exception as exc:
            logger.warning("Error reading pipeline card from %s: %s", folder, exc)

        pipelines.append(info)

    return pipelines


def _card_has_artifacts(card: dict) -> bool:
    """Returns True if any job in the card produced a model or simulation."""
    for job in card.get("jobs", []) or []:
        if job.get("model_id") or job.get("simulation_id"):
            return True
    return False


def find_cleanup_candidates(stale_hours: int = 24) -> tuple[list[str], list[str]]:
    """Identify pipeline folders eligible for cleanup.

    Pipelines with ``status == "partial"`` are preserved. Runs that are
    clearly dead, empty, or stale without recorded artifacts are marked as
    cleanup candidates.
    """
    cutoff = datetime.now() - timedelta(hours=stale_hours)
    run_folders = sorted(
        glob.glob(os.path.join(PIPELINES_DIR, PIPELINE_RUN_FOLDER_PREFIX + "_*")),
    )

    empty_ids: list[str] = []
    orphan_ids: list[str] = []

    for folder in run_folders:
        pipeline_id = os.path.basename(folder)
        card_path = os.path.join(folder, PIPELINE_CARD_FILENAME)

        if not folder_has_files(folder):
            empty_ids.append(pipeline_id)
            continue

        if not os.path.exists(card_path):
            start_time = parse_folder_start_time(pipeline_id, PIPELINE_RUN_FOLDER_PREFIX)
            if start_time is not None and start_time < cutoff:
                orphan_ids.append(pipeline_id)
            continue

        try:
            with open(card_path, encoding="utf-8") as f:
                card = json.load(f)
        except Exception:
            start_time = parse_folder_start_time(pipeline_id, PIPELINE_RUN_FOLDER_PREFIX)
            if start_time is not None and start_time < cutoff:
                orphan_ids.append(pipeline_id)
            continue

        status = card.get("status")
        if status == "failed":
            orphan_ids.append(pipeline_id)
        elif status == "in_progress" and not _card_has_artifacts(card):
            start_time = parse_folder_start_time(pipeline_id, PIPELINE_RUN_FOLDER_PREFIX)
            if start_time is not None and start_time < cutoff:
                orphan_ids.append(pipeline_id)

    return empty_ids, orphan_ids


def cleanup_pipelines(
    mode: Literal["empty", "orphans", "both"] = "both",
    stale_hours: int = 24,
) -> tuple[list[str], list[str]]:
    """Delete pipeline folders selected by the catalog cleanup policy."""
    empty_ids, _orphan_ids = find_cleanup_candidates(stale_hours=stale_hours)
    to_delete_empty = empty_ids if mode in ("empty", "both") else []
    # Orphan cleanup intentionally disabled — pipelines may still be running
    # when their child jobs are still updating their cards. Re-enable here
    # once a stronger heartbeat exists.
    return delete_run_folders(PIPELINES_DIR, to_delete_empty), []


@dataclass
class DeletePipelineOutcome:
    """Result of attempting to delete a pipeline and its cascade artifacts."""

    found: bool
    deleted_model_ids: list[str] = field(default_factory=list)
    deleted_simulation_ids: list[str] = field(default_factory=list)


def _collect_artifact_ids(pipeline: dict) -> tuple[list[str], list[str]]:
    """Extract model and simulation IDs recorded in the pipeline's card.

    Only artifacts produced by the pipeline itself are listed in its card —
    jobs that reuse an existing ``model_id`` from config don't register one.
    So the cascade only removes artifacts this pipeline created.
    """
    model_ids: list[str] = []
    simulation_ids: list[str] = []
    for job in pipeline.get("jobs", []) or []:
        model_id = job.get("model_id")
        simulation_id = job.get("simulation_id")
        if model_id:
            model_ids.append(model_id)
        if simulation_id:
            simulation_ids.append(simulation_id)
    return model_ids, simulation_ids


def get_pipeline_artifact_ids(pipeline_id: str) -> tuple[list[str], list[str]] | None:
    """Return ``(model_ids, simulation_ids)`` produced by the pipeline.

    Returns ``None`` when the pipeline is not found in the catalog. Only
    artifacts the pipeline created itself are included — jobs that reuse an
    existing ``model_id`` from config don't register one.
    """
    pipeline = next(
        (p for p in list_available_pipelines() if p["pipeline_id"] == pipeline_id),
        None,
    )
    if pipeline is None:
        return None
    return _collect_artifact_ids(pipeline)


def delete_pipeline(pipeline_id: str) -> DeletePipelineOutcome:
    """Delete a pipeline folder and cascade to the artifacts it produced."""
    pipeline = next(
        (p for p in list_available_pipelines() if p["pipeline_id"] == pipeline_id),
        None,
    )
    if pipeline is None:
        return DeletePipelineOutcome(found=False)

    model_ids, simulation_ids = _collect_artifact_ids(pipeline)

    deleted_simulation_ids: list[str] = []
    for simulation_id in simulation_ids:
        shutil.rmtree(f"{SIMULATIONS_DIR}/{simulation_id}", ignore_errors=True)
        deleted_simulation_ids.append(simulation_id)

    deleted_model_ids: list[str] = []
    for model_id in model_ids:
        shutil.rmtree(f"{MODELS_DIR}/{model_id}", ignore_errors=True)
        deleted_model_ids.append(model_id)

    shutil.rmtree(f"{PIPELINES_DIR}/{pipeline_id}", ignore_errors=True)
    return DeletePipelineOutcome(
        found=True,
        deleted_model_ids=deleted_model_ids,
        deleted_simulation_ids=deleted_simulation_ids,
    )


def format_available_pipelines(pipelines: list[dict], output: str = "json") -> str:
    """Render the pipelines list as JSON or as an ASCII table."""
    output_normalized = output.strip().lower()
    if output_normalized == "json":
        return json.dumps(pipelines, indent=2, ensure_ascii=False)

    if output_normalized != "table":
        raise ValueError("output must be either 'json' or 'table'")

    headers = ["pipeline_id", "status", "jobs", "timestamp"]

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
    for pipeline in pipelines:
        jobs = pipeline.get("jobs", [])
        jobs_text = str(len(jobs)) if jobs else "-"

        rows.append(
            [
                str(pipeline.get("pipeline_id", "")),
                str(pipeline.get("status", "")),
                jobs_text,
                _pretty_timestamp(pipeline.get("timestamp", "")),
            ]
        )

    if not rows:
        return "No pipelines found."

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


def list_available_pipelines_output(output: str = "json") -> str:
    """Return available pipelines formatted as JSON or table."""
    return format_available_pipelines(list_available_pipelines(), output=output)


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="List pipeline sessions")
    parser.add_argument("--format", choices=["json", "table"], default="json")
    args = parser.parse_args()
    print(list_available_pipelines_output(output=args.format))


if __name__ == "__main__":
    main()
