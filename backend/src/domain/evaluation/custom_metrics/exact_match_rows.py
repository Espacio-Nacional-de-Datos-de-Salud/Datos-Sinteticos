from collections.abc import Iterable

import pandas as pd

from backend.src.config.evaluation import EXACT_MATCH_SHOW_FILTERED_ROWS
from backend.src.domain.evaluation.custom_metrics.base import MetricEvaluator
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


def _crp_and_matches(
    syn_indexed: pd.DataFrame,
    real_str: pd.DataFrame,
    cols: Iterable[str],
    syn_total: int,
    extract_rows: bool = False,
    include_rows: bool = False,
) -> dict:
    """Compute CRP for ``cols`` and optionally extract matching rows.

    Returns ``{"count", "proportion", "synthetic_indices"?, "rows"?}``. The
    count/proportion are always computed; ``synthetic_indices`` and ``rows``
    (verbatim real-data records) are only included when both ``extract_rows``
    and ``include_rows`` are True — ``include_rows`` reflects the privacy
    toggle that controls whether matching rows are surfaced in the report.
    """
    cols = list(cols)
    real_sub = real_str[cols].drop_duplicates()
    matches = pd.merge(syn_indexed[["__syn_idx__"] + cols], real_sub, on=cols, how="inner")
    count = len(matches)
    out = {"count": count, "proportion": count / syn_total if syn_total else 0.0}
    if extract_rows and include_rows and count > 0:
        out["synthetic_indices"] = matches["__syn_idx__"].tolist()
        out["rows"] = matches.drop(columns=["__syn_idx__"]).to_dict(orient="records")
    return out


class ExactMatchRows(MetricEvaluator):
    """Locate synthetic rows that are verbatim copies of real rows.

    Returns CRP for every column-combination (full + leave-one-out) and EMR
    (the actual rows) only for those combinations with CRP > 0.
    """

    def __init__(self, show_filtered_rows: bool | None = None, **kwargs) -> None:
        """Initialize the metric.

        Args:
            show_filtered_rows: Per-run override for whether matching (verbatim
                real) rows are surfaced in the report. ``None`` ⇒ global config.
            **kwargs: Forwarded to the base evaluator.
        """
        super().__init__(**kwargs)
        self._show_filtered_rows = (
            show_filtered_rows
            if show_filtered_rows is not None
            else EXACT_MATCH_SHOW_FILTERED_ROWS
        )

    @staticmethod
    def name() -> str:
        return "exact_match_rows"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        if real_data.empty or synthetic_data.empty:
            return self._empty_result()

        shared_cols = [c for c in real_data.columns if c in synthetic_data.columns]
        if not shared_cols:
            return self._empty_result()

        real_str = real_data[shared_cols].astype(str)
        syn_str = synthetic_data[shared_cols].astype(str)
        syn_indexed = syn_str.reset_index().rename(columns={"index": "__syn_idx__"})
        syn_total = len(synthetic_data)
        include_rows = self._show_filtered_rows

        full = _crp_and_matches(
            syn_indexed,
            real_str,
            shared_cols,
            syn_total,
            extract_rows=True,
            include_rows=include_rows,
        )
        score = full["proportion"]
        full_count = full["count"]

        loo = {}
        if len(shared_cols) >= 2:
            for excluded in shared_cols:
                remaining = [c for c in shared_cols if c != excluded]
                crp = _crp_and_matches(
                    syn_indexed,
                    real_str,
                    remaining,
                    syn_total,
                    extract_rows=False,
                )
                if crp["count"] > full_count:
                    crp = _crp_and_matches(
                        syn_indexed,
                        real_str,
                        remaining,
                        syn_total,
                        extract_rows=True,
                        include_rows=include_rows,
                    )
                loo[excluded] = crp

        if score == 0.0 and all(v["count"] == 0 for v in loo.values()):
            return self._empty_result()

        if full["count"] > 0:
            logger.warning(
                "ExactMatchRows: %d synthetic row(s) are verbatim copies of real data (%.2f%%)."
                % (full["count"], score * 100)
            )

        new_loo = [c for c, v in loo.items() if v["count"] > full_count]
        if new_loo:
            logger.warning(
                "ExactMatchRows: column(s) %s reveal NEW matches when excluded — likely encoding mismatch."
                % new_loo
            )

        return {
            "score": score,
            "additional": {"full_match": full, "leave_one_out": loo},
        }

    @staticmethod
    def _empty_result() -> dict:
        return {"score": 0.0}
