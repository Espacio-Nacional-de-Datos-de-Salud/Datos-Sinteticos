"""Nearest Neighbour Distance Ratio (NNDR) metric.

Computes the ratio between each record's distance to its nearest neighbour
and its second nearest. Ratios close to 0 indicate strong anchoring to a
single real record (privacy risk); ratios close to 1 indicate the record
sits in a dense region.
"""

import numpy as np
import pandas as pd
from backend.src.infrastructure.logging_config import get_logger
from backend.src.domain.evaluation.custom_metrics.base import MetricEvaluator
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

logger = get_logger(__name__)


class NNDR(MetricEvaluator):
    """Nearest Neighbour Distance Ratio (NNDR) — real and synthetic.

    ``nndr.syn``: for each synthetic record, ratio of its distance to the
    nearest real record vs the second nearest real record (d1/d2).  A ratio
    close to 1 means the record sits in a dense region (good generalisation);
    a ratio close to 0 means it is anchored to a single real record (privacy
    risk).

    ``nndr.real``: same ratio computed on real records against other real
    records (baseline).

    Both directions: higher is safer because the nearest and second-nearest
    neighbours are similarly distant, which suggests less anchoring to a
    single real record.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        return "nndr"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        if len(real_data) < 3 or len(synthetic_data) == 0:
            logger.warning("Cannot calculate NNDR, not enough data.")
            return {"score": float("inf")}

        real_processed, syn_processed = self._encode_categorical_columns(real_data, synthetic_data)
        real_processed = real_processed.dropna()
        syn_processed = syn_processed.dropna()

        if len(real_processed) < 3 or len(syn_processed) == 0:
            logger.warning("Cannot calculate NNDR, not enough non-NaN data.")
            return {"score": float("inf")}

        scaler = StandardScaler()
        real_scaled = scaler.fit_transform(real_processed)
        syn_scaled = scaler.transform(syn_processed)

        # nndr.syn: fit on real, query synthetic (k=2)
        nn = NearestNeighbors(n_neighbors=2, metric="euclidean")
        nn.fit(real_scaled)
        d_syn, _ = nn.kneighbors(syn_scaled)
        syn_ratios = d_syn[:, 0] / np.where(d_syn[:, 1] > 0, d_syn[:, 1], np.finfo(float).eps)

        # nndr.real: fit on real, query real (k=3 to skip self at index 0)
        nn3 = NearestNeighbors(n_neighbors=3, metric="euclidean")
        nn3.fit(real_scaled)
        d_real, _ = nn3.kneighbors(real_scaled)
        real_ratios = d_real[:, 1] / np.where(d_real[:, 2] > 0, d_real[:, 2], np.finfo(float).eps)

        return {
            "scores": {
                "nndr.real": {
                    "mean": float(np.mean(real_ratios)),
                    "min": float(np.min(real_ratios)),
                    "max": float(np.max(real_ratios)),
                },
                "nndr.syn": {
                    "mean": float(np.mean(syn_ratios)),
                    "min": float(np.min(syn_ratios)),
                    "max": float(np.max(syn_ratios)),
                },
            },
        }
