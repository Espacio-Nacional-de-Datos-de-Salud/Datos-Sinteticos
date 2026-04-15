"""CLI and helpers to list inspection sessions awaiting training."""

import argparse
import glob
import json
import os

from config.general_config import (
    INSPECTION_CARD_FILENAME,
    INSPECTION_RUN_FOLDER_PREFIX,
    INSPECTIONS_DIR,
)

from src.core.logging_config import get_logger

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
            "folder": folder,
            "timestamp": "",
            "tables": {},
            "file_paths": [],
        }

        try:
            with open(card_path, encoding="utf-8") as handle:
                card = json.load(handle)

            info["inspection_name"] = card.get("inspection_name", "") or info["inspection_id"]
            info["timestamp"] = card.get("timestamp", "")
            info["tables"] = card.get("tables", {}) or {}
            info["file_paths"] = card.get("file_paths", []) or []
        except Exception as exc:
            logger.warning("Error reading inspection card from %s: %s", folder, exc)

        inspections.append(info)

    return inspections


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
