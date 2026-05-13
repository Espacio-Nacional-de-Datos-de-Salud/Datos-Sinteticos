from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


DATE_COLUMNS = {"dob", "admittime", "dischtime"}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def safe_mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None and not pd.isna(v)]
    return float(np.mean(clean)) if clean else None


def detection_score(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return max(0.0, 1 - abs(value - 0.5) / 0.5)


def build_scores(summary: dict[str, Any]) -> dict[str, float | None]:
    fidelity = summary["fidelity"]
    privacy = summary["privacy"]
    utility = summary["utility"]

    fidelity_score = safe_mean(
        [
            1 - min(fidelity["jsd"] / 0.2, 1) if fidelity["jsd"] is not None else None,
            fidelity["inv_kl"],
            fidelity["inv_tvd"],
            1 - min(fidelity["cmd"] / 1.0, 1) if fidelity["cmd"] is not None else None,
            fidelity["cio"],
        ]
    )

    privacy_score = safe_mean(
        [
            min(privacy["dcr"] / 0.5, 1) if privacy["dcr"] is not None else None,
            privacy["nndr"],
            1 - min(privacy["emr"], 1) if privacy["emr"] is not None else None,
            detection_score(privacy["detection_mlp"]),
        ]
    )

    utility_score = safe_mean(
        [
            utility["linear_syn_ood"],
            utility["mlp_syn_ood"],
            detection_score(privacy["detection_mlp"]),
        ]
    )

    global_score = safe_mean(
        [
            fidelity_score,
            privacy_score,
            utility_score,
        ]
    )

    return {
        "fidelity_score": fidelity_score,
        "privacy_score": privacy_score,
        "utility_score": utility_score,
        "global_score": global_score,
    }


def build_report_data(evaluation_dir: Path) -> dict[str, Any]:
    eval_card = load_json(evaluation_dir / "eval_card.json")
    tvd_detail = load_json(evaluation_dir / "average_complementary_tvd_report.json")
    cio_detail = load_json(evaluation_dir / "confidence_interval_overlap_report.json")
    cmd_detail = load_json(evaluation_dir / "correlation_matrix_distance_report.json")
    k_detail = load_json(evaluation_dir / "k_anonymity_report.json")

    eval_report = pd.read_csv(evaluation_dir / "eval_report.csv")
    metrics = dict(zip(eval_report["metric"], eval_report["mean"]))

    metadata = {
        "evaluation_id": eval_card.get("evaluation_id"),
        "evaluation_name": eval_card.get("evaluation_name"),
        "status": eval_card.get("status"),
        "model_id": eval_card.get("model_id"),
        "simulation_id": eval_card.get("simulation_id"),
        "pipeline_id": eval_card.get("pipeline_id"),
        "job_name": eval_card.get("job_name"),
        "timestamp": eval_card.get("timestamp"),
    }

    summary = {
        "fidelity": {
            "jsd": metrics.get("stats.jensenshannon_dist.marginal"),
            "inv_kl": metrics.get("stats.inv_kl_divergence.marginal"),
            "inv_tvd": metrics.get("average_complementary_tvd"),
            "cmd": metrics.get("correlation_matrix_distance"),
            "cio": metrics.get("confidence_interval_overlap"),
        },
        "privacy": {
            "dcr": metrics.get("dcr.syn"),
            "nndr": metrics.get("nndr.syn"),
            "k_anonymity": metrics.get("k_anonymity.syn"),
            "emr": metrics.get("sanity.common_rows_proportion.score"),
            "detection_mlp": metrics.get("detection.detection_mlp.mean"),
        },
        "utility": {
            "linear_gt": metrics.get("performance.linear_model.gt"),
            "linear_syn_id": metrics.get("performance.linear_model.syn_id"),
            "linear_syn_ood": metrics.get("performance.linear_model.syn_ood"),
            "mlp_gt": metrics.get("performance.mlp.gt"),
            "mlp_syn_id": metrics.get("performance.mlp.syn_id"),
            "mlp_syn_ood": metrics.get("performance.mlp.syn_ood"),
        },
    }

    tvd_by_column = [
        {"column": column, "complementary_tvd": value}
        for column, value in sorted(tvd_detail.items(), key=lambda x: x[1])
    ]

    cio_by_statistic = []
    for key, value in cio_detail.items():
        parts = key.split("_")
        stat = parts[-1] if parts else None
        column = parts[-2] if len(parts) >= 2 else None

        real_value = value.get("real_value")
        synthetic_value = value.get("synthetic_value")

        cio_by_statistic.append(
            {
                "key": key,
                "column": column,
                "stat": stat,
                "overlap": value.get("overlap"),
                "real_value": real_value,
                "synthetic_value": synthetic_value,
                "abs_diff": abs(real_value - synthetic_value)
                if real_value is not None and synthetic_value is not None
                else None,
                "real_ci_lower": value.get("real_ci_lower"),
                "real_ci_upper": value.get("real_ci_upper"),
                "synthetic_ci_lower": value.get("synthetic_ci_lower"),
                "synthetic_ci_upper": value.get("synthetic_ci_upper"),
            }
        )

    cmd = [{"metric": metric, "value": value} for metric, value in cmd_detail.items()]

    k_anonymity_subsets = []
    for subset_name, subset in k_detail.get("subsets", {}).items():
        columns = subset.get("columns", [])
        has_date_column = any(col in DATE_COLUMNS for col in columns)

        k_anonymity_subsets.append(
            {
                "subset": subset_name,
                "columns": ", ".join(columns),
                "has_date_column": has_date_column,
                "real_k": subset.get("real_k"),
                "syn_k": subset.get("syn_k"),
                "real_n_eq_classes": subset.get("real_eq_class_stats", {}).get("n_eq_classes"),
                "syn_n_eq_classes": subset.get("syn_eq_class_stats", {}).get("n_eq_classes"),
                "real_size_min": subset.get("real_eq_class_stats", {}).get("size_min"),
                "syn_size_min": subset.get("syn_eq_class_stats", {}).get("size_min"),
                "real_size_median": subset.get("real_eq_class_stats", {}).get("size_median"),
                "syn_size_median": subset.get("syn_eq_class_stats", {}).get("size_median"),
            }
        )

    k_anonymity_subsets = sorted(
        k_anonymity_subsets,
        key=lambda row: (
            not row["has_date_column"],
            row["syn_k"] if row["syn_k"] is not None else -1,
        ),
    )

    k_anonymity_column_granularity = []
    for column, value in k_detail.get("column_granularity", {}).items():
        k_anonymity_column_granularity.append(
            {
                "column": column,
                "real_k": value.get("real_k"),
                "syn_k": value.get("syn_k"),
                "real_n_unique": value.get("real_n_unique"),
                "syn_n_unique": value.get("syn_n_unique"),
                "is_date_column": column in DATE_COLUMNS,
            }
        )

    k_anonymity_column_granularity = sorted(
        k_anonymity_column_granularity,
        key=lambda row: (
            not row["is_date_column"],
            row["syn_k"] if row["syn_k"] is not None else -1,
        ),
    )

    time_report_path = evaluation_dir / "time_profiling_report.txt"
    time_report = time_report_path.read_text(encoding="utf-8") if time_report_path.exists() else ""

    report_data = {
        "metadata": metadata,
        "scores": build_scores(summary),
        "summary": summary,
        "details": {
            "fidelity": {
                "tvd_by_column": tvd_by_column,
                "cio_by_statistic": cio_by_statistic,
                "cmd": cmd,
            },
            "privacy": {
                "k_anonymity_subsets": k_anonymity_subsets,
                "k_anonymity_column_granularity": k_anonymity_column_granularity,
            },
            "utility": {
                "metrics": summary["utility"],
            },
            "logs": {
                "time_report": time_report,
            },
        },
    }

    return report_data


def generate_report_data_json(evaluation_dir: Path) -> Path:
    report_data = build_report_data(evaluation_dir)
    output_path = evaluation_dir / "report_data.json"

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    return output_path


def generate_report_artifacts(evaluation_dir: Path) -> dict[str, Path]:
    report_data = build_report_data(evaluation_dir)

    report_data_path = evaluation_dir / "report_data.json"
    with report_data_path.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)

    template_path = Path(__file__).parent / "templates" / "synthetic_eval_report_template.html"

    html_template = template_path.read_text(encoding="utf-8")

    embedded_json = json.dumps(report_data, ensure_ascii=False, indent=2).replace(
        "</script>", "<\\/script>"
    )

    html = html_template.replace(
        "__REPORT_DATA_JSON__",
        embedded_json,
    )

    html_path = evaluation_dir / "synthetic_eval_report.html"
    html_path.write_text(html, encoding="utf-8")

    return {
        "report_data": report_data_path,
        "html": html_path,
    }
