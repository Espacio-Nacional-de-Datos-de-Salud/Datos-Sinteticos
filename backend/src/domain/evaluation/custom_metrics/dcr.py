"""Distance to Closest Record (DCR) metric.

Quantifies how close each synthetic record sits to its nearest real record
and compares it against the real-to-real baseline. Low ``dcr.syn`` relative
to ``dcr.real`` suggests the synthetic data may be memorising real records.
"""

import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from backend.src.domain.evaluation.custom_metrics.base import MetricEvaluator
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


class DCR(MetricEvaluator):
    """Distance to Closest Record (DCR) — real and synthetic.

    ``dcr.syn``: mean distance from each synthetic record to its nearest real
    record.  Low values indicate synthetic records may be memorising real ones.

    ``dcr.real``: mean distance from each real record to its nearest *other*
    real record (baseline).  Comparing dcr.syn against dcr.real tells you
    whether synthetic records sit at natural data density or are suspiciously
    close to real ones.

    Both directions: higher is safer (more distance = less leakage risk).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        return "dcr"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        if len(real_data) < 2 or len(synthetic_data) == 0:
            logger.warning("Cannot calculate DCR, not enough data.")
            return {"score": float("inf")}

        real_data, synthetic_data = self._sample_for_expensive_metric(real_data, synthetic_data)

        real_processed, syn_processed = self._encode_categorical_columns(real_data, synthetic_data)
        real_processed = real_processed.dropna()
        syn_processed = syn_processed.dropna()

        if len(real_processed) < 2 or len(syn_processed) == 0:
            logger.warning("Cannot calculate DCR, not enough non-NaN data.")
            return {"score": float("inf")}

        scaler = StandardScaler()
        real_scaled = scaler.fit_transform(real_processed)
        syn_scaled = scaler.transform(syn_processed)

        # dcr.syn: each synthetic -> nearest real
        nn = NearestNeighbors(n_neighbors=1, metric="euclidean")
        nn.fit(real_scaled)
        syn_distances, _ = nn.kneighbors(syn_scaled)
        syn_dcr = syn_distances[:, 0]

        # dcr.real: each real -> nearest other real (k=2, skip self at index 0)
        nn2 = NearestNeighbors(n_neighbors=2, metric="euclidean")
        nn2.fit(real_scaled)
        real_distances, _ = nn2.kneighbors(real_scaled)
        real_dcr = real_distances[:, 1]

        return {
            "scores": {
                "dcr.real": {
                    "mean": float(np.mean(real_dcr)),
                    "min": float(np.min(real_dcr)),
                    "max": float(np.max(real_dcr)),
                },
                "dcr.syn": {
                    "mean": float(np.mean(syn_dcr)),
                    "min": float(np.min(syn_dcr)),
                    "max": float(np.max(syn_dcr)),
                },
            },
        }
