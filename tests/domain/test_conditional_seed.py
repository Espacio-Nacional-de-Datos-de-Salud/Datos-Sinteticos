import numpy as np
import pandas as pd
import pytest
from unittest.mock import patch
from backend.src.domain.conditional_seed import (
    _allocate_categorical,
    _generate_numeric,
    _generate_daterange,
    build_sample_seed,
    _first_subject_table,
    _datetime_columns,
    attach_sample_seeds,
)


def test_allocate_categorical_respects_proportions() -> None:
    weights = {"A": 0.5, "B": 0.3, "C": 0.2}
    rng = np.random.default_rng(seed=42)
    result = _allocate_categorical(weights, 100, rng)
    assert len(result) == 100
    assert result.count("A") == 50
    assert result.count("B") == 30
    assert result.count("C") == 20

def test_allocate_categorical_handles_remainder() -> None:
    weights = {"X": 0.33, "Y": 0.33, "Z": 0.34}
    rng = np.random.default_rng(seed=42)
    result = _allocate_categorical(weights, 10, rng)
    assert len(result) == 10
    assert result.count("Z") >= result.count("X")

def test_allocate_categorical_single_category() -> None:
    weights = {"only": 1.0}
    rng = np.random.default_rng(seed=42)
    result = _allocate_categorical(weights, 50, rng)
    assert len(result) == 50
    assert all(v == "only" for v in result)

def test_generate_numeric_uniform() -> None:
    cond = {"min": 10, "max": 20, "generator": "uniform"}
    rng = np.random.default_rng(seed=42)
    result = _generate_numeric(cond, 100, rng)
    assert len(result) == 100
    assert np.all(result >= 10)
    assert np.all(result <= 20)

def test_generate_numeric_normal() -> None:
    cond = {"min": 0, "max": 100, "generator": "normal", "mean": 50, "std": 10}
    rng = np.random.default_rng(seed=42)
    result = _generate_numeric(cond, 100, rng)
    assert len(result) == 100
    assert np.all(result >= 0)
    assert np.all(result <= 100)

def test_generate_numeric_integer() -> None:
    cond = {"min": 1, "max": 5, "generator": "uniform", "integer": True}
    rng = np.random.default_rng(seed=42)
    result = _generate_numeric(cond, 50, rng)
    assert len(result) == 50
    assert result.dtype == np.int64
    assert np.all(result >= 1)
    assert np.all(result <= 5)

def test_generate_daterange_uniform() -> None:
    cond = {"start": "2023-01-01", "end": "2023-12-31"}
    rng = np.random.default_rng(seed=42)
    result = _generate_daterange(cond, 100, rng)
    assert len(result) == 100
    assert pd.api.types.is_datetime64_any_dtype(result)
    assert result.min() >= pd.Timestamp("2023-01-01")
    assert result.max() <= pd.Timestamp("2023-12-31")

def test_generate_daterange_same_date() -> None:
    cond = {"start": "2023-01-01", "end": "2023-01-01"}
    rng = np.random.default_rng(seed=42)
    result = _generate_daterange(cond, 10, rng)
    assert len(result) == 10
    assert all(d == pd.Timestamp("2023-01-01") for d in result)

def test_build_sample_seed_mixed_conditions() -> None:
    conditions = [
        {"column": "status", "mode": "fixed", "value": "active"},
        {"column": "region", "mode": "categorical", "weights": {"N": 0.5, "S": 0.5}},
        {"column": "age", "mode": "numeric", "min": 18, "max": 65, "generator": "uniform"},
        {"column": "joined", "mode": "daterange", "start": "2020-01-01", "end": "2022-01-01"}
    ]
    df = build_sample_seed(conditions, 10)
    assert len(df) == 10
    assert list(df["status"]) == ["active"] * 10
    assert set(df["region"]) == {"N", "S"}
    assert df["age"].min() >= 18
    assert df["age"].max() <= 65
    assert df["joined"].min() >= pd.Timestamp("2020-01-01")

def test_build_sample_seed_invalid_mode() -> None:
    conditions = [{"column": "col", "mode": "invalid"}]
    with pytest.raises(ValueError, match="Unknown conditional mode"):
        build_sample_seed(conditions, 5)

def test_first_subject_table() -> None:
    metadata = {
        "tables": [
            {"name": "context_table", "foreign_keys": [{"is_context": True}]},
            {"name": "subject_table", "foreign_keys": []}
        ]
    }
    assert _first_subject_table(metadata) == "subject_table"

def test_first_subject_table_no_tables() -> None:
    assert _first_subject_table({}) is None

def test_datetime_columns() -> None:
    metadata = {
        "tables": [
            {
                "name": "users",
                "columns": [
                    {"name": "id", "model_encoding_type": "NUMERIC"},
                    {"name": "created_at", "model_encoding_type": "DATETIME"},
                    {"name": "updated_at", "model_encoding_type": "auto_DATETIME"}
                ]
            }
        ]
    }
    assert _datetime_columns(metadata, "users") == {"created_at", "updated_at"}
    assert _datetime_columns(metadata, "nonexistent") == set()

def test_attach_sample_seeds_no_conditions() -> None:
    config = {"tables": [{"name": "users"}]}
    assert attach_sample_seeds(config, None, {}) == config
    assert attach_sample_seeds(config, {"conditions": []}, {}) == config

@patch("backend.src.domain.conditional_seed.logger")
def test_attach_sample_seeds_no_target_table(mock_logger) -> None:
    config = {"tables": []}
    conditional = {"conditions": [{"column": "x", "mode": "fixed", "value": 1}]}
    result = attach_sample_seeds(config, conditional, {})
    assert result == config
    mock_logger.warning.assert_called_once()
    assert "no subject table found" in mock_logger.warning.call_args[0][0]

@patch("backend.src.domain.conditional_seed.logger")
def test_attach_sample_seeds_missing_table_in_config(mock_logger) -> None:
    config = {"tables": [{"name": "other_table"}]}
    conditional = {"table": "users", "conditions": [{"column": "x", "mode": "fixed", "value": 1}]}
    result = attach_sample_seeds(config, conditional, {})
    assert result == config
    mock_logger.warning.assert_called_once()
    assert "not in the simulation config" in mock_logger.warning.call_args[0][0]

def test_attach_sample_seeds_success() -> None:
    config = {"tables": [{"name": "users", "configuration": {"sample_size": 100}}]}
    conditional = {
        "table": "users",
        "conditions": [{"column": "status", "mode": "fixed", "value": "active"}]
    }
    metadata = {"tables": [{"name": "users", "columns": []}]}
    
    result = attach_sample_seeds(config, conditional, metadata)
    
    table_cfg = result["tables"][0]["configuration"]
    assert "sample_size" not in table_cfg
    assert "sample_seed_data" in table_cfg
    df = table_cfg["sample_seed_data"]
    assert len(df) == 100
    assert list(df["status"]) == ["active"] * 100

def test_attach_sample_seeds_with_datetime_parsing() -> None:
    config = {"tables": [{"name": "users", "configuration": {"sample_size": 2}}]}
    conditional = {
        "table": "users",
        "conditions": [
            {"column": "created_at", "mode": "fixed", "value": "2023-01-01T00:00:00"}
        ]
    }
    metadata = {
        "tables": [
            {
                "name": "users",
                "columns": [{"name": "created_at", "model_encoding_type": "DATETIME"}]
            }
        ]
    }
    
    result = attach_sample_seeds(config, conditional, metadata)
    df = result["tables"][0]["configuration"]["sample_seed_data"]
    
    assert pd.api.types.is_datetime64_any_dtype(df["created_at"])
    assert df["created_at"].iloc[0] == pd.Timestamp("2023-01-01T00:00:00")