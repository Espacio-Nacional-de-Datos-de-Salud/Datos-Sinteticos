from __future__ import annotations

import pandas as pd

from backend.src.domain.evaluation.custom_metrics.distribution_comparison_report import (
    DistributionComparisonReport,
)


def test_distribution_comparison_report_builds_mostly_like_payload() -> None:
    real = pd.DataFrame(
        {
            "age": [10, 20, 30, 40, 50, 60],
            "sex": ["F", "F", "M", "M", "M", "F"],
            "flag": [0, 0, 1, 1, 1, 0],
        }
    )
    synthetic = pd.DataFrame(
        {
            "age": [10, 25, 35, 45, 55, 65],
            "sex": ["F", "M", "M", "M", "F", "F"],
            "flag": [0, 1, 1, 1, 0, 0],
        }
    )

    result = DistributionComparisonReport().evaluate(real, synthetic)

    assert set(result["scores"]) == {
        "1_tvd.univariate",
        "1_tvd.bivariate",
        "1_tvd.trivariate",
        "1_tvd.overall",
    }
    assert 0 <= result["scores"]["1_tvd.univariate"]["mean"] <= 1

    payload = result["additional"]
    assert payload["summary"]["univariate"]["n"] == 3
    assert payload["summary"]["bivariate"]["n"] == 3
    assert payload["summary"]["trivariate"]["n"] == 1
    assert payload["correlations"]["real"]["columns"] == ["age", "sex", "flag"]
    assert payload["accuracy_matrix"]["columns"] == ["age", "sex", "flag"]
    assert len(payload["univariate_plots"]) == 3
    assert payload["bivariate_plots"]

    accuracy_table = payload["accuracy_table"]
    assert {row["column"] for row in accuracy_table} == {"age", "sex", "flag"}
    for row in accuracy_table:
        assert set(row) == {"column", "univariate", "bivariate", "trivariate"}
        assert 0 <= row["univariate"] <= 1
        assert 0 <= row["bivariate"] <= 1
        assert 0 <= row["trivariate"] <= 1
