from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


def _json_sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _json_sanitize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_sanitize(v) for v in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, np.floating):
        f = float(value)
        return None if math.isnan(f) or math.isinf(f) else f
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.bool_):
        return bool(value)
    return value


DATE_COLUMNS = {"dob", "admittime", "dischtime"}


def _load_time_report_text(evaluation_dir: Path) -> str:
    """Read the JSON time-profiling report and render it as the legacy text table.

    The HTML evaluation report embeds this string as plain text inside a <pre>-style
    block. Keeping the text format here means the template needs no changes.
    """
    from backend.src.infrastructure.time_profiling import Profiler

    json_path = evaluation_dir / "time_profiling_report.json"
    if not json_path.exists():
        return ""
    try:
        with json_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return ""
    if not payload.get("phases"):
        note = payload.get("note") or "Sin fases registradas."
        return f"{payload.get('header', 'Timing breakdown')}:\n  {note}"
    return Profiler._format_text(payload)


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _deep_get(mapping: dict[str, Any], path: list[str], default: Any = None) -> Any:
    current: Any = mapping
    for key in path:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
    return default


def _find_simulation_dir(evaluation_dir: Path, simulation_id: str | None) -> Path | None:
    if not simulation_id:
        return None

    outputs_dir = evaluation_dir.parent.parent
    simulation_dir = outputs_dir / "simulations" / simulation_id
    if simulation_dir.exists():
        return simulation_dir

    return None


def _extract_training_parameters(evaluation_dir: Path, eval_card: dict[str, Any]) -> dict[str, Any]:
    """Best-effort extraction of the training parameters used by Mostly AI."""

    direct = eval_card.get("training_parameters")
    if isinstance(direct, dict) and direct:
        return {
            "model_size": direct.get("model_size"),
            "epsilon": direct.get("epsilon"),
            "flexible_generation": direct.get("flexible_generation"),
            "raw_model": direct.get("raw_model"),
        }

    candidates: list[dict[str, Any]] = [eval_card]

    simulation_dir = _find_simulation_dir(evaluation_dir, eval_card.get("simulation_id"))
    if simulation_dir:
        for filename in [
            "simulation_card.json",
            "sim_metadata.json",
            "job_progress.json",
            "metadata.json",
        ]:
            candidates.append(load_json(simulation_dir / filename))

    model_settings: dict[str, Any] = {}

    for candidate in candidates:
        possible = (
            _deep_get(candidate, ["mostly_ai", "model_settings"])
            or _deep_get(candidate, ["config", "mostly_ai", "model_settings"])
            or _deep_get(candidate, ["model_settings"])
            or _deep_get(candidate, ["training", "model_settings"])
            or _deep_get(candidate, ["training_parameters", "model_settings"])
        )

        if isinstance(possible, dict):
            model_settings.update(possible)

    differential_privacy = model_settings.get("differential_privacy") or {}

    model_name = model_settings.get("model")
    if isinstance(model_name, str) and "/" in model_name:
        model_size = model_name.split("/")[-1]
    else:
        model_size = model_name

    epsilon = (
        differential_privacy.get("max_epsilon") if isinstance(differential_privacy, dict) else None
    )

    return {
        "model_size": model_size,
        "epsilon": epsilon,
        "flexible_generation": model_settings.get("enable_flexible_generation"),
        "raw_model": model_name,
    }


def safe_mean(values: list[float | None]) -> float | None:
    clean = [v for v in values if v is not None and not pd.isna(v)]
    return float(np.mean(clean)) if clean else None


def detection_score(value: float | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return max(0.0, 1 - abs(value - 0.5) / 0.5)


def bounded_ratio(numerator: float | None, denominator: float | None) -> float | None:
    if (
        numerator is None
        or denominator is None
        or pd.isna(numerator)
        or pd.isna(denominator)
        or denominator <= 0
    ):
        return None
    return max(0.0, min(float(numerator) / float(denominator), 1.0))


def privacy_penalty_score(k_anonymity: float | None) -> float:
    if k_anonymity is None or pd.isna(k_anonymity):
        return 0.0
    normalized_k = max(0.0, min(float(k_anonymity) / 5.0, 1.0))
    return (1.0 - normalized_k) * 0.2


def privacy_penalty_from_subsets(rows: list[dict[str, Any]]) -> float:
    if not rows:
        return 0.0

    problematic = [row for row in rows if (row.get("k_deficit") or 0) > 0]
    if not problematic:
        return 0.0

    affected_share = len(problematic) / len(rows)
    deficit_severity = safe_mean(
        [
            min((row.get("k_deficit") or 0) / max(float(row.get("real_k") or 1), 1.0), 1.0)
            for row in problematic
        ]
    )
    return min(0.2, 0.1 * affected_share + 0.1 * (deficit_severity or 0.0))


def k_anonymity_risk(syn_k: float | None) -> str:
    if syn_k is None or pd.isna(syn_k):
        return "desconocido"
    if syn_k <= 1:
        return "alto"
    if syn_k < 5:
        return "medio"
    return "bajo"


def build_scores(
    summary: dict[str, Any],
    privacy_penalty: float | None = None,
) -> dict[str, float | None]:
    fidelity = summary["fidelity"]
    privacy = summary["privacy"]
    utility = summary["utility"]

    fidelity_distribution_score = safe_mean(
        [
            1 - min(fidelity["jsd"] / 0.2, 1) if fidelity["jsd"] is not None else None,
            fidelity["inv_kl"],
            fidelity["inv_tvd"],
            fidelity["cio"],
        ]
    )
    fidelity_structure_score = safe_mean(
        [
            1 - min(fidelity["cmd"] / 1.0, 1) if fidelity["cmd"] is not None else None,
        ]
    )
    fidelity_score = safe_mean(
        [
            fidelity_distribution_score,
            fidelity_structure_score,
        ]
    )

    privacy_base_score = safe_mean(
        [
            min(privacy["dcr"] / 0.5, 1) if privacy["dcr"] is not None else None,
            privacy["nndr"],
            1 - min(privacy["emr"], 1) if privacy["emr"] is not None else None,
            detection_score(privacy["detection_mlp"]),
        ]
    )
    if privacy_penalty is None:
        privacy_penalty = privacy_penalty_score(privacy["k_anonymity"])
    privacy_score = (
        max(0.0, privacy_base_score - privacy_penalty) if privacy_base_score is not None else None
    )

    utility_real_score = safe_mean(
        [
            utility["linear_gt"],
            utility["mlp_gt"],
        ]
    )
    utility_synthetic_score = safe_mean(
        [
            utility["linear_syn_id"],
            utility["linear_syn_ood"],
            utility["mlp_syn_id"],
            utility["mlp_syn_ood"],
        ]
    )
    utility_relative_score = bounded_ratio(utility_synthetic_score, utility_real_score)
    utility_score = utility_relative_score

    global_score = safe_mean(
        [
            fidelity_score,
            privacy_score,
        ]
    )

    return {
        "fidelity_score": fidelity_score,
        "fidelity_distribution_score": fidelity_distribution_score,
        "fidelity_structure_score": fidelity_structure_score,
        "privacy_base_score": privacy_base_score,
        "privacy_penalty": privacy_penalty,
        "privacy_score": privacy_score,
        "utility_real_score": utility_real_score,
        "utility_synthetic_score": utility_synthetic_score,
        "utility_relative_score": utility_relative_score,
        "utility_score": utility_score,
        "global_score": global_score,
    }


def build_report_data(evaluation_dir: Path) -> dict[str, Any]:
    eval_card = load_json(evaluation_dir / "eval_card.json")
    cio_detail = load_json(evaluation_dir / "confidence_interval_overlap_report.json")
    cmd_detail = load_json(evaluation_dir / "correlation_matrix_distance_report.json")
    k_detail = load_json(evaluation_dir / "k_anonymity_report.json")
    distribution_detail = load_json(evaluation_dir / "1_tvd_report.json")
    utility_tests_detail = load_json(evaluation_dir / "utility_tests_report.json")

    eval_report = pd.read_csv(evaluation_dir / "eval_report.csv")
    metrics = dict(zip(eval_report["metric"], eval_report["mean"]))

    training_parameters = _extract_training_parameters(evaluation_dir, eval_card)

    metadata = {
        "evaluation_id": eval_card.get("evaluation_id"),
        "evaluation_name": eval_card.get("evaluation_name"),
        "status": eval_card.get("status"),
        "model_id": eval_card.get("model_id"),
        "simulation_id": eval_card.get("simulation_id"),
        "pipeline_id": eval_card.get("pipeline_id"),
        "job_name": eval_card.get("job_name"),
        "timestamp": eval_card.get("timestamp"),
        "training_parameters": training_parameters,
    }

    summary = {
        "fidelity": {
            "jsd": metrics.get("stats.jensenshannon_dist.marginal"),
            "inv_kl": metrics.get("stats.inv_kl_divergence.marginal"),
            "inv_tvd": metrics.get("1_tvd.univariate"),
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
            "utility_tests_score": metrics.get("utility_tests"),
        },
    }

    univariate_tvd = distribution_detail.get("scores", {}).get("univariate", {})
    tvd_by_column = [
        {"column": column, "complementary_tvd": value}
        for column, value in sorted(univariate_tvd.items(), key=lambda x: x[1])
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

    k_anonymity_problem_subsets = []
    for row in k_anonymity_subsets:
        real_k = row["real_k"]
        syn_k = row["syn_k"]
        k_gap = (
            syn_k - real_k
            if real_k is not None
            and syn_k is not None
            and not pd.isna(real_k)
            and not pd.isna(syn_k)
            else None
        )
        k_deficit = max(0, -k_gap) if k_gap is not None else None
        k_anonymity_problem_subsets.append(
            {
                **row,
                "k_gap": k_gap,
                "k_deficit": k_deficit,
                "risk": k_anonymity_risk(syn_k),
            }
        )

    privacy_penalty = privacy_penalty_from_subsets(k_anonymity_problem_subsets)
    k_anonymity_problem_subsets = sorted(
        k_anonymity_problem_subsets,
        key=lambda row: (
            row["syn_k"] if row["syn_k"] is not None else float("inf"),
            -(row["k_deficit"] or 0),
            not row["has_date_column"],
        ),
    )[:8]

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

    time_report = _load_time_report_text(evaluation_dir)

    report_data = {
        "metadata": metadata,
        "scores": build_scores(
            summary,
            privacy_penalty=privacy_penalty,
        ),
        "summary": summary,
        "details": {
            "fidelity": {
                "tvd_by_column": tvd_by_column,
                "cio_by_statistic": cio_by_statistic,
                "cmd": cmd,
                "distribution_comparison": distribution_detail,
                "correlation_matrices": distribution_detail.get("correlations", {}),
                "correlation_difference_matrix": distribution_detail.get("correlations", {}).get(
                    "absolute_difference"
                ),
            },
            "privacy": {
                "k_anonymity_problem_subsets": k_anonymity_problem_subsets,
                "k_anonymity_subsets": k_anonymity_subsets,
                "k_anonymity_column_granularity": k_anonymity_column_granularity,
            },
            "utility": {
                "metrics": summary["utility"],
                "utility_tests": utility_tests_detail,
                "utility_tests_summary": utility_tests_detail.get("summary", {}),
                "utility_tests_rows": utility_tests_detail.get("tests", []),
                "utility_tests_config": utility_tests_detail.get("config", {}),
            },
            "logs": {
                "time_report": time_report,
            },
        },
    }

    return report_data


def generate_report_data_json(evaluation_dir: Path) -> Path:
    report_data = _json_sanitize(build_report_data(evaluation_dir))
    output_path = evaluation_dir / "report_data.json"

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False, allow_nan=False)

    return output_path


def generate_report_artifacts(evaluation_dir: Path) -> dict[str, Path]:
    report_data = _json_sanitize(build_report_data(evaluation_dir))

    report_data_path = evaluation_dir / "report_data.json"
    with report_data_path.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False, allow_nan=False)

    template_path = Path(__file__).parent / "templates" / "synthetic_eval_report_template.html"

    html_template = template_path.read_text(encoding="utf-8")

    embedded_json = json.dumps(report_data, ensure_ascii=False, indent=2, allow_nan=False).replace(
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
