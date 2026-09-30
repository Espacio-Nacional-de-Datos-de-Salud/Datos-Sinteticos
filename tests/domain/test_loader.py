import os
import pandas as pd
import pytest
from unittest.mock import patch, MagicMock

from backend.src.domain.loader import FileDataLoader
from backend.src.infrastructure.errors import DataLoadError

# -----------------------------------------------------------------------------
# Unit Tests
# -----------------------------------------------------------------------------

@patch("backend.src.domain.loader.os.path.exists")
@patch("backend.src.domain.loader.pd.read_parquet")
def test_loader_unit_parquet_success(mock_read_parquet, mock_exists):
    """Unit test to verify loading a Parquet file works."""
    mock_exists.return_value = True
    mock_df = pd.DataFrame({"val": [10.5]})
    mock_read_parquet.return_value = mock_df

    loader = FileDataLoader()
    data = loader.load(["data/transactions.parquet"])

    assert "transactions" in data
    assert data["transactions"].equals(mock_df)

@patch("backend.src.domain.loader.logger")
@patch("backend.src.domain.loader.os.path.exists")
def test_loader_unit_unsupported_format(mock_exists, mock_logger):
    """Unit test to verify unsupported extensions are skipped."""
    mock_exists.return_value = True

    loader = FileDataLoader()
    with pytest.raises(DataLoadError, match="Could not load any valid table"):
        loader.load(["data/notes.txt"])

    assert any("Unsupported format for %s. Skipping." in call.args[0] and "notes.txt" in call.args for call in mock_logger.warning.call_args_list)

# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------

@pytest.fixture
def temp_data_files(tmp_path):
    """Fixture to set up real temporary files for integration testing."""
    csv_file = tmp_path / "data1.csv"
    csv_file.write_text("id,name\n1,Alice\n2,Bob")
    
    csv_custom_file = tmp_path / "data2.csv"
    csv_custom_file.write_text("id;age\n1;30\n2;25")
    
    parquet_file = tmp_path / "data3.parquet"
    pd.DataFrame({"value": [10.5, 20.1]}).to_parquet(parquet_file)
    
    txt_file = tmp_path / "data4.txt"
    txt_file.write_text("some unsupported text")
    
    return {
        "csv": str(csv_file),
        "csv_custom": str(csv_custom_file),
        "parquet": str(parquet_file),
        "txt": str(txt_file),
        "missing": str(tmp_path / "missing.csv")
    }

def test_loader_integration_multiple_files(temp_data_files):
    """Integration test: successfully loading multiple file formats from the file system."""
    loader = FileDataLoader()
    sources = [temp_data_files["csv"], temp_data_files["parquet"]]
    
    data = loader.load(sources)
    
    assert "data1" in data
    assert "data3" in data
    assert len(data["data1"]) == 2
    assert len(data["data3"]) == 2

def test_loader_integration_custom_separator(temp_data_files):
    """Integration test: loading a CSV with a custom separator."""
    loader = FileDataLoader()
    data = loader.load([temp_data_files["csv_custom"]], sep=";")
    
    assert "data2" in data
    assert list(data["data2"].columns) == ["id", "age"]

@patch("backend.src.domain.loader.logger")
def test_loader_integration_missing_and_unsupported(mock_logger, temp_data_files):
    """Integration test: skipping missing and unsupported files gracefully."""
    loader = FileDataLoader()
    sources = [temp_data_files["txt"], temp_data_files["missing"], temp_data_files["csv"]]
    
    data = loader.load(sources)
    
    # Should only load the valid CSV, skipping the missing and unsupported ones
    assert list(data.keys()) == ["data1"]
    assert any("Unsupported format" in str(call) for call in mock_logger.warning.call_args_list)
    assert any("does not exist" in str(call) for call in mock_logger.warning.call_args_list)

def test_loader_integration_no_valid_tables(temp_data_files):
    """Integration test: raising DataLoadError when no files can be loaded."""
    loader = FileDataLoader()
    with pytest.raises(DataLoadError, match="Could not load any valid table"):
        loader.load([temp_data_files["missing"], temp_data_files["txt"]])

@patch("backend.src.domain.loader.logger")
def test_loader_integration_read_error(mock_logger, temp_data_files):
    """Integration test: skipping a file that causes a read error and failing if none are valid."""
    loader = FileDataLoader()
    
    # Intentionally corrupt a parquet file by giving it CSV content
    corrupted_parquet = temp_data_files["csv"] + ".parquet"
    with open(corrupted_parquet, "w") as f:
        f.write("this is not parquet format")
        
    with pytest.raises(DataLoadError):
        loader.load([corrupted_parquet])
        
    assert any("Error loading" in str(call) for call in mock_logger.warning.call_args_list)
