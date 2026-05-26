from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from backend.src.config.evaluation import UTILITY_TESTS_CONFIG
from backend.src.domain.evaluation.custom_metrics.base import MetricEvaluator
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


class UtilityTests(MetricEvaluator):
    """User-defined utility checks comparing real vs synthetic aggregate values.

    These tests are intended to answer whether the synthetic dataset preserves
    specific indicators relevant to the intended downstream use.
    """

    supports_multitable = True

    @staticmethod
    def name() -> str:
        return "utility_tests"

    def evaluate(
        self,
        real_data: dict[str, pd.DataFrame],
        synthetic_data: dict[str, pd.DataFrame],
    ) -> dict:
        config = UTILITY_TESTS_CONFIG or {}
        if not config.get("enabled", False):
            return self._empty_result("utility_tests disabled")

        tests = config.get("tests", [])
        if not tests:
            return self._empty_result("no utility tests configured")

        default_tolerance = float(config.get("default_tolerance", 0.10))

        rows = []
        for test in tests:
            try:
                row = self._evaluate_test(
                    test=test,
                    real_data=real_data,
                    synthetic_data=synthetic_data,
                    default_tolerance=default_tolerance,
                )
                rows.append(row)
            except Exception as exc:
                logger.exception("Failed to evaluate utility test %s: %s", test.get("name"), exc)
                rows.append(
                    {
                        "name": test.get("name", "unknown"),
                        "metric": test.get("metric"),
                        "weight": float(test.get("weight", 1.0)),
                        "real_value": None,
                        "synthetic_value": None,
                        "absolute_error": None,
                        "relative_error": None,
                        "score": None,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

        valid_rows = [
            row for row in rows
            if isinstance(row.get("score"), (int, float)) and not math.isnan(row["score"])
        ]

        total_weight = sum(float(row.get("weight", 1.0)) for row in valid_rows)
        if total_weight > 0:
            score = sum(
                float(row["score"]) * float(row.get("weight", 1.0))
                for row in valid_rows
            ) / total_weight
        else:
            score = None

        additional = {
            "summary": {
                "score": score,
                "n_tests": len(rows),
                "n_valid_tests": len(valid_rows),
                "total_weight": total_weight,
            },
            "tests": rows,
            "config": config,
        }

        return {
            "scores": {
                "utility_tests": {
                    "mean": score,
                    "min": min((row["score"] for row in valid_rows), default=None),
                    "max": max((row["score"] for row in valid_rows), default=None),
                }
            },
            "additional": additional,
        }

    def _empty_result(self, reason: str) -> dict:
        return {
            "scores": {
                "utility_tests": {
                    "mean": None,
                    "min": None,
                    "max": None,
                }
            },
            "additional": {
                "summary": {
                    "score": None,
                    "n_tests": 0,
                    "n_valid_tests": 0,
                    "total_weight": 0,
                    "reason": reason,
                },
                "tests": [],
                "config": UTILITY_TESTS_CONFIG or {},
            },
        }

    def _evaluate_test(
        self,
        test: dict[str, Any],
        real_data: dict[str, pd.DataFrame],
        synthetic_data: dict[str, pd.DataFrame],
        default_tolerance: float,
    ) -> dict[str, Any]:
        name = test.get("name", "unknown")
        metric = test.get("metric")
        weight = float(test.get("weight", 1.0))
        tolerance = float(test.get("tolerance", default_tolerance))

        real_value = self._compute_metric(test, real_data)
        synthetic_value = self._compute_metric(test, synthetic_data)

        absolute_error, relative_error = self._errors(real_value, synthetic_value)
        score = self._score_from_relative_error(relative_error, tolerance)

        return {
            "name": name,
            "metric": metric,
            "table": test.get("table"),
            "filter": test.get("filter"),
            "column": test.get("column"),
            "weight": weight,
            "tolerance": tolerance,
            "real_value": real_value,
            "synthetic_value": synthetic_value,
            "absolute_error": absolute_error,
            "relative_error": relative_error,
            "score": score,
            "status": "ok",
        }

    def _compute_metric(
        self,
        spec: dict[str, Any],
        data: dict[str, pd.DataFrame],
    ) -> float:
        metric = spec.get("metric")

        if metric in {"rate", "ratio"}:
            numerator = self._compute_metric(spec["numerator"], data)
            denominator = self._compute_metric(spec["denominator"], data)
            if denominator == 0:
                return float("nan")
            return float(numerator / denominator)

        table_name = spec.get("table")
        if not table_name:
            raise ValueError(f"Metric '{metric}' requires a table")

        if table_name not in data:
            available = ", ".join(data.keys())
            raise ValueError(f"Table '{table_name}' not found. Available tables: {available}")

        frame = data[table_name]
        filtered = self._apply_filter(frame, spec.get("filter"))

        if metric == "count":
            return float(len(filtered))

        if metric == "proportion":
            denominator = len(frame)
            if denominator == 0:
                return float("nan")
            return float(len(filtered) / denominator)

        column = spec.get("column")
        if not column:
            raise ValueError(f"Metric '{metric}' requires a column")

        if column not in filtered.columns:
            raise ValueError(f"Column '{column}' not found in table '{table_name}'")

        series = pd.to_numeric(filtered[column], errors="ignore")

        if metric == "nunique":
            return float(filtered[column].nunique(dropna=True))
        if metric == "mean":
            return float(pd.to_numeric(series, errors="coerce").mean())
        if metric == "median":
            return float(pd.to_numeric(series, errors="coerce").median())
        if metric == "sum":
            return float(pd.to_numeric(series, errors="coerce").sum())
        if metric == "std":
            return float(pd.to_numeric(series, errors="coerce").std())
        if metric == "min":
            return float(pd.to_numeric(series, errors="coerce").min())
        if metric == "max":
            return float(pd.to_numeric(series, errors="coerce").max())
        if metric == "percentile":
            q = float(spec.get("percentile", 0.5))
            return float(pd.to_numeric(series, errors="coerce").quantile(q))

        raise ValueError(f"Unsupported utility metric: {metric}")

    @staticmethod
    def _apply_filter(frame: pd.DataFrame, filter_expr: str | None) -> pd.DataFrame:
        if not filter_expr:
            return frame

        try:
            return frame.query(filter_expr)
        except Exception as exc:
            raise ValueError(f"Invalid filter expression '{filter_expr}': {exc}") from exc

    @staticmethod
    def _errors(real_value: float, synthetic_value: float) -> tuple[float | None, float | None]:
        if real_value is None or synthetic_value is None:
            return None, None

        if pd.isna(real_value) or pd.isna(synthetic_value):
            return None, None

        absolute_error = abs(float(synthetic_value) - float(real_value))

        if float(real_value) == 0:
            relative_error = 0.0 if float(synthetic_value) == 0 else 1.0
        else:
            relative_error = absolute_error / abs(float(real_value))

        return float(absolute_error), float(relative_error)

    @staticmethod
    def _score_from_relative_error(
        relative_error: float | None,
        tolerance: float,
    ) -> float | None:
        if relative_error is None or pd.isna(relative_error):
            return None

        if tolerance <= 0:
            return 1.0 if relative_error == 0 else 0.0

        return float(max(0.0, 1.0 - min(relative_error / tolerance, 1.0)))