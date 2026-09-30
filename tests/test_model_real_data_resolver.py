"""Regression tests for the post-preprocess real-data source of truth.

The model's column dropdown reads from the inspection metadata (which includes
columns derived by logical rules), so the values endpoint must read from the
same preprocessed dataset — not the raw upload, where a column like
``is_adult`` doesn't yet exist. These tests pin that contract and the matching
auto-bind behavior of ``resolve_simulation_inputs``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from backend.src.config.general import (
    MODEL_CARD_FILENAME,
    PROCESSED_DATA_DIRNAME,
    SIM_CARD_FILENAME,
)
from backend.src.infrastructure.errors import ModelNotFoundError
from backend.src.runs.catalog import models as models_catalog
from backend.src.runs.catalog import simulations as simulations_catalog


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _scaffold_model_and_inspection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    raw_columns: list[str],
    processed_columns: list[str],
    table_name: str = "patients",
    use_model_local_processed: bool = False,
) -> tuple[str, Path]:
    """Lay out a fake models/inspections tree and patch the catalog dirs."""
    models_dir = tmp_path / "models"
    inspections_dir = tmp_path / "inspections"
    model_id = "model_20260101_120000"
    inspection_id = "inspection_20260101_115959"

    raw_csv = tmp_path / "raw" / f"{table_name}.csv"
    raw_csv.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({col: [1, 2, 3] for col in raw_columns}).to_csv(raw_csv, index=False)

    model_dir = models_dir / model_id
    model_dir.mkdir(parents=True)
    _write_json(
        model_dir / MODEL_CARD_FILENAME,
        {
            "model_id": model_id,
            "inspection_id": inspection_id,
            "data_sources": [{"path": str(raw_csv)}],
        },
    )

    processed_target = (
        model_dir / PROCESSED_DATA_DIRNAME
        if use_model_local_processed
        else inspections_dir / inspection_id / PROCESSED_DATA_DIRNAME
    )
    processed_target.mkdir(parents=True)
    pd.DataFrame(
        {col: [10, 20, 30] for col in processed_columns}
    ).to_parquet(processed_target / f"{table_name}.parquet")

    monkeypatch.setattr(models_catalog, "MODELS_DIR", str(models_dir))
    monkeypatch.setattr(simulations_catalog, "MODELS_DIR", str(models_dir))
    monkeypatch.setattr(simulations_catalog, "INSPECTIONS_DIR", str(inspections_dir))

    return model_id, processed_target


def test_resolve_prefers_inspection_processed_over_raw(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_id, processed_dir = _scaffold_model_and_inspection(
        tmp_path,
        monkeypatch,
        raw_columns=["age"],
        processed_columns=["age", "is_adult"],
    )

    resolved = models_catalog.resolve_model_real_data_paths(model_id)

    assert resolved == [str(processed_dir / "patients.parquet")]


def test_resolve_prefers_model_local_processed_over_inspection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Set up the inspection copy first, then add a model-local copy that wins.
    model_id, _inspection_processed = _scaffold_model_and_inspection(
        tmp_path,
        monkeypatch,
        raw_columns=["age"],
        processed_columns=["age", "is_adult"],
    )
    model_processed = tmp_path / "models" / model_id / PROCESSED_DATA_DIRNAME
    model_processed.mkdir(parents=True)
    pd.DataFrame({"age": [99], "is_adult": [1]}).to_parquet(
        model_processed / "patients.parquet"
    )

    resolved = models_catalog.resolve_model_real_data_paths(model_id)

    assert resolved == [str(model_processed / "patients.parquet")]


def test_resolve_falls_back_to_raw_when_no_preprocessed_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Legacy model with raw data_sources but no processed_data on disk.
    models_dir = tmp_path / "models"
    model_id = "model_legacy"
    raw_csv = tmp_path / "raw" / "patients.csv"
    raw_csv.parent.mkdir(parents=True)
    raw_csv.write_text("age\n1\n", encoding="utf-8")
    model_dir = models_dir / model_id
    model_dir.mkdir(parents=True)
    _write_json(
        model_dir / MODEL_CARD_FILENAME,
        {"model_id": model_id, "data_sources": [{"path": str(raw_csv)}]},
    )
    monkeypatch.setattr(models_catalog, "MODELS_DIR", str(models_dir))
    monkeypatch.setattr(simulations_catalog, "MODELS_DIR", str(models_dir))

    resolved = models_catalog.resolve_model_real_data_paths(model_id)

    assert resolved == [str(raw_csv)]


def test_list_model_column_values_returns_values_for_derived_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The whole point of this refactor: `is_adult` exists only in the
    # preprocessed parquet, never in the raw CSV. Before the fix this raised
    # because pandas was given `usecols=['is_adult']` against the raw CSV.
    model_id, _ = _scaffold_model_and_inspection(
        tmp_path,
        monkeypatch,
        raw_columns=["age"],
        processed_columns=["age", "is_adult"],
    )

    values = models_catalog.list_model_column_values(
        model_id, table="patients", column="is_adult"
    )

    assert sorted(values) == ["10", "20", "30"]


def test_list_model_column_values_raises_for_missing_column(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_id, _ = _scaffold_model_and_inspection(
        tmp_path,
        monkeypatch,
        raw_columns=["age"],
        processed_columns=["age", "is_adult"],
    )

    # ``height`` was dropped by preprocessing — must surface a clean 404-style
    # error rather than pandas' generic "Usecols do not match" message.
    with pytest.raises(ModelNotFoundError):
        models_catalog.list_model_column_values(
            model_id, table="patients", column="height"
        )


def test_resolve_simulation_inputs_uses_preprocessed_real_data(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_id, processed_dir = _scaffold_model_and_inspection(
        tmp_path,
        monkeypatch,
        raw_columns=["age"],
        processed_columns=["age", "is_adult"],
    )

    simulations_dir = tmp_path / "simulations"
    simulation_id = "simulation_20260101_130000"
    sim_dir = simulations_dir / simulation_id
    synthetic_dir = sim_dir / simulations_catalog.SYNTHETIC_DATA_DIRNAME
    synthetic_dir.mkdir(parents=True)
    synthetic_file = synthetic_dir / "patients_synthetic.csv"
    synthetic_file.write_text("age,is_adult\n42,1\n", encoding="utf-8")
    _write_json(
        sim_dir / SIM_CARD_FILENAME,
        {"simulation_id": simulation_id, "model_id": model_id},
    )
    monkeypatch.setattr(simulations_catalog, "SIMULATIONS_DIR", str(simulations_dir))

    resolved = simulations_catalog.resolve_simulation_inputs(simulation_id)

    assert resolved.real_data_files == [str(processed_dir / "patients.parquet")]
