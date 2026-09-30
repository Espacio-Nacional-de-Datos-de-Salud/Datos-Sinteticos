from __future__ import annotations

import pandas as pd

from backend.src.domain.evaluation.custom_metrics.base import MetricEvaluator
from backend.src.domain.evaluation.utils import align_datasets_structure_and_types, normalize_for_exact_match


def test_align_datasets_preserves_relational_table_names() -> None:
    real = {
        "tabla_personas_mod": pd.DataFrame(
            {"id_per": [1, 2], "SEXO": [1, 2], "ANIO_NAC": [1980, 1990]}
        ),
        "tabla_visitas_mod": pd.DataFrame(
            {
                "id_visita": [10, 11],
                "id_per": [1, 2],
                "FECHA_VISITA": ["2024-01-01", "2024-01-02"],
            }
        ),
    }
    synthetic = {
        "tabla_personas_mod_synthetic": pd.DataFrame(
            {"id_per": [3], "SEXO": [1], "ANIO_NAC": [1985], "extra": ["ignored"]}
        ),
        "tabla_visitas_mod_synthetic": pd.DataFrame(
            {"id_visita": [12], "id_per": [3], "FECHA_VISITA": ["2024-01-03"]}
        ),
    }

    aligned_real, aligned_synthetic = align_datasets_structure_and_types(
        real, synthetic
    )

    assert list(aligned_real) == ["tabla_personas_mod", "tabla_visitas_mod"]
    assert list(aligned_synthetic) == ["tabla_personas_mod", "tabla_visitas_mod"]
    assert list(aligned_real["tabla_personas_mod"].columns) == [
        "id_per",
        "SEXO",
        "ANIO_NAC",
    ]
    assert list(aligned_synthetic["tabla_personas_mod"].columns) == [
        "id_per",
        "SEXO",
        "ANIO_NAC",
    ]


def test_expensive_metric_sampling_is_deterministic(monkeypatch) -> None:
    import backend.src.domain.evaluation.custom_metrics.base as base_module

    monkeypatch.setattr(base_module, "MAX_ROWS_PER_TABLE_FOR_EXPENSIVE_METRICS", 3)
    monkeypatch.setattr(base_module, "EXPENSIVE_METRICS_RANDOM_STATE", 7)

    real = pd.DataFrame({"x": range(10)})
    synthetic = pd.DataFrame({"x": range(20)})

    sampled_real, sampled_synthetic = MetricEvaluator()._sample_for_expensive_metric(
        real, synthetic
    )

    assert len(sampled_real) == 3
    assert len(sampled_synthetic) == 3
    assert sampled_real["x"].tolist() == [8, 5, 0]
    assert sampled_synthetic["x"].tolist() == [1, 17, 2]


def test_normalize_for_exact_match_converts_booleans_to_canonical_form() -> None:
    real = pd.DataFrame({"EXPIRE_FLAG": [True, False, True], "id": [1, 2, 3]})
    synthetic = pd.DataFrame({"EXPIRE_FLAG": [1, 0, 1], "id": [1, 2, 3]})

    norm_real, norm_syn = normalize_for_exact_match(real, synthetic)

    assert norm_real["EXPIRE_FLAG"].dtype == "Int64"
    assert norm_syn["EXPIRE_FLAG"].dtype == "Int64"
    assert norm_real["EXPIRE_FLAG"].tolist() == [1, 0, 1]
    assert norm_syn["EXPIRE_FLAG"].tolist() == [1, 0, 1]
    assert norm_real["id"].tolist() == [1, 2, 3]
    assert norm_syn["id"].tolist() == [1, 2, 3]


def test_normalize_for_exact_match_handles_string_booleans() -> None:
    real = pd.DataFrame({"flag": ["true", "false", "True", "FALSE"]})
    synthetic = pd.DataFrame({"flag": [1, 0, 1, 0]})

    norm_real, norm_syn = normalize_for_exact_match(real, synthetic)

    assert norm_real["flag"].tolist() == [1, 0, 1, 0]
    assert norm_syn["flag"].tolist() == [1, 0, 1, 0]
