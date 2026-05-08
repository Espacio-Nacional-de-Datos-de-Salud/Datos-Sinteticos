"""Custom evaluation metrics used by the project evaluation engines.

Each metric class lives in its own module under this package. The custom
metrics runner imports them through this ``__init__`` to keep the call
site concise and preserve the import path ``from src.evaluation.metrics import X``.
"""

from backend.src.evaluation.custom_metrics.average_complementary_tvd import AverageComplementaryTVD
from backend.src.evaluation.custom_metrics.base import MetricEvaluator
from backend.src.evaluation.custom_metrics.confidence_interval_overlap import (
    ConfidenceIntervalOverlap,
)
from backend.src.evaluation.custom_metrics.correlation_matrix_distance import (
    CorrelationMatrixDistance,
)
from backend.src.evaluation.custom_metrics.dcr import DCR
from backend.src.evaluation.custom_metrics.k_anonymity import KAnonymity

try:
    from backend.src.evaluation.custom_metrics.l_diversity_pycanon import LDiversityPyCanon
except Exception:
    LDiversityPyCanon = None
from backend.src.evaluation.custom_metrics.nndr import NNDR

__all__ = [
    "AverageComplementaryTVD",
    "ConfidenceIntervalOverlap",
    "CorrelationMatrixDistance",
    "DCR",
    "KAnonymity",
    "LDiversityPyCanon",
    "MetricEvaluator",
    "NNDR",
]
