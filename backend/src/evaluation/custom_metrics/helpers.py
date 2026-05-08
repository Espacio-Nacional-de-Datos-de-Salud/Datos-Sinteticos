"""Shared helpers for metrics that operate on quasi-identifier subsets.

Both k-anonymity and l-diversity evaluate privacy over user-defined
combinations of columns (`QUASI_IDENTIFIER_SUBSETS`). When no such config is
provided, they fall back to pairwise combinations of every column. The logic
is identical for both metrics and lives here to avoid duplication.
"""

from itertools import combinations

import pandas as pd
from backend.src.config.evaluation import QUASI_IDENTIFIER_SUBSETS
from backend.src.core.logging_config import get_logger

logger = get_logger(__name__)


def pairwise_quasi_identifier_subsets(columns: list[str]) -> dict[str, list[str]]:
    """Build pairwise-combination subsets when no explicit QI config is provided.

    Args:
        columns (list[str]): Dataset columns to combine.

    Returns:
        dict[str, list[str]]: Mapping ``"col1/col2" -> [col1, col2]``.
    """
    return {f"{col1}/{col2}": [col1, col2] for col1, col2 in combinations(columns, 2)}


def resolve_quasi_identifier_subsets(
    real_data: pd.DataFrame,
) -> tuple[dict[str, list[str]], str]:
    """Return the configured QI subsets, or pairwise fallbacks, plus their source label.

    Args:
        real_data (pd.DataFrame): Real dataset used to derive pairwise fallbacks
            when no explicit configuration is provided.

    Returns:
        tuple[dict[str, list[str]], str]: ``(subsets, source)`` where ``source``
        identifies whether the subsets came from config or pairwise fallback.
    """
    if QUASI_IDENTIFIER_SUBSETS is not None:
        source = "config.evaluation.evaluation_config.QUASI_IDENTIFIER_SUBSETS"
        return QUASI_IDENTIFIER_SUBSETS, source

    logger.debug("No Quasi Identifiers found in config. Performing pairwise combinations")
    return (
        pairwise_quasi_identifier_subsets(list(real_data.columns)),
        "pairwise_combinations_of_all_columns",
    )
