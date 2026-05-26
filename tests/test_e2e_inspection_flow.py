"""End-to-end test for `run_inspection_flow`.

Exercises the real I/O path of the inspection service in an isolated
``outputs/inspections/`` directory. The heavy collaborators
(``FileDataLoader``, ``DataPreprocessor``, ``extract_rules_from_config``)
are stubbed so the test stays in ``.venv_core`` and runs in a few hundred
milliseconds, but every other line — directory creation, card writes,
parquet caching, metadata snapshotting, profiling gating, name
resolution — runs for real against tmp_path.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from backend.src.config.general import (
    AUTODETECTED_INSPECTION_METADATA_FILENAME,
    INSPECTION_CARD_FILENAME,
    INSPECTION_METADATA_FILENAME,
    PROCESSED_DATA_DIRNAME,
    TIME_PROFILING_REPORT_FILENAME,
)
from backend.src.domain.rules_config import RejectionSamplingConfig
from backend.src.runs.tracking import inspection_tracker as inspection_tracker_module
from backend.src.sessions import inspection as inspection_service


@pytest.fixture
def isolated_inspections_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    inspections_dir = tmp_path / "inspections"
    inspections_dir.mkdir()
    # ``INSPECTIONS_DIR`` is imported into both the service (used by lookup
    # helpers) and the tracker (used to materialize new session folders);
    # patch both to redirect all I/O into the temporary directory.
    monkeypatch.setattr(inspection_service, "INSPECTIONS_DIR", str(inspections_dir))
    monkeypatch.setattr(inspection_tracker_module, "INSPECTIONS_DIR", str(inspections_dir))
    monkeypatch.setattr(
        inspection_service,
        "extract_rules_and_rejection_config",
        lambda _path: ([], RejectionSamplingConfig()),
    )
    return inspections_dir


def _stub_data_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    *,
    processed_data: dict[str, pd.DataFrame] | None = None,
    relationships: dict | None = None,
    encoding_types: dict | None = None,
    data_profiles: dict | None = None,
) -> None:
    processed_data = processed_data or {
        "patients": pd.DataFrame({"id": [1, 2, 3], "age": [10, 20, 30]})
    }
    relationships = relationships or {"pks": {"patients": "id"}, "fks": []}
    encoding_types = encoding_types or {"patients": {"age": "INTEGER"}}

    fake_loader = MagicMock()
    fake_loader.return_value.load = MagicMock(return_value=processed_data)
    monkeypatch.setattr(inspection_service, "FileDataLoader", fake_loader)

    fake_preprocessor_instance = SimpleNamespace(
        rule_manager=SimpleNamespace(add_rule=lambda _r: None),
        run=MagicMock(
            return_value=SimpleNamespace(
                processed_data=processed_data,
                metadata={},
                relationships=relationships,
                encoding_types=encoding_types,
                rule_manager=SimpleNamespace(),
                data_profiles=data_profiles,
            )
        ),
    )
    monkeypatch.setattr(
        inspection_service, "DataPreprocessor", lambda _data, composite_pk_config=None: fake_preprocessor_instance
    )


def test_run_inspection_flow_writes_full_session_layout(
    isolated_inspections_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_data_pipeline(monkeypatch)
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("rules: []\n", encoding="utf-8")

    result = inspection_service.run_inspection_flow(
        file_paths=["/data/patients.csv"],
        mostly_config_path="/cfg/mostly.yaml",
        rules_config_path=str(rules_file),
        enable_data_profiling=False,
    )

    assert result is not None
    assert result.tables == {"patients": 3}
    assert result.relationships == {"pks": {"patients": "id"}, "fks": []}

    session_dir = Path(result.output_directory)
    assert session_dir.is_dir()

    # Card written with completed status and the configured inputs.
    card = json.loads((session_dir / INSPECTION_CARD_FILENAME).read_text())
    assert card["status"] == "completed"
    assert card["tables"] == {"patients": 3}
    assert card["file_paths"] == ["/data/patients.csv"]
    assert card["enable_data_profiling"] is False

    # Both metadata files written; autodetected is the frozen snapshot.
    metadata = json.loads((session_dir / INSPECTION_METADATA_FILENAME).read_text())
    autodetected = json.loads(
        (session_dir / AUTODETECTED_INSPECTION_METADATA_FILENAME).read_text()
    )
    assert metadata == autodetected
    assert metadata["relationships"]["pks"] == {"patients": "id"}

    # Processed data cached as parquet.
    parquet_path = session_dir / PROCESSED_DATA_DIRNAME / "patients.parquet"
    assert parquet_path.is_file()
    cached = pd.read_parquet(parquet_path)
    assert list(cached.columns) == ["id", "age"]
    assert len(cached) == 3

    # Rules snapshot copied.
    snapshot = session_dir / inspection_service.RULES_SNAPSHOT_FILENAME
    assert snapshot.read_text() == "rules: []\n"
    assert card["rules_config_path"] == str(snapshot)

    # Timing report produced by the finally-block.
    assert (session_dir / TIME_PROFILING_REPORT_FILENAME).is_file()


def test_run_inspection_flow_marks_card_failed_on_loader_error(
    isolated_inspections_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from backend.src.infrastructure.errors import DataLoadError

    fake_loader_class = MagicMock()
    fake_loader_class.return_value.load = MagicMock(
        side_effect=DataLoadError("bad data")
    )
    monkeypatch.setattr(inspection_service, "FileDataLoader", fake_loader_class)
    monkeypatch.setattr(inspection_service, "DataPreprocessor", MagicMock())

    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("rules: []\n", encoding="utf-8")

    result = inspection_service.run_inspection_flow(
        file_paths=["/data/x.csv"],
        mostly_config_path="/cfg/mostly.yaml",
        rules_config_path=str(rules_file),
        enable_data_profiling=False,
    )
    assert result is None

    sessions = list(isolated_inspections_dir.iterdir())
    assert len(sessions) == 1
    card = json.loads((sessions[0] / INSPECTION_CARD_FILENAME).read_text())
    assert card["status"] == "failed"
    assert "DataLoadError" in card["error_message"]


def test_run_inspection_flow_skips_when_cancelled_before_start(
    isolated_inspections_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import threading

    monkeypatch.setattr(inspection_service, "FileDataLoader", MagicMock())
    monkeypatch.setattr(inspection_service, "DataPreprocessor", MagicMock())

    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("rules: []\n", encoding="utf-8")

    cancel = threading.Event()
    cancel.set()

    result = inspection_service.run_inspection_flow(
        file_paths=["/data/x.csv"],
        mostly_config_path="/cfg/mostly.yaml",
        rules_config_path=str(rules_file),
        enable_data_profiling=False,
        cancel_event=cancel,
    )
    assert result is None

    sessions = list(isolated_inspections_dir.iterdir())
    assert len(sessions) == 1
    card = json.loads((sessions[0] / INSPECTION_CARD_FILENAME).read_text())
    assert card["status"] == "cancelled"


def test_load_inspection_artifacts_round_trips_session_data(
    isolated_inspections_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_data_pipeline(monkeypatch)
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("rules: []\n", encoding="utf-8")

    result = inspection_service.run_inspection_flow(
        file_paths=["/data/patients.csv"],
        mostly_config_path="/cfg/mostly.yaml",
        rules_config_path=str(rules_file),
        enable_data_profiling=False,
    )
    assert result is not None

    card, processed_data, inspection_metadata = (
        inspection_service.load_inspection_artifacts(result.inspection_id)
    )
    assert card["inspection_id"] == result.inspection_id
    assert "patients" in processed_data
    assert len(processed_data["patients"]) == 3
    assert inspection_metadata["relationships"]["pks"] == {"patients": "id"}


def test_resolve_inspection_rules_config_path_prefers_snapshot(
    isolated_inspections_dir: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _stub_data_pipeline(monkeypatch)
    rules_file = tmp_path / "rules.yaml"
    rules_file.write_text("rules: []\n", encoding="utf-8")

    result = inspection_service.run_inspection_flow(
        file_paths=["/data/patients.csv"],
        mostly_config_path="/cfg/mostly.yaml",
        rules_config_path=str(rules_file),
        enable_data_profiling=False,
    )
    assert result is not None

    resolved = inspection_service.resolve_inspection_rules_config_path(
        result.inspection_id
    )
    assert resolved.endswith(inspection_service.RULES_SNAPSHOT_FILENAME)
    assert Path(resolved).is_file()


def test_resolve_inspection_rules_config_path_raises_when_nothing_resolves(
    isolated_inspections_dir: Path,
) -> None:
    # Folder exists but has no snapshot and no card.
    (isolated_inspections_dir / "insp_x").mkdir()
    with pytest.raises(FileNotFoundError, match="Rules config not found"):
        inspection_service.resolve_inspection_rules_config_path("insp_x")
