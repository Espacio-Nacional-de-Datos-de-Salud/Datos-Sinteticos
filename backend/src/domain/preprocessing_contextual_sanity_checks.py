"""Module with helper functions for contextual sanity checks."""

import pandas as pd
from backend.src.domain.preprocessing.logical_rules import (
    ForeignKeysConsistencyRule,
    LogicalRuleManager,
)
from backend.src.domain.preprocessing.utils import validate_referential_integrity


def _build_table_name_to_pks_mapping(metadata: dict) -> dict[str, str]:
    """Extracts the per-table primary key mapping from metadata.

    Args:
        metadata (dict): Tabular metadata with structure ``{"tables": [...]}``.

    Returns:
        dict[str, str]: Mapping ``{table_name: pk_column}`` for tables
            that declare ``primary_key``.
    """
    table_pks = {}
    for table in metadata.get("tables", []):
        if "primary_key" in table:
            table_pks[table["name"]] = table["primary_key"]
    return table_pks


def _build_table_definition(metadata: dict) -> dict[str, dict]:
    """Indexes each full table definition by name.

    Args:
        metadata (dict): Tabular metadata with structure ``{"tables": [...]}``.

    Returns:
        dict[str, dict]: Dictionary ``{table_name: table_definition}``.
    """
    return {table["name"]: table for table in metadata.get("tables", [])}


def _deduplicate_definitions(definitions: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    """Removes duplicate definitions while preserving appearance order.

    Args:
        definitions (list[dict]): List of candidate definitions.
        key_fields (tuple[str, ...]): Fields that form the uniqueness key.

    Returns:
        list[dict]: Deduplicated list, keeping the first occurrence of
            each combination of ``key_fields``.
    """
    seen: set[tuple] = set()
    deduped: list[dict] = []

    for definition in definitions:
        key = tuple(definition.get(field) for field in key_fields)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(definition)

    return deduped


def _collect_all_fks_to_check(
    metadata: dict, rule_manager: LogicalRuleManager | None = None
) -> list[dict]:
    """Builds the inventory of general referential-integrity checks.

    Starts from FKs declared in ``metadata`` and, if ``rule_manager`` exists,
    also adds FKs reconstructed by ``ForeignKeysConsistencyRule``.
    This keeps the number of general checks stable between old models
    (with explicit FK in metadata) and new models (with derived FK).

    Args:
        metadata (dict): Tabular metadata.
        rule_manager (LogicalRuleManager | None): Loaded rule manager used to
            infer derived FKs. Defaults to None.

    Returns:
        list[dict]: Check definitions with keys ``child_table``,
            ``child_fk_column`` and ``parent_table``.
    """
    checks: list[dict] = []

    for table in metadata.get("tables", []):
        for fk in table.get("foreign_keys", []):
            checks.append(
                {
                    "child_table": table["name"],
                    "child_fk_column": fk["column"],
                    "parent_table": fk["referenced_table"],
                }
            )

    if rule_manager is not None:
        for rule in rule_manager.rules:
            if not isinstance(rule, ForeignKeysConsistencyRule):
                continue
            checks.append(
                {
                    "child_table": rule.table_target,
                    "child_fk_column": rule.target_col,
                    "parent_table": rule.referenced_table,
                }
            )

    return _deduplicate_definitions(checks, ("child_table", "child_fk_column", "parent_table"))


def _select_parent_consistency_fk(parent_fks: list[dict], child_fk: dict) -> dict | None:
    """Selects the parent FK that allows validating contextual consistency.

    First tries an exact match by referenced table and column name.
    If not found, accepts a single match by referenced table.
    If there is ambiguity, returns ``None`` to avoid inferring an uncertain check.

    Args:
        parent_fks (list[dict]): FKs declared in the parent table.
        child_fk (dict): Candidate FK declared in the child table.

    Returns:
        dict | None: Parent FK that acts as source of truth for the
            comparison, or ``None`` if it cannot be inferred uniquely.
    """
    exact_matches = [
        fk
        for fk in parent_fks
        if fk["referenced_table"] == child_fk["referenced_table"]
        and fk["column"] == child_fk["column"]
    ]
    if len(exact_matches) == 1:
        return exact_matches[0]

    table_matches = [
        fk for fk in parent_fks if fk["referenced_table"] == child_fk["referenced_table"]
    ]
    if len(table_matches) == 1:
        return table_matches[0]

    return None


def _collect_all_contextual_relationships_to_check(
    metadata: dict, rule_manager: LogicalRuleManager | None = None
) -> list[dict]:
    """Builds the inventory of general contextual-consistency checks.

    Detects child -> parent -> grandparent patterns and builds checks to
    validate that an FK in the child table matches the FK derivable from its
    context parent table. It also incorporates derived rules present in
    ``rule_manager`` to keep a stable inventory across old and new schemas.

    Args:
        metadata (dict): Tabular metadata.
        rule_manager (LogicalRuleManager | None): Loaded rule manager used to
            infer checks on reconstructed FKs. Defaults to None.

    Returns:
        list[dict]: Check definitions with keys ``child_table``,
            ``parent_table``, ``context_fk_column``, ``child_fk_column`` and
            ``parent_source_column``.
    """
    table_defs = _build_table_definition(metadata)
    checks: list[dict] = []

    for child_table in metadata.get("tables", []):
        child_fks = child_table.get("foreign_keys", [])
        context_fk = next((fk for fk in child_fks if fk.get("is_context")), None)
        if context_fk is None:
            continue

        parent_name = context_fk["referenced_table"]
        parent_table = table_defs.get(parent_name)
        if parent_table is None:
            continue

        for child_fk in child_fks:
            if child_fk is context_fk:
                continue

            source_fk = _select_parent_consistency_fk(
                parent_table.get("foreign_keys", []), child_fk
            )
            if source_fk is None:
                continue

            checks.append(
                {
                    "child_table": child_table["name"],
                    "parent_table": parent_name,
                    "context_fk_column": context_fk["column"],
                    "child_fk_column": child_fk["column"],
                    "parent_source_column": source_fk["column"],
                }
            )

    if rule_manager is not None:
        for rule in rule_manager.rules:
            if not isinstance(rule, ForeignKeysConsistencyRule):
                continue
            checks.append(
                {
                    "child_table": rule.table_target,
                    "parent_table": rule.table_origin,
                    "context_fk_column": next(
                        (
                            fk["column"]
                            for fk in table_defs.get(rule.table_target, {}).get("foreign_keys", [])
                            if fk.get("is_context") and fk["referenced_table"] == rule.table_origin
                        ),
                        None,
                    ),
                    "child_fk_column": rule.target_col,
                    "parent_source_column": rule.source_col,
                }
            )

    contextual_checks = [check for check in checks if check.get("context_fk_column")]
    return _deduplicate_definitions(
        contextual_checks,
        (
            "child_table",
            "parent_table",
            "context_fk_column",
            "child_fk_column",
            "parent_source_column",
        ),
    )


def _build_general_sanity_check_row(
    check_name: str,
    rule_label: str,
    table_name: str,
    status: str,
    failed_rows: int,
    total_rows: int,
    details: str,
) -> dict:
    """Builds a standardized row for the general sanity report.

    Args:
        check_name (str): Technical check name.
        rule_label (str): Human-readable label of the validated relationship or rule.
        table_name (str): Table where the check applies.
        status (str): Check status: ``PASS``, ``FAIL``, or ``SKIPPED``.
        failed_rows (int): Number of failed rows.
        total_rows (int): Total number of evaluated rows.
        details (str): Summarized result description.

    Returns:
        dict: Row with the unified sanity-check report schema.
    """
    return {
        "type": "general",
        "check": check_name,
        "rule": rule_label,
        "table": table_name,
        "status": status,
        "failed_rows": failed_rows,
        "total_rows": total_rows,
        "details": details,
    }


def _get_referential_skip_reason(
    child_name: str,
    child_fk_col: str,
    parent_name: str,
    synthetic_data: dict[str, pd.DataFrame],
    table_pks: dict[str, str],
) -> str | None:
    """Returns the skip reason if any precondition fails, or None if everything is OK."""
    if child_name not in synthetic_data:
        return f"Table '{child_name}' not found in data"
    if parent_name not in synthetic_data:
        return f"Parent table '{parent_name}' not found in data"
    parent_pk_col = table_pks.get(parent_name)
    if not parent_pk_col:
        return f"PK for '{parent_name}' not found in metadata"
    if child_fk_col not in synthetic_data[child_name].columns:
        return f"Child column '{child_fk_col}' not found in data"
    if parent_pk_col not in synthetic_data[parent_name].columns:
        return f"Parent PK column '{parent_pk_col}' not found in data"
    return None


def _evaluate_single_referential_integrity_check(
    fk_check: dict,
    synthetic_data: dict[str, pd.DataFrame],
    table_pks: dict[str, str],
) -> dict:
    """Evaluates a single referential-integrity check and returns its report row.

    Validates preconditions (existence of tables, columns, and PKs) and, if all
    is available, calculates how many child rows point to a missing parent.

    Args:
        fk_check (dict): Check definition with keys ``child_table``,
            ``child_fk_column`` and ``parent_table``.
        synthetic_data (dict[str, pd.DataFrame]): Generated synthetic tables.
        table_pks (dict[str, str]): Mapping ``{table_name: pk_column}``.

    Returns:
        dict: Report row with unified sanity-check schema.
    """
    child_name = fk_check["child_table"]
    child_fk_col = fk_check["child_fk_column"]
    parent_name = fk_check["parent_table"]
    check_label = f"FK {child_name}.{child_fk_col} -> {parent_name}"

    skip_reason = _get_referential_skip_reason(
        child_name, child_fk_col, parent_name, synthetic_data, table_pks
    )
    if skip_reason is not None:
        return _build_general_sanity_check_row(
            "referential_integrity", check_label, child_name, "SKIPPED", 0, 0, skip_reason
        )

    parent_pk_col = table_pks[parent_name]
    child_df = synthetic_data[child_name]
    parent_df = synthetic_data[parent_name]

    orphan_count, total_children = validate_referential_integrity(
        parent_df[parent_pk_col], child_df[child_fk_col]
    )

    if orphan_count == 0:
        status = "PASS"
        details = f"100% integrity ({total_children} rows)"
    else:
        success_rate = round(((total_children - orphan_count) / total_children) * 100, 2)
        parent_vals = set(parent_df[parent_pk_col].dropna().unique())
        child_non_null = child_df[child_fk_col].dropna()
        orphan_examples = (
            child_non_null[~child_non_null.isin(parent_vals)].head(3).astype(str).tolist()
        )
        details = (
            f"{orphan_count} orphans, {success_rate}% integrity"
            f" | examples: {', '.join(orphan_examples)}"
        )
        status = "FAIL"

    return _build_general_sanity_check_row(
        "referential_integrity",
        check_label,
        child_name,
        status,
        orphan_count,
        total_children,
        details,
    )


def _get_contextual_skip_reason(
    child_name: str,
    parent_name: str,
    context_fk_col: str,
    child_fk_col: str,
    parent_source_col: str,
    synthetic_data: dict[str, pd.DataFrame],
    table_pks: dict[str, str],
) -> str | None:
    """Returns the skip reason if any precondition fails, or None if everything is OK."""
    if child_name not in synthetic_data:
        return f"Table '{child_name}' not found in data"
    if parent_name not in synthetic_data:
        return f"Parent table '{parent_name}' not found in data"
    parent_pk_col = table_pks.get(parent_name)
    if not parent_pk_col:
        return f"PK for '{parent_name}' not found in metadata"

    child_df = synthetic_data[child_name]
    required_child_cols = {context_fk_col, child_fk_col}
    if not required_child_cols.issubset(child_df.columns):
        missing = sorted(required_child_cols.difference(child_df.columns))
        return f"Missing child columns: {', '.join(missing)}"

    parent_df = synthetic_data[parent_name]
    required_parent_cols = {parent_pk_col, parent_source_col}
    if not required_parent_cols.issubset(parent_df.columns):
        missing = sorted(required_parent_cols.difference(parent_df.columns))
        return f"Missing parent columns: {', '.join(missing)}"

    return None


def _evaluate_single_contextual_fk_check(
    check: dict,
    synthetic_data: dict[str, pd.DataFrame],
    table_pks: dict[str, str],
) -> dict:
    """Evaluates one contextual FK-consistency check and returns its report row.

    Validates preconditions, then merges child and parent through the context key
    and compares the child FK with the parent source column.

    Args:
        check (dict): Check definition with keys ``child_table``,
            ``parent_table``, ``context_fk_column``, ``child_fk_column``
            and ``parent_source_column``.
        synthetic_data (dict[str, pd.DataFrame]): Generated synthetic tables.
        table_pks (dict[str, str]): Mapping ``{table_name: pk_column}``.

    Returns:
        dict: Report row with unified sanity-check schema.
    """
    child_name = check["child_table"]
    parent_name = check["parent_table"]
    context_fk_col = check["context_fk_column"]
    child_fk_col = check["child_fk_column"]
    parent_source_col = check["parent_source_column"]
    check_label = (
        f"Context FK {child_name}.{child_fk_col} via {child_name}.{context_fk_col}"
        f" -> {parent_name}.{parent_source_col}"
    )

    skip_reason = _get_contextual_skip_reason(
        child_name,
        parent_name,
        context_fk_col,
        child_fk_col,
        parent_source_col,
        synthetic_data,
        table_pks,
    )
    if skip_reason is not None:
        return _build_general_sanity_check_row(
            "contextual_fk_consistency", check_label, child_name, "SKIPPED", 0, 0, skip_reason
        )

    parent_pk_col = table_pks[parent_name]
    child_df = synthetic_data[child_name]
    parent_df = synthetic_data[parent_name]

    merged = child_df[[context_fk_col, child_fk_col]].merge(
        parent_df[[parent_pk_col, parent_source_col]],
        left_on=context_fk_col,
        right_on=parent_pk_col,
        how="left",
        suffixes=("_child", "_parent"),
    )
    matched_rows = merged[parent_pk_col].notna()
    total_rows = int(matched_rows.sum())

    if total_rows == 0:
        return _build_general_sanity_check_row(
            "contextual_fk_consistency",
            check_label,
            child_name,
            "SKIPPED",
            0,
            0,
            "No matched parent rows to compare",
        )

    child_compare_col = child_fk_col
    parent_compare_col = parent_source_col
    if child_fk_col == parent_source_col:
        child_compare_col = f"{child_fk_col}_child"
        parent_compare_col = f"{parent_source_col}_parent"

    comparison = merged.loc[matched_rows, [child_compare_col, parent_compare_col]]
    matches = (comparison[child_compare_col] == comparison[parent_compare_col]) | (
        comparison[child_compare_col].isna() & comparison[parent_compare_col].isna()
    )
    mismatch_mask = pd.Series(False, index=merged.index)
    mismatch_mask.loc[comparison.index] = ~matches
    mismatch_count = int(mismatch_mask.sum())

    if mismatch_count == 0:
        status = "PASS"
        details = f"100% contextual FK consistency ({total_rows} rows)"
    else:
        success_rate = round(((total_rows - mismatch_count) / total_rows) * 100, 2)
        failing_examples = merged.loc[mismatch_mask].head(3)
        example_chunks = []
        for _, failing_row in failing_examples.iterrows():
            example_chunks.append(
                f"{context_fk_col}={failing_row[context_fk_col]} | "
                f"child {child_fk_col}={failing_row[child_compare_col]} | "
                f"parent {parent_source_col}={failing_row[parent_compare_col]}"
            )
        status = "FAIL"
        details = (
            f"{mismatch_count} mismatches, {success_rate}% consistency"
            f" | examples: {'; '.join(example_chunks)}"
        )

    return _build_general_sanity_check_row(
        "contextual_fk_consistency",
        check_label,
        child_name,
        status,
        mismatch_count,
        total_rows,
        details,
    )
