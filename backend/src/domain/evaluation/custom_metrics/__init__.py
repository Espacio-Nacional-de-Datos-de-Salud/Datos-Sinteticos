"""Custom evaluation metrics used by the project evaluation engines.

The exports are lazy so importing one metric does not load every optional
privacy/statistics dependency in this package.
"""

from __future__ import annotations

__all__ = [
    "CorrelationMatrixDistance",
    "DCR",
    "DistributionComparisonReport",
    "ExactMatchRows",
    "KAnonymity",
    "LDiversityPyCanon",
    "MetricEvaluator",
    "NNDR",
    "UtilityTests",
]


def __getattr__(name: str):
    if name == "CorrelationMatrixDistance":
        from backend.src.domain.evaluation.custom_metrics.correlation_matrix_distance import (
            CorrelationMatrixDistance,
        )

        return CorrelationMatrixDistance
    if name == "DCR":
        from backend.src.domain.evaluation.custom_metrics.dcr import DCR

        return DCR
    if name == "DistributionComparisonReport":
        from backend.src.domain.evaluation.custom_metrics.distribution_comparison_report import (
            DistributionComparisonReport,
        )

        return DistributionComparisonReport

    if name == "ExactMatchRows":
        from backend.src.domain.evaluation.custom_metrics.exact_match_rows import ExactMatchRows

        return ExactMatchRows

    if name == "KAnonymity":
        from backend.src.domain.evaluation.custom_metrics.k_anonymity import KAnonymity

        return KAnonymity
    if name == "LDiversityPyCanon":
        try:
            from backend.src.domain.evaluation.custom_metrics.l_diversity_pycanon import (
                LDiversityPyCanon,
            )
        except Exception:
            return None
        return LDiversityPyCanon
    if name == "MetricEvaluator":
        from backend.src.domain.evaluation.custom_metrics.base import MetricEvaluator

        return MetricEvaluator
    if name == "NNDR":
        from backend.src.domain.evaluation.custom_metrics.nndr import NNDR

        return NNDR
    if name == "UtilityTests":
        from backend.src.domain.evaluation.custom_metrics.utility_tests import UtilityTests

        return UtilityTests

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
