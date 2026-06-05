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
    _build_table_name_to_pks_mapping,
    _collect_all_contextual_relationships_to_check,
    _collect_all_fks_to_check,
    _evaluate_single_contextual_fk_check,
    _evaluate_single_referential_integrity_check,
)
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


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

    if not reports:
        return pd.DataFrame()

    return pd.concat(reports, ignore_index=True)


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
