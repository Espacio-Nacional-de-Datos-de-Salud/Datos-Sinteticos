"""CLI and helpers to list trained models available under ``outputs/models/``.

Scans model folders for ``generator.zip`` and surfaces summary metadata from
``model_card.json`` and ``metadata.json`` so users can pick a ``model_id``
for the simulate/evaluate stages.
"""

import argparse
import json
import os

from config.general_config import (
    GENERATOR_ZIP_NAME,
    METADATA_FILENAME,
    MODEL_CARD_FILENAME,
    MODEL_RUN_FOLDER_PREFIX,
    MODELS_DIR,
)

from src.core.logging_config import get_logger

logger = get_logger(__name__)


def list_available_models() -> list[dict]:
    """Lists all trained models with their metadata.

    Scans the models directory for valid model folders (those containing
    a generator.zip) and extracts summary information from model_card.json
    and metadata.json when available.

    Returns:
        list[dict]: List of model info dicts, each with keys:
            - model_id (str): Folder name / model identifier.
            - folder (str): Absolute path to the model folder.
            - timestamp (str): Training timestamp (from model_card).
            - tables (str): Comma-separated table names (from metadata).
            - train_size (int | str | None): Total training rows when available.
            - training_table_sizes (dict[str, int]): Per-table training row counts.
            - accuracy (float | None): Overall generator accuracy (from model_card).
            - data_sources (list[dict]): Data source paths and hashes (from model_card).
    """
    import glob as _glob

    run_folders = sorted(
        _glob.glob(os.path.join(MODELS_DIR, MODEL_RUN_FOLDER_PREFIX + "_*")),
        reverse=True,
    )

    models = []
    for folder in run_folders:
        generator_zip = os.path.join(folder, GENERATOR_ZIP_NAME)
        if not os.path.exists(generator_zip):
            continue

        card_path = os.path.join(folder, MODEL_CARD_FILENAME)
        metadata_path = os.path.join(folder, METADATA_FILENAME)

        model_info: dict = {
            "model_id": os.path.basename(folder),
            "folder": folder,
            "timestamp": "",
            "tables": "",
            "train_size": None,
            "training_table_sizes": {},
            "accuracy": None,
            "data_sources": [],
        }

        if os.path.exists(card_path):
            try:
                with open(card_path, encoding="utf-8") as f:
                    card = json.load(f)
                model_info["timestamp"] = card.get("timestamp", "")
                model_info["data_sources"] = card.get("data_sources", [])
                stats = card.get("mostly_statistics", {})
                model_info["accuracy"] = stats.get("generator_accuracy")

                table_sizes = card.get("training_table_sizes", {})
                if isinstance(table_sizes, dict) and table_sizes:
                    normalized_sizes: dict[str, int] = {}
                    for table_name, size in table_sizes.items():
                        if isinstance(size, int):
                            normalized_sizes[str(table_name)] = size
                    model_info["training_table_sizes"] = normalized_sizes
                    model_info["train_size"] = (
                        sum(normalized_sizes.values()) if normalized_sizes else None
                    )
            except Exception as exc:
                logger.warning("Error reading model_card from %s: %s", folder, exc)

        if os.path.exists(metadata_path):
            try:
                with open(metadata_path, encoding="utf-8") as f:
                    meta = json.load(f)
                model_info["tables"] = ", ".join(t["name"] for t in meta.get("tables", []))
            except Exception as exc:
                logger.warning("Error reading metadata from %s: %s", folder, exc)

        models.append(model_info)

    return models


def format_available_models(models: list[dict], output: str = "json") -> str:
    """Formats model list as JSON or as a compact table.

    Args:
        models: The list returned by list_available_models().
        output: Either "json" or "table".
    """
    output_normalized = output.strip().lower()
    if output_normalized == "json":
        return json.dumps(models, indent=2, ensure_ascii=False)

    if output_normalized != "table":
        raise ValueError("output must be either 'json' or 'table'")

    headers = ["model_id", "tables (size)", "timestamp", "accuracy"]

    def _pretty_timestamp(raw_value: object) -> str:
        value = str(raw_value or "").strip()
        if not value:
            return "-"

        # Canonical project format: YYYYMMDD_HHMMSS
        if len(value) == 15 and value[8] == "_" and value.replace("_", "").isdigit():
            return (
                f"{value[:4]}-{value[4:6]}-{value[6:8]} {value[9:11]}:{value[11:13]}:{value[13:15]}"
            )

        # Lightweight fallback for ISO-like timestamps.
        if "T" in value:
            return value.replace("T", " ").replace("Z", "")

        return value

    rows = []
    for model in models:
        accuracy = model.get("accuracy")
        if isinstance(accuracy, (int, float)):
            accuracy_text = f"{accuracy:.4f}"
        else:
            accuracy_text = "-"

        table_sizes = model.get("training_table_sizes", {})
        if isinstance(table_sizes, dict) and table_sizes:
            tables_text = ", ".join(
                f"{name} ({size})" for name, size in sorted(table_sizes.items())
            )
        else:
            tables_text = "desconocido"

        rows.append(
            [
                str(model.get("model_id", "")),
                tables_text,
                _pretty_timestamp(model.get("timestamp", "")),
                accuracy_text,
            ]
        )

    if not rows:
        return "No models found."

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


def list_available_models_output(output: str = "json") -> str:
    """Returns available models as either JSON or a formatted table."""
    return format_available_models(list_available_models(), output=output)


def main() -> None:
    """CLI entrypoint with selectable output format."""
    parser = argparse.ArgumentParser(description="List available trained models")
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="Output format",
    )
    args = parser.parse_args()
    print(list_available_models_output(output=args.format))


if __name__ == "__main__":
    main()
