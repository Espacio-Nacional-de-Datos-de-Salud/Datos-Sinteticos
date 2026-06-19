"""CLI and helpers to list simulations available under ``outputs/simulations/``.

Scans simulation folders, reads their ``sim_card.json`` and associated
``model_card.json`` for lineage, and resolves simulation inputs for the
evaluation stage (synthetic files, real data references, model linkage).
"""

import argparse
import csv
import glob as _glob
import json
import os
import shutil
from dataclasses import dataclass, field
from typing import Literal

from backend.src.config.general import (
    EVALUATIONS_DIR,
    INSPECTION_METADATA_FILENAME,
    INSPECTIONS_DIR,
    METADATA_FILENAME,
    MODEL_CARD_FILENAME,
    MODELS_DIR,
    PROCESSED_DATA_DIRNAME,
    SIM_CARD_FILENAME,
    SIMULATION_RUN_FOLDER_PREFIX,
    SIMULATIONS_DIR,
)
from backend.src.infrastructure.errors import (
    DataSourceNotFoundError,
    ModelCardNotFoundError,
    SimCardNotFoundError,
    SimulationNotFoundError,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.runs.card_io import read_json, write_json
from backend.src.runs.catalog._base import (
    find_run_cleanup_candidates,
    folder_started_at_ms,
    purge_all_runs,
    read_total_run_duration_seconds,
)
from backend.src.runs.catalog.evaluations import list_available_evaluations

logger = get_logger(__name__)

SYNTHETIC_DATA_DIRNAME = "synthetic_data"
SIM_METADATA_FILENAME = "sim_metadata.json"


def read_simulation_relationships(simulation_dir: str) -> list[dict]:
    """Return the table foreign-key edges recorded in ``sim_metadata.json``.

    Each edge is ``{parent, child, column, is_context}`` where ``parent`` is the
    referenced table and ``child`` is the table holding the FK column. The UI
    uses these to draw a simplified schema diagram of the simulation. Returns an
    empty list when the metadata file is missing or unreadable.
    """
    metadata_path = os.path.join(simulation_dir, SIM_METADATA_FILENAME)
    if not os.path.isfile(metadata_path):
        return []
    try:
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Error reading %s: %s", metadata_path, exc)
        return []

    relationships: list[dict] = []
    for table in metadata.get("tables", []):
        child = table.get("name")
        for fk in table.get("foreign_keys", []) or []:
            parent = fk.get("referenced_table")
            column = fk.get("column")
            if not (child and parent and column):
                continue
            relationships.append(
                {
                    "parent": parent,
                    "child": child,
                    "column": column,
                    "is_context": bool(fk.get("is_context")),
                }
            )
    return relationships


def _list_synthetic_files_from_directory(synthetic_dir: str) -> list[str]:
    return sorted(
        os.path.join(synthetic_dir, fname)
        for fname in os.listdir(synthetic_dir)
        if os.path.isfile(os.path.join(synthetic_dir, fname))
    )


def list_synthetic_table_names(simulation_dir: str) -> list[str]:
    """Return synthetic table names from the simulation's ``synthetic_data/`` directory."""
    synthetic_dir = os.path.join(simulation_dir, SYNTHETIC_DATA_DIRNAME)
    if not os.path.isdir(synthetic_dir):
        return []

    source_names = [
        os.path.basename(path) for path in _list_synthetic_files_from_directory(synthetic_dir)
    ]

    table_names: list[str] = []
    for fname in sorted(source_names):
        base, _ = os.path.splitext(fname)
        if base.endswith("_synthetic"):
            base = base[: -len("_synthetic")]
        table_names.append(base)
    return table_names


def list_available_simulations() -> list[dict]:
    """Lists all simulation runs with their metadata.

    Scans the simulations directory for valid simulation folders (those
    containing a ``synthetic_data`` subdirectory) and extracts summary
    information from ``sim_card.json`` when available. Each simulation
    entry is additionally enriched with the linked model's overall
    accuracy (when the model card can be read).

    Returns:
        list[dict]: List of simulation info dicts, each with keys:
            - simulation_id (str): Folder name / simulation identifier.
            - folder (str): Absolute path to the simulation folder.
            - timestamp (str): Simulation timestamp (from sim_card).
            - model_id (str | None): ID of the model used (from sim_card).
            - tables (str): Comma-separated synthetic table names found
                under ``synthetic_data/``.
            - training_table_sizes (dict[str, int]): Per-table training rows
                loaded through ``sim_card.model_id -> model_card``.
            - model_accuracy (float | None): Overall generator accuracy of
                the linked model, if the model card is readable.
    """

    run_folders = sorted(
        _glob.glob(os.path.join(SIMULATIONS_DIR, SIMULATION_RUN_FOLDER_PREFIX + "_*")),
        reverse=True,
    )

    simulations = []
    for folder in run_folders:
        sim_card_path = os.path.join(folder, SIM_CARD_FILENAME)
        synthetic_dir = os.path.join(folder, SYNTHETIC_DATA_DIRNAME)

        # Include in-progress runs (card exists) even without synthetic data yet
        has_card = os.path.exists(sim_card_path)
        has_synthetic = os.path.isdir(synthetic_dir)
        if not has_card and not has_synthetic:
            continue

        sim_info: dict = {
            "simulation_id": os.path.basename(folder),
            "simulation_name": None,
            "folder": folder,
            "status": "",
            "timestamp": "",
            "model_id": None,
            "sample_size": None,
            "mother_table": None,
            "mother_table_size": None,
            "target_table": None,
            "target_table_rows": None,
            "tables": "",
            "training_table_sizes": {},
            "relationships": [],
            "model_accuracy": None,
            "progress": None,
            "duration_seconds": read_total_run_duration_seconds(folder),
            "started_at_ms": folder_started_at_ms(folder, SIMULATION_RUN_FOLDER_PREFIX),
        }

        if has_card:
            try:
                with open(sim_card_path, encoding="utf-8") as f:
                    card = json.load(f)
                sim_info["simulation_name"] = card.get("simulation_name") or card.get(
                    "simulation_id"
                )
                sim_info["status"] = card.get("status", "")
                sim_info["error_message"] = card.get("error_message")
                sim_info["timestamp"] = card.get("timestamp", "")
                sim_info["model_id"] = card.get("model_id")
                sim_info["sample_size"] = card.get("sample_size")
                sim_info["mother_table"] = card.get("mother_table")
                sim_info["mother_table_size"] = card.get("mother_table_size")
                sim_info["target_table"] = card.get("target_table")
                sim_info["target_table_rows"] = card.get("target_table_rows")
                sim_info["progress"] = card.get("progress")
            except Exception as exc:
                logger.warning("Error reading sim_card from %s: %s", folder, exc)

        # Extract table names from synthetic_data/ files.
        try:
            sim_info["tables"] = ", ".join(list_synthetic_table_names(folder))
        except OSError as exc:
            logger.warning("Error listing synthetic data in %s: %s", folder, exc)

        # Foreign-key edges drive the simplified schema diagram in the UI.
        sim_info["relationships"] = read_simulation_relationships(folder)

        # Best-effort enrichment with the linked model's accuracy.
        model_id = sim_info["model_id"]
        if model_id:
            model_card_path = os.path.join(MODELS_DIR, model_id, MODEL_CARD_FILENAME)
            if os.path.exists(model_card_path):
                try:
                    with open(model_card_path, encoding="utf-8") as f:
                        model_card = json.load(f)
                    stats = model_card.get("mostly_statistics", {})
                    sim_info["model_accuracy"] = stats.get("generator_accuracy")
                    table_sizes = model_card.get("training_table_sizes", {})
                    if isinstance(table_sizes, dict) and table_sizes:
                        normalized_sizes: dict[str, int] = {}
                        for table_name, size in table_sizes.items():
                            if isinstance(size, int):
                                normalized_sizes[str(table_name)] = size
                        sim_info["training_table_sizes"] = normalized_sizes
                except Exception as exc:
                    logger.warning(
                        "Error reading model_card for linked model %s: %s", model_id, exc
                    )

        simulations.append(sim_info)

    return simulations


def find_cleanup_candidates(stale_hours: int = 24) -> tuple[list[str], list[str]]:
    """Identify simulation folders eligible for cleanup.

    See ``base.find_run_cleanup_candidates`` for the policy.
    """
    return find_run_cleanup_candidates(
        base_dir=SIMULATIONS_DIR,
        folder_prefix=SIMULATION_RUN_FOLDER_PREFIX,
        card_filename=SIM_CARD_FILENAME,
        stale_hours=stale_hours,
    )


def group_evaluation_ids_by_simulation(evaluations: list[dict]) -> dict[str, list[str]]:
    """Build a simulation_id -> evaluation_ids index for cleanup checks."""
    grouped: dict[str, list[str]] = {}
    for evaluation in evaluations:
        linked_simulation_id = evaluation.get("simulation_id")
        evaluation_id = evaluation.get("evaluation_id")
        if not linked_simulation_id or not evaluation_id:
            continue
        grouped.setdefault(str(linked_simulation_id), []).append(str(evaluation_id))
    return grouped


def cleanup_simulations(
    mode: Literal["empty", "orphans", "both"] = "both",
    stale_hours: int = 24,
) -> tuple[list[str], list[str], list[str]]:
    """Delete simulation folders selected by the catalog cleanup policy.

    Simulations linked to any evaluation are skipped (mirrors how
    ``cleanup_models`` skips models with linked simulations).
    """
    empty_ids, orphan_ids = find_cleanup_candidates(stale_hours=stale_hours)

    to_delete_empty = empty_ids if mode in ("empty", "both") else []
    to_delete_orphans = orphan_ids if mode in ("orphans", "both") else []

    evaluation_ids_by_simulation = group_evaluation_ids_by_simulation(list_available_evaluations())

    deleted_empty: list[str] = []
    deleted_orphans: list[str] = []
    skipped: list[str] = []

    for simulation_id in to_delete_empty:
        if evaluation_ids_by_simulation.get(simulation_id):
            skipped.append(simulation_id)
            continue
        shutil.rmtree(f"{SIMULATIONS_DIR}/{simulation_id}", ignore_errors=True)
        deleted_empty.append(simulation_id)

    for simulation_id in to_delete_orphans:
        if evaluation_ids_by_simulation.get(simulation_id):
            skipped.append(simulation_id)
            continue
        shutil.rmtree(f"{SIMULATIONS_DIR}/{simulation_id}", ignore_errors=True)
        deleted_orphans.append(simulation_id)

    return deleted_empty, deleted_orphans, skipped


DeleteMode = Literal["safe", "force", "cascade"]


@dataclass
class DeleteSimulationOutcome:
    """Result of attempting to delete a single simulation folder."""

    status: Literal["deleted", "not_found", "has_linked_evaluations"]
    linked_evaluation_ids: list[str] = field(default_factory=list)
    deleted_evaluation_ids: list[str] = field(default_factory=list)


def delete_simulation(simulation_id: str, mode: DeleteMode = "safe") -> DeleteSimulationOutcome:
    """Delete a single simulation folder.

    ``mode`` controls how linked evaluations are handled:
    - ``safe`` (default): refuse with ``has_linked_evaluations`` when any exist.
    - ``force``: delete the simulation only, leaving its evaluations orphaned.
    - ``cascade``: delete the simulation and every linked evaluation.
    """
    if not any(s["simulation_id"] == simulation_id for s in list_available_simulations()):
        return DeleteSimulationOutcome(status="not_found")

    evaluation_ids_by_simulation = group_evaluation_ids_by_simulation(list_available_evaluations())
    linked_evaluation_ids = evaluation_ids_by_simulation.get(simulation_id, [])
    if linked_evaluation_ids and mode == "safe":
        return DeleteSimulationOutcome(
            status="has_linked_evaluations",
            linked_evaluation_ids=linked_evaluation_ids,
        )

    deleted_evaluation_ids: list[str] = []
    if mode == "cascade":
        for evaluation_id in linked_evaluation_ids:
            shutil.rmtree(f"{EVALUATIONS_DIR}/{evaluation_id}", ignore_errors=True)
            deleted_evaluation_ids.append(evaluation_id)

    shutil.rmtree(f"{SIMULATIONS_DIR}/{simulation_id}", ignore_errors=True)
    return DeleteSimulationOutcome(status="deleted", deleted_evaluation_ids=deleted_evaluation_ids)


def purge_all_simulations() -> list[str]:
    """Delete every simulation folder regardless of status."""
    return purge_all_runs(SIMULATIONS_DIR)


def rename_simulation(simulation_id: str, name: str) -> bool:
    """Update ``simulation_name`` in the simulation card. Returns False if not found."""
    card_path = os.path.join(SIMULATIONS_DIR, simulation_id, SIM_CARD_FILENAME)
    if not os.path.exists(card_path):
        return False
    card = read_json(card_path)
    card["simulation_name"] = name
    write_json(card_path, card)
    return True


def format_available_simulations(simulations: list[dict], output: str = "json") -> str:
    """Formats simulation list as JSON or as a compact table.

    Args:
        simulations: The list returned by list_available_simulations().
        output: Either "json" or "table".
    """
    output_normalized = output.strip().lower()
    if output_normalized == "json":
        return json.dumps(simulations, indent=2, ensure_ascii=False)

    if output_normalized != "table":
        raise ValueError("output must be either 'json' or 'table'")

    headers = ["simulation_id", "model_id", "tables (size)", "timestamp", "model_accuracy"]

    def _pretty_timestamp(raw_value: object) -> str:
        value = str(raw_value or "").strip()
        if not value:
            return "-"

        # Canonical project format: YYYYMMDD_HHMMSS
        if len(value) == 15 and value[8] == "_" and value.replace("_", "").isdigit():
            return (
                f"{value[:4]}-{value[4:6]}-{value[6:8]} {value[9:11]}:{value[11:13]}:{value[13:15]}"
            )

        if "T" in value:
            return value.replace("T", " ").replace("Z", "")

        return value

    rows = []
    for sim in simulations:
        accuracy = sim.get("model_accuracy")
        if isinstance(accuracy, (int, float)):
            accuracy_text = f"{accuracy:.4f}"
        else:
            accuracy_text = "-"

        table_sizes = sim.get("training_table_sizes", {})
        if isinstance(table_sizes, dict) and table_sizes:
            tables_text = ", ".join(
                f"{name} ({size})" for name, size in sorted(table_sizes.items())
            )
        else:
            tables_text = "desconocido"

        rows.append(
            [
                str(sim.get("simulation_id", "")),
                str(sim.get("model_id") or "-"),
                tables_text,
                _pretty_timestamp(sim.get("timestamp", "")),
                accuracy_text,
            ]
        )

    if not rows:
        return "No simulations found."

    widths = [len(h) for h in headers]
    for row in rows:
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    # Keep output readable in standard terminals.
    max_widths = [24, 24, 56, 19, 14]
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


def list_available_simulations_output(output: str = "json") -> str:
    """Returns available simulations as either JSON or a formatted table."""
    return format_available_simulations(list_available_simulations(), output=output)


@dataclass(frozen=True)
class ResolvedSimulationInputs:
    """Inputs required to run the evaluation pipeline for a simulation.

    Attributes:
        simulation_id: Identifier of the resolved simulation.
        simulation_dir: Absolute path to the simulation folder.
        synthetic_files: Absolute paths to the synthetic data files produced.
        model_id: Identifier of the model used to generate the simulation.
        metadata_path: Absolute path to the model's metadata.json file
            (may not exist; the caller handles its absence).
        real_data_files: Absolute paths of the real data files used to train
            the model (from the model_card's data_sources).
    """

    simulation_id: str
    simulation_dir: str
    synthetic_files: list[str]
    model_id: str
    metadata_path: str
    real_data_files: list[str]


def resolve_simulation_inputs(simulation_id: str) -> ResolvedSimulationInputs:
    """Resolve all evaluation inputs by tracing a simulation back to its training data.

    Resolution chain:
        simulation_id → simulation folder → sim_card.json → model_id →
        model folder → model_card.json → data_sources → real data files.

    Args:
        simulation_id: Identifier of the simulation (folder name under
            ``outputs/simulations/``).

    Returns:
        ResolvedSimulationInputs: All paths and identifiers needed to run
            the evaluation pipeline.

    Raises:
        SimulationNotFoundError: Simulation folder or synthetic_data subdir missing.
        SimCardNotFoundError: sim_card.json missing, unreadable, or without model_id.
        ModelCardNotFoundError: Linked model folder or model_card.json missing or unreadable.
        DataSourceNotFoundError: model_card has no data_sources, or referenced files
            are missing from disk.
    """
    simulation_dir = os.path.join(SIMULATIONS_DIR, simulation_id)
    if not os.path.isdir(simulation_dir):
        raise SimulationNotFoundError(f"Simulation folder not found: {simulation_dir}")

    synthetic_dir = os.path.join(simulation_dir, SYNTHETIC_DATA_DIRNAME)
    if not os.path.isdir(synthetic_dir):
        raise SimulationNotFoundError(
            f"Synthetic data folder not found in simulation: {synthetic_dir}"
        )

    synthetic_files = _list_synthetic_files_from_directory(synthetic_dir)
    if not synthetic_files:
        raise SimulationNotFoundError(f"No synthetic files found in {synthetic_dir}")

    sim_card_path = os.path.join(simulation_dir, SIM_CARD_FILENAME)
    if not os.path.exists(sim_card_path):
        raise SimCardNotFoundError(f"sim_card.json not found: {sim_card_path}")

    try:
        with open(sim_card_path, encoding="utf-8") as f:
            sim_card = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise SimCardNotFoundError(
            f"Failed to read sim_card.json at {sim_card_path}: {exc}"
        ) from exc

    model_id = sim_card.get("model_id")
    if not model_id:
        raise SimCardNotFoundError(
            f"sim_card.json at {sim_card_path} does not reference a model_id."
        )

    model_dir = os.path.join(MODELS_DIR, model_id)
    if not os.path.isdir(model_dir):
        raise ModelCardNotFoundError(
            f"Linked model folder not found for model_id '{model_id}': {model_dir}"
        )

    model_card_path = os.path.join(model_dir, MODEL_CARD_FILENAME)
    if not os.path.exists(model_card_path):
        raise ModelCardNotFoundError(f"model_card.json not found: {model_card_path}")

    try:
        with open(model_card_path, encoding="utf-8") as f:
            model_card = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise ModelCardNotFoundError(
            f"Failed to read model_card.json at {model_card_path}: {exc}"
        ) from exc

    real_data_files = _resolve_real_data_paths_from_card(model_id, model_card)
    if not real_data_files:
        raise DataSourceNotFoundError(
            f"No real data available for model '{model_id}': neither a preprocessed "
            f"copy nor any usable data_source paths in {model_card_path}."
        )

    metadata_path = os.path.join(model_dir, METADATA_FILENAME)

    return ResolvedSimulationInputs(
        simulation_id=simulation_id,
        simulation_dir=simulation_dir,
        synthetic_files=synthetic_files,
        model_id=model_id,
        metadata_path=metadata_path,
        real_data_files=real_data_files,
    )


def _table_name_from_file(path: str) -> str:
    """Return the catalog table name represented by a data file.

    Args:
        path (str): Source file path.

    Returns:
        str: File stem, with the simulation ``_synthetic`` suffix removed.
    """
    base, _ = os.path.splitext(os.path.basename(path))
    if base.endswith("_synthetic"):
        return base[: -len("_synthetic")]
    return base


def _read_columns_from_file(path: str) -> list[str]:
    """Read column names from a supported tabular data file.

    Args:
        path (str): CSV, JSON, or parquet file path.

    Returns:
        list[str]: Column names found in the file.
    """
    extension = os.path.splitext(path)[1].lstrip(".").lower()
    if extension == "csv":
        with open(path, encoding="utf-8", newline="") as fh:
            return [str(column) for column in (next(csv.reader(fh), []) or [])]
    if extension == "json":
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, list) and payload and isinstance(payload[0], dict):
            return [str(column) for column in payload[0].keys()]
        if isinstance(payload, dict):
            return [str(column) for column in payload.keys()]
    if extension == "parquet":
        import pyarrow.parquet as pq

        return [str(column) for column in pq.ParquetFile(path).schema_arrow.names]
    return []


def _columns_from_files(paths: list[str]) -> dict[str, list[str]]:
    """Read column names from a set of data files grouped by table name.

    Args:
        paths (list[str]): Data file paths to inspect.

    Returns:
        dict[str, list[str]]: Mapping of table names to column names.
    """
    tables: dict[str, list[str]] = {}
    for path in paths:
        try:
            columns = _read_columns_from_file(path)
        except Exception as exc:
            logger.warning("Could not read columns from %s: %s", path, exc)
            continue
        if columns:
            tables[_table_name_from_file(path)] = columns
    return tables


def _resolve_real_data_paths_from_card(model_id: str, model_card: dict) -> list[str]:
    """Return the paths that represent the data the model trained on.

    Preference order keeps evaluation honest: the synthetic side carries the
    post-preprocess schema (derived columns present, dropped columns absent),
    so the real side must too. Falls back to raw ``data_sources`` only for
    legacy models that pre-date persisted preprocessing.

    1. ``outputs/models/<model_id>/processed_data/*.parquet`` — model-local
       copy written by training when inspection metadata is edited.
    2. ``outputs/inspections/<inspection_id>/processed_data/*.parquet`` —
       inspection-level copy linked from the model card.
    3. Raw ``data_sources`` paths from the model card (only when no
       preprocessed copy exists).
    """
    model_processed = os.path.join(MODELS_DIR, model_id, PROCESSED_DATA_DIRNAME)
    if os.path.isdir(model_processed):
        paths = sorted(
            os.path.join(model_processed, name)
            for name in os.listdir(model_processed)
            if name.endswith(".parquet")
        )
        if paths:
            return paths

    inspection_id = model_card.get("inspection_id")
    if inspection_id:
        inspection_processed = os.path.join(INSPECTIONS_DIR, inspection_id, PROCESSED_DATA_DIRNAME)
        if os.path.isdir(inspection_processed):
            paths = sorted(
                os.path.join(inspection_processed, name)
                for name in os.listdir(inspection_processed)
                if name.endswith(".parquet")
            )
            if paths:
                return paths

    data_sources = model_card.get("data_sources") or []
    raw_paths: list[str] = []
    missing: list[str] = []
    for entry in data_sources:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not path:
            continue
        if not os.path.exists(path):
            missing.append(path)
            continue
        raw_paths.append(path)
    if missing and not raw_paths:
        # Surface the missing-paths context only when there's no preprocessed
        # fallback and no usable raw file — gives a clearer error.
        logger.warning(
            "Raw data_sources for model '%s' are missing and no preprocessed copy was found: %s",
            model_id,
            missing,
        )
    return raw_paths


def _columns_from_model_metadata(metadata_path: str) -> dict[str, list[str]]:
    """Read table columns from a Mostly AI model metadata file.

    Args:
        metadata_path (str): Path to ``metadata.json`` in a model folder.

    Returns:
        dict[str, list[str]]: Mapping of table names to column names.
    """
    if not os.path.exists(metadata_path):
        return {}
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)
    tables = metadata.get("tables", [])
    if not isinstance(tables, list):
        return {}

    result: dict[str, list[str]] = {}
    for table in tables:
        if not isinstance(table, dict):
            continue
        table_name = table.get("name")
        raw_columns = table.get("columns", [])
        if not table_name or not isinstance(raw_columns, list):
            continue
        columns = [
            str(column.get("name"))
            for column in raw_columns
            if isinstance(column, dict) and column.get("name")
        ]
        if columns:
            result[str(table_name)] = columns
    return result


def _columns_from_inspection_metadata(inspection_id: str | None) -> dict[str, list[str]]:
    """Read table columns from the source inspection metadata.

    Args:
        inspection_id (str | None): Source inspection identifier from a model card.

    Returns:
        dict[str, list[str]]: Mapping of table names to column names.
    """
    if not inspection_id:
        return {}
    metadata_path = os.path.join(INSPECTIONS_DIR, inspection_id, INSPECTION_METADATA_FILENAME)
    if not os.path.exists(metadata_path):
        return {}
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)
    encoding_types = metadata.get("encoding_types", {})
    if not isinstance(encoding_types, dict):
        return {}
    return {
        str(table): [str(column) for column in cols.keys()]
        for table, cols in encoding_types.items()
        if isinstance(cols, dict) and cols
    }


def _encoding_to_kind(encoding: object) -> str:
    """Map a Mostly AI ``model_encoding_type`` to a coarse UI kind.

    Returns one of ``numeric``, ``datetime`` or ``categorical`` (the default).
    """
    text = str(encoding or "").upper()
    if "DATETIME" in text:
        return "datetime"
    if "NUMERIC" in text:
        return "numeric"
    return "categorical"


def _column_types_from_model_metadata(metadata_path: str) -> dict[str, dict[str, str]]:
    """Read ``{table: {column: kind}}`` from a Mostly AI model metadata file."""
    if not os.path.exists(metadata_path):
        return {}
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)
    tables = metadata.get("tables", [])
    if not isinstance(tables, list):
        return {}

    result: dict[str, dict[str, str]] = {}
    for table in tables:
        if not isinstance(table, dict):
            continue
        table_name = table.get("name")
        raw_columns = table.get("columns", [])
        if not table_name or not isinstance(raw_columns, list):
            continue
        kinds = {
            str(column.get("name")): _encoding_to_kind(column.get("model_encoding_type"))
            for column in raw_columns
            if isinstance(column, dict) and column.get("name")
        }
        if kinds:
            result[str(table_name)] = kinds
    return result


def _column_types_from_inspection_metadata(
    inspection_id: str | None,
) -> dict[str, dict[str, str]]:
    """Read ``{table: {column: kind}}`` from the source inspection metadata."""
    if not inspection_id:
        return {}
    metadata_path = os.path.join(INSPECTIONS_DIR, inspection_id, INSPECTION_METADATA_FILENAME)
    if not os.path.exists(metadata_path):
        return {}
    with open(metadata_path, encoding="utf-8") as f:
        metadata = json.load(f)
    encoding_types = metadata.get("encoding_types", {})
    if not isinstance(encoding_types, dict):
        return {}
    return {
        str(table): {str(column): _encoding_to_kind(enc) for column, enc in cols.items()}
        for table, cols in encoding_types.items()
        if isinstance(cols, dict) and cols
    }


def list_simulation_columns(simulation_id: str) -> dict[str, list[str]]:
    """Return available table columns for a completed simulation.

    The lookup prefers the source inspection metadata and falls back to model
    metadata, real data files, then synthetic output files.

    Args:
        simulation_id (str): Simulation identifier under ``outputs/simulations``.

    Returns:
        dict[str, list[str]]: Mapping of table names to available column names.

    Raises:
        SimulationNotFoundError: No columns can be resolved for the simulation.
    """
    resolved = resolve_simulation_inputs(simulation_id)
    model_dir = os.path.dirname(resolved.metadata_path)
    model_card_path = os.path.join(model_dir, MODEL_CARD_FILENAME)
    try:
        with open(model_card_path, encoding="utf-8") as f:
            model_card = json.load(f)
        inspection_id = model_card.get("inspection_id")
    except Exception:
        inspection_id = None

    sources = (
        lambda: _columns_from_inspection_metadata(inspection_id),
        lambda: _columns_from_model_metadata(resolved.metadata_path),
        lambda: _columns_from_files(resolved.real_data_files),
        lambda: _columns_from_files(resolved.synthetic_files),
    )
    for load_columns in sources:
        try:
            columns_by_table = load_columns()
        except Exception as exc:
            logger.warning("Could not load columns for simulation %s: %s", simulation_id, exc)
            continue
        if columns_by_table:
            return columns_by_table

    raise SimulationNotFoundError(f"Could not find columns for simulation '{simulation_id}'.")


def main() -> None:
    """CLI entrypoint with selectable output format."""
    parser = argparse.ArgumentParser(description="List available simulations")
    parser.add_argument(
        "--format",
        choices=["json", "table"],
        default="json",
        help="Output format",
    )
    args = parser.parse_args()
    print(list_available_simulations_output(output=args.format))


if __name__ == "__main__":
    main()
