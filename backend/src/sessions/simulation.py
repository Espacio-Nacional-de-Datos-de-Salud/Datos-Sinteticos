"""Simulation flow service for the synthetic data tool."""

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from backend.src.config.general import (
    MOSTLYAI_DIR,
    SIM_CARD_FILENAME,
    SIMULATION_RUN_FOLDER_PREFIX,
    SIMULATIONS_DIR,
    SYNTHETIC_DATA_FILE_FORMAT,
    TIME_PROFILING_REPORT_FILENAME,
    normalize_synthetic_data_file_format,
    refresh_run_timestamp,
)
from backend.src.domain.conditional_seed import attach_sample_seeds
from backend.src.domain.general_sanity_checks import run_general_sanity_checks
from backend.src.domain.preprocessing.logical_rules import LogicalRuleManager
from backend.src.domain.preprocessing.metadata_extractor import MetadataExtractor
from backend.src.domain.preprocessing.metadata_formatter import MetadataFormatter
from backend.src.domain.synthesis import MostlyAIEngine
from backend.src.infrastructure.date_parsing import restore_date_format
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import (
    SIMULATION_PHASES,
    SimulationPhase,
    advance_progress,
    initial_progress,
)
from backend.src.infrastructure.time_profiling import profiler
from backend.src.infrastructure.utils import create_simulation_config, delete_empty_folders
from backend.src.runs.card_io import mark_card_failed, update_card_status, write_json
from backend.src.runs.tracking import SimulationTracker

logger = get_logger(__name__)


def _resolve_rejection_sampling_config(rule_manager: object) -> dict[str, Any]:
    config = getattr(rule_manager, "rejection_sampling_config", {}) or {}
    max_attempts = int(config.get("max_attempts", 5))
    overgenerate_factor = float(config.get("overgenerate_factor", 2.0))
    if max_attempts < 1:
        max_attempts = 1
    if overgenerate_factor < 1.0:
        overgenerate_factor = 1.0
    return {
        "max_attempts": max_attempts,
        "overgenerate_factor": overgenerate_factor,
    }


def _build_relationship_maps(metadata: dict) -> tuple[dict[str, str], dict[str, list[dict]]]:
    table_pks: dict[str, str] = {}
    table_fks: dict[str, list[dict]] = {}

    for table in metadata.get("tables", []):
        table_name = table.get("name")
        if not table_name:
            continue
        pk = table.get("primary_key")
        if pk:
            table_pks[table_name] = pk
        table_fks[table_name] = list(table.get("foreign_keys", []))

    return table_pks, table_fks


def _restore_original_date_formats(
    synthetic_results: dict[str, pd.DataFrame],
    rule_manager: LogicalRuleManager,
) -> None:
    """Re-render datetime columns back to the textual layout detected at inspection.

    Mostly AI emits datetime columns as ISO 8601; without this step a column
    originally formatted as DD/MM/YYYY would silently switch to YYYY-MM-DD in
    the synthetic output. Mutates ``synthetic_results`` in place.
    """
    date_formats = getattr(rule_manager, "date_formats", None) or {}
    for table_name, cols in date_formats.items():
        df = synthetic_results.get(table_name)
        if df is None:
            continue
        for col, fmt in cols.items():
            if fmt is None or col not in df.columns:
                continue
            df[col] = restore_date_format(df[col], fmt)


def _cascade_delete_tables(
    data_dict: dict[str, pd.DataFrame],
    metadata: dict,
    rejected_indices: dict[str, set[int]],
) -> tuple[dict[str, pd.DataFrame], dict[str, int]]:
    table_pks, table_fks = _build_relationship_maps(metadata)
    rejected_indices = {k: set(v) for k, v in rejected_indices.items()}
    rejected_pks: dict[str, set[Any]] = {}

    for table, indices in rejected_indices.items():
        if table not in data_dict:
            continue
        pk = table_pks.get(table)
        if not pk or pk not in data_dict[table].columns:
            continue
        df = data_dict[table]
        existing = [idx for idx in indices if idx in df.index]
        if existing:
            rejected_pks[table] = set(df.loc[existing, pk].dropna().tolist())

    changed = True
    while changed:
        changed = False
        for child_table, fks in table_fks.items():
            if child_table not in data_dict:
                continue
            child_df = data_dict[child_table]
            for fk in fks:
                fk_col = fk.get("column")
                parent_table = fk.get("referenced_table")
                if not fk_col or not parent_table:
                    continue
                if fk_col not in child_df.columns:
                    continue
                rejected_parent = rejected_pks.get(parent_table)
                if not rejected_parent:
                    continue
                to_drop = set(child_df[child_df[fk_col].isin(rejected_parent)].index)
                if not to_drop:
                    continue
                existing = rejected_indices.setdefault(child_table, set())
                new_indices = to_drop - existing
                if not new_indices:
                    continue
                existing.update(new_indices)
                pk = table_pks.get(child_table)
                if pk and pk in child_df.columns:
                    rejected_pks.setdefault(child_table, set()).update(
                        child_df.loc[list(new_indices), pk].dropna().tolist()
                    )
                changed = True

    filtered = {}
    rejected_counts = {}
    for table, df in data_dict.items():
        indices = rejected_indices.get(table, set())
        rejected_counts[table] = len(indices)
        if indices:
            filtered[table] = df.drop(index=sorted(indices))
        else:
            filtered[table] = df

    return filtered, rejected_counts


def _generate_with_rejection_sampling(
    engine: MostlyAIEngine,
    generator: object,
    metadata: dict | object,
    rule_manager: LogicalRuleManager,
    sample_size: int,
    cancel_event: threading.Event | None = None,
    progress_copy_dest: str | None = None,
    conditional: dict | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], str]:
    config = _resolve_rejection_sampling_config(rule_manager)
    max_attempts = config["max_attempts"]
    overgenerate_factor = config["overgenerate_factor"]
    logger.info(
        "Starting rejection sampling with max_attempts=%d and overgenerate_factor=%.2f",
        max_attempts,
        overgenerate_factor,
    )
    rejection_rules = rule_manager.get_rejection_rules()

    accepted_batches: dict[str, list[pd.DataFrame]] = {}
    accepted_counts: dict[str, int] = {}
    table_columns: dict[str, list[str]] = {}
    last_sd_id: str = ""
    stats: dict[str, Any] = {
        "enabled": True,
        "max_attempts": max_attempts,
        "overgenerate_factor": overgenerate_factor,
        "attempts": 0,
        "rules": [type(rule).__name__ for rule in rejection_rules],
        "tables": {},
        "partial_results": False,
    }

    table_names = [table.get("name") for table in metadata.get("tables", [])]

    for attempt in range(1, max_attempts + 1):
        remaining = {
            table: max(sample_size - accepted_counts.get(table, 0), 0) for table in table_names
        }
        if all(count == 0 for count in remaining.values()):
            logger.info(
                "Rejection sampling: All required samples accepted before reaching max attempts."
            )
            break
        logger.debug(f"Rejection sampling attempt {attempt}/{max_attempts}")
        logger.debug(f"Remaining samples needed per table: {remaining}")
        max_remaining = max(remaining.values())
        batch_size = max(1, int(max_remaining * overgenerate_factor))

        simulation_config = create_simulation_config(metadata, batch_size)
        runtime_config = attach_sample_seeds(simulation_config, conditional, metadata)
        raw_synthetic_results, last_sd_id = engine.simulate(
            generator,
            runtime_config,
            cancel_event=cancel_event,
            progress_copy_dest=progress_copy_dest,
        )
        synthetic_results = rule_manager.apply_all_post(raw_synthetic_results)
        _restore_original_date_formats(synthetic_results, rule_manager)

        for table_name, df in synthetic_results.items():
            table_columns.setdefault(table_name, list(df.columns))
            stats["tables"].setdefault(table_name, {"generated": 0, "accepted": 0, "rejected": 0})
            stats["tables"][table_name]["generated"] += int(len(df))

        rejection_indices = rule_manager.collect_rejection_failures(
            synthetic_results, rejection_rules
        )
        logger.debug(
            f"Number of rejections in attempt {attempt}: {sum(len(idxs) for idxs in rejection_indices.values())}"
        )
        for table_name, df in synthetic_results.items():
            remaining_count = remaining.get(table_name, 0)
            if remaining_count <= 0:
                rejection_indices.setdefault(table_name, set()).update(df.index)
                continue
            if len(df) > remaining_count:
                rejection_indices.setdefault(table_name, set()).update(df.index[remaining_count:])

        filtered_results, _ = _cascade_delete_tables(synthetic_results, metadata, rejection_indices)

        for table_name, df in filtered_results.items():
            accepted_batches.setdefault(table_name, []).append(df)
            accepted_counts[table_name] = accepted_counts.get(table_name, 0) + int(len(df))
            rejected = int(len(synthetic_results[table_name]) - len(df))
            stats["tables"][table_name]["accepted"] += int(len(df))
            stats["tables"][table_name]["rejected"] += rejected

        stats["attempts"] = attempt
    final_results: dict[str, pd.DataFrame] = {}
    for table_name in table_names:
        batches = accepted_batches.get(table_name, [])
        if batches:
            final_results[table_name] = pd.concat(batches, ignore_index=True)
        else:
            final_results[table_name] = pd.DataFrame(columns=table_columns.get(table_name, []))

    stats["partial_results"] = any(
        accepted_counts.get(table_name, 0) < sample_size for table_name in table_names
    )
    # apply post rules
    return final_results, stats, last_sd_id


@dataclass(frozen=True)
class SimulationSession:
    """Pre-initialized simulation session created before the background task runs."""

    simulation_id: str
    output_directory: str
    card_path: str
    timestamp: str
    synthetic_data_file_format: str


def initialize_simulation_session(
    model_id: str,
    synthetic_data_file_format: str | None = None,
    name: str | None = None,
) -> SimulationSession:
    """Create the output folder and the ``in_progress`` sim card.

    Refreshes the run timestamp and materializes the session on disk.

    Args:
        model_id (str): ID of the model to simulate from.

    Returns:
        SimulationSession: Descriptor of the newly created simulation session.
    """
    timestamp = refresh_run_timestamp()
    effective_file_format = normalize_synthetic_data_file_format(
        synthetic_data_file_format or SYNTHETIC_DATA_FILE_FORMAT
    )
    simulation_id = f"{SIMULATION_RUN_FOLDER_PREFIX}_{timestamp}"
    output_directory = os.path.join(SIMULATIONS_DIR, simulation_id)
    synthetic_data_directory = os.path.join(output_directory, "synthetic_data")
    card_path = os.path.join(output_directory, SIM_CARD_FILENAME)

    os.makedirs(synthetic_data_directory, exist_ok=True)
    logger.info("Created simulation output directory: %s", output_directory)

    write_json(
        card_path,
        {
            "simulation_id": simulation_id,
            "simulation_name": name.strip() if name and name.strip() else simulation_id,
            "status": "in_progress",
            "model_id": model_id,
            "timestamp": timestamp,
            "synthetic_data_file_format": effective_file_format,
            "progress": initial_progress(SIMULATION_PHASES),
        },
        indent=4,
    )

    return SimulationSession(
        simulation_id=simulation_id,
        output_directory=output_directory,
        card_path=card_path,
        timestamp=timestamp,
        synthetic_data_file_format=effective_file_format,
    )


def extract_synthetic_metadata(synthetic_results: dict[str, pd.DataFrame]) -> dict:
    """Extract and format metadata from synthetic data.

    Analyzes the generated synthetic data to detect structural metadata
    (primary keys, foreign keys, and column encoding types) and formats it
    into a standardized structure compatible with the synthesis engine.

    Args:
        synthetic_results (dict[str, pd.DataFrame]): Dictionary of synthetic data
            tables {table_name: dataframe}.

    Returns:
        dict: Formatted metadata {tables: [{name, columns, foreign_keys, ...}, ...]}.
    """
    try:
        extractor = MetadataExtractor(synthetic_results)
        pks = extractor.extract_primary_keys()
        fks = extractor.extract_foreign_keys(pks)
        encoding_types = extractor.extract_encoding_types(pks)

        relationships_data = {"pks": pks, "fks": fks}
        formatter = MetadataFormatter(engine_name="mostly")
        metadata = formatter.format(
            data_dfs=synthetic_results,
            relationships_data=relationships_data,
            types_data=encoding_types,
        )
        return metadata
    except Exception as error:
        logger.warning("Failed to extract synthetic metadata: %s", error)
        return {"tables": []}


def run_all_sanity_checks(
    synthetic_results: dict[str, pd.DataFrame],
    metadata: dict | object,
    rule_manager: object,
) -> pd.DataFrame | None:
    """Runs all sanity checks (logical rules + general structural checks).

    Args:
        synthetic_results (dict): Generated synthetic data dataframes.
        metadata (dict | object): Model metadata definitions.
        rule_manager (object): The RuleManager instance loaded from training.

    Returns:
        pd.DataFrame | None: Target combined DataFrame of validation reports,
                             or None if there are no checks.
    """
    sanity_checks: list[pd.DataFrame] = []

    rules_report = rule_manager.run_rules_sanity_checks(synthetic_results)
    if not rules_report.empty:
        sanity_checks.append(rules_report)

    general_report = run_general_sanity_checks(
        synthetic_data=synthetic_results,
        metadata=metadata,
        rule_manager=rule_manager,
    )
    if not general_report.empty:
        sanity_checks.append(general_report)

    if sanity_checks:
        return pd.concat(sanity_checks, ignore_index=True)
    return None


def run_simulation_flow(
    generator: object,
    metadata: dict | object,
    rule_manager: object,
    model_id: str,
    sample_size: int | None,
    mostly_config_path: str,
    synthetic_data_file_format: str | None = None,
    mostly_ai_overrides: dict | None = None,
    pipeline_id: str = "none",
    job_name: str | None = None,
    session: SimulationSession | None = None,
    cancel_event: threading.Event | None = None,
    table_sample_sizes: dict[str, int] | None = None,
    conditional: dict | None = None,
) -> str | None:
    """Execute the core simulation workflow entirely isolated from callers.

    Instantiates a SimulationTracker, builds execution cards, requests generation
    from the Engine, applies post-processing logic, conducts sanity checks, and
    extracts metadata from synthetic data.

    Args:
        generator (object): The previously restored Mostly AI Generator.
        metadata (dict | object): Restored model schema metadata from training.
        rule_manager (object): Restored applied rules to use in post-processing.
        model_id (str): The unique ID or folder name for the model context.
        sample_size (int | None): Default row count applied to subject tables
            (those without an ``is_context`` FK) when ``table_sample_sizes``
            does not override them. Mostly AI cascades counts for context
            children from their parent, so this value never directly sets a
            child table's size.
        mostly_config_path (str): Mostly AI configuration bindings.
        mostly_ai_overrides (dict | None, optional): Real-time parameter overlaps.
        pipeline_id (str, optional): ID grouping this run optionally.
        table_sample_sizes (dict[str, int] | None, optional): Per-table row-count
            overrides. Only entries targeting subject tables take effect;
            entries for context children are ignored with a warning (Mostly
            AI has no native way to set their size — they always cascade).
        conditional (dict | None, optional): Conditional-generation spec. When
            present, a ``sample_seed`` table is built for the target subject
            table so generation is conditioned on the constrained columns.
        job_name (str | None, optional): Explicit nomenclature for job logging.

    Returns:
        str | None: The simulation tracking ID if successful. None on failure.
    """
    from backend.src.infrastructure.cancellation import JobCancelled

    if cancel_event is not None and cancel_event.is_set():
        logger.info(
            "Simulation %s cancelled before execution started.",
            session.simulation_id if session else "",
        )
        if session:
            update_card_status(session.card_path, "cancelled")
        return None

    try:
        if session:
            advance_progress(session.card_path, SIMULATION_PHASES, SimulationPhase.GENERATING)
        with SimulationTracker(
            model_id=model_id,
            pipeline_id=pipeline_id,
            job_name=job_name,
            simulation_id=session.simulation_id if session else None,
            synthetic_data_file_format=(
                session.synthetic_data_file_format
                if session
                else normalize_synthetic_data_file_format(
                    synthetic_data_file_format or SYNTHETIC_DATA_FILE_FORMAT
                )
            ),
        ) as sim_tracker:
            engine = MostlyAIEngine(
                config_path=mostly_config_path,
                config_overrides=mostly_ai_overrides,
                run_dir=sim_tracker.output_directory,
                local_dir=MOSTLYAI_DIR,
            )

            # Each engine starts a fresh SDK server on a new port; the generator
            # from training is gone from that server's state after export_to_file.
            # Re-import from the zip so this server's instance knows about it.
            generator, _ = engine.load_generator_by_id(model_id)

            simulation_config = create_simulation_config(metadata, sample_size, table_sample_sizes)
            sim_tracker.save_sim_config(simulation_config)
            sim_tracker.save_sim_card(sample_size=sample_size)

            # The seed DataFrame is non-serializable, so it is injected into a
            # runtime-only copy of the config *after* the JSON config is saved.
            runtime_config = attach_sample_seeds(simulation_config, conditional, metadata)
            if conditional and conditional.get("conditions"):
                write_json(
                    os.path.join(sim_tracker.output_directory, "conditional_config.json"),
                    conditional,
                    indent=4,
                )

            raw_rejection_rules = (
                rule_manager.get_rejection_rules()
                if hasattr(rule_manager, "get_rejection_rules")
                else []
            )
            # remove all rejection rules that apply to tables not not present
            table_names = {table.get("name") for table in simulation_config.get("tables", [])}
            rejection_rules = [
                rule for rule in raw_rejection_rules if rule.table_target in table_names
            ]
            use_rejection = bool(rejection_rules) and sample_size is not None
            with profiler.phase("mostlyai simulate"):
                job_progress_dest = os.path.join(sim_tracker.output_directory, "job_progress.json")
                if use_rejection:
                    synthetic_results, rejection_stats, _ = _generate_with_rejection_sampling(
                        engine=engine,
                        generator=generator,
                        metadata=metadata,
                        rule_manager=rule_manager,
                        sample_size=sample_size,
                        cancel_event=cancel_event,
                        progress_copy_dest=job_progress_dest,
                        conditional=conditional,
                    )
                    rejection_stats["sample_size"] = sample_size
                    sim_tracker.save_rejection_sampling_report(rejection_stats)
                else:
                    if rejection_rules and sample_size is None:
                        logger.warning(
                            "Rejection sampling requested but sample_size is None; falling back to single-pass simulation."
                        )
                    raw_synthetic_results, _ = engine.simulate(
                        generator,
                        runtime_config,
                        cancel_event=cancel_event,
                        progress_copy_dest=job_progress_dest,
                    )
                    if session:
                        advance_progress(
                            session.card_path, SIMULATION_PHASES, SimulationPhase.APPLYING_RULES
                        )
                    with profiler.phase("apply rules"):
                        synthetic_results = rule_manager.apply_all_post(raw_synthetic_results)
                        _restore_original_date_formats(synthetic_results, rule_manager)
                    if rejection_rules:
                        rejection_indices = rule_manager.collect_rejection_failures(
                            synthetic_results, rejection_rules
                        )
                        if rejection_indices:
                            synthetic_results, _ = _cascade_delete_tables(
                                synthetic_results, metadata, rejection_indices
                            )
            with profiler.phase("save results"):
                sim_tracker.save_synthetic_results(synthetic_results)
            if session:
                advance_progress(session.card_path, SIMULATION_PHASES, SimulationPhase.VALIDATION)
            with profiler.phase("sanity checks"):
                # check if this is being run twice
                combined_report = run_all_sanity_checks(synthetic_results, metadata, rule_manager)
            if combined_report is not None:
                sim_tracker.save_sanity_report(combined_report)

            with profiler.phase("save metadata"):
                synthetic_metadata = extract_synthetic_metadata(synthetic_results)
                sim_tracker.save_sim_metadata(synthetic_metadata)

            logger.info("Simulation finished successfully (ID: %s).", sim_tracker.simulation_id)
            delete_empty_folders(Path(sim_tracker.output_directory).parent.parent)

            return sim_tracker.simulation_id

    except JobCancelled:
        return None
    except Exception as error:
        logger.error("Simulation flow failed: %s", error, exc_info=True)
        if session:
            mark_card_failed(session.card_path, error)
        return None
    finally:
        if session:
            timing_report_path = os.path.join(
                session.output_directory,
                TIME_PROFILING_REPORT_FILENAME,
            )
            profiler.report("Simulation timing breakdown", output_path=timing_report_path)


def run_simulation_flow_from_model(
    model_id: str,
    sample_size: int | None,
    mostly_config_path: str,
    synthetic_data_file_format: str | None = None,
    mostly_ai_overrides: dict | None = None,
    pipeline_id: str = "none",
    job_name: str | None = None,
    session: SimulationSession | None = None,
    cancel_event: threading.Event | None = None,
    table_sample_sizes: dict[str, int] | None = None,
    conditional: dict | None = None,
) -> str | None:
    """Load a trained generator by model ID and run the simulation flow.

    Wraps ``load_generator_artifacts`` + ``run_simulation_flow`` so API
    background tasks can trigger a simulation from just a ``model_id``.

    Args:
        model_id: Folder name of the trained model to simulate from.
        sample_size: Default row count for subject tables (see
            ``run_simulation_flow``).
        mostly_config_path: Path to the Mostly AI configuration file.
        mostly_ai_overrides: Engine overrides applied at runtime.
        pipeline_id: Pipeline ID grouping this run.
        job_name: Human name of the job currently executing.
        session: Pre-initialized session; when provided its ``simulation_id`` is
            reused so the client-facing ID is stable across pre-init and execution.
        table_sample_sizes: Per-table row-count overrides for subject tables.
            Context-child entries are ignored (Mostly AI cascades their counts
            from the parent).
        conditional: Conditional-generation spec (see ``run_simulation_flow``).

    Returns:
        The ``simulation_id`` if successful, ``None`` on failure.
    """
    try:
        from backend.src.sessions.artifacts import load_generator_artifacts

        if session:
            advance_progress(
                session.card_path, SIMULATION_PHASES, SimulationPhase.LOADING_GENERATOR
            )
        with profiler.phase("load generator artifacts"):
            generator, metadata, rule_manager = load_generator_artifacts(
                model_id, mostly_config_path
            )
        return run_simulation_flow(
            generator=generator,
            metadata=metadata,
            rule_manager=rule_manager,
            model_id=model_id,
            sample_size=sample_size,
            mostly_config_path=mostly_config_path,
            synthetic_data_file_format=synthetic_data_file_format,
            mostly_ai_overrides=mostly_ai_overrides,
            pipeline_id=pipeline_id,
            job_name=job_name,
            session=session,
            cancel_event=cancel_event,
            table_sample_sizes=table_sample_sizes,
            conditional=conditional,
        )
    except Exception as error:
        logger.error("Simulation-from-model flow failed: %s", error, exc_info=True)
        if session:
            mark_card_failed(session.card_path, error)
        return None
