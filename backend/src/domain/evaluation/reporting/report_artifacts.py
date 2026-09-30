from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from backend.src.config.evaluation import TSTR_TARGET_COLUMN, TSTR_TASK_TYPE


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
MOSTLYAI_TABULAR_MODEL_TYPE = "TabularARGN"
MOSTLYAI_TABULAR_MODEL_TYPE_FULL_NAME = "Tabular Auto-Regressive Generative Network"


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


def _evaluated_table_names(evaluated_tables: Any) -> list[str] | None:
    """Normalize the card's ``evaluated_tables`` (dicts or strings) to names."""
    if not isinstance(evaluated_tables, list):
        return None
    names = [
        entry.get("table") if isinstance(entry, dict) else entry for entry in evaluated_tables
    ]
    return [name for name in names if isinstance(name, str)]


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
    return current


def safe_mean(values: list[Any]) -> float | None:
    cleaned_values = [float(value) for value in values if value is not None and not pd.isna(value)]
    if not cleaned_values:
        return None
    return float(sum(cleaned_values) / len(cleaned_values))


def _infer_model_type(
    raw_model: str | None,
    explicit_model_type: str | None = None,
) -> tuple[str | None, str | None]:
    if explicit_model_type:
        return explicit_model_type, MOSTLYAI_TABULAR_MODEL_TYPE_FULL_NAME
    if isinstance(raw_model, str) and raw_model.startswith("MOSTLY_AI/"):
        return MOSTLYAI_TABULAR_MODEL_TYPE, MOSTLYAI_TABULAR_MODEL_TYPE_FULL_NAME
    return None, None


def _empty_modeling_configuration() -> dict[str, Any]:
    return {
        "requested_modeling_mode": None,
        "applied_modeling_mode": "backend_default",
        "detected_modeling_mode": None,
        "entity_key": None,
        "time_column": None,
        "backend_supports_manual_modeling_mode": False,
        "backend_manual_config_method": "not_found",
        "backend_sequence_config_applied": False,
        "warnings": [],
    }


def _merge_modeling_configuration(
    current: dict[str, Any],
    candidate: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(candidate, dict):
        return current
    merged = current.copy()
    for key, value in candidate.items():
        if key == "warnings":
            existing = merged.get("warnings")
            existing_list = existing if isinstance(existing, list) else []
            new_list = value if isinstance(value, list) else []
            merged["warnings"] = list(dict.fromkeys([*existing_list, *new_list]))
        elif value is not None and value != "":
            merged[key] = value
    return merged


def _find_simulation_dir(evaluation_dir: Path, simulation_id: str | None) -> Path | None:
    if not simulation_id:
        return None

    outputs_dir = evaluation_dir.parent.parent
    simulation_dir = outputs_dir / "simulations" / simulation_id
    if simulation_dir.exists():
        return simulation_dir

    return None


def _find_model_dir(evaluation_dir: Path, model_id: str | None) -> Path | None:
    if not model_id:
        return None

    outputs_dir = evaluation_dir.parent.parent
    model_dir = outputs_dir / "models" / model_id
    if model_dir.exists():
        return model_dir

    return None


def _extract_training_parameters(evaluation_dir: Path, eval_card: dict[str, Any]) -> dict[str, Any]:
    """Best-effort extraction of the training parameters used by Mostly AI."""

    direct = eval_card.get("training_parameters")
    if isinstance(direct, dict) and direct:
        direct_modeling_configuration = (
            direct.get("modeling_configuration")
            if isinstance(direct.get("modeling_configuration"), dict)
            else {}
        )
        direct_parameters = {
            "model_type": direct.get("model_type"),
            "model_type_full_name": direct.get("model_type_full_name"),
            "model_size": direct.get("model_size"),
            "epsilon": direct.get("epsilon"),
            "flexible_generation": direct.get("flexible_generation"),
            "raw_model": direct.get("raw_model"),
            "modeling_mode": direct.get("modeling_mode"),
            "modeling_configuration": direct_modeling_configuration,
        }
        model_type, model_type_full_name = _infer_model_type(
            direct_parameters["raw_model"],
            direct_parameters["model_type"],
        )
        direct_parameters["model_type"] = model_type
        direct_parameters["model_type_full_name"] = (
            direct_parameters["model_type_full_name"] or model_type_full_name
        )
    else:
        direct_parameters = {}

    candidates: list[dict[str, Any]] = [eval_card]

    simulation_dir = _find_simulation_dir(evaluation_dir, eval_card.get("simulation_id"))
    if simulation_dir:
        for filename in [
            "simulation_card.json",
            "sim_card.json",
            "sim_metadata.json",
            "job_progress.json",
            "metadata.json",
            "training/model_card.json",
        ]:
            candidates.append(load_json(simulation_dir / filename))

    # The actual training settings (model type/size, flexible generation, DP)
    # live in the model directory, not the evaluation or simulation outputs.
    model_dir = _find_model_dir(evaluation_dir, eval_card.get("model_id"))
    if model_dir:
        for filename in [
            "model_card.json",
            "metadata.json",
            "configs/mostly_config.json",
            "configs/general_config.json",
        ]:
            candidates.append(load_json(model_dir / filename))

    model_settings: dict[str, Any] = {}
    differential_privacy: dict[str, Any] = {}

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

        possible_dp = (
            _deep_get(candidate, ["mostly_ai", "differential_privacy"])
            or _deep_get(candidate, ["config", "mostly_ai", "differential_privacy"])
            or _deep_get(candidate, ["differential_privacy"])
        )
        if isinstance(possible_dp, dict):
            differential_privacy.update(possible_dp)

    model_settings_dp = model_settings.get("differential_privacy") or {}
    if isinstance(model_settings_dp, dict):
        differential_privacy.update(model_settings_dp)

    model_name = model_settings.get("model")
    if isinstance(model_name, str) and "/" in model_name:
        model_size = model_name.split("/")[-1]
    else:
        model_size = model_name
    model_type, model_type_full_name = _infer_model_type(
        model_name or direct_parameters.get("raw_model"),
        direct_parameters.get("model_type") or model_settings.get("model_type"),
    )

    modeling_mode = None
    modeling_configuration = _empty_modeling_configuration()
    for candidate in candidates:
        for path in [
            ["training_parameters", "modeling_configuration"],
            ["modeling_configuration"],
            ["mostly_statistics", "modeling_configuration"],
        ]:
            modeling_configuration = _merge_modeling_configuration(
                modeling_configuration,
                _deep_get(candidate, path),
            )
        possible_mode = (
            _deep_get(candidate, ["training_parameters", "modeling_mode"])
            or _deep_get(
                candidate,
                ["training_parameters", "modeling_configuration", "detected_modeling_mode"],
            )
            or _deep_get(candidate, ["modeling_configuration", "detected_modeling_mode"])
            or _deep_get(candidate, ["detected_modeling_mode"])
            or _deep_get(candidate, ["mostly_statistics", "detected_modeling_mode"])
            or _deep_get(candidate, ["mostly_ai", "model_settings", "modeling_mode"])
            or _deep_get(candidate, ["mostly_ai", "model_settings", "requested_modeling_mode"])
            or _deep_get(candidate, ["model_settings", "modeling_mode"])
            or _deep_get(candidate, ["model_settings", "requested_modeling_mode"])
        )
        if isinstance(possible_mode, str) and possible_mode:
            modeling_mode = possible_mode

    direct_modeling_configuration = direct_parameters.get("modeling_configuration")
    if isinstance(direct_modeling_configuration, dict):
        modeling_configuration = _merge_modeling_configuration(
            modeling_configuration, direct_modeling_configuration
        )

    if modeling_mode and not modeling_configuration.get("detected_modeling_mode"):
        modeling_configuration["detected_modeling_mode"] = modeling_mode

    epsilon = differential_privacy.get(
        "max_epsilon",
        differential_privacy.get("epsilon", direct_parameters.get("epsilon")),
    )

    return {
        "model_type": model_type or direct_parameters.get("model_type"),
        "model_type_full_name": model_type_full_name
        or direct_parameters.get("model_type_full_name"),
        "model_size": model_size or direct_parameters.get("model_size"),
        "epsilon": epsilon,
        "flexible_generation": model_settings.get(
            "enable_flexible_generation", direct_parameters.get("flexible_generation")
        ),
        "raw_model": model_name or direct_parameters.get("raw_model"),
        "modeling_mode": modeling_mode,
        "modeling_configuration": modeling_configuration,
    }


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


def l_diversity_component_score(real_l: float | None, syn_l: float | None) -> float | None:
    if syn_l is None or pd.isna(syn_l):
        return None

    absolute_score = max(0.0, min(float(syn_l) / 3.0, 1.0))
    relative_score = bounded_ratio(syn_l, real_l)
    if relative_score is None:
        return absolute_score
    return min(absolute_score, relative_score)


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


def _as_finite_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(number) or math.isinf(number):
        return None
    return number


def _is_std_narrative_note(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    return value.startswith(
        (
            "La desviación estándar sintética",
            "La dispersión sintética",
            "La desviación estándar real",
            "No hay suficiente información numérica",
        )
    )


def _enrich_utility_tests_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue

        enriched = row.copy()
        context = row.get("context")
        context = context if isinstance(context, dict) else {}
        if context:
            context = context.copy()
            if _is_std_narrative_note(context.get("note")):
                context.pop("note", None)
            enriched["context"] = context

        real_std = _as_finite_number(enriched.get("real_std", context.get("real_std")))
        synthetic_std = _as_finite_number(
            enriched.get("synthetic_std", context.get("synthetic_std"))
        )
        std_delta = _as_finite_number(enriched.get("std_delta"))
        if std_delta is None and real_std is not None and synthetic_std is not None:
            std_delta = synthetic_std - real_std

        std_relative_delta = _as_finite_number(enriched.get("std_relative_delta"))
        if (
            std_relative_delta is None
            and std_delta is not None
            and real_std is not None
            and real_std != 0
        ):
            std_relative_delta = std_delta / real_std

        enriched["real_std"] = real_std
        enriched["synthetic_std"] = synthetic_std
        enriched["std_delta"] = std_delta
        enriched["std_relative_delta"] = std_relative_delta
        enriched_rows.append(enriched)

    return enriched_rows


def _extract_exact_match_rows_summary(detail: dict[str, Any]) -> dict[str, Any]:
    full_match = detail.get("full_match") if isinstance(detail, dict) else {}
    full_match = full_match if isinstance(full_match, dict) else {}
    leave_one_out = detail.get("leave_one_out") if isinstance(detail, dict) else {}
    leave_one_out = leave_one_out if isinstance(leave_one_out, dict) else {}

    loo_rows = []
    full_count = _as_finite_number(full_match.get("count")) or 0
    for excluded_column, payload in leave_one_out.items():
        if not isinstance(payload, dict):
            continue
        count = _as_finite_number(payload.get("count")) or 0
        proportion = _as_finite_number(payload.get("proportion"))
        loo_rows.append(
            {
                "excluded_column": excluded_column,
                "count": count,
                "proportion": proportion,
                "extra_matches": max(0, count - full_count),
            }
        )

    loo_rows = sorted(
        loo_rows,
        key=lambda row: (-(row["extra_matches"] or 0), row["excluded_column"]),
    )
    rows_preview = full_match.get("rows", [])
    n_rows_preview = len(rows_preview) if isinstance(rows_preview, list) else 0
    return {
        "count": full_count,
        "proportion": _as_finite_number(full_match.get("proportion")),
        "n_rows_preview": n_rows_preview,
        "leave_one_out": loo_rows,
    }


def _extract_l_diversity_rows(detail: dict[str, Any]) -> list[dict[str, Any]]:
    subsets = detail.get("subsets") if isinstance(detail, dict) else {}
    if not isinstance(subsets, dict):
        return []

    rows = []
    for subset_name, subset in subsets.items():
        if not isinstance(subset, dict):
            continue
        real_l = _as_finite_number(subset.get("real_l"))
        syn_l = _as_finite_number(subset.get("syn_l"))
        rows.append(
            {
                "subset": subset_name,
                "columns": ", ".join(subset.get("columns", [])),
                "sensitive_columns": ", ".join(subset.get("sensitive_columns", [])),
                "real_l": real_l,
                "syn_l": syn_l,
                "l_gap": syn_l - real_l if real_l is not None and syn_l is not None else None,
                "risk": l_diversity_risk(syn_l),
                "sensitive_column_scores": subset.get("sensitive_column_scores", {}),
            }
        )

    return sorted(
        rows,
        key=lambda row: (
            row["syn_l"] if row["syn_l"] is not None else float("inf"),
            row["subset"],
        ),
    )


def k_anonymity_risk(syn_k: float | None) -> str:
    if syn_k is None or pd.isna(syn_k):
        return "desconocido"
    if syn_k <= 1:
        return "alto"
    if syn_k < 5:
        return "medio"
    return "bajo"


def l_diversity_risk(syn_l: float | None) -> str:
    if syn_l is None or pd.isna(syn_l):
        return "desconocido"
    if syn_l <= 1:
        return "alto"
    if syn_l < 3:
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
            privacy.get("l_diversity_score"),
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
            utility["mlp_syn_id"],
        ]
    )
    utility_relative_score = bounded_ratio(utility_synthetic_score, utility_real_score)

    # The Utilidad badge combines both available facets: predictive (TSTR
    # relative performance) and statistical (user-defined utility tests). When
    # both are present it is their mean; when only one is available the badge
    # shows that one and ``utility_source`` tells the UI which facet it reflects
    # so it can label the value accordingly.
    utility_tests_score = utility.get("utility_tests_score")
    has_predictive = utility_relative_score is not None and not pd.isna(utility_relative_score)
    has_statistical = utility_tests_score is not None and not pd.isna(utility_tests_score)
    if has_predictive and has_statistical:
        utility_source = "both"
    elif has_predictive:
        utility_source = "predictive"
    elif has_statistical:
        utility_source = "statistical"
    else:
        utility_source = "none"
    utility_score = safe_mean([utility_relative_score, utility_tests_score])

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
        "l_diversity_score": privacy.get("l_diversity_score"),
        "privacy_penalty": privacy_penalty,
        "privacy_score": privacy_score,
        "utility_real_score": utility_real_score,
        "utility_synthetic_score": utility_synthetic_score,
        "utility_relative_score": utility_relative_score,
        "utility_tests_score": utility_tests_score,
        "utility_source": utility_source,
        "utility_score": utility_score,
        "global_score": global_score,
    }


def build_report_data(
    evaluation_dir: Path,
    eval_card: dict[str, Any] | None = None,
    evaluated_table: str | None = None,
    base_dir: Path | None = None,
    evaluation_parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the structured report payload.

    Args:
        evaluation_dir: Directory holding the metric artifacts (``eval_report.csv``,
            ``*_report.json``). For multi-table runs this is ``tables/<table>/``.
        eval_card: Pre-loaded ``eval_card.json``. Loaded from ``evaluation_dir``
            when omitted (legacy flat layout).
        evaluated_table: Name of the single table this report covers.
        base_dir: Evaluation root used to locate the parent simulation/model
            directories for training-parameter extraction. Defaults to
            ``evaluation_dir`` (legacy flat layout).
        evaluation_parameters: Per-table TSTR parameters (target/task) for this
            report. Falls back to the card's global parameters when omitted.
    """
    base_dir = base_dir or evaluation_dir
    if eval_card is None:
        eval_card = load_json(evaluation_dir / "eval_card.json")
    cmd_detail = load_json(evaluation_dir / "correlation_matrix_distance_report.json")
    k_detail = load_json(evaluation_dir / "k_anonymity_report.json")
    l_diversity_detail = load_json(evaluation_dir / "l_diversity_report.json") or load_json(
        evaluation_dir / "l_diversity_pycanon_report.json"
    )
    exact_match_detail = load_json(evaluation_dir / "exact_match_rows_report.json")
    distribution_detail = load_json(evaluation_dir / "1_tvd_report.json")
    utility_tests_detail = load_json(evaluation_dir / "utility_tests_report.json")

    eval_report = pd.read_csv(evaluation_dir / "eval_report.csv")
    metrics = dict(zip(eval_report["metric"], eval_report["mean"], strict=False))

    training_parameters = _extract_training_parameters(base_dir, eval_card)
    exact_emr = metrics.get("exact_match_rows")
    fallback_emr = metrics.get("sanity.common_rows_proportion.score")
    emr_value = exact_emr if exact_emr is not None and not pd.isna(exact_emr) else fallback_emr
    emr_source = (
        "exact_match_rows"
        if exact_emr is not None and not pd.isna(exact_emr)
        else "common_rows_proportion"
    )

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
        "evaluation_parameters": {
            **(
                evaluation_parameters
                or eval_card.get("evaluation_parameters")
                or {"target_column": TSTR_TARGET_COLUMN, "task_type": TSTR_TASK_TYPE}
            ),
            "evaluated_table": evaluated_table,
            "evaluated_tables": _evaluated_table_names(eval_card.get("evaluated_tables")),
        },
    }

    summary = {
        "fidelity": {
            "jsd": metrics.get("stats.jensenshannon_dist.marginal"),
            "inv_kl": metrics.get("stats.inv_kl_divergence.marginal"),
            "inv_tvd": metrics.get("1_tvd.univariate"),
            "cmd": metrics.get("correlation_matrix_distance"),
        },
        "privacy": {
            "dcr": metrics.get("dcr.syn"),
            "nndr": metrics.get("nndr.syn"),
            "k_anonymity": metrics.get("k_anonymity.syn"),
            "l_diversity_real": metrics.get("l_diversity.real"),
            "l_diversity_syn": metrics.get("l_diversity.syn"),
            "l_diversity_score": l_diversity_component_score(
                metrics.get("l_diversity.real"),
                metrics.get("l_diversity.syn"),
            ),
            "emr": emr_value,
            "emr_source": emr_source,
            "detection_mlp": metrics.get("detection.detection_mlp.mean"),
        },
        "utility": {
            "linear_gt": metrics.get("performance.linear_model.gt"),
            "linear_syn_id": metrics.get("performance.linear_model.syn_id"),
            "mlp_gt": metrics.get("performance.mlp.gt"),
            "mlp_syn_id": metrics.get("performance.mlp.syn_id"),
            "utility_tests_score": metrics.get("utility_tests"),
        },
    }

    univariate_tvd = distribution_detail.get("scores", {}).get("univariate", {})
    tvd_by_column = [
        {"column": column, "complementary_tvd": value}
        for column, value in sorted(univariate_tvd.items(), key=lambda x: x[1])
    ]

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

    exact_match_summary = _extract_exact_match_rows_summary(exact_match_detail)
    l_diversity_rows = _extract_l_diversity_rows(l_diversity_detail)
    l_diversity_summary = {
        "real_l": summary["privacy"].get("l_diversity_real"),
        "syn_l": summary["privacy"].get("l_diversity_syn"),
        "n_subsets": len(l_diversity_rows),
        "skipped": l_diversity_detail.get("skipped"),
        "skip_reason": l_diversity_detail.get("skip_reason"),
    }

    time_report = _load_time_report_text(evaluation_dir)
    utility_tests_rows = _enrich_utility_tests_rows(utility_tests_detail.get("tests", []))
    utility_tests_for_report = {
        **utility_tests_detail,
        "tests": utility_tests_rows,
    }

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
                "exact_match_rows": exact_match_detail,
                "exact_match_summary": exact_match_summary,
                "l_diversity": l_diversity_detail,
                "l_diversity_summary": l_diversity_summary,
                "l_diversity_subsets": l_diversity_rows,
            },
            "utility": {
                "metrics": summary["utility"],
                "utility_tests": utility_tests_for_report,
                "utility_tests_summary": utility_tests_detail.get("summary", {}),
                "utility_tests_rows": utility_tests_rows,
                "utility_tests_config": utility_tests_detail.get("config", {}),
            },
            "logs": {
                "time_report": time_report,
            },
        },
    }

    return report_data


def generate_report_data_json(
    evaluation_dir: Path,
    eval_card: dict[str, Any] | None = None,
    evaluated_table: str | None = None,
    base_dir: Path | None = None,
    evaluation_parameters: dict[str, Any] | None = None,
) -> Path:
    report_data = _json_sanitize(
        build_report_data(
            evaluation_dir, eval_card, evaluated_table, base_dir, evaluation_parameters
        )
    )
    output_path = evaluation_dir / "report_data.json"

    with output_path.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False, allow_nan=False)

    return output_path


def _write_report_files(output_dir: Path, report_data: dict[str, Any]) -> dict[str, Path]:
    """Persist ``report_data.json`` and the self-contained HTML report.

    The HTML template embeds the JSON inline (placeholder ``__REPORT_DATA_JSON__``)
    so the report renders without a separate fetch.
    """
    report_data_path = output_dir / "report_data.json"
    with report_data_path.open("w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False, allow_nan=False)

    template_path = Path(__file__).parent / "templates" / "synthetic_eval_report_template.html"
    html_template = template_path.read_text(encoding="utf-8")

    embedded_json = json.dumps(report_data, ensure_ascii=False, indent=2, allow_nan=False).replace(
        "</script>", "<\\/script>"
    )
    html = html_template.replace("__REPORT_DATA_JSON__", embedded_json)

    html_path = output_dir / "synthetic_eval_report.html"
    html_path.write_text(html, encoding="utf-8")

    return {"report_data": report_data_path, "html": html_path}


def generate_report_artifacts(
    evaluation_dir: Path,
    eval_card: dict[str, Any] | None = None,
    evaluated_table: str | None = None,
    base_dir: Path | None = None,
    evaluation_parameters: dict[str, Any] | None = None,
) -> dict[str, Path]:
    report_data = _json_sanitize(
        build_report_data(
            evaluation_dir, eval_card, evaluated_table, base_dir, evaluation_parameters
        )
    )
    return _write_report_files(evaluation_dir, report_data)


def _mean_merge(dicts: list[dict[str, Any]]) -> dict[str, Any]:
    """Recursively merge structurally-identical dicts, averaging numeric leaves.

    Numeric leaves become the mean of the present (non-null) values across
    ``dicts``; nested dicts recurse; booleans and non-numeric values fall back to
    the first present value. Keys missing everywhere yield ``None``.
    """
    keys: list[str] = []
    for d in dicts:
        for key in d:
            if key not in keys:
                keys.append(key)

    out: dict[str, Any] = {}
    for key in keys:
        present = [d[key] for d in dicts if isinstance(d, dict) and key in d]
        non_null = [v for v in present if v is not None]
        if not non_null:
            out[key] = None
        elif all(isinstance(v, dict) for v in non_null):
            out[key] = _mean_merge(non_null)
        elif all(isinstance(v, bool) for v in non_null):
            out[key] = non_null[0]
        elif all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in non_null):
            out[key] = float(sum(non_null) / len(non_null))
        else:
            out[key] = non_null[0]
    return out


def build_combined_report_data(
    per_table: dict[str, dict[str, Any]],
    base_dir: Path,
) -> dict[str, Any]:
    """Build the unified multi-table report payload.

    The headline ``scores`` and ``summary`` are the per-axis mean across every
    evaluated table; ``tables`` carries each table's full report data so the
    HTML report can switch the per-metric detail by table via a dropdown.
    """
    tables = list(per_table.keys())
    score_list = [rd.get("scores", {}) for rd in per_table.values()]
    summary_list = [rd.get("summary", {}) for rd in per_table.values()]

    combined_scores = _mean_merge(score_list)
    # utility_source is categorical, not numeric: derive it from which facets any
    # table contributed instead of averaging the string.
    has_predictive = any(s.get("utility_relative_score") is not None for s in score_list)
    has_statistical = any(s.get("utility_tests_score") is not None for s in score_list)
    combined_scores["utility_source"] = (
        "both"
        if has_predictive and has_statistical
        else "predictive"
        if has_predictive
        else "statistical"
        if has_statistical
        else "none"
    )

    first_metadata = next(iter(per_table.values())).get("metadata", {}) if per_table else {}
    metadata = {**first_metadata}
    eval_params = {**(metadata.get("evaluation_parameters") or {})}
    eval_params["evaluated_table"] = None
    eval_params["evaluated_tables"] = tables
    metadata["evaluation_parameters"] = eval_params

    return {
        "metadata": metadata,
        "scores": combined_scores,
        "summary": _mean_merge(summary_list),
        "details": {"logs": {"time_report": _load_time_report_text(base_dir)}},
        "tables": per_table,
        "table_order": tables,
    }


def generate_combined_report_artifacts(
    base_dir: Path,
    per_table: dict[str, dict[str, Any]],
) -> dict[str, Path]:
    """Write the single unified report (HTML + JSON) at the evaluation root."""
    report_data = _json_sanitize(build_combined_report_data(per_table, base_dir))
    return _write_report_files(base_dir, report_data)
