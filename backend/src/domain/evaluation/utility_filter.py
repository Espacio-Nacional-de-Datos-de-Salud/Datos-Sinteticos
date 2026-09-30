from __future__ import annotations

import pandas as pd


def drop_ood_performance_rows(report: pd.DataFrame) -> pd.DataFrame:
    """Remove out-of-distribution predictive utility rows from evaluation output."""
    if report.empty:
        return report

    metric_names = report.index.to_series().astype(str)
    keep_mask = ~metric_names.str.startswith("performance.") | ~metric_names.str.endswith(
        ".syn_ood"
    )
    return report.loc[keep_mask.to_numpy()]
