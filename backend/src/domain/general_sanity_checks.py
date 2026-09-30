"""General sanity checks for synthetic data.

Runs structural validations that apply regardless of user-defined rules:
referential integrity between primary keys and foreign keys and contextual
consistency of derivable FK relationships. Results are aggregated into a
single DataFrame consumed by the tracking layer.
"""

import pandas as pd

from backend.src.domain.preprocessing.logical_rules import (
    LogicalRuleManager,
)
from backend.src.domain.preprocessing_contextual_sanity_checks import (
    _build_general_sanity_check_row,
    _build_table_name_to_pks_mapping,
    _collect_all_contextual_relationships_to_check,
    _collect_all_fks_to_check,
    _evaluate_single_contextual_fk_check,
    _evaluate_single_referential_integrity_check,
)
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)

# A synthetic column at or above this null share is treated as broken. Default
# 1.0 flags only fully-empty columns — the unambiguous "this column failed to
# generate" signal (e.g. a populated source datetime that came back blank).
# Kept conservative so legitimately high-null columns (already surfaced at
# inspection time) don't spam the report.
BROKEN_COLUMN_NULL_THRESHOLD = 1.0


def run_general_sanity_checks(
    synthetic_data: dict[str, pd.DataFrame] | pd.DataFrame,
    metadata: dict,
    rule_manager: LogicalRuleManager | None = None,
) -> pd.DataFrame:
    """Runs all general sanity checks and unifies their results.

    Orchestrates structural checks independent of specific rules:
    classic referential integrity and contextual consistency of derivable FKs.

    Args:
        synthetic_data (dict[str, pd.DataFrame] | pd.DataFrame): Dictionary
            of synthetic tables or a single DataFrame.
        metadata (dict): Tabular metadata.
        rule_manager (LogicalRuleManager | None): Loaded rule manager to
            incorporate derived FKs into the checks inventory. Defaults to None.

    Returns:
        pd.DataFrame: Concatenation of all general sanity checks with
            esquema [type, check, rule, table, status, failed_rows, total_rows,
            details]. Empty if none applies.
    """

    reports: list[pd.DataFrame] = []

    referential_report = sanity_check_referential_integrity(
        synthetic_data=synthetic_data,
        metadata=metadata,
        rule_manager=rule_manager,
    )
    if not referential_report.empty:
        reports.append(referential_report)

    contextual_report = sanity_check_contextual_fk_consistency(
        synthetic_data=synthetic_data,
        metadata=metadata,
        rule_manager=rule_manager,
    )
    if not contextual_report.empty:
        reports.append(contextual_report)

    column_health_report = sanity_check_column_health(synthetic_data=synthetic_data)
    if not column_health_report.empty:
        reports.append(column_health_report)

    if not reports:
        return pd.DataFrame()

    return pd.concat(reports, ignore_index=True)


def _null_fraction(series: pd.Series) -> float:
    """Share of a column that is missing: true nulls plus blank/whitespace strings."""
    total = len(series)
    if total == 0:
        return 0.0
    is_null = series.isna()
    is_blank_str = series.astype(str).str.strip().eq("") & ~is_null
    return float((is_null | is_blank_str).mean())


def sanity_check_column_health(
    synthetic_data: dict[str, pd.DataFrame] | pd.DataFrame,
    null_threshold: float = BROKEN_COLUMN_NULL_THRESHOLD,
) -> pd.DataFrame:
    """Flags synthetic columns that came back entirely (or near-entirely) empty.

    A column that is fully null in the output is almost always a broken
    simulation — e.g. a populated source datetime that failed to generate or
    reconstruct. These slip past every other check: a null silently "satisfies"
    an inequality rule and is irrelevant to referential integrity, so without
    this structural pass a 100%-empty column can still report full compliance.
    One report row is emitted per offending column.

    Args:
        synthetic_data (dict[str, pd.DataFrame] | pd.DataFrame): Synthetic
            tables or a single DataFrame.
        null_threshold (float): Null share (0–1) at or above which a column is
            flagged. Defaults to ``BROKEN_COLUMN_NULL_THRESHOLD`` (fully empty).

    Returns:
        pd.DataFrame: Rows with the unified sanity-check schema (one per broken
            column). Empty if every column has data.
    """
    if isinstance(synthetic_data, pd.DataFrame):
        tables = {"data": synthetic_data}
    else:
        tables = synthetic_data

    logger.info("=" * 80)
    logger.info("%s", f"{'COLUMN HEALTH CHECK':^80}")
    logger.info("=" * 80)

    rows: list[dict] = []
    for table_name, df in tables.items():
        if df is None:
            continue
        # A table that came back with columns but zero rows is itself a broken
        # result (e.g. rejection sampling discarded every row). Flag it instead
        # of letting an empty table pass silently.
        if len(df) == 0:
            if len(df.columns) == 0:
                continue
            logger.error("BROKEN TABLE | '%s' has 0 rows", table_name)
            rows.append(
                _build_general_sanity_check_row(
                    check_name="column_health",
                    rule_label=f"Table '{table_name}' is empty",
                    table_name=table_name,
                    status="FAIL",
                    failed_rows=0,
                    total_rows=0,
                    details=f"{table_name}: 0 rows generated",
                )
            )
            continue
        total = len(df)
        for col in df.columns:
            null_fraction = _null_fraction(df[col])
            if null_fraction < null_threshold:
                continue
            null_count = int(round(null_fraction * total))
            pct = round(null_fraction * 100, 2)
            logger.error(
                "BROKEN COLUMN | '%s'.'%s' is %.2f%% null (%d/%d rows empty)",
                table_name,
                col,
                pct,
                null_count,
                total,
            )
            rows.append(
                _build_general_sanity_check_row(
                    check_name="column_health",
                    rule_label=f"Column '{col}' is empty",
                    table_name=table_name,
                    status="FAIL",
                    failed_rows=null_count,
                    total_rows=total,
                    details=f"{col}: {pct}% null ({null_count}/{total} rows empty)",
                )
            )

    if not rows:
        logger.info("No empty columns detected.")
        return pd.DataFrame()

    return pd.DataFrame(rows)


def sanity_check_referential_integrity(
    synthetic_data: dict[str, pd.DataFrame] | pd.DataFrame,
    metadata: dict,
    rule_manager: LogicalRuleManager | None = None,
) -> pd.DataFrame:
    """Validates referential integrity of foreign keys in synthetic data.

    Produces one report row for each FK that should exist in the final
    result. The checks inventory is built from ``metadata`` and,
    optionally, from reconstruction rules in ``rule_manager``.
    This also allows validating derived FKs that are no longer part of the
    training schema.

    If there is only one table (or a standalone DataFrame), it returns an empty DataFrame
    so it does not appear in the unified report.

    Args:
        synthetic_data (dict[str, pd.DataFrame] | pd.DataFrame): Dictionary
            of synthetic tables or a single DataFrame.
        metadata (dict): Metadata with table structure, PKs, and FKs.
        rule_manager (LogicalRuleManager | None): Rule manager used to
            include derived FKs in the check inventory. Defaults to None.

    Returns:
        pd.DataFrame: Reporte con columnas [type, check, rule, table, status,
            failed_rows, total_rows, details]. Empty if not applicable.

    Example:
        >>> report = sanity_check_referential_integrity(
        ...     synthetic_data, metadata, rule_manager
        ... )
        >>> report[report['status'] == 'FAIL']
    """

    # 1. Input Validation — single table: nothing to check, return empty
    if isinstance(synthetic_data, pd.DataFrame) or len(synthetic_data) < 2:
        logger.info("Single DataFrame or insufficient tables provided. No relationships to check.")
        return pd.DataFrame()

    logger.info("=" * 80)
    logger.info("%s", f"{'REFERENTIAL INTEGRITY CHECK':^80}")
    logger.info("=" * 80)

    rows: list[dict] = []
    table_pks = _build_table_name_to_pks_mapping(metadata)

    for fk_check in _collect_all_fks_to_check(metadata, rule_manager):
        rows.append(
            _evaluate_single_referential_integrity_check(fk_check, synthetic_data, table_pks)
        )

    if not rows:
        logger.info("No foreign keys found in metadata tables.")
        return pd.DataFrame()

    report_df = pd.DataFrame(rows)

    logger.info("\n%s", report_df.to_string(index=False))
    logger.info("=" * 80)

    return report_df


def sanity_check_contextual_fk_consistency(
    synthetic_data: dict[str, pd.DataFrame] | pd.DataFrame,
    metadata: dict,
    rule_manager: LogicalRuleManager | None = None,
) -> pd.DataFrame:
    """Validates consistency between a child FK and the FK derivable from its context.

    Detects hierarchical relationships where a child table keeps a
    ``context key`` to its parent and, additionally, there is an FK that can
    be reconstructed from that parent. The check compares both values and reports
    discrepancies with concrete examples of failed rows.

    Args:
        synthetic_data (dict[str, pd.DataFrame] | pd.DataFrame): Dictionary
            of synthetic tables or a single DataFrame.
        metadata (dict): Tabular metadata.
        rule_manager (LogicalRuleManager | None): Rule manager used to
            include derived FKs in the check inventory. Defaults to None.

    Returns:
        pd.DataFrame: Reporte con columnas [type, check, rule, table, status,
            failed_rows, total_rows, details]. Empty if not applicable.

    Example:
        >>> report = sanity_check_contextual_fk_consistency(
        ...     synthetic_data, metadata, rule_manager
        ... )
        >>> report[report['status'] == 'FAIL']
    """

    if isinstance(synthetic_data, pd.DataFrame) or len(synthetic_data) < 2:
        logger.info("Single DataFrame or insufficient tables provided. No contextual checks.")
        return pd.DataFrame()

    logger.info("=" * 80)
    logger.info("%s", f"{'CONTEXTUAL FK CONSISTENCY CHECK':^80}")
    logger.info("=" * 80)

    rows: list[dict] = []
    table_pks = _build_table_name_to_pks_mapping(metadata)

    for check in _collect_all_contextual_relationships_to_check(metadata, rule_manager):
        rows.append(_evaluate_single_contextual_fk_check(check, synthetic_data, table_pks))

    if not rows:
        logger.info("No contextual FK consistency checks inferred.")
        return pd.DataFrame()

    report_df = pd.DataFrame(rows)

    logger.info("\n%s", report_df.to_string(index=False))
    logger.info("=" * 80)

    return report_df
