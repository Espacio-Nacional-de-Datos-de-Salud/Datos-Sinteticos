from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PREVIEW_NOTICE = (
    "Vista previa con valores simulados de utilidad predictiva. "
    "No usar como resultado oficial."
)

MOCK_UTILITY_VALUES = {
    "linear_gt": 0.76,
    "linear_syn_id": 0.70,
    "linear_syn_ood": 0.64,
    "mlp_gt": 0.79,
    "mlp_syn_id": 0.73,
    "mlp_syn_ood": 0.66,
}

MOCK_UTILITY_RELATIVE_SCORE = 0.82
MOCK_UTILITY_TESTS_SCORE = 0.74


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2, allow_nan=False)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def apply_preview_overrides(data: dict[str, Any]) -> dict[str, Any]:
    metadata = data.setdefault("metadata", {})
    metadata["preview_mode"] = True
    metadata["preview_notice"] = PREVIEW_NOTICE

    summary = data.setdefault("summary", {})
    utility_summary = summary.setdefault("utility", {})
    utility_summary.update(MOCK_UTILITY_VALUES)
    utility_summary["utility_tests_score"] = utility_summary.get(
        "utility_tests_score",
        MOCK_UTILITY_TESTS_SCORE,
    )

    details = data.setdefault("details", {})
    utility_details = details.setdefault("utility", {})
    utility_metrics = utility_details.setdefault("metrics", {})
    utility_metrics.update(MOCK_UTILITY_VALUES)
    utility_metrics["utility_tests_score"] = utility_metrics.get(
        "utility_tests_score",
        utility_summary["utility_tests_score"],
    )

    utility_tests_summary = utility_details.setdefault("utility_tests_summary", {})
    if utility_tests_summary.get("score") is None:
        utility_tests_summary["score"] = utility_summary["utility_tests_score"]

    real_score = _mean([MOCK_UTILITY_VALUES["linear_gt"], MOCK_UTILITY_VALUES["mlp_gt"]])
    synthetic_score = _mean(
        [
            MOCK_UTILITY_VALUES["linear_syn_id"],
            MOCK_UTILITY_VALUES["linear_syn_ood"],
            MOCK_UTILITY_VALUES["mlp_syn_id"],
            MOCK_UTILITY_VALUES["mlp_syn_ood"],
        ]
    )

    scores = data.setdefault("scores", {})
    scores["utility_real_score"] = real_score
    scores["utility_synthetic_score"] = synthetic_score
    scores["utility_relative_score"] = MOCK_UTILITY_RELATIVE_SCORE
    scores["utility_score"] = MOCK_UTILITY_RELATIVE_SCORE

    return data


def render_preview_html(report_data: dict[str, Any], output_path: Path) -> None:
    template_path = (
        _repo_root()
        / "backend"
        / "src"
        / "domain"
        / "evaluation"
        / "reporting"
        / "templates"
        / "synthetic_eval_report_template.html"
    )
    template = template_path.read_text(encoding="utf-8")
    embedded_json = json.dumps(report_data, ensure_ascii=False, indent=2, allow_nan=False).replace(
        "</script>",
        "<\\/script>",
    )
    output_path.write_text(template.replace("__REPORT_DATA_JSON__", embedded_json), encoding="utf-8")


def generate_preview(evaluation_dir: Path) -> dict[str, Path]:
    report_data_path = evaluation_dir / "report_data.json"
    if not report_data_path.exists():
        raise FileNotFoundError(
            f"No existe {report_data_path}. Genera primero el reporte oficial."
        )

    preview_data = apply_preview_overrides(_load_json(report_data_path))

    preview_data_path = evaluation_dir / "report_data_preview.json"
    preview_html_path = evaluation_dir / "synthetic_eval_report_preview.html"

    _write_json(preview_data_path, preview_data)
    render_preview_html(preview_data, preview_html_path)

    return {
        "report_data_preview": preview_data_path,
        "html_preview": preview_html_path,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Genera una vista previa HTML con valores simulados de utilidad predictiva.",
    )
    parser.add_argument("evaluation_dir", type=Path, help="Carpeta de evaluación existente.")
    args = parser.parse_args()

    paths = generate_preview(args.evaluation_dir)
    print(paths)


if __name__ == "__main__":
    main()
