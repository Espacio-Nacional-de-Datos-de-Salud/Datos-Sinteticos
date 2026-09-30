"""Simulation flow service for the synthetic data tool."""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from pathlib import Path
from collections.abc import Iterable
from typing import Any

import pandas as pd

from backend.src.config.general import (
    MODEL_CARD_FILENAME,
    MODELS_DIR,
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
from backend.src.domain.synthesis import (
    SynthesisEngine,
    create_engine,
    resolve_active_engine,
)
from backend.src.infrastructure.date_parsing import restore_date_format
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import (
    SIMULATION_PHASES,
    ProfilerPhase,
    SimulationPhase,
    advance_progress,
    initial_progress,
)
from backend.src.infrastructure.time_profiling import profiler
from backend.src.infrastructure.utils import (
    _is_subject_table,
    create_simulation_config,
    delete_empty_folders,
)
from backend.src.runs.card_io import mark_card_failed, read_json, update_card_status, write_json
from backend.src.runs.tracking import SimulationTracker

logger = get_logger(__name__)


def _resolve_rejection_sampling_config(
    rule_manager: object,
    sampling_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Resolve sampling knobs: per-request overrides > rules.yaml > defaults.

    Defaults lean on overgeneration (×3) over retries (2 attempts): every retry
    restarts the engine, which costs far more than drawing a bigger batch.
    """
    active_config = {}
    try:
        from backend.src.domain.rules_config import extract_rules_and_rejection_config
        from backend.src.sessions.configs import resolve_config_path

        rules_path = str(resolve_config_path("rules"))
        _, rejection_config = extract_rules_and_rejection_config(rules_path)
        active_config = rejection_config.as_dict()
    except Exception as e:
        logger.warning("Could not read active rules.yaml configuration: %s", e)

    overrides = sampling_overrides or {}
    config = getattr(rule_manager, "rejection_sampling_config", {}) or {}
    max_attempts = int(
        overrides.get("max_attempts")
        or active_config.get("max_attempts")
        or config.get("max_attempts", 2)
    )
    overgenerate_factor = float(
        overrides.get("overgenerate_factor")
        or active_config.get("overgenerate_factor")
        or config.get("overgenerate_factor", 3.0)
    )
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


def _resolve_subject_targets(
    metadata: dict | object,
    sample_size: int | None,
    table_sample_sizes: dict[str, int] | None,
) -> dict[str, int]:
    """Resolve the requested row count per *subject* table.

    Only subject tables (no ``is_context`` FK) have a controllable size — the
    Mostly engine cascades context-child counts from their parent and ignores any
    explicit child size. So rejection sampling is driven entirely by these
    subject targets: overgenerate subjects, let children cascade, then reject the
    non-compliant child rows. A per-table override wins over the global
    ``sample_size`` fallback; entries for non-subject tables are ignored.

    Returns:
        dict[str, int]: ``{subject_table: target_rows}`` for tables with a
            positive target. Empty when no subject size was requested (in which
            case rejection sampling cannot run — see the gate in the caller).
    """
    targets: dict[str, int] = {}
    for table_meta in metadata.get("tables", []):
        name = table_meta["name"]
        if not _is_subject_table(table_meta):
            continue
        size = None
        if table_sample_sizes and name in table_sample_sizes:
            size = table_sample_sizes[name]
        elif sample_size is not None:
            size = sample_size
        if size is not None and int(size) > 0:
            targets[name] = int(size)
    return targets


def _resolve_mother_table(
    metadata: dict | object,
    sample_size: int | None,
    table_sample_sizes: dict[str, int] | None,
    training_table_sizes: dict[str, int] | None,
) -> tuple[str | None, int | None]:
    """Pick the mother (root subject) table and its enforced row count.

    The mother table is the subject table (no ``is_context`` FK) whose size the
    engine actually honors; context children cascade their counts from it, so its
    count is the only meaningful single number for the run. When several subject
    tables exist we take the one with the largest resolved size as the mother.

    Each subject's size is resolved with the same precedence the engine uses:
    a per-table override, then the global ``sample_size``, then the training size
    (the default when nothing was requested).

    Returns:
        tuple[str | None, int | None]: ``(mother_table, size)``; ``(None, None)``
            when no subject size could be resolved.
    """
    training_table_sizes = training_table_sizes or {}
    mother: str | None = None
    mother_size: int | None = None
    for table_meta in metadata.get("tables", []):
        name = table_meta["name"]
        if not _is_subject_table(table_meta):
            continue
        if table_sample_sizes and name in table_sample_sizes:
            size = table_sample_sizes[name]
        elif sample_size is not None:
            size = sample_size
        else:
            size = training_table_sizes.get(name)
        if size is None or int(size) <= 0:
            continue
        if mother_size is None or int(size) > mother_size:
            mother, mother_size = name, int(size)
    return mother, mother_size


def _load_training_table_sizes(model_id: str | None) -> dict[str, int]:
    """Read per-table training row counts persisted in the model card.

    Used only to derive *informational* child-table targets for rejection
    sampling (the engine cannot be asked for a child size). Returns an empty
    mapping when unavailable.
    """
    if not model_id:
        return {}
    card_path = os.path.join(MODELS_DIR, model_id, MODEL_CARD_FILENAME)
    try:
        card = read_json(card_path)
    except (FileNotFoundError, ValueError):
        return {}
    sizes = card.get("training_table_sizes") or {}
    return {k: int(v) for k, v in sizes.items() if isinstance(v, (int, float))}


def _resolve_child_targets(
    metadata: dict | object,
    rejection_child_tables: set[str],
    subject_targets: dict[str, int],
    training_table_sizes: dict[str, int],
) -> dict[str, int]:
    """Proportional row targets for rejection-rule *child* tables.

    The engine cascades child counts from the subject, so these targets cannot be
    requested. They exist only to tell rejection sampling how hard to try: a child
    table should end up with roughly ``ratio × subject_target`` compliant rows,
    where ``ratio`` is its child:subject count in the real training data. When the
    subject size equals the real one the target equals the real child size;
    otherwise it scales proportionally.

    Returns ``{child_table: target_rows}`` for child tables we can scale; tables
    without usable training sizes are omitted (no target → no extra retries).
    """
    table_pks, table_fks = _build_relationship_maps(
        metadata if isinstance(metadata, dict) else {"tables": []}
    )
    targets: dict[str, int] = {}
    for child in rejection_child_tables:
        child_size = training_table_sizes.get(child)
        if not child_size:
            continue
        # Find the subject this child cascades from (context FK → a subject table).
        subject = None
        for fk in table_fks.get(child, []):
            ref = fk.get("referenced_table")
            if ref in subject_targets:
                subject = ref
                break
        if subject is None and len(subject_targets) == 1:
            subject = next(iter(subject_targets))
        if subject is None:
            continue
        subject_train = training_table_sizes.get(subject)
        if not subject_train:
            continue
        ratio = child_size / subject_train
        targets[child] = max(1, round(ratio * subject_targets[subject]))
    return targets


def _resolve_display_targets(
    table_names: Iterable[str],
    training_table_sizes: dict[str, int],
    anchor_table: str | None,
    anchor_rows: int | None,
) -> dict[str, int]:
    """Per-table row objetivo for the report, scaled to the requested size.

    Purely informational: every table's real training count is rescaled by
    ``anchor_rows / anchor_train`` so the «Objetivo» column reflects the
    proportions of the real data at the requested scale — including tables that
    carry no rejection rule. No objetivo is guaranteed: the run drives the anchor
    (fixed) table towards its goal and the rest cascade, but a restrictive rule
    can leave even the anchor short — exactly the gap this column exposes.
    Returns ``{}`` when there is no usable anchor.
    """
    if not anchor_table or not anchor_rows or anchor_rows <= 0:
        return {}
    anchor_train = training_table_sizes.get(anchor_table) or 0
    if anchor_train <= 0:
        return {}
    factor = anchor_rows / anchor_train
    targets: dict[str, int] = {}
    for name in table_names:
        size = training_table_sizes.get(name)
        if size:
            targets[name] = max(1, round(size * factor))
    return targets


def _select_best_subjects(
    results: dict[str, pd.DataFrame],
    metadata: dict | object,
    subject_targets: dict[str, int],
    rejection_child_tables: set[str],
) -> dict[str, pd.DataFrame]:
    """Keep exactly ``target`` subjects per subject table — the ones that carry the
    most compliant child rows — and cascade-drop the rest.

    Children belong to subjects, so to maximise compliant child rows while holding
    the subject count exactly at the requested size we rank each subject by how
    many (already rule-compliant) child rows it contributes across the
    rejection-rule child tables, keep the top ``target``, and cascade-delete the
    non-selected subjects (which removes their children, preserving referential
    integrity). Subjects that tie or contribute nothing still fill the count so
    the subject total stays exact.
    """
    table_pks, table_fks = _build_relationship_maps(
        metadata if isinstance(metadata, dict) else {"tables": []}
    )
    drop_indices: dict[str, set[int]] = {}
    for subject, target in subject_targets.items():
        df = results.get(subject)
        if df is None or len(df) <= target:
            continue
        pk = table_pks.get(subject)
        if not pk or pk not in df.columns:
            # No PK to attribute children by — keep the first ``target`` rows.
            drop_indices[subject] = set(df.index[target:])
            continue

        score = pd.Series(0, index=df[pk].to_numpy(), dtype="int64")
        for child in rejection_child_tables:
            cdf = results.get(child)
            if cdf is None or cdf.empty:
                continue
            fk_col = next(
                (
                    fk.get("column")
                    for fk in table_fks.get(child, [])
                    if fk.get("referenced_table") == subject
                ),
                None,
            )
            if not fk_col or fk_col not in cdf.columns:
                continue
            counts = cdf.groupby(fk_col).size()
            score = score.add(counts, fill_value=0)
        # Top ``target`` subject keys by compliant-child contribution.
        ranked_pks = score.sort_values(ascending=False, kind="stable").index[:target]
        keep = set(ranked_pks)
        drop_indices[subject] = set(df.index[~df[pk].isin(keep)])

    if not drop_indices:
        return results
    trimmed, _ = _cascade_delete_tables(results, metadata, drop_indices)
    return trimmed


def _generate_with_rejection_sampling(
    engine: SynthesisEngine,
    generator: object,
    metadata: dict | object,
    rule_manager: LogicalRuleManager,
    subject_targets: dict[str, int],
    cancel_event: threading.Event | None = None,
    progress_copy_dest: str | None = None,
    conditional: dict | None = None,
    training_table_sizes: dict[str, int] | None = None,
    session: SimulationSession | None = None,
    sampling_overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], str]:
    config = _resolve_rejection_sampling_config(rule_manager, sampling_overrides)
    max_attempts = config["max_attempts"]
    overgenerate_factor = config["overgenerate_factor"]
    logger.info(
        "Starting rejection sampling with max_attempts=%d and overgenerate_factor=%.2f",
        max_attempts,
        overgenerate_factor,
    )
    rejection_rules = rule_manager.get_rejection_rules()

    table_names = [table.get("name") for table in metadata.get("tables", [])]

    # Child tables (non-subject) carrying a rejection rule. Their compliant-row
    # targets cannot be requested from the engine (it cascades child counts), so
    # we use them only to decide how hard to retry and to report the gap.
    rejection_child_tables = {
        rule.table_target for rule in rejection_rules if rule.table_target not in subject_targets
    }
    child_targets = _resolve_child_targets(
        metadata, rejection_child_tables, subject_targets, training_table_sizes or {}
    )

    # Informational per-table objetivo for the report: scale every table to the
    # proportions of the real data, anchored on the largest subject (the table
    # whose size is held exactly). Subject targets stay exact; non-subject tables
    # show the proportional goal they cascade towards but cannot be forced to hit.
    anchor_table = max(subject_targets, key=subject_targets.get, default=None)
    display_targets = _resolve_display_targets(
        table_names,
        training_table_sizes or {},
        anchor_table,
        subject_targets.get(anchor_table) if anchor_table else None,
    )
    all_targets = {**display_targets, **subject_targets}

    last_sd_id: str = ""
    stats: dict[str, Any] = {
        "enabled": True,
        "max_attempts": max_attempts,
        "overgenerate_factor": overgenerate_factor,
        "attempts": 0,
        "rules": [type(rule).__name__ for rule in rejection_rules],
        "tables": {},
        "partial_results": False,
        "subject_targets": dict(subject_targets),
        "child_targets": dict(child_targets),
        "all_targets": all_targets,
        "fixed_tables": sorted(subject_targets),
        "selection": "best_subset",
    }

    # Best-subset strategy: each attempt draws a progressively larger single
    # batch (overgenerate_factor × attempt × target), rejects non-compliant rows,
    # then keeps exactly ``target`` subjects — the ones contributing the most
    # compliant child rows. Subjects stay exact; a bigger draw on later attempts
    # widens the candidate pool to better hit child targets. We keep the best
    # attempt (most compliant child rows) and stop early once child targets are
    # met. Attempts are not concatenated — that would risk duplicate subject PKs
    # across batches and corrupt FK cascades.
    best_results: dict[str, pd.DataFrame] | None = None
    best_raw_results: dict[str, pd.DataFrame] | None = None
    best_score = -1
    best_table_stats: dict[str, dict[str, int]] = {}
    best_attempt = 1
    best_post_warnings: list[dict[str, Any]] = []
    attempt_history = []

    for attempt in range(1, max_attempts + 1):
        _update_attempt_progress(session, attempt, max_attempts)
        with profiler.phase(f"Intento {attempt}"):
            batch_targets = {
                table: max(target, int(target * overgenerate_factor))
                for table, target in subject_targets.items()
            }
            logger.debug(
                f"Rejection sampling attempt {attempt}/{max_attempts}; draw={batch_targets}"
            )
            simulation_config = create_simulation_config(
                metadata, sample_size=None, table_sample_sizes=batch_targets
            )
            runtime_config = attach_sample_seeds(simulation_config, conditional, metadata)
            raw_synthetic_results, last_sd_id = engine.simulate(
                generator,
                runtime_config,
                cancel_event=cancel_event,
                progress_copy_dest=progress_copy_dest,
            )
            synthetic_results = rule_manager.apply_all_post(raw_synthetic_results)
            post_warnings = list(getattr(rule_manager, "post_warnings", []))
            _restore_original_date_formats(synthetic_results, rule_manager)

            generated_counts = {t: int(len(df)) for t, df in synthetic_results.items()}

            # Drop rows that fail the rule (plus any FK-dependent children).
            rule_rejection_indices = rule_manager.collect_rejection_failures(
                synthetic_results, rejection_rules
            )
            logger.debug(
                f"Rule rejections in attempt {attempt}: "
                f"{sum(len(idxs) for idxs in rule_rejection_indices.values())}"
            )
            compliant_results, rule_rejected_counts = _cascade_delete_tables(
                synthetic_results, metadata, rule_rejection_indices
            )
            compliant_counts = {t: int(len(df)) for t, df in compliant_results.items()}

            # Keep exactly ``target`` subjects — those with the most compliant child
            # rows — and cascade-drop the rest (overflow, not a rule failure).
            selected = _select_best_subjects(
                compliant_results, metadata, subject_targets, rejection_child_tables
            )

            attempt_table_stats: dict[str, dict[str, int]] = {}
            for table_name in table_names:
                accepted = int(len(selected.get(table_name, pd.DataFrame())))
                generated = generated_counts.get(table_name, 0)
                rejected = int(rule_rejected_counts.get(table_name, 0))
                compliant = compliant_counts.get(table_name, 0)
                attempt_table_stats[table_name] = {
                    "generated": generated,
                    "accepted": accepted,
                    "rejected": rejected,
                    "trimmed": max(0, compliant - accepted),
                }

            # Score this attempt by total compliant child rows kept for rejection
            # tables — that is exactly what we are trying to maximise.
            score = sum(
                attempt_table_stats.get(t, {}).get("accepted", 0) for t in rejection_child_tables
            )

            attempt_history.append(
                {
                    "attempt": attempt,
                    "multiplier": float(overgenerate_factor),
                    "tables": attempt_table_stats,
                    "score": score,
                    "post_reconstruction_warnings": post_warnings,
                }
            )

            stats["attempts"] = attempt
            if score > best_score:
                best_score = score
                best_results = selected
                best_table_stats = attempt_table_stats
                best_attempt = attempt
                best_post_warnings = post_warnings
                best_raw_results = {t: df.copy() for t, df in raw_synthetic_results.items()}

            child_targets_met = all(
                attempt_table_stats.get(t, {}).get("accepted", 0) >= target
                for t, target in child_targets.items()
            )
            subjects_met = all(
                int(len(selected.get(t, pd.DataFrame()))) >= target
                for t, target in subject_targets.items()
            )
            if subjects_met and child_targets_met:
                logger.info(
                    "Rejection sampling: subject and child targets met on attempt %d.", attempt
                )
                break

    final_results: dict[str, pd.DataFrame] = best_results or {}
    for table_name in table_names:
        final_results.setdefault(table_name, pd.DataFrame())
    stats["tables"] = best_table_stats
    # Degraded reconstructions (e.g. an all-null target) cannot be caught by the
    # null-tolerant rejection check, so the report must carry them explicitly.
    stats["post_reconstruction_warnings"] = best_post_warnings

    for history_entry in attempt_history:
        history_entry["is_best"] = history_entry["attempt"] == best_attempt
    stats["attempt_history"] = attempt_history

    stats["partial_results"] = any(
        int(len(final_results.get(t, pd.DataFrame()))) < target
        for t, target in subject_targets.items()
    ) or any(
        best_table_stats.get(t, {}).get("accepted", 0) < target
        for t, target in child_targets.items()
    )
    return final_results, stats, last_sd_id, best_raw_results or {}


def _resolve_fixed_target_mother(
    metadata: dict | object,
    target_table: str,
) -> str | None:
    """Find the subject (mother) table the target table cascades from.

    Walks context foreign keys upward from ``target_table`` until reaching a
    subject table. Falls back to the only subject table when the chain cannot be
    followed (e.g. denormalized metadata).
    """
    _, table_fks = _build_relationship_maps(
        metadata if isinstance(metadata, dict) else {"tables": []}
    )
    subject_names = {
        t["name"] for t in metadata.get("tables", []) if _is_subject_table(t)
    }
    current = target_table
    seen = {current}
    while current not in subject_names:
        parent = next(
            (
                fk.get("referenced_table")
                for fk in table_fks.get(current, [])
                if fk.get("is_context") and fk.get("referenced_table")
            ),
            None,
        )
        if parent is None or parent in seen:
            break
        seen.add(parent)
        current = parent
    if current in subject_names:
        return current
    if len(subject_names) == 1:
        return next(iter(subject_names))
    return None


def _update_attempt_progress(session: SimulationSession | None, attempt: int, max_attempts: int):
    if not session:
        return
    try:
        from backend.src.infrastructure.progress import (
            SIMULATION_PHASES,
            SimulationPhase,
            _write_progress,
        )

        index = SIMULATION_PHASES.index(SimulationPhase.GENERATING)
        label = f"Generando datos sintéticos (Intento {attempt}/{max_attempts})"
        _write_progress(session.card_path, index, len(SIMULATION_PHASES), label)
    except Exception as e:
        logger.warning("Could not update attempt progress in session card: %s", e)


def _generate_with_fixed_target_sampling(
    engine: SynthesisEngine,
    generator: object,
    metadata: dict | object,
    rule_manager: LogicalRuleManager,
    target_table: str,
    target_rows: int,
    mother_table: str,
    cancel_event: threading.Event | None = None,
    progress_copy_dest: str | None = None,
    conditional: dict | None = None,
    training_table_sizes: dict[str, int] | None = None,
    session: SimulationSession | None = None,
    sampling_overrides: dict[str, Any] | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, Any], str, dict[str, pd.DataFrame]]:
    """Oversimulate the mother table until ``target_table`` holds ``target_rows``
    compliant rows, then trim the overflow.

    The engine cannot size a context child directly — children always cascade
    from their subject — so the only lever is how many mother rows to draw. Each
    attempt draws a single batch (attempts are never concatenated: duplicate
    subject PKs across batches would corrupt FK cascades), measures the actual
    compliant-child yield per mother row, and re-estimates the next draw from it.
    The mother and every non-target table end up with whatever size the target
    requires. Runs with or without rejection rules; without rules every row
    counts as compliant and the loop only corrects the cascade-ratio estimate.
    """
    training_table_sizes = training_table_sizes or {}
    config = _resolve_rejection_sampling_config(rule_manager, sampling_overrides)
    max_attempts = config["max_attempts"]
    overgenerate_factor = config["overgenerate_factor"]

    rejection_rules = [
        rule
        for rule in rule_manager.get_rejection_rules()
        if rule.table_target in {t.get("name") for t in metadata.get("tables", [])}
    ]
    table_names = [table.get("name") for table in metadata.get("tables", [])]

    # First-draw estimate from the real child:mother ratio, always pre-inflated
    # by the overgeneration factor: the cascade almost always yields fewer child
    # rows than the training ratio predicts (and rejection rules, when present,
    # cut it further), so undershooting the first draw means paying an engine
    # restart — far more expensive than the extra rows. Yield is re-measured
    # after each attempt.
    mother_train = training_table_sizes.get(mother_table) or 0
    target_train = training_table_sizes.get(target_table) or 0
    ratio = (target_train / mother_train) if mother_train and target_train else 1.0
    draw = max(1, round(target_rows / ratio * overgenerate_factor))

    logger.info(
        "Starting fixed-target sampling: %d compliant rows of '%s' (mother '%s', "
        "initial draw %d, max_attempts=%d)",
        target_rows,
        target_table,
        mother_table,
        draw,
        max_attempts,
    )

    last_sd_id: str = ""
    stats: dict[str, Any] = {
        "enabled": True,
        "max_attempts": max_attempts,
        "overgenerate_factor": overgenerate_factor,
        "attempts": 0,
        "rules": [type(rule).__name__ for rule in rejection_rules],
        "tables": {},
        "partial_results": False,
        "subject_targets": {},
        "child_targets": {target_table: target_rows},
        "all_targets": _resolve_display_targets(
            [t.get("name") for t in metadata.get("tables", [])],
            training_table_sizes,
            target_table,
            target_rows,
        ),
        "fixed_tables": [target_table],
        "selection": "fixed_target",
        "target_table": target_table,
        "target_rows": target_rows,
    }

    best_results: dict[str, pd.DataFrame] | None = None
    best_raw_results: dict[str, pd.DataFrame] | None = None
    best_score = -1
    best_table_stats: dict[str, dict[str, int]] = {}
    best_attempt = 1
    best_post_warnings: list[dict[str, Any]] = []
    attempt_history = []

    for attempt in range(1, max_attempts + 1):
        _update_attempt_progress(session, attempt, max_attempts)
        with profiler.phase(f"Intento {attempt}"):
            logger.debug(
                f"Fixed-target attempt {attempt}/{max_attempts}; mother draw={draw}"
            )
            simulation_config = create_simulation_config(
                metadata, sample_size=None, table_sample_sizes={mother_table: draw}
            )
            runtime_config = attach_sample_seeds(simulation_config, conditional, metadata)
            raw_synthetic_results, last_sd_id = engine.simulate(
                generator,
                runtime_config,
                cancel_event=cancel_event,
                progress_copy_dest=progress_copy_dest,
            )
            synthetic_results = rule_manager.apply_all_post(raw_synthetic_results)
            post_warnings = list(getattr(rule_manager, "post_warnings", []))
            _restore_original_date_formats(synthetic_results, rule_manager)

            generated_counts = {t: int(len(df)) for t, df in synthetic_results.items()}

            if rejection_rules:
                rule_rejection_indices = rule_manager.collect_rejection_failures(
                    synthetic_results, rejection_rules
                )
                compliant_results, rule_rejected_counts = _cascade_delete_tables(
                    synthetic_results, metadata, rule_rejection_indices
                )
            else:
                compliant_results, rule_rejected_counts = synthetic_results, {}
            compliant_counts = {t: int(len(df)) for t, df in compliant_results.items()}

            compliant_target = compliant_counts.get(target_table, 0)
            # Enough compliant target rows: trim the overflow (cascading to the
            # target's own descendants) so the count is exact. Mother and other
            # tables keep whatever the draw produced — they were never fixed.
            if compliant_target > target_rows:
                target_df = compliant_results[target_table]
                overflow = {target_table: set(target_df.index[target_rows:])}
                selected, _ = _cascade_delete_tables(compliant_results, metadata, overflow)
            else:
                selected = compliant_results

            attempt_table_stats: dict[str, dict[str, int]] = {}
            for table_name in table_names:
                accepted = int(len(selected.get(table_name, pd.DataFrame())))
                attempt_table_stats[table_name] = {
                    "generated": generated_counts.get(table_name, 0),
                    "accepted": accepted,
                    "rejected": int(rule_rejected_counts.get(table_name, 0)),
                    "trimmed": max(0, compliant_counts.get(table_name, 0) - accepted),
                }

            score = min(compliant_target, target_rows)
            attempt_history.append(
                {
                    "attempt": attempt,
                    "multiplier": float(overgenerate_factor),
                    "subject_draw": {mother_table: draw},
                    "tables": attempt_table_stats,
                    "score": score,
                    "post_reconstruction_warnings": post_warnings,
                }
            )

            stats["attempts"] = attempt
            if score > best_score:
                best_score = score
                best_results = selected
                best_table_stats = attempt_table_stats
                best_attempt = attempt
                best_post_warnings = post_warnings
                best_raw_results = {t: df.copy() for t, df in raw_synthetic_results.items()}

            if compliant_target >= target_rows:
                logger.info("Fixed-target sampling: target met on attempt %d.", attempt)
                break

            # Re-estimate the draw from the measured compliant yield per mother
            # row, with a 20% safety margin. A zero yield gives no signal, so
            # fall back to multiplying the draw. Growth is capped at 5× per
            # attempt so one unlucky batch cannot explode the next request.
            measured_yield = compliant_target / draw if draw else 0.0
            if measured_yield > 0:
                next_draw = round(target_rows / measured_yield * 1.2)
            else:
                next_draw = round(draw * max(overgenerate_factor, 2.0))
            draw = max(draw + 1, min(next_draw, draw * 5))

    final_results: dict[str, pd.DataFrame] = best_results or {}
    for table_name in table_names:
        final_results.setdefault(table_name, pd.DataFrame())
    stats["tables"] = best_table_stats
    stats["post_reconstruction_warnings"] = best_post_warnings
    for history_entry in attempt_history:
        history_entry["is_best"] = history_entry["attempt"] == best_attempt
    stats["attempt_history"] = attempt_history
    stats["partial_results"] = (
        best_table_stats.get(target_table, {}).get("accepted", 0) < target_rows
    )
    return final_results, stats, last_sd_id, best_raw_results or {}


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
        formatter = MetadataFormatter(engine_name=resolve_active_engine())
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
    rejection_applied: bool = True,
) -> pd.DataFrame | None:
    """Runs all sanity checks (logical rules + general structural checks).

    Args:
        synthetic_results (dict): Generated synthetic data dataframes.
        metadata (dict | object): Model metadata definitions.
        rule_manager (object): The RuleManager instance loaded from training.
        rejection_applied (bool): Whether rejection sampling actually ran this
            simulation. When False, rejection-sampling rules were not enforced,
            so they are reported as SKIPPED rather than validated (which would
            show a misleading PASS/FAIL on data the rule never shaped).

    Returns:
        pd.DataFrame | None: Target combined DataFrame of validation reports,
                             or None if there are no checks.
    """
    sanity_checks: list[pd.DataFrame] = []

    rules_report = rule_manager.run_rules_sanity_checks(
        synthetic_results, unenforced_rejection=not rejection_applied
    )
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
    fixed_target: dict | None = None,
    sampling_overrides: dict | None = None,
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
        fixed_target (dict | None, optional): ``{"table": str, "rows": int}``.
            Enforce an exact compliant row count on one table instead of on the
            mother: the mother is oversimulated adaptively until the target is
            met and every other table floats. Overrides ``sample_size`` and
            ``table_sample_sizes``. A target that is itself a subject table is
            equivalent to a per-table size and is handled by the regular path.
        sampling_overrides (dict | None, optional): Per-request ``max_attempts``
            / ``overgenerate_factor`` for rejection and fixed-target sampling;
            takes precedence over the rules.yaml configuration.
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
            engine = create_engine(
                engine_name=resolve_active_engine(),
                config_path=mostly_config_path,
                config_overrides=mostly_ai_overrides,
                run_dir=sim_tracker.output_directory,
                local_dir=MOSTLYAI_DIR,
            )

            # Each engine starts a fresh SDK server on a new port; the generator
            # from training is gone from that server's state after export_to_file.
            # Re-import from the zip so this server's instance knows about it.
            generator, _ = engine.load_generator_by_id(model_id)

            # Fixed-target mode: enforce a row count on one table and let the
            # rest float. A subject target is just a per-table size (the engine
            # honors it directly), so it folds into the regular path; only a
            # context child needs the adaptive oversimulation loop.
            target_table: str | None = None
            target_rows: int | None = None
            fixed_target_mother: str | None = None
            if fixed_target:
                table_meta_by_name = {t["name"]: t for t in metadata.get("tables", [])}
                requested_table = str(fixed_target.get("table") or "")
                requested_rows = int(fixed_target.get("rows") or 0)
                if requested_table not in table_meta_by_name or requested_rows <= 0:
                    raise ValueError(
                        f"Invalid fixed_target: table '{requested_table}' not in the "
                        f"model schema or non-positive row count {requested_rows}."
                    )
                sample_size = None
                if _is_subject_table(table_meta_by_name[requested_table]):
                    table_sample_sizes = {requested_table: requested_rows}
                else:
                    table_sample_sizes = None
                    target_table, target_rows = requested_table, requested_rows
                    fixed_target_mother = _resolve_fixed_target_mother(metadata, target_table)
                    if fixed_target_mother is None:
                        raise ValueError(
                            f"Could not resolve the mother (subject) table that "
                            f"'{target_table}' cascades from."
                        )
            use_fixed_target = target_table is not None

            simulation_config = create_simulation_config(metadata, sample_size, table_sample_sizes)
            sim_tracker.save_sim_config(simulation_config)
            mother_table, mother_table_size = _resolve_mother_table(
                metadata,
                sample_size,
                table_sample_sizes,
                _load_training_table_sizes(model_id),
            )
            sim_tracker.save_sim_card(
                sample_size=sample_size,
                mother_table=fixed_target_mother or mother_table,
                # In fixed-target mode the mother floats: its final size is an
                # outcome of the run, not a request, so no size is persisted.
                mother_table_size=None if use_fixed_target else mother_table_size,
                target_table=target_table,
                target_table_rows=target_rows,
            )

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
            # Rejection sampling is driven by *subject* table targets: the engine
            # only honors sizes on subjects (children cascade), so we overgenerate
            # subjects and reject non-compliant rows. The target can come from the
            # global sample_size OR from table_sample_sizes — checking only the
            # global one silently disabled rejection whenever the size was set
            # per-table, dropping into a destructive single pass.
            subject_targets = _resolve_subject_targets(metadata, sample_size, table_sample_sizes)
            use_rejection = not use_fixed_target and bool(rejection_rules) and bool(subject_targets)
            rejection_applied = use_rejection or (use_fixed_target and bool(rejection_rules))
            best_raw_results: dict[str, pd.DataFrame] = {}
            with profiler.phase(ProfilerPhase.MOSTLYAI_SIMULATE):
                job_progress_dest = os.path.join(sim_tracker.output_directory, "job_progress.json")
                if use_fixed_target:
                    (
                        synthetic_results,
                        rejection_stats,
                        _,
                        best_raw_results,
                    ) = _generate_with_fixed_target_sampling(
                        engine=engine,
                        generator=generator,
                        metadata=metadata,
                        rule_manager=rule_manager,
                        target_table=target_table,
                        target_rows=target_rows,
                        mother_table=fixed_target_mother,
                        cancel_event=cancel_event,
                        progress_copy_dest=job_progress_dest,
                        conditional=conditional,
                        training_table_sizes=_load_training_table_sizes(model_id),
                        session=session,
                        sampling_overrides=sampling_overrides,
                    )
                    rejection_stats["sample_size"] = None
                    sim_tracker.save_rejection_sampling_report(rejection_stats)
                elif use_rejection:
                    (
                        synthetic_results,
                        rejection_stats,
                        _,
                        best_raw_results,
                    ) = _generate_with_rejection_sampling(
                        engine=engine,
                        generator=generator,
                        metadata=metadata,
                        rule_manager=rule_manager,
                        subject_targets=subject_targets,
                        cancel_event=cancel_event,
                        progress_copy_dest=job_progress_dest,
                        conditional=conditional,
                        training_table_sizes=_load_training_table_sizes(model_id),
                        session=session,
                        sampling_overrides=sampling_overrides,
                    )
                    rejection_stats["sample_size"] = sample_size
                    sim_tracker.save_rejection_sampling_report(rejection_stats)
                else:
                    # No subject target ⇒ rejection sampling cannot overgenerate.
                    # The single-pass fallback must be NON-DESTRUCTIVE: deleting
                    # violators here (no retries, no overgeneration) silently
                    # decimates tables. Instead, leave the data untouched and let
                    # the rules report SKIPPED so the user sees they were not
                    # applied.
                    if rejection_rules:
                        logger.warning(
                            "Rejection sampling requested but no subject sample size was set. "
                            "Rejection rules %s will NOT be enforced this run; set a sample size "
                            "to enable rejection sampling. Generating a single uncontrolled pass.",
                            [type(rule).__name__ for rule in rejection_rules],
                        )
                    raw_synthetic_results, _ = engine.simulate(
                        generator,
                        runtime_config,
                        cancel_event=cancel_event,
                        progress_copy_dest=job_progress_dest,
                    )
                    best_raw_results = {t: df.copy() for t, df in raw_synthetic_results.items()}
                    if session:
                        advance_progress(
                            session.card_path, SIMULATION_PHASES, SimulationPhase.APPLYING_RULES
                        )
                    with profiler.phase(ProfilerPhase.APPLY_RULES):
                        synthetic_results = rule_manager.apply_all_post(raw_synthetic_results)
                        _restore_original_date_formats(synthetic_results, rule_manager)
            with profiler.phase(ProfilerPhase.SAVE_RESULTS):
                sim_tracker.save_synthetic_results(synthetic_results)
                sim_tracker.save_auxiliary_columns(best_raw_results, synthetic_results, metadata)
            if session:
                advance_progress(session.card_path, SIMULATION_PHASES, SimulationPhase.VALIDATION)
            with profiler.phase(ProfilerPhase.SANITY_CHECKS):
                # check if this is being run twice
                combined_report = run_all_sanity_checks(
                    synthetic_results, metadata, rule_manager, rejection_applied=rejection_applied
                )
            if combined_report is not None:
                sim_tracker.save_sanity_report(combined_report)

            with profiler.phase(ProfilerPhase.SAVE_METADATA):
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
    fixed_target: dict | None = None,
    sampling_overrides: dict | None = None,
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
        fixed_target: Exact-row-count spec for one table (see
            ``run_simulation_flow``).

    Returns:
        The ``simulation_id`` if successful, ``None`` on failure.
    """
    try:
        from backend.src.sessions.artifacts import load_generator_artifacts

        if session:
            advance_progress(
                session.card_path, SIMULATION_PHASES, SimulationPhase.LOADING_GENERATOR
            )
        with profiler.phase(ProfilerPhase.LOAD_GENERATOR_ARTIFACTS):
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
            fixed_target=fixed_target,
            sampling_overrides=sampling_overrides,
        )
    except Exception as error:
        logger.error("Simulation-from-model flow failed: %s", error, exc_info=True)
        if session:
            mark_card_failed(session.card_path, error)
        return None
