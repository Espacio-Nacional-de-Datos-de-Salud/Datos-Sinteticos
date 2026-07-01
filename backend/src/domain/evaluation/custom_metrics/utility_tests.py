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
    # Each per-table evaluation report only shows the tests targeting that table.
    supports_table_filter = True

    def __init__(self, config: dict | None = None, **kwargs) -> None:
        """Initialize the metric.

        Args:
            config: Per-run override for the ``utility_tests`` config block
                (enabled flag + tests). ``None`` ⇒ global config.
            **kwargs: Forwarded to the base evaluator.
        """
        super().__init__(**kwargs)
        self._config = config

    @staticmethod
    def name() -> str:
        return "utility_tests"

    def evaluate(
        self,
        real_data: dict[str, pd.DataFrame],
        synthetic_data: dict[str, pd.DataFrame],
        evaluated_table: str | None = None,
    ) -> dict:
        config = self._config if self._config is not None else (UTILITY_TESTS_CONFIG or {})
        if not config.get("enabled", False):
            return self._empty_result("utility_tests disabled")

        tests = config.get("tests", [])
        if evaluated_table is not None:
            tests = [test for test in tests if test.get("table") == evaluated_table]
        if not tests:
            return self._empty_result("no utility tests configured")

        rows = []
        for test in tests:
            try:
                row = self._evaluate_test(
                    test=test,
                    real_data=real_data,
                    synthetic_data=synthetic_data,
                )
                rows.append(row)
            except Exception as exc:
                logger.exception("Failed to evaluate utility test %s: %s", test.get("name"), exc)
                rows.append(
                    {
                        "name": test.get("name", "unknown"),
                        "metric": test.get("metric"),
                        "table": test.get("table"),
                        "column": test.get("column"),
                        "weight": float(test.get("weight", 1.0)),
                        "real_value": None,
                        "synthetic_value": None,
                        "absolute_error": None,
                        "relative_discrepancy": None,
                        "score": None,
                        "status": "failed",
                        "error": str(exc),
                    }
                )

        valid_rows = [
            row
            for row in rows
            if isinstance(row.get("score"), (int, float)) and not math.isnan(row["score"])
        ]

        total_weight = sum(float(row.get("weight", 1.0)) for row in valid_rows)
        if total_weight > 0:
            score = (
                sum(float(row["score"]) * float(row.get("weight", 1.0)) for row in valid_rows)
                / total_weight
            )
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
                "config": (
                    self._config if self._config is not None else (UTILITY_TESTS_CONFIG or {})
                ),
            },
        }

    def _evaluate_test(
        self,
        test: dict[str, Any],
        real_data: dict[str, pd.DataFrame],
        synthetic_data: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        name = test.get("name", "unknown")
        metric = test.get("metric")
        weight = float(test.get("weight", 1.0))

        real_value = self._compute_metric(test, real_data)
        synthetic_value = self._compute_metric(test, synthetic_data)

        absolute_error, relative_discrepancy = self._errors(real_value, synthetic_value)
        relative_precision = self._precision_from_relative_error(relative_discrepancy)

        context = self._build_context(
            test=test,
            real_data=real_data,
            synthetic_data=synthetic_data,
            real_value=real_value,
            synthetic_value=synthetic_value,
        )

        return {
            "name": name,
            "metric": metric,
            "table": test.get("table"),
            "filter": test.get("filter"),
            "column": test.get("column"),
            "weight": weight,
            "real_value": real_value,
            "synthetic_value": synthetic_value,
            "absolute_error": absolute_error,
            "relative_discrepancy": relative_discrepancy,
            "relative_precision": relative_precision,
            # ``score`` mirrors the relative precision and drives the weighted
            # axis mean; kept for backward compatibility with the report wiring.
            "score": relative_precision,
            "status": "ok",
            "context": context,
        }

    def _load_table(self, test: dict[str, Any], data: dict[str, pd.DataFrame]) -> pd.DataFrame:
        table_name = test.get("table")
        if not table_name:
            raise ValueError("Utility test requires a table")
        if table_name not in data:
            available = ", ".join(data.keys())
            raise ValueError(f"Table '{table_name}' not found. Available tables: {available}")
        return data[table_name]

    def _build_context(
        self,
        test: dict[str, Any],
        real_data: dict[str, pd.DataFrame],
        synthetic_data: dict[str, pd.DataFrame],
        real_value: float | None,
        synthetic_value: float | None,
    ) -> dict[str, Any]:
        metric = test.get("metric")
        if real_value is None or synthetic_value is None:
            return {
                "metric_type": metric,
                "note": "No hay contexto adicional debido a valores inválidos.",
            }

        if metric in {"rate", "ratio"}:
            return self._build_ratio_context(test, real_data, synthetic_data)
        if metric == "count":
            return self._build_count_context(test, real_data, synthetic_data)
        if metric == "proportion":
            return self._build_proportion_context(test, real_data, synthetic_data)
        if metric in {"nunique", "mean", "median", "sum", "std", "min", "max", "percentile"}:
            return self._build_numeric_context(test, real_data, synthetic_data)

        return {
            "metric_type": metric,
            "note": "No hay contexto adicional disponible para esta prueba.",
        }

    def _build_ratio_context(
        self,
        test: dict[str, Any],
        real_data: dict[str, pd.DataFrame],
        synthetic_data: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        def pair(spec: dict[str, Any] | None) -> tuple[float | None, float | None]:
            if not spec:
                return None, None
            try:
                return (
                    self._compute_metric(spec, real_data),
                    self._compute_metric(spec, synthetic_data),
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to compute rate/ratio component: %s", exc)
                return None, None

        real_num, synthetic_num = pair(test.get("numerator"))
        real_den, synthetic_den = pair(test.get("denominator"))
        return {
            "metric_type": test.get("metric"),
            "real_numerator": real_num,
            "synthetic_numerator": synthetic_num,
            "real_denominator": real_den,
            "synthetic_denominator": synthetic_den,
            "note": (
                "La tasa/razón es el cociente entre numerador y denominador; "
                "se comparan ambos componentes entre real y sintético."
            ),
        }

    def _build_count_context(
        self,
        test: dict[str, Any],
        real_data: dict[str, pd.DataFrame],
        synthetic_data: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        real_frame = self._load_table(test, real_data)
        synthetic_frame = self._load_table(test, synthetic_data)
        return {
            "metric_type": "count",
            "real_rows": len(self._apply_filter(real_frame, test.get("filter"))),
            "synthetic_rows": len(self._apply_filter(synthetic_frame, test.get("filter"))),
            "note": "Cuenta las filas que cumplen el filtro especificado en cada dataset.",
        }

    def _build_proportion_context(
        self,
        test: dict[str, Any],
        real_data: dict[str, pd.DataFrame],
        synthetic_data: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        real_frame = self._load_table(test, real_data)
        synthetic_frame = self._load_table(test, synthetic_data)
        real_filtered = self._apply_filter(real_frame, test.get("filter"))
        synthetic_filtered = self._apply_filter(synthetic_frame, test.get("filter"))
        return {
            "metric_type": "proportion",
            "real_total_rows": len(real_frame),
            "synthetic_total_rows": len(synthetic_frame),
            "real_filtered_rows": len(real_filtered),
            "synthetic_filtered_rows": len(synthetic_filtered),
            "note": "La proporción se calcula sobre el total de filas de la tabla tras aplicar el filtro.",
        }

    def _build_numeric_context(
        self,
        test: dict[str, Any],
        real_data: dict[str, pd.DataFrame],
        synthetic_data: dict[str, pd.DataFrame],
    ) -> dict[str, Any]:
        real_frame = self._load_table(test, real_data)
        synthetic_frame = self._load_table(test, synthetic_data)
        filtered_real = self._apply_filter(real_frame, test.get("filter"))
        filtered_synthetic = self._apply_filter(synthetic_frame, test.get("filter"))
        column = test.get("column")
        if (
            not column
            or column not in filtered_real.columns
            or column not in filtered_synthetic.columns
        ):
            return {
                "metric_type": test.get("metric"),
                "note": "No se encontró la columna para generar contexto adicional.",
            }

        real_series = pd.to_numeric(filtered_real[column], errors="coerce")
        synthetic_series = pd.to_numeric(filtered_synthetic[column], errors="coerce")

        real_stats = self._compute_series_stats(real_series)
        synthetic_stats = self._compute_series_stats(synthetic_series)

        note = self._build_dispersion_note(real_stats, synthetic_stats)

        return {
            "metric_type": test.get("metric"),
            "real_count": real_stats["count"],
            "synthetic_count": synthetic_stats["count"],
            "real_null_count": real_stats["null_count"],
            "synthetic_null_count": synthetic_stats["null_count"],
            "real_std": real_stats["std"],
            "synthetic_std": synthetic_stats["std"],
            "real_mean": real_stats["mean"],
            "synthetic_mean": synthetic_stats["mean"],
            "note": note,
        }

    @staticmethod
    def _compute_series_stats(series: pd.Series) -> dict[str, Any]:
        numeric = pd.to_numeric(series, errors="coerce")
        valid = numeric.dropna()
        return {
            "count": int(len(series)),
            "null_count": int(series.isna().sum()),
            "mean": float(valid.mean()) if len(valid) else None,
            "std": float(valid.std()) if len(valid) else None,
        }

    @staticmethod
    def _build_dispersion_note(
        real_stats: dict[str, Any],
        synthetic_stats: dict[str, Any],
    ) -> str:
        real_std = real_stats.get("std")
        synthetic_std = synthetic_stats.get("std")
        if real_std is None or synthetic_std is None:
            return "No hay suficiente información numérica para añadir contexto de dispersión."

        if real_std == synthetic_std:
            return "La dispersión sintética coincide con la dispersión real."

        if real_std == 0:
            return "La desviación estándar real es 0; compare la variabilidad absoluta en lugar de relativa."

        diff = synthetic_std - real_std
        relative_change = abs(diff) / real_std
        direction = "mayor" if diff > 0 else "menor"
        return f"La desviación estándar sintética es {relative_change:.1%} {direction} que la real."

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

        if metric == "custom_formula":
            return self._eval_custom_formula(spec, filtered)

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
    def _eval_custom_formula(spec: dict[str, Any], frame: pd.DataFrame) -> float:
        """Evaluate a user-defined formula over the (filtered) table.

        The expression sees the filtered DataFrame as ``df`` plus ``np`` and
        ``pd``, so it can combine one or several columns, e.g.
        ``df['charges'].sum() / df['age'].mean()``. Builtins are restricted to a
        small numeric whitelist. Same trust model as the pandas ``query``
        filters already accepted in this config.
        """
        formula = spec.get("formula")
        if not formula or not str(formula).strip():
            raise ValueError("custom_formula requires a non-empty 'formula' expression")

        safe_globals = {
            "__builtins__": {
                "abs": abs,
                "min": min,
                "max": max,
                "sum": sum,
                "len": len,
                "round": round,
            }
        }
        local_ns = {"df": frame, "np": np, "pd": pd}
        try:
            result = eval(formula, safe_globals, local_ns)  # noqa: S307
        except Exception as exc:
            raise ValueError(f"Invalid custom_formula '{formula}': {exc}") from exc

        if hasattr(result, "item"):
            try:
                result = result.item()
            except (ValueError, AttributeError):
                pass
        return float(result)

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
        """Absolute error and a symmetric, bounded relative discrepancy.

        Relative discrepancy = ``|s - r| / (|s| + |r|)`` (SMAPE family). It is
        symmetric (swapping real/synthetic gives the same value) and always in
        ``[0, 1]``, so the derived precision never depends on which value is
        larger nor blows past 100%. Reported as "Discrepancia rel." — it is not
        the textbook relative error (which divides by the real value only).
        """
        if real_value is None or synthetic_value is None:
            return None, None

        if pd.isna(real_value) or pd.isna(synthetic_value):
            return None, None

        real = float(real_value)
        synthetic = float(synthetic_value)
        absolute_error = abs(synthetic - real)

        denom = abs(synthetic) + abs(real)
        relative_error = 0.0 if denom == 0 else absolute_error / denom

        return float(absolute_error), float(relative_error)

    @staticmethod
    def _precision_from_relative_error(
        relative_discrepancy: float | None,
    ) -> float | None:
        """Relative precision = 1 - relative_discrepancy (already in [0, 1])."""
        if relative_discrepancy is None or pd.isna(relative_discrepancy):
            return None

        return float(max(0.0, 1.0 - float(relative_discrepancy)))
