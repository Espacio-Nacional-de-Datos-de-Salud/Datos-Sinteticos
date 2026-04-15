"""CLI and helpers to list simulations available under ``outputs/simulations/``.

Scans simulation folders, reads their ``sim_card.json`` and associated
``model_card.json`` for lineage, and resolves simulation inputs for the
evaluation stage (synthetic files, real data references, model linkage).
"""

import argparse
import json
import os
from dataclasses import dataclass

from config.general_config import (
    METADATA_FILENAME,
    MODEL_CARD_FILENAME,
    MODELS_DIR,
    SIM_CARD_FILENAME,
    SIMULATION_RUN_FOLDER_PREFIX,
    SIMULATIONS_DIR,
)

from src.core.errors import (
    DataSourceNotFoundError,
    ModelCardNotFoundError,
    SimCardNotFoundError,
    SimulationNotFoundError,
)
from src.core.logging_config import get_logger

logger = get_logger(__name__)

SYNTHETIC_DATA_DIRNAME = "synthetic_data"


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
    import glob as _glob

    run_folders = sorted(
        _glob.glob(os.path.join(SIMULATIONS_DIR, SIMULATION_RUN_FOLDER_PREFIX + "_*")),
        reverse=True,
    )

    simulations = []
    for folder in run_folders:
        synthetic_dir = os.path.join(folder, SYNTHETIC_DATA_DIRNAME)
        if not os.path.isdir(synthetic_dir):
            continue

        sim_card_path = os.path.join(folder, SIM_CARD_FILENAME)

        sim_info: dict = {
            "simulation_id": os.path.basename(folder),
            "folder": folder,
            "timestamp": "",
            "model_id": None,
            "tables": "",
            "training_table_sizes": {},
            "model_accuracy": None,
        }

        if os.path.exists(sim_card_path):
            try:
                with open(sim_card_path, encoding="utf-8") as f:
                    card = json.load(f)
                sim_info["timestamp"] = card.get("timestamp", "")
                sim_info["model_id"] = card.get("model_id")
            except Exception as exc:
                logger.warning("Error reading sim_card from %s: %s", folder, exc)

        # Extract table names from synthetic_data/ files.
        try:
            synthetic_tables = []
            for fname in sorted(os.listdir(synthetic_dir)):
                base, _ = os.path.splitext(fname)
                if base.endswith("_synthetic"):
                    base = base[: -len("_synthetic")]
                synthetic_tables.append(base)
            sim_info["tables"] = ", ".join(synthetic_tables)
        except OSError as exc:
            logger.warning("Error listing synthetic_data in %s: %s", folder, exc)

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

    synthetic_files = sorted(
        os.path.join(synthetic_dir, fname)
        for fname in os.listdir(synthetic_dir)
        if os.path.isfile(os.path.join(synthetic_dir, fname))
    )
    if not synthetic_files:
        raise SimulationNotFoundError(f"No synthetic files found in {synthetic_dir}")

    sim_card_path = os.path.join(simulation_dir, SIM_CARD_FILENAME)
    if not os.path.exists(sim_card_path):
        raise SimCardNotFoundError(f"sim_card.json not found: {sim_card_path}")

    try:
        with open(sim_card_path, encoding="utf-8") as f:
            sim_card = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        raise SimCardNotFoundError(f"Failed to read sim_card.json at {sim_card_path}: {exc}")

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
        raise ModelCardNotFoundError(f"Failed to read model_card.json at {model_card_path}: {exc}")

    data_sources = model_card.get("data_sources") or []
    if not data_sources:
        raise DataSourceNotFoundError(f"model_card.json at {model_card_path} has no data_sources.")

    real_data_files: list[str] = []
    missing: list[str] = []
    for entry in data_sources:
        path = entry.get("path") if isinstance(entry, dict) else None
        if not path:
            continue
        if not os.path.exists(path):
            missing.append(path)
            continue
        real_data_files.append(path)

    if missing:
        raise DataSourceNotFoundError(
            f"Real data files referenced by model '{model_id}' are missing: {missing}"
        )
    if not real_data_files:
        raise DataSourceNotFoundError(
            f"model_card.json at {model_card_path} has no usable data_source paths."
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
