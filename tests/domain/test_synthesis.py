from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from backend.src.domain.synthesis.mostly import (
    MostlyAIEngine,
    _cap_training_tables,
    _find_free_port,
    _positive_int,
    _table_model_settings,
)
from backend.src.infrastructure.errors import TableMetadataMissingError

# -----------------------------------------------------------------------------
# Utility Function Tests
# -----------------------------------------------------------------------------


def test_find_free_port():
    """Test that _find_free_port returns a free port across 1000 calls.
    Should not return ports 0-1024 (reserved by system)"""
    for _ in range(3000):
        port = _find_free_port()
        assert isinstance(port, int)
        assert port > 1024


def test_positive_int():
    assert _positive_int("10") == 10
    assert _positive_int(5) == 5
    assert _positive_int(0) is None
    assert _positive_int("-5") is None
    assert _positive_int(None) is None
    assert _positive_int("abc") is None


def test_table_model_settings_without_overrides_returns_base():
    base = {"max_epochs": 5, "differential_privacy": {"delta": 1e-5}}
    assert _table_model_settings(base, {}, "users") is base
    assert _table_model_settings(base, {"per_table": {"other": {}}}, "users") is base


def test_table_model_settings_merges_and_drops_nulls():
    base = {"max_epochs": 5, "differential_privacy": {"delta": 1e-5}}
    settings = {
        "per_table": {
            "deep_child": {"differential_privacy": None, "batch_size": 8},
        }
    }
    merged = _table_model_settings(base, settings, "deep_child")
    assert "differential_privacy" not in merged
    assert merged["batch_size"] == 8
    assert merged["max_epochs"] == 5
    # base settings are not mutated
    assert base["differential_privacy"] == {"delta": 1e-5}


def test_table_model_settings_strips_local_fields_from_overrides():
    base = {"max_epochs": 5}
    settings = {"per_table": {"users": {"entity_key": "id", "batch_size": 4}}}
    merged = _table_model_settings(base, settings, "users")
    assert "entity_key" not in merged
    assert merged["batch_size"] == 4


def test_cap_training_tables_no_limit():
    data = {"users": pd.DataFrame({"id": [1, 2]})}
    capped = _cap_training_tables(data, {}, max_sample_size=None, random_state=42)
    assert capped == data


def test_cap_training_tables_with_limit():
    data = {"users": pd.DataFrame({"id": [1, 2, 3, 4, 5]})}
    metadata = {"tables": [{"name": "users"}]}

    capped = _cap_training_tables(data, metadata, max_sample_size=2, random_state=42)

    assert "users" in capped
    assert len(capped["users"]) == 2


def test_cap_training_tables_cascading_foreign_keys():
    # Setup data where orders depend on users
    data = {
        "users": pd.DataFrame({"id": [1, 2, 3]}),
        "orders": pd.DataFrame({"order_id": [10, 20, 30], "user_id": [1, 2, 3]}),
    }
    metadata = {
        "tables": [
            {"name": "users", "primary_key": "id"},
            {
                "name": "orders",
                "foreign_keys": [{"column": "user_id", "referenced_table": "users"}],
            },
        ]
    }

    # Cap users to 1 row
    capped = _cap_training_tables(data, metadata, max_sample_size=1, random_state=42)

    assert len(capped["users"]) == 1
    # Only the order corresponding to the sampled user should remain
    sampled_user_id = capped["users"].iloc[0]["id"]
    assert len(capped["orders"]) == 1
    assert capped["orders"].iloc[0]["user_id"] == sampled_user_id


# -----------------------------------------------------------------------------
# MostlyAIEngine Tests
# -----------------------------------------------------------------------------


@pytest.fixture
def mock_mostly():
    with patch("backend.src.domain.synthesis.mostly.MostlyAI") as mock:
        instance = MagicMock()
        mock.return_value = instance
        yield instance


@pytest.fixture
def base_config(tmp_path):
    config_path = tmp_path / "mostly_ai.yaml"
    config_path.write_text(
        "generator:\n  name: test_gen\n  description: test desc\n  random_state: 42"
    )
    return str(config_path)


def test_mostlyai_engine_init(base_config, mock_mostly):
    engine = MostlyAIEngine(config_path=base_config, local=True)
    assert engine.mostly == mock_mostly
    assert engine.config["generator"]["description"] == "test desc"
    assert "test_gen" in engine.config["generator"]["name"]


@patch("backend.src.domain.synthesis.mostly.backend_model_settings")
@patch("backend.src.domain.synthesis.mostly.build_modeling_configuration")
@patch("backend.src.domain.synthesis.mostly.MostlyAIEngine._raise_if_training_failed")
def test_engine_train_success(
    mock_raise, mock_build, mock_backend, base_config, mock_mostly
):
    engine = MostlyAIEngine(config_path=base_config, local=True)

    mock_build.return_value = {}
    mock_backend.return_value = {}

    data = {"users": pd.DataFrame({"id": [1]})}
    metadata = {"tables": [{"name": "users", "columns": [{"name": "id"}]}]}

    # Mock generator creation
    mock_generator = MagicMock()
    mock_mostly.generators.create.return_value = mock_generator

    gen = engine.train(data, metadata)

    assert gen == mock_generator
    mock_mostly.generators.create.assert_called_once()
    mock_generator.training.start.assert_called_once()
    mock_generator.training.wait.assert_called_once()
    mock_raise.assert_called_once_with(mock_generator)


def test_engine_train_missing_metadata(base_config, mock_mostly):
    engine = MostlyAIEngine(config_path=base_config, local=True)
    data = {"users": pd.DataFrame({"id": [1]})}
    # Missing metadata for "users"
    metadata = {"tables": [{"name": "other_table"}]}

    with pytest.raises(TableMetadataMissingError, match="No metadata found"):
        engine.train(data, metadata)


@patch("backend.src.domain.synthesis.mostly.os.path.isdir")
@patch("backend.src.domain.synthesis.mostly.os.path.exists")
def test_load_generator_by_id(mock_exists, mock_isdir, base_config, mock_mostly):
    engine = MostlyAIEngine(config_path=base_config, local=True)

    mock_isdir.return_value = True
    mock_exists.return_value = True

    mock_gen = MagicMock()
    mock_mostly.generators.import_from_file.return_value = mock_gen

    gen, folder = engine.load_generator_by_id("model_123")

    assert gen == mock_gen
    assert "model_123" in folder
    mock_mostly.generators.import_from_file.assert_called_once()


@patch("backend.src.domain.synthesis.mostly.os.path.isdir")
def test_load_generator_not_found(mock_isdir, base_config, mock_mostly):
    engine = MostlyAIEngine(config_path=base_config, local=True)
    mock_isdir.return_value = False

    with pytest.raises(FileNotFoundError, match="Model folder not found"):
        engine.load_generator_by_id("model_123")


def test_engine_simulate_success(base_config, mock_mostly):
    engine = MostlyAIEngine(config_path=base_config, local=True)

    mock_generator = MagicMock()
    mock_generator.id = "gen_1"

    mock_dataset = MagicMock()
    mock_dataset.id = "sd_1"

    # Mocking the dataset object
    mock_mostly.synthetic_datasets.create.return_value = mock_dataset
    mock_mostly.synthetic_datasets.get.return_value = mock_dataset

    mock_df = pd.DataFrame({"val": [1]})
    mock_dataset.data.return_value = mock_df

    mock_config = MagicMock()
    mock_config_table = MagicMock()
    type(mock_config_table).name = "users"
    mock_config.tables = [mock_config_table]
    mock_dataset.config.return_value = mock_config

    sim_config = {"tables": [{"name": "users"}]}

    data_dict, sd_id = engine.simulate(mock_generator, sim_config)

    assert sd_id == "sd_1"
    assert "users" in data_dict
    assert data_dict["users"].equals(mock_df)

    mock_mostly.synthetic_datasets.create.assert_called_once()
    mock_dataset.generation.start.assert_called_once()
    mock_dataset.generation.wait.assert_called_once()
