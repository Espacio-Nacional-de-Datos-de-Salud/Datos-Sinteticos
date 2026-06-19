"""CLI and helpers to list trained models available under ``outputs/models/``.

Scans model folders for ``generator.zip`` and surfaces summary metadata from
``model_card.json`` and ``metadata.json`` so users can pick a ``model_id``
for the simulate/evaluate stages.
"""

import argparse
import glob as _glob
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Literal

from backend.src.config.general import (
    GENERATOR_ZIP_NAME,
    METADATA_FILENAME,
    MODEL_CARD_FILENAME,
    MODEL_RUN_FOLDER_PREFIX,
    MODELS_DIR,
)
from backend.src.infrastructure.errors import ModelNotFoundError
from backend.src.infrastructure.logging_config import get_logger
from backend.src.runs.card_io import read_json, write_json
from backend.src.runs.catalog._base import (
    find_run_cleanup_candidates,
    folder_started_at_ms,
    purge_all_runs,
    read_total_run_duration_seconds,
)
from backend.src.runs.catalog.simulations import (
    DeleteMode,
    _column_types_from_inspection_metadata,
    _column_types_from_model_metadata,
    _columns_from_files,
    _columns_from_inspection_metadata,
    _columns_from_model_metadata,
    _resolve_real_data_paths_from_card,
    _table_name_from_file,
    delete_simulation,
    list_available_simulations,
)

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

    run_folders = sorted(
        _glob.glob(os.path.join(MODELS_DIR, MODEL_RUN_FOLDER_PREFIX + "_*")),
        reverse=True,
    )

    models = []
    for folder in run_folders:
        card_path = os.path.join(folder, MODEL_CARD_FILENAME)
        metadata_path = os.path.join(folder, METADATA_FILENAME)
        generator_zip = os.path.join(folder, GENERATOR_ZIP_NAME)

        # Include in-progress runs (card exists) even without generator.zip
        has_card = os.path.exists(card_path)
        has_generator = os.path.exists(generator_zip)
        if not has_card and not has_generator:
            continue

        model_info: dict = {
            "model_id": os.path.basename(folder),
            "model_name": None,
            "folder": folder,
            "status": "",
            "timestamp": "",
            "timestamp_ms": None,
            "tables": "",
            "train_size": None,
            "training_table_sizes": {},
            "subject_tables": [],
            "accuracy": None,
            "qa_report_filename": None,
            "data_sources": [],
            "progress": None,
            "inspection_id": None,
            "brc_id": None,
            "brc_name": None,
            "duration_seconds": read_total_run_duration_seconds(folder),
            "started_at_ms": folder_started_at_ms(folder, MODEL_RUN_FOLDER_PREFIX),
        }

        if has_card:
            try:
                with open(card_path, encoding="utf-8") as f:
                    card = json.load(f)
                model_info["model_name"] = card.get("model_name") or card.get("model_id")
                model_info["status"] = card.get("status", "")
                model_info["error_message"] = card.get("error_message")
                model_info["timestamp"] = card.get("timestamp", "")
                model_info["timestamp_ms"] = card.get("timestamp_ms")
                model_info["data_sources"] = card.get("data_sources", [])
                model_info["progress"] = card.get("progress")
                model_info["inspection_id"] = card.get("inspection_id")
                model_info["brc_id"] = card.get("brc_id")
                model_info["brc_name"] = card.get("brc_name")
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
                # A table is a "subject" (root) when no foreign key marks it as a
                # context child. Mostly AI only honors per-table sample_size on
                # subjects; context children always cascade from their parent.
                # The UI uses this list to grey out non-subject inputs.
                model_info["subject_tables"] = [
                    t["name"]
                    for t in meta.get("tables", [])
                    if not any(fk.get("is_context") for fk in (t.get("foreign_keys") or []))
                ]
            except Exception as exc:
                logger.warning("Error reading metadata from %s: %s", folder, exc)

        qa_reports_dir = os.path.join(folder, "qa_reports")
        if os.path.isdir(qa_reports_dir):
            html_files = [f for f in os.listdir(qa_reports_dir) if f.endswith(".html")]
            if html_files:
                model_info["qa_report_filename"] = sorted(html_files)[0]

        models.append(model_info)

    return models


def group_simulation_ids_by_model(simulations: list[dict]) -> dict[str, list[str]]:
    """Build a model_id -> simulation_ids index for cleanup checks."""
    grouped: dict[str, list[str]] = {}
    for simulation in simulations:
        linked_model_id = simulation.get("model_id")
        simulation_id = simulation.get("simulation_id")
        if not linked_model_id or not simulation_id:
            continue
        grouped.setdefault(str(linked_model_id), []).append(str(simulation_id))
    return grouped


def find_cleanup_candidates(stale_hours: int = 24) -> tuple[list[str], list[str]]:
    """Identify model folders eligible for cleanup.

    See ``base.find_run_cleanup_candidates`` for the policy.
    """
    return find_run_cleanup_candidates(
        base_dir=MODELS_DIR,
        folder_prefix=MODEL_RUN_FOLDER_PREFIX,
        card_filename=MODEL_CARD_FILENAME,
        stale_hours=stale_hours,
    )


def cleanup_models(
    mode: Literal["empty", "orphans", "both"] = "both",
    stale_hours: int = 24,
) -> tuple[list[str], list[str], list[str]]:
    """Delete model folders selected by the catalog cleanup policy.

    Models linked to simulations are skipped.
    """
    empty_ids, orphan_ids = find_cleanup_candidates(stale_hours=stale_hours)

    to_delete_empty = empty_ids if mode in ("empty", "both") else []
    to_delete_orphans = orphan_ids if mode in ("orphans", "both") else []

    simulation_ids_by_model = group_simulation_ids_by_model(list_available_simulations())

    deleted_empty: list[str] = []
    deleted_orphans: list[str] = []
    skipped: list[str] = []

    for model_id in to_delete_empty:
        if simulation_ids_by_model.get(model_id):
            skipped.append(model_id)
            continue
        shutil.rmtree(f"{MODELS_DIR}/{model_id}", ignore_errors=True)
        deleted_empty.append(model_id)

    for model_id in to_delete_orphans:
        if simulation_ids_by_model.get(model_id):
            skipped.append(model_id)
            continue
        shutil.rmtree(f"{MODELS_DIR}/{model_id}", ignore_errors=True)
        deleted_orphans.append(model_id)

    return deleted_empty, deleted_orphans, skipped


def purge_all_models() -> list[str]:
    """Delete every model folder regardless of status or simulation links."""
    return purge_all_runs(MODELS_DIR)


def rename_model(model_id: str, name: str) -> bool:
    """Update ``model_name`` in the model card. Returns False if not found."""
    card_path = os.path.join(MODELS_DIR, model_id, MODEL_CARD_FILENAME)
    if not os.path.exists(card_path):
        return False
    card = read_json(card_path)
    card["model_name"] = name
    write_json(card_path, card)
    return True


@dataclass
class DeleteModelOutcome:
    """Result of attempting to delete a single model folder."""

    status: Literal["deleted", "not_found", "has_linked_simulations"]
    linked_simulation_ids: list[str] = field(default_factory=list)
    deleted_simulation_ids: list[str] = field(default_factory=list)
    deleted_evaluation_ids: list[str] = field(default_factory=list)


def delete_model(model_id: str, mode: DeleteMode = "safe") -> DeleteModelOutcome:
    """Delete a single model folder.

    ``mode`` controls how linked simulations are handled:
    - ``safe`` (default): refuse with ``has_linked_simulations`` when any exist.
    - ``force``: delete the model only, leaving its simulations orphaned.
    - ``cascade``: delete the model, its simulations, and their evaluations.
    """
    if not any(m["model_id"] == model_id for m in list_available_models()):
        return DeleteModelOutcome(status="not_found")

    simulation_ids_by_model = group_simulation_ids_by_model(list_available_simulations())
    linked_simulation_ids = simulation_ids_by_model.get(model_id, [])
    if linked_simulation_ids and mode == "safe":
        return DeleteModelOutcome(
            status="has_linked_simulations",
            linked_simulation_ids=linked_simulation_ids,
        )

    deleted_simulation_ids: list[str] = []
    deleted_evaluation_ids: list[str] = []
    if mode == "cascade":
        for simulation_id in linked_simulation_ids:
            outcome = delete_simulation(simulation_id, mode="cascade")
            deleted_simulation_ids.append(simulation_id)
            deleted_evaluation_ids.extend(outcome.deleted_evaluation_ids)

    shutil.rmtree(f"{MODELS_DIR}/{model_id}", ignore_errors=True)
    return DeleteModelOutcome(
        status="deleted",
        deleted_simulation_ids=deleted_simulation_ids,
        deleted_evaluation_ids=deleted_evaluation_ids,
    )


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


def _read_model_card(model_id: str) -> dict:
    folder = os.path.join(MODELS_DIR, model_id)
    card_path = os.path.join(folder, MODEL_CARD_FILENAME)
    if not os.path.isdir(folder) or not os.path.exists(card_path):
        raise ModelNotFoundError(f"Model '{model_id}' not found.")
    with open(card_path, encoding="utf-8") as f:
        return json.load(f)


def _model_data_source_paths(model_card: dict) -> list[str]:
    sources = model_card.get("data_sources") or []
    paths: list[str] = []
    for entry in sources:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if path and os.path.exists(path):
            paths.append(path)
    return paths


def resolve_model_real_data_paths(model_id: str) -> list[str]:
    """Return the paths that materialise the data the model trained on.

    Thin wrapper around :func:`_resolve_real_data_paths_from_card` so callers
    that only have a ``model_id`` don't need to read the card themselves.
    See that function's docstring for the resolution order.
    """
    card = _read_model_card(model_id)
    return _resolve_real_data_paths_from_card(model_id, card)


def read_model_training_config(model_id: str) -> dict:
    """Return the full Mostly AI config the model was trained with.

    Reads ``configs/mostly_config.json`` (archived at training time, with all
    overrides already merged in) and returns it verbatim under a ``config``
    key. Returning the whole object — rather than a hand-picked subset — keeps
    the summary in sync with every configurable parameter (training limits,
    differential privacy, per-table overrides, …) without this function needing
    to know the schema.

    Raises ``ModelNotFoundError`` when the model folder does not exist; returns
    ``{"config": {}}`` when the config file was never written (e.g. a run that
    failed before archiving).
    """
    folder = os.path.join(MODELS_DIR, model_id)
    if not os.path.isdir(folder):
        raise ModelNotFoundError(f"Model '{model_id}' not found.")

    config_path = os.path.join(folder, "configs", "mostly_config.json")
    if not os.path.exists(config_path):
        return {"config": {}}

    try:
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)
    except Exception as exc:
        logger.warning("Could not read training config for model %s: %s", model_id, exc)
        config = {}

    return {"config": config if isinstance(config, dict) else {}}


def list_model_columns(model_id: str) -> dict[str, list[str]]:
    """Return ``{table: [columns]}`` for a trained model.

    Tries the source inspection metadata, then the model's ``metadata.json``,
    then the original training files. Mirrors ``list_simulation_columns`` so
    the frontend can offer column dropdowns before any simulation has run.
    """
    card = _read_model_card(model_id)
    inspection_id = card.get("inspection_id")
    metadata_path = os.path.join(MODELS_DIR, model_id, METADATA_FILENAME)
    real_files = _model_data_source_paths(card)

    sources = (
        lambda: _columns_from_inspection_metadata(inspection_id),
        lambda: _columns_from_model_metadata(metadata_path),
        lambda: _columns_from_files(real_files),
    )
    for load_columns in sources:
        try:
            columns_by_table = load_columns()
        except Exception as exc:
            logger.warning("Could not load columns for model %s: %s", model_id, exc)
            continue
        if columns_by_table:
            return columns_by_table

    raise ModelNotFoundError(f"Could not find columns for model '{model_id}'.")


def list_model_column_types(model_id: str) -> dict[str, dict[str, str]]:
    """Return ``{table: {column: kind}}`` for a trained model.

    ``kind`` is one of ``numeric``, ``datetime`` or ``categorical`` — a coarse
    classification derived from each column's Mostly AI encoding type. Used by
    the conditional-generation UI to offer only the constraint types that make
    sense for a column (e.g. a numeric range only on numeric columns).

    Prefers the source inspection metadata, then the model's ``metadata.json``.
    Returns an empty dict when neither is available rather than raising — the
    UI then falls back to offering all constraint types.
    """
    card = _read_model_card(model_id)
    inspection_id = card.get("inspection_id")
    metadata_path = os.path.join(MODELS_DIR, model_id, METADATA_FILENAME)

    sources = (
        lambda: _column_types_from_inspection_metadata(inspection_id),
        lambda: _column_types_from_model_metadata(metadata_path),
    )
    for load_types in sources:
        try:
            types_by_table = load_types()
        except Exception as exc:
            logger.warning("Could not load column types for model %s: %s", model_id, exc)
            continue
        if types_by_table:
            return types_by_table

    return {}


def _load_model_metadata(model_id: str) -> dict:
    """Load and return ``metadata.json`` for ``model_id``, or ``{}`` on failure."""
    metadata_path = os.path.join(MODELS_DIR, model_id, METADATA_FILENAME)
    if not os.path.exists(metadata_path):
        return {}
    try:
        with open(metadata_path) as f:
            return json.load(f)
    except Exception as exc:
        logger.warning("Could not read metadata for model %s: %s", model_id, exc)
        return {}


def collect_key_columns(metadata: dict) -> set[str]:
    """Return every column *name* that is a primary or foreign key in the schema.

    Keys are collected globally across all tables, not per table. In a
    denormalized schema a key column (e.g. ``person_id``) is physically present
    in child tables where it is *not* a declared foreign key — it is a PK of its
    own table and an FK of an intermediate context parent. Conditioning on such
    a column is meaningless (FK-consistency POST reconstructs it from the parent
    anyway), so any column whose name is a key anywhere is treated as off-limits.
    """
    keys: set[str] = set()
    for table in metadata.get("tables", []):
        pk = table.get("primary_key")
        if isinstance(pk, str) and pk:
            keys.add(pk)
        elif isinstance(pk, list):
            keys.update(c for c in pk if isinstance(c, str) and c)
        for fk in table.get("foreign_keys", []) or []:
            col = fk.get("column")
            if col:
                keys.add(col)
    return keys


def list_model_key_columns(model_id: str) -> list[str]:
    """Return the sorted PK/FK column names for a model (see ``collect_key_columns``)."""
    return sorted(collect_key_columns(_load_model_metadata(model_id)))


def list_model_column_values(
    model_id: str,
    table: str,
    column: str,
    limit: int = 200,
) -> list[str]:
    """Return up to ``limit`` distinct values for ``column`` in ``table``.

    Reads from the preprocessed dataset the model actually trained on (via
    :func:`resolve_model_real_data_paths`) so values for derived columns —
    e.g. ``is_adult`` materialised by a logical rule from ``date_of_birth``
    — resolve correctly, and columns dropped by rules don't leak. Values are
    sorted by descending frequency and stringified for JSON serialisation.
    Used by the conditional-generation UI to populate value dropdowns.
    """
    import pandas as pd

    real_files = resolve_model_real_data_paths(model_id)
    path = next(
        (p for p in real_files if _table_name_from_file(p) == table),
        None,
    )
    if path is None:
        raise ModelNotFoundError(
            f"Table '{table}' not found among training data for model '{model_id}'."
        )

    extension = os.path.splitext(path)[1].lstrip(".").lower()
    try:
        if extension == "csv":
            series = pd.read_csv(path, usecols=[column])[column]
        elif extension == "parquet":
            series = pd.read_parquet(path, columns=[column])[column]
        elif extension == "json":
            series = pd.read_json(path)[column]
        else:
            raise ModelNotFoundError(f"Unsupported extension for values: {extension!r}")
    except (ValueError, KeyError) as exc:
        # Column genuinely absent from the training data — surface a clear
        # 404 instead of pandas' less specific 'Usecols do not match'.
        raise ModelNotFoundError(
            f"Column '{column}' not found in table '{table}' for model '{model_id}'."
        ) from exc

    counts = series.dropna().astype(str).value_counts()
    return [str(value) for value in counts.head(limit).index.tolist()]


if __name__ == "__main__":
    main()
