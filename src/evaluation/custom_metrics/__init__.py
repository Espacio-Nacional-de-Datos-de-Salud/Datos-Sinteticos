"""Custom evaluation metrics used by the project evaluation engines.

Each metric class lives in its own module under this package. The custom
metrics runner imports them through this ``__init__`` to keep the call
site concise and preserve the import path ``from src.evaluation.metrics import X``.
"""

from src.evaluation.custom_metrics.average_complementary_tvd import AverageComplementaryTVD
from src.evaluation.custom_metrics.base import MetricEvaluator
from src.evaluation.custom_metrics.confidence_interval_overlap import ConfidenceIntervalOverlap
from src.evaluation.custom_metrics.correlation_matrix_distance import CorrelationMatrixDistance
from src.evaluation.custom_metrics.dcr import DCR
from src.evaluation.custom_metrics.k_anonymity import KAnonymity
from src.evaluation.custom_metrics.l_diversity_pycanon import LDiversityPyCanon
from src.evaluation.custom_metrics.nndr import NNDR

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
