"""Mostly-inspired distribution comparison artefact for the evaluation report.

This metric intentionally keeps only the lightweight pieces we want from the
Mostly QA report: shared-bin distribution plots, correlation heatmaps,
univariate/bivariate/trivariate ``1 - TVD`` summaries, and an accuracy matrix.
It does not import Mostly or any embedding/model-report dependencies.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import numpy as np
import pandas as pd

from backend.src.config.evaluation import TVD_N_BINS
from backend.src.domain.evaluation.custom_metrics.base import MetricEvaluator
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)

MISSING_LABEL = "__MISSING__"
OTHER_LABEL = "__OTHER__"
MAX_UNIVARIATE_PLOTS = 18
MAX_BIVARIATE_PLOTS = 12
MAX_MATRIX_COLUMNS = 30
MAX_TRIVARIATE_COMBINATIONS = 120
MAX_CATEGORICAL_LEVELS = 14
MAX_BIVARIATE_LEVELS = 12


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None and not pd.isna(v)]
    return float(np.mean(clean)) if clean else None


class DistributionComparisonReport(MetricEvaluator):
    """Build distribution-comparison data used by ``synthetic_eval_report.html``."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.n_bins = TVD_N_BINS

    @staticmethod
    def name() -> str:
        return "distribution_comparison_report"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        if len(real_data) == 0 or len(synthetic_data) == 0:
            return self._empty_result()

        columns = [col for col in real_data.columns if col in synthetic_data.columns]
        if not columns:
            return self._empty_result()

        binned_real: dict[str, pd.Series] = {}
        binned_syn: dict[str, pd.Series] = {}
        univariate_scores: dict[str, float] = {}
        univariate_plots: list[dict[str, Any]] = []

        for column in columns:
            try:
                real_bins, syn_bins, plot_payload = self._bin_column(
                    real_data[column], synthetic_data[column], column
                )
                binned_real[column] = real_bins
                binned_syn[column] = syn_bins
                score = self._one_minus_tvd(real_bins, syn_bins)
                univariate_scores[column] = score
                plot_payload["one_minus_tvd"] = score
                univariate_plots.append(plot_payload)
            except Exception as exc:
                logger.warning("Failed to compute distribution plot for column %s: %s", column, exc)

        bivariate_scores = self._calculate_bivariate_scores(binned_real, binned_syn)
        trivariate_scores = self._calculate_trivariate_scores(binned_real, binned_syn)
        summary = self._build_summary(univariate_scores, bivariate_scores, trivariate_scores)

        report = {
            "summary": summary,
            "univariate_plots": sorted(
                univariate_plots,
                key=lambda item: item.get("one_minus_tvd", 1.0),
            )[:MAX_UNIVARIATE_PLOTS],
            "bivariate_plots": self._build_bivariate_plots(
                binned_real, binned_syn, bivariate_scores
            ),
            "accuracy_table": self._build_accuracy_table(
                columns, univariate_scores, bivariate_scores, trivariate_scores
            ),
            "accuracy_matrix": self._build_accuracy_matrix(
                columns, univariate_scores, bivariate_scores
            ),
            "correlations": self._build_correlations(real_data[columns], synthetic_data[columns]),
            "scores": {
                "univariate": univariate_scores,
                "bivariate": [
                    {"columns": [col1, col2], "one_minus_tvd": score}
                    for (col1, col2), score in sorted(
                        bivariate_scores.items(), key=lambda item: item[1]
                    )
                ],
                "trivariate": [
                    {"columns": list(cols), "one_minus_tvd": score}
                    for cols, score in sorted(trivariate_scores.items(), key=lambda item: item[1])
                ],
            },
        }

        return {
            "scores": {
                "1_tvd.univariate": {
                    "mean": summary["univariate"]["mean_1_tvd"],
                    "min": summary["univariate"]["min_1_tvd"],
                    "max": summary["univariate"]["max_1_tvd"],
                },
                "1_tvd.bivariate": {
                    "mean": summary["bivariate"]["mean_1_tvd"],
                    "min": summary["bivariate"]["min_1_tvd"],
                    "max": summary["bivariate"]["max_1_tvd"],
                },
                "1_tvd.trivariate": {
                    "mean": summary["trivariate"]["mean_1_tvd"],
                    "min": summary["trivariate"]["min_1_tvd"],
                    "max": summary["trivariate"]["max_1_tvd"],
                },
                "1_tvd.overall": {
                    "mean": _mean(
                        [
                            summary["univariate"]["mean_1_tvd"],
                            summary["bivariate"]["mean_1_tvd"],
                            summary["trivariate"]["mean_1_tvd"],
                        ]
                    )
                },
            },
            "additional": report,
        }

    def _empty_result(self) -> dict:
        return {
            "scores": {
                "1_tvd.univariate": {"mean": None},
                "1_tvd.bivariate": {"mean": None},
                "1_tvd.trivariate": {"mean": None},
                "1_tvd.overall": {"mean": None},
            },
            "additional": {},
        }

    def _bin_column(
        self, real: pd.Series, syn: pd.Series, column: str
    ) -> tuple[pd.Series, pd.Series, dict[str, Any]]:
        if pd.api.types.is_datetime64_any_dtype(real) or pd.api.types.is_datetime64_any_dtype(syn):
            real_num = (
                pd.to_datetime(real, errors="coerce")
                .astype("int64")
                .replace(-9223372036854775808, np.nan)
            )
            syn_num = (
                pd.to_datetime(syn, errors="coerce")
                .astype("int64")
                .replace(-9223372036854775808, np.nan)
            )
            labels, real_bins, syn_bins = self._bin_numeric(real_num, syn_num)
            kind = "datetime"
        elif pd.api.types.is_numeric_dtype(real) or pd.api.types.is_numeric_dtype(syn):
            real_num = pd.to_numeric(real, errors="coerce")
            syn_num = pd.to_numeric(syn, errors="coerce")
            labels, real_bins, syn_bins = self._bin_numeric(real_num, syn_num)
            kind = "numeric"
        else:
            labels, real_bins, syn_bins = self._bin_categorical(real, syn)
            kind = "categorical"

        real_dist = self._distribution_for_labels(real_bins, labels)
        syn_dist = self._distribution_for_labels(syn_bins, labels)

        return real_bins, syn_bins, {
            "column": column,
            "kind": kind,
            "labels": labels,
            "real": real_dist,
            "synthetic": syn_dist,
        }

    def _bin_numeric(
        self, real: pd.Series, syn: pd.Series
    ) -> tuple[list[str], pd.Series, pd.Series]:
        real_clean = real.dropna()
        syn_clean = syn.dropna()
        combined = pd.concat([real_clean, syn_clean])
        if combined.empty:
            labels = [MISSING_LABEL]
            return labels, self._missing_series(real), self._missing_series(syn)

        quantiles = np.linspace(0, 1, self.n_bins + 1)
        edges = np.unique(np.nanquantile(combined.to_numpy(dtype=float), quantiles))
        if len(edges) < 2:
            value = float(edges[0])
            edges = np.array([value - 0.5, value + 0.5])

        edges[0] = -np.inf
        edges[-1] = np.inf
        labels = [self._format_bin_label(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]

        real_bins = pd.cut(real, bins=edges, labels=labels, include_lowest=True, duplicates="drop")
        syn_bins = pd.cut(syn, bins=edges, labels=labels, include_lowest=True, duplicates="drop")
        real_bins = real_bins.astype("object").where(~real.isna(), MISSING_LABEL)
        syn_bins = syn_bins.astype("object").where(~syn.isna(), MISSING_LABEL)

        if real.isna().any() or syn.isna().any():
            labels = [*labels, MISSING_LABEL]
        return labels, real_bins.astype(str), syn_bins.astype(str)

    def _bin_categorical(
        self, real: pd.Series, syn: pd.Series
    ) -> tuple[list[str], pd.Series, pd.Series]:
        real_values = real.astype("object").where(~real.isna(), MISSING_LABEL).astype(str)
        syn_values = syn.astype("object").where(~syn.isna(), MISSING_LABEL).astype(str)
        counts = pd.concat([real_values, syn_values]).value_counts()
        top_labels = counts.head(MAX_CATEGORICAL_LEVELS).index.to_list()
        labels = list(top_labels)
        has_other = len(counts) > len(top_labels)
        if has_other:
            labels.append(OTHER_LABEL)

        real_bins = real_values.where(real_values.isin(top_labels), OTHER_LABEL)
        syn_bins = syn_values.where(syn_values.isin(top_labels), OTHER_LABEL)
        return labels, real_bins, syn_bins

    @staticmethod
    def _missing_series(series: pd.Series) -> pd.Series:
        return pd.Series([MISSING_LABEL] * len(series), index=series.index, dtype="object")

    @staticmethod
    def _format_bin_label(left: float, right: float) -> str:
        if math.isinf(left) and math.isinf(right):
            return "all"
        if math.isinf(left):
            return f"<= {right:.4g}"
        if math.isinf(right):
            return f"> {left:.4g}"
        return f"{left:.4g} - {right:.4g}"

    @staticmethod
    def _distribution_for_labels(values: pd.Series, labels: list[str]) -> list[float]:
        counts = values.value_counts(normalize=True)
        return [float(counts.get(label, 0.0)) for label in labels]

    @staticmethod
    def _one_minus_tvd(real_bins: pd.Series, syn_bins: pd.Series) -> float:
        real_counts = real_bins.value_counts(normalize=True)
        syn_counts = syn_bins.value_counts(normalize=True)
        labels = set(real_counts.index) | set(syn_counts.index)
        tvd = sum(abs(real_counts.get(label, 0.0) - syn_counts.get(label, 0.0)) for label in labels)
        return float(min(1.0, max(0.0, 1.0 - tvd / 2.0)))

    def _calculate_bivariate_scores(
        self,
        binned_real: dict[str, pd.Series],
        binned_syn: dict[str, pd.Series],
    ) -> dict[tuple[str, str], float]:
        scores: dict[tuple[str, str], float] = {}
        for col1, col2 in itertools.combinations(binned_real.keys(), 2):
            scores[(col1, col2)] = self._one_minus_tvd_frame(
                pd.concat([binned_real[col1], binned_real[col2]], axis=1),
                pd.concat([binned_syn[col1], binned_syn[col2]], axis=1),
            )
        return scores

    def _calculate_trivariate_scores(
        self,
        binned_real: dict[str, pd.Series],
        binned_syn: dict[str, pd.Series],
    ) -> dict[tuple[str, str, str], float]:
        combinations = list(itertools.combinations(binned_real.keys(), 3))
        if len(combinations) > MAX_TRIVARIATE_COMBINATIONS:
            combinations = combinations[:MAX_TRIVARIATE_COMBINATIONS]

        scores: dict[tuple[str, str, str], float] = {}
        for cols in combinations:
            scores[cols] = self._one_minus_tvd_frame(
                pd.concat([binned_real[col] for col in cols], axis=1),
                pd.concat([binned_syn[col] for col in cols], axis=1),
            )
        return scores

    @staticmethod
    def _one_minus_tvd_frame(real_frame: pd.DataFrame, syn_frame: pd.DataFrame) -> float:
        real_counts = real_frame.value_counts(normalize=True)
        syn_counts = syn_frame.value_counts(normalize=True)
        keys = set(real_counts.index) | set(syn_counts.index)
        tvd = sum(abs(real_counts.get(key, 0.0) - syn_counts.get(key, 0.0)) for key in keys)
        return float(min(1.0, max(0.0, 1.0 - tvd / 2.0)))

    @staticmethod
    def _build_summary(
        univariate_scores: dict[str, float],
        bivariate_scores: dict[tuple[str, str], float],
        trivariate_scores: dict[tuple[str, str, str], float],
    ) -> dict[str, dict[str, float | int | None]]:
        def row(values: list[float]) -> dict[str, float | int | None]:
            return {
                "mean_1_tvd": _mean(values),
                "min_1_tvd": float(np.min(values)) if values else None,
                "max_1_tvd": float(np.max(values)) if values else None,
                "n": len(values),
            }

        return {
            "univariate": row(list(univariate_scores.values())),
            "bivariate": row(list(bivariate_scores.values())),
            "trivariate": row(list(trivariate_scores.values())),
        }

    def _build_bivariate_plots(
        self,
        binned_real: dict[str, pd.Series],
        binned_syn: dict[str, pd.Series],
        bivariate_scores: dict[tuple[str, str], float],
    ) -> list[dict[str, Any]]:
        plots: list[dict[str, Any]] = []
        worst_pairs = sorted(bivariate_scores.items(), key=lambda item: item[1])[
            :MAX_BIVARIATE_PLOTS
        ]
        for (col1, col2), score in worst_pairs:
            x_labels = self._top_labels_for_pair(binned_real[col1], binned_syn[col1])
            y_labels = self._top_labels_for_pair(binned_real[col2], binned_syn[col2])
            real_matrix = self._pair_distribution_matrix(
                binned_real[col1], binned_real[col2], x_labels, y_labels
            )
            syn_matrix = self._pair_distribution_matrix(
                binned_syn[col1], binned_syn[col2], x_labels, y_labels
            )
            diff_matrix = [
                [abs(real_matrix[i][j] - syn_matrix[i][j]) for j in range(len(x_labels))]
                for i in range(len(y_labels))
            ]
            plots.append(
                {
                    "columns": [col1, col2],
                    "one_minus_tvd": score,
                    "x_labels": x_labels,
                    "y_labels": y_labels,
                    "real": real_matrix,
                    "synthetic": syn_matrix,
                    "absolute_difference": diff_matrix,
                }
            )
        return plots

    @staticmethod
    def _top_labels_for_pair(real: pd.Series, syn: pd.Series) -> list[str]:
        counts = pd.concat([real, syn]).value_counts()
        labels = counts.head(MAX_BIVARIATE_LEVELS).index.astype(str).to_list()
        if len(counts) > len(labels):
            labels.append(OTHER_LABEL)
        return labels

    @staticmethod
    def _pair_distribution_matrix(
        x: pd.Series, y: pd.Series, x_labels: list[str], y_labels: list[str]
    ) -> list[list[float]]:
        x_norm = x.where(x.isin(x_labels), OTHER_LABEL)
        y_norm = y.where(y.isin(y_labels), OTHER_LABEL)
        counts = pd.concat([x_norm, y_norm], axis=1).value_counts(normalize=True)
        return [
            [float(counts.get((x_label, y_label), 0.0)) for x_label in x_labels]
            for y_label in y_labels
        ]

    @staticmethod
    def _build_accuracy_table(
        columns: list[str],
        univariate_scores: dict[str, float],
        bivariate_scores: dict[tuple[str, str], float],
        trivariate_scores: dict[tuple[str, str, str], float],
    ) -> list[dict[str, Any]]:
        """Per-column accuracy aggregated as Mostly does: univariate score plus
        the mean bivariate/trivariate score across every combination the column
        takes part in."""
        rows: list[dict[str, Any]] = []
        for column in columns:
            bivariate = [
                score for cols, score in bivariate_scores.items() if column in cols
            ]
            trivariate = [
                score for cols, score in trivariate_scores.items() if column in cols
            ]
            rows.append(
                {
                    "column": column,
                    "univariate": _safe_float(univariate_scores.get(column)),
                    "bivariate": _mean(bivariate),
                    "trivariate": _mean(trivariate),
                }
            )
        rows.sort(
            key=lambda item: item["univariate"] if item["univariate"] is not None else 1.0
        )
        return rows

    @staticmethod
    def _build_accuracy_matrix(
        columns: list[str],
        univariate_scores: dict[str, float],
        bivariate_scores: dict[tuple[str, str], float],
    ) -> dict[str, Any]:
        matrix_columns = columns[:MAX_MATRIX_COLUMNS]
        values: list[list[float | None]] = []
        for row_col in matrix_columns:
            row: list[float | None] = []
            for col in matrix_columns:
                if row_col == col:
                    row.append(_safe_float(univariate_scores.get(col)))
                else:
                    score = bivariate_scores.get((row_col, col))
                    if score is None:
                        score = bivariate_scores.get((col, row_col))
                    row.append(_safe_float(score))
            values.append(row)
        return {"columns": matrix_columns, "values": values}

    def _build_correlations(self, real: pd.DataFrame, syn: pd.DataFrame) -> dict[str, Any]:
        try:
            real_processed, syn_processed = self._encode_for_correlation(real, syn)
            real_corr = real_processed.corr().fillna(0.0)
            syn_corr = syn_processed.corr().fillna(0.0).reindex(
                index=real_corr.index, columns=real_corr.columns, fill_value=0.0
            )
            diff = (real_corr - syn_corr).abs()
            return {
                "real": self._matrix_payload(real_corr),
                "synthetic": self._matrix_payload(syn_corr),
                "absolute_difference": self._matrix_payload(diff),
            }
        except Exception as exc:
            logger.warning(
                "Failed to compute correlation matrices for distribution report: %s", exc
            )
            return {}

    @staticmethod
    def _encode_for_correlation(
        real: pd.DataFrame, syn: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        real_processed = pd.DataFrame(index=real.index)
        syn_processed = pd.DataFrame(index=syn.index)
        for column in real.columns:
            if (
                pd.api.types.is_numeric_dtype(real[column])
                and pd.api.types.is_numeric_dtype(syn[column])
            ):
                real_processed[column] = pd.to_numeric(real[column], errors="coerce")
                syn_processed[column] = pd.to_numeric(syn[column], errors="coerce")
                continue

            combined = pd.concat([real[column], syn[column]], ignore_index=True).astype("object")
            combined = combined.where(~combined.isna(), MISSING_LABEL).astype(str)
            categories = pd.Index(combined.unique())
            mapping = {value: idx for idx, value in enumerate(categories)}
            real_processed[column] = (
                real[column]
                .astype("object")
                .where(~real[column].isna(), MISSING_LABEL)
                .astype(str)
                .map(mapping)
            )
            syn_processed[column] = (
                syn[column]
                .astype("object")
                .where(~syn[column].isna(), MISSING_LABEL)
                .astype(str)
                .map(mapping)
            )
        return real_processed, syn_processed

    @staticmethod
    def _matrix_payload(matrix: pd.DataFrame) -> dict[str, Any]:
        columns = [str(col) for col in matrix.columns[:MAX_MATRIX_COLUMNS]]
        values = matrix.iloc[:MAX_MATRIX_COLUMNS, :MAX_MATRIX_COLUMNS].to_numpy(dtype=float)
        return {
            "columns": columns,
            "values": [[_safe_float(value) for value in row] for row in values],
        }
