"""Tests for `backend.src.api.main` and its routers.

Integration tests of the FastAPI application's HTTP request/response cycle.
Verifies artifact catalog operations (list, create, delete), configuration
bootstrap and reset, job cancellation, artifact downloads, and metadata
fallback routing. Uses `client`, `isolated_files_root`, `isolated_config_root`,
and `zip_stream_stub` fixtures for test isolation.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.src.api.main import app
from backend.src.api.routers import (
    evaluations as evaluations_router,
)
from backend.src.api.routers import (
    inspections as inspections_router,
)
from backend.src.api.routers import (
    models as models_router,
)
from backend.src.api.routers import (
    pipelines as pipelines_router,
)
from backend.src.api.routers import (
    simulations as simulations_router,
)
from backend.src.config.general import METADATA_FILENAME, MODEL_CARD_FILENAME
from backend.src.runs.catalog import simulations as simulations_catalog
from backend.src.runs.catalog.inspections import DeleteInspectionOutcome
from backend.src.runs.catalog.models import DeleteModelOutcome
from backend.src.runs.catalog.simulations import DeleteSimulationOutcome
from backend.src.infrastructure.errors import (
    GeneratorEssentialsIncompleteError,
    InspectionNotFoundError,
    InspectionProfilingNotFoundError,
    ModelNotFoundError,
    PipelineNotFoundError,
    SimulationNotFoundError,
    SyntheticDataNotFoundError,
)
from backend.src.sessions import configs as configs_service
from backend.src.sessions import files as files_service


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _assert_zip_response(response, expected_name: str) -> None:
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert (
        response.headers["content-disposition"]
        == f'attachment; filename="{expected_name}"'
    )
    assert response.content == b"zip-content"


@pytest.fixture
def isolated_files_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data_root = tmp_path / "backend-data"
    uploads_dir = data_root / "uploads"
    data_root.mkdir(parents=True)
    monkeypatch.setattr(files_service, "_DATA_ROOT", data_root)
    monkeypatch.setattr(files_service, "UPLOADS_DIR", uploads_dir)
    return data_root


@pytest.fixture
def isolated_config_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    project_root = tmp_path / "project"
    config_root = project_root / "backend" / "config"
    frontend_dir = project_root / "frontend"
    config_root.mkdir(parents=True)
    frontend_dir.mkdir(parents=True)

    monkeypatch.setattr(configs_service, "_PROJECT_ROOT", project_root)
    monkeypatch.setattr(configs_service, "_CONFIG_ROOT", config_root)
    monkeypatch.setattr(
        configs_service, "_FRONTEND_ENV_EXAMPLE", frontend_dir / "env.example.local"
    )
    monkeypatch.setattr(
        configs_service, "_FRONTEND_ENV_LOCAL", frontend_dir / ".env.local"
    )
    return config_root


def _create_example_config(
    config_root: Path, relative_path: str, content: str = "key: value\n"
) -> Path:
    example_path = config_root / relative_path
    example_path.parent.mkdir(parents=True, exist_ok=True)
    example_path.write_text(content, encoding="utf-8")
    return example_path


def _bundle(name: str) -> SimpleNamespace:
    return SimpleNamespace(archive_name=name)


@pytest.fixture
def zip_stream_stub(monkeypatch: pytest.MonkeyPatch) -> None:
    for router in (
        inspections_router,
        models_router,
        simulations_router,
        evaluations_router,
        pipelines_router,
    ):
        monkeypatch.setattr(
            router, "build_zip_stream", lambda bundle: iter([b"zip-content"])
        )


def test_health_endpoint_returns_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_get_files_returns_available_data_files(
    client: TestClient, isolated_files_root: Path
) -> None:
    (isolated_files_root / "patients.csv").write_text("id\n1\n", encoding="utf-8")
    (isolated_files_root / "visits.json").write_text('{"id": 1}', encoding="utf-8")
    (isolated_files_root / "ignore.txt").write_text("x", encoding="utf-8")

    response = client.get("/files/")

    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["patients.csv", "visits.json"]


def test_get_files_filters_by_extension(
    client: TestClient, isolated_files_root: Path
) -> None:
    (isolated_files_root / "patients.csv").write_text("id\n1\n", encoding="utf-8")
    (isolated_files_root / "visits.json").write_text('{"id": 1}', encoding="utf-8")

    response = client.get("/files/?ext=csv")

    assert response.status_code == 200
    assert [item["extension"] for item in response.json()] == ["csv"]


def test_upload_files_returns_saved_file_metadata(
    client: TestClient, isolated_files_root: Path
) -> None:
    response = client.post(
        "/files/upload",
        files=[("files", ("new-data.csv", b"id\n1\n", "text/csv"))],
    )

    assert response.status_code == 201
    assert response.json()[0]["name"] == "new-data.csv"
    assert (isolated_files_root / "uploads" / "new-data.csv").exists()


def test_delete_uploads_returns_removed_names(
    client: TestClient, isolated_files_root: Path
) -> None:
    uploads_dir = isolated_files_root / "uploads"
    uploads_dir.mkdir(parents=True)
    (uploads_dir / "a.csv").write_text("a", encoding="utf-8")
    (uploads_dir / "b.json").write_text("b", encoding="utf-8")

    response = client.delete("/files/uploads")

    assert response.status_code == 200
    assert response.json() == ["a.csv", "b.json"]
    assert list(uploads_dir.iterdir()) == []


def test_configs_bootstrap_creates_real_files(
    client: TestClient, isolated_config_root: Path, tmp_path: Path
) -> None:
    _create_example_config(isolated_config_root, "general.example.yaml")
    _create_example_config(isolated_config_root, "rules.example.yaml")
    frontend_example = tmp_path / "project" / "frontend" / "env.example.local"
    frontend_example.write_text(
        "NEXT_PUBLIC_API_URL=http://localhost:8000\n", encoding="utf-8"
    )

    response = client.post("/configs/bootstrap")

    assert response.status_code == 200
    assert "general.yaml" in response.json()["created"]
    assert (isolated_config_root / "general.yaml").exists()


def test_configs_clean_removes_real_yaml_files(
    client: TestClient, isolated_config_root: Path
) -> None:
    _create_example_config(isolated_config_root, "general.example.yaml")
    (isolated_config_root / "general.yaml").write_text("key: value\n", encoding="utf-8")

    response = client.delete("/configs/")

    assert response.status_code == 200
    assert response.json()["removed"] == ["general.yaml"]
    assert not (isolated_config_root / "general.yaml").exists()


def test_configs_reset_recreates_from_templates(
    client: TestClient, isolated_config_root: Path, tmp_path: Path
) -> None:
    _create_example_config(
        isolated_config_root, "general.example.yaml", "from: template\n"
    )
    (isolated_config_root / "general.yaml").write_text(
        "from: stale\n", encoding="utf-8"
    )
    frontend_example = tmp_path / "project" / "frontend" / "env.example.local"
    frontend_example.write_text("X=1\n", encoding="utf-8")

    response = client.post("/configs/reset")

    assert response.status_code == 200
    assert "general.yaml" in response.json()["created"]
    assert (
        (isolated_config_root / "general.yaml")
        .read_text(encoding="utf-8")
        .endswith("from: template\n")
    )


def test_get_configs_lists_existing_config_files(
    client: TestClient, isolated_config_root: Path
) -> None:
    _create_example_config(isolated_config_root, "general.example.yaml")
    _create_example_config(
        isolated_config_root, "pipelines/example_pipeline.example.yaml"
    )
    (isolated_config_root / "general.yaml").write_text("a: 1\n", encoding="utf-8")
    (isolated_config_root / "pipelines" / "example_pipeline.yaml").parent.mkdir(
        parents=True, exist_ok=True
    )
    (isolated_config_root / "pipelines" / "example_pipeline.yaml").write_text(
        "pipeline: true\n", encoding="utf-8"
    )

    response = client.get("/configs/")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [
        "general.yaml",
        "pipelines/example_pipeline.yaml",
    ]


def test_get_single_config_returns_content_and_metadata(
    client: TestClient, isolated_config_root: Path
) -> None:
    _create_example_config(isolated_config_root, "general.example.yaml")
    (isolated_config_root / "general.yaml").write_text(
        "settings:\n  test: true\n", encoding="utf-8"
    )

    response = client.get("/configs/general")

    assert response.status_code == 200
    assert response.json()["id"] == "general"
    assert "settings:" in response.json()["content"]


def test_put_config_writes_updated_content(
    client: TestClient, isolated_config_root: Path
) -> None:
    _create_example_config(isolated_config_root, "rules.example.yaml", "allow: true\n")

    response = client.put("/configs/rules", json={"content": "allow: false\n"})

    assert response.status_code == 200
    assert (isolated_config_root / "rules.yaml").read_text(
        encoding="utf-8"
    ) == "allow: false\n"
    assert response.json()["content"] == "allow: false\n"


def test_delete_config_resets_file_from_template(
    client: TestClient, isolated_config_root: Path
) -> None:
    _create_example_config(
        isolated_config_root, "general.example.yaml", "from: example\n"
    )
    (isolated_config_root / "general.yaml").write_text(
        "from: edited\n", encoding="utf-8"
    )

    response = client.delete("/configs/general")

    assert response.status_code == 204
    assert (
        (isolated_config_root / "general.yaml")
        .read_text(encoding="utf-8")
        .endswith("from: example\n")
    )


def test_get_inspections_returns_catalog_entries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        inspections_router,
        "list_available_inspections",
        lambda: [
            {
                "inspection_id": "inspection_1",
                "inspection_name": "Admissions",
                "status": "completed",
                "timestamp": "20260421_120000",
                "tables": {"patients": 3},
                "file_paths": ["/tmp/patients.csv"],
            }
        ],
    )

    response = client.get("/inspections/")

    assert response.status_code == 200
    assert response.json()[0]["inspection_name"] == "Admissions"


def test_create_inspection_returns_new_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        inspections_router,
        "initialize_inspection_session",
        lambda name=None: SimpleNamespace(inspection_id="inspection_20260101_120000"),
    )
    monkeypatch.setattr(inspections_router, "run_inspection_flow", lambda **_: None)
    monkeypatch.setattr(
        inspections_router, "resolve_config_path", lambda _: Path("/tmp/config.yaml")
    )

    response = client.post("/inspections/", json={"file_paths": ["/tmp/patients.csv"]})

    assert response.status_code == 202
    assert response.json() == {
        "inspection_id": "inspection_20260101_120000",
        "status": "in_progress",
    }


def test_cleanup_inspections_returns_deleted_ids(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        inspections_router,
        "cleanup_inspections_catalog",
        lambda mode, stale_hours: (["empty_1"], ["orphan_1"], [], []),
    )

    response = client.delete("/inspections/cleanup?mode=both&stale_hours=48")

    assert response.status_code == 200
    assert response.json()["deleted_ids"] == ["empty_1", "orphan_1"]


def test_get_inspection_returns_matching_entry(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        inspections_router,
        "list_available_inspections",
        lambda: [
            {
                "inspection_id": "inspection_20260101_120000",
                "inspection_name": "Run",
                "status": "completed",
            }
        ],
    )

    response = client.get("/inspections/inspection_20260101_120000")

    assert response.status_code == 200
    assert response.json()["inspection_id"] == "inspection_20260101_120000"


def test_get_inspection_autodetect_returns_saved_metadata(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(inspections_router, "INSPECTIONS_DIR", str(tmp_path))
    _write_json(
        tmp_path
        / "inspection_20260101_120000"
        / inspections_router.INSPECTION_METADATA_FILENAME,
        {"relationships": {"pks": {"patients": "id"}, "fks": []}, "encoding_types": {}},
    )

    response = client.get("/inspections/inspection_20260101_120000/autodetect")

    assert response.status_code == 200
    assert response.json()["relationships"]["pks"] == {"patients": "id"}


def test_put_inspection_autodetect_persists_payload(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(inspections_router, "INSPECTIONS_DIR", str(tmp_path))
    (tmp_path / "inspection_20260101_120000").mkdir()
    metadata_path = (
        tmp_path
        / "inspection_20260101_120000"
        / inspections_router.INSPECTION_METADATA_FILENAME
    )
    _write_json(
        metadata_path, {"relationships": {"pks": {}, "fks": []}, "encoding_types": {}}
    )

    payload = {
        "relationships": {"pks": {"patients": "id"}, "fks": []},
        "encoding_types": {"patients": {"age": "TABULAR_NUMERIC_AUTO"}},
    }

    # Update relationships and encoding types via separate endpoints
    resp_rel = client.put(
        "/inspections/inspection_20260101_120000/autodetect/relationships",
        json=payload["relationships"],
    )
    assert resp_rel.status_code == 200

    resp_enc = client.put(
        "/inspections/inspection_20260101_120000/autodetect/encoding-types",
        json=payload["encoding_types"],
    )
    assert resp_enc.status_code == 200

    saved = json.loads(metadata_path.read_text(encoding="utf-8"))
    assert saved == payload


def test_delete_inspection_returns_deleted_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        inspections_router,
        "delete_inspection_catalog",
        lambda inspection_id, mode="safe": DeleteInspectionOutcome(status="deleted"),
    )

    response = client.delete("/inspections/inspection_20260101_120000")

    assert response.status_code == 200
    assert response.json() == {
        "deleted_id": "inspection_20260101_120000",
        "deleted_model_ids": [],
        "deleted_simulation_ids": [],
        "deleted_evaluation_ids": [],
    }


def test_download_inspection_returns_zip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, zip_stream_stub: None
) -> None:
    monkeypatch.setattr(
        inspections_router,
        "build_full_inspection_bundle",
        lambda inspection_id: _bundle("inspection.zip"),
    )

    response = client.get("/inspections/inspection_20260101_120000/download")

    _assert_zip_response(response, "inspection.zip")


def test_download_inspection_profiling_returns_zip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, zip_stream_stub: None
) -> None:
    monkeypatch.setattr(
        inspections_router,
        "build_inspection_profiling_bundle",
        lambda inspection_id: _bundle("inspection-profiling.zip"),
    )

    response = client.get("/inspections/inspection_20260101_120000/download/profiling")

    _assert_zip_response(response, "inspection-profiling.zip")


def test_get_models_returns_catalog_entries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        models_router,
        "list_available_models",
        lambda: [
            {
                "model_id": "model_20260101_120000",
                "status": "completed",
                "timestamp": "20260421_120000",
            }
        ],
    )

    response = client.get("/models/")

    assert response.status_code == 200
    assert response.json()[0]["model_id"] == "model_20260101_120000"


def test_create_model_training_returns_new_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        models_router,
        "initialize_training_session",
        lambda name=None: SimpleNamespace(model_id="model_20260101_120000"),
    )
    monkeypatch.setattr(models_router, "register_cancel", lambda model_id: object())
    monkeypatch.setattr(models_router, "run_training_flow", lambda **_: None)
    monkeypatch.setattr(
        models_router, "resolve_config_path", lambda _: Path("/tmp/config.yaml")
    )

    response = client.post("/models/", json={"file_paths": ["/tmp/patients.csv"]})

    assert response.status_code == 202
    assert response.json() == {
        "model_id": "model_20260101_120000",
        "status": "in_progress",
    }


def test_cleanup_models_returns_deleted_and_skipped_ids(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        models_router,
        "cleanup_models_catalog",
        lambda mode, stale_hours: (["empty_1"], ["orphan_1"], ["linked_1"]),
    )

    response = client.delete("/models/cleanup")

    assert response.status_code == 200
    assert response.json()["skipped_ids"] == ["linked_1"]


def test_cancel_model_marks_job_cancelled(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(models_router, "MODELS_DIR", str(tmp_path))
    monkeypatch.setattr(models_router, "request_cancel", lambda model_id: None)
    _write_json(
        tmp_path / "model_20260101_120000" / models_router.MODEL_CARD_FILENAME,
        {"status": "in_progress"},
    )

    response = client.post("/models/model_20260101_120000/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_get_model_returns_matching_entry(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        models_router,
        "list_available_models",
        lambda: [{"model_id": "model_20260101_120000", "status": "completed"}],
    )

    response = client.get("/models/model_20260101_120000")

    assert response.status_code == 200
    assert response.json()["model_id"] == "model_20260101_120000"


def test_delete_model_returns_deleted_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        models_router,
        "delete_model_catalog",
        lambda model_id, mode="safe": DeleteModelOutcome(status="deleted"),
    )

    response = client.delete("/models/model_20260101_120000")

    assert response.status_code == 200
    assert response.json() == {
        "deleted_id": "model_20260101_120000",
        "deleted_simulation_ids": [],
        "deleted_evaluation_ids": [],
    }


def test_download_model_generator_returns_zip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, zip_stream_stub: None
) -> None:
    monkeypatch.setattr(
        models_router,
        "build_generator_essentials_bundle",
        lambda model_id: _bundle("generator.zip"),
    )

    response = client.get("/models/model_20260101_120000/download/generator")

    _assert_zip_response(response, "generator.zip")


def test_download_model_folder_returns_zip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, zip_stream_stub: None
) -> None:
    monkeypatch.setattr(
        models_router, "build_full_model_bundle", lambda model_id: _bundle("model.zip")
    )

    response = client.get("/models/model_20260101_120000/download")

    _assert_zip_response(response, "model.zip")


def test_get_simulations_returns_catalog_entries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        simulations_router,
        "list_available_simulations",
        lambda: [
            {"simulation_id": "simulation_20260101_120000", "status": "completed"}
        ],
    )

    response = client.get("/simulations/")

    assert response.status_code == 200
    assert response.json()[0]["simulation_id"] == "simulation_20260101_120000"


def test_create_simulation_returns_new_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        simulations_router,
        "initialize_simulation_session",
        lambda model_id, synthetic_data_file_format=None, name=None: SimpleNamespace(
            simulation_id="simulation_20260101_120000",
            synthetic_data_file_format=synthetic_data_file_format or "csv",
        ),
    )
    monkeypatch.setattr(
        simulations_router, "register_cancel", lambda simulation_id: object()
    )
    monkeypatch.setattr(
        simulations_router, "run_simulation_flow_from_model", lambda **_: None
    )
    monkeypatch.setattr(
        simulations_router, "resolve_config_path", lambda _: Path("/tmp/config.yaml")
    )

    response = client.post(
        "/simulations/",
        json={
            "model_id": "model_20260101_120000",
            "sample_size": 10,
            "synthetic_data_file_format": "parquet",
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "simulation_id": "simulation_20260101_120000",
        "status": "in_progress",
    }


def test_cleanup_simulations_returns_deleted_ids(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        simulations_router,
        "cleanup_simulations_catalog",
        lambda mode, stale_hours: (["empty_1"], ["orphan_1"], []),
    )

    response = client.delete("/simulations/cleanup")

    assert response.status_code == 200
    assert response.json()["deleted_ids"] == ["empty_1", "orphan_1"]


def test_cancel_simulation_marks_job_cancelled(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(simulations_router, "SIMULATIONS_DIR", str(tmp_path))
    monkeypatch.setattr(
        simulations_router, "request_cancel", lambda simulation_id: None
    )
    _write_json(
        tmp_path / "simulation_20260101_120000" / simulations_router.SIM_CARD_FILENAME,
        {"status": "in_progress"},
    )

    response = client.post("/simulations/simulation_20260101_120000/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_get_simulation_returns_matching_entry(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        simulations_router,
        "list_available_simulations",
        lambda: [
            {"simulation_id": "simulation_20260101_120000", "status": "completed"}
        ],
    )

    response = client.get("/simulations/simulation_20260101_120000")

    assert response.status_code == 200
    assert response.json()["simulation_id"] == "simulation_20260101_120000"


def test_delete_simulation_returns_deleted_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        simulations_router,
        "delete_simulation_catalog",
        lambda simulation_id, mode="safe": DeleteSimulationOutcome(status="deleted"),
    )

    response = client.delete("/simulations/simulation_20260101_120000")

    assert response.status_code == 200
    assert response.json() == {
        "deleted_id": "simulation_20260101_120000",
        "deleted_evaluation_ids": [],
    }


def test_download_simulation_synthetic_dataset_returns_zip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, zip_stream_stub: None
) -> None:
    monkeypatch.setattr(
        simulations_router,
        "build_synthetic_data_bundle",
        lambda simulation_id: _bundle("synthetic.zip"),
    )

    response = client.get(
        "/simulations/simulation_20260101_120000/download/synthetic-dataset"
    )

    _assert_zip_response(response, "synthetic.zip")


def test_download_simulation_folder_returns_zip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, zip_stream_stub: None
) -> None:
    monkeypatch.setattr(
        simulations_router,
        "build_full_simulation_bundle",
        lambda simulation_id: _bundle("simulation.zip"),
    )

    response = client.get("/simulations/simulation_20260101_120000/download")

    _assert_zip_response(response, "simulation.zip")


def test_get_simulation_columns_falls_back_to_model_metadata(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "models" / "model_20260101_120000"
    metadata_path = model_dir / METADATA_FILENAME
    _write_json(model_dir / MODEL_CARD_FILENAME, {"model_id": "model_20260101_120000"})
    _write_json(
        metadata_path,
        {
            "tables": [
                {
                    "name": "patients",
                    "columns": [{"name": "patient_id"}, {"name": "age"}],
                }
            ]
        },
    )
    monkeypatch.setattr(
        simulations_catalog,
        "resolve_simulation_inputs",
        lambda simulation_id: SimpleNamespace(
            simulation_id=simulation_id,
            metadata_path=str(metadata_path),
            real_data_files=[],
            synthetic_files=[],
        ),
    )

    response = client.get("/simulations/simulation_20260101_120000/columns")

    assert response.status_code == 200
    assert response.json() == {"patients": ["patient_id", "age"]}


def test_get_simulation_columns_falls_back_to_synthetic_files(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    model_dir = tmp_path / "models" / "model_20260101_120000"
    model_dir.mkdir(parents=True)
    metadata_path = model_dir / METADATA_FILENAME
    synthetic_path = tmp_path / "synthetic_data" / "patients_synthetic.csv"
    synthetic_path.parent.mkdir(parents=True)
    synthetic_path.write_text("patient_id,age\n1,42\n", encoding="utf-8")
    _write_json(model_dir / MODEL_CARD_FILENAME, {"model_id": "model_20260101_120000"})
    monkeypatch.setattr(
        simulations_catalog,
        "resolve_simulation_inputs",
        lambda simulation_id: SimpleNamespace(
            simulation_id=simulation_id,
            metadata_path=str(metadata_path),
            real_data_files=[],
            synthetic_files=[str(synthetic_path)],
        ),
    )

    response = client.get("/simulations/simulation_20260101_120000/columns")

    assert response.status_code == 200
    assert response.json() == {"patients": ["patient_id", "age"]}


def test_get_evaluations_returns_catalog_entries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        evaluations_router,
        "list_available_evaluations",
        lambda: [
            {
                "evaluation_id": "evaluation_20260101_120000",
                "status": "completed",
                "timestamp": "20260421_120000",
            }
        ],
    )

    response = client.get("/evaluations/")

    assert response.status_code == 200
    assert response.json()[0]["evaluation_id"] == "evaluation_20260101_120000"


def test_create_evaluation_returns_new_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        evaluations_router,
        "resolve_simulation_inputs",
        lambda simulation_id: SimpleNamespace(
            simulation_id=simulation_id, model_id="model_20260101_120000"
        ),
    )
    monkeypatch.setattr(
        evaluations_router,
        "initialize_evaluation_session",
        lambda simulation_id, model_id, name=None: SimpleNamespace(
            evaluation_id="evaluation_20260101_120000"
        ),
    )
    monkeypatch.setattr(
        evaluations_router, "register_cancel", lambda evaluation_id: object()
    )
    monkeypatch.setattr(
        evaluations_router, "run_evaluation_flow_from_simulation", lambda **_: None
    )

    response = client.post(
        "/evaluations/", json={"simulation_id": "simulation_20260101_120000"}
    )

    assert response.status_code == 202
    assert response.json() == {
        "evaluation_id": "evaluation_20260101_120000",
        "status": "in_progress",
    }


def test_cleanup_evaluations_returns_deleted_ids(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        evaluations_router,
        "cleanup_evaluations_catalog",
        lambda mode, stale_hours: (["empty_1"], ["orphan_1"]),
    )

    response = client.delete("/evaluations/cleanup")

    assert response.status_code == 200
    assert response.json()["deleted_ids"] == ["empty_1", "orphan_1"]


def test_cancel_evaluation_marks_job_cancelled(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(evaluations_router, "EVALUATIONS_DIR", str(tmp_path))
    monkeypatch.setattr(
        evaluations_router, "request_cancel", lambda evaluation_id: None
    )
    _write_json(
        tmp_path / "evaluation_20260101_120000" / evaluations_router.EVAL_CARD_FILENAME,
        {"status": "in_progress"},
    )

    response = client.post("/evaluations/evaluation_20260101_120000/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_get_evaluation_returns_matching_entry(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        evaluations_router,
        "list_available_evaluations",
        lambda: [
            {
                "evaluation_id": "evaluation_20260101_120000",
                "status": "completed",
                "timestamp": "20260421_120000",
            }
        ],
    )

    response = client.get("/evaluations/evaluation_20260101_120000")

    assert response.status_code == 200
    assert response.json()["evaluation_id"] == "evaluation_20260101_120000"


def test_delete_evaluation_returns_deleted_id(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        evaluations_router, "delete_evaluation_catalog", lambda evaluation_id: True
    )

    response = client.delete("/evaluations/evaluation_20260101_120000")

    assert response.status_code == 200
    assert response.json() == {"deleted_id": "evaluation_20260101_120000"}


def test_download_evaluation_returns_zip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, zip_stream_stub: None
) -> None:
    monkeypatch.setattr(
        evaluations_router,
        "build_evaluation_bundle",
        lambda evaluation_id: _bundle("evaluation.zip"),
    )

    response = client.get("/evaluations/evaluation_20260101_120000/download")

    _assert_zip_response(response, "evaluation.zip")


def test_get_pipelines_returns_catalog_entries(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pipelines_router,
        "list_available_pipelines",
        lambda: [
            {
                "pipeline_id": "pipeline_20260101_120000",
                "status": "completed",
                "timestamp": "20260421_120000",
            }
        ],
    )

    response = client.get("/pipelines/")

    assert response.status_code == 200
    assert response.json()[0]["pipeline_id"] == "pipeline_20260101_120000"


def test_create_pipeline_returns_new_job(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pipelines_router,
        "initialize_pipeline_session",
        lambda config_path: SimpleNamespace(pipeline_id="pipeline_20260101_120000"),
    )
    monkeypatch.setattr(
        pipelines_router, "register_cancel", lambda pipeline_id: object()
    )
    monkeypatch.setattr(pipelines_router, "run_pipeline_from_config", lambda **_: None)

    response = client.post("/pipelines/", json={"config_path": "/tmp/pipeline.yaml"})

    assert response.status_code == 202
    assert response.json() == {
        "pipeline_id": "pipeline_20260101_120000",
        "status": "in_progress",
    }


def test_get_pipeline_returns_matching_entry(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pipelines_router,
        "list_available_pipelines",
        lambda: [
            {
                "pipeline_id": "pipeline_20260101_120000",
                "status": "completed",
                "timestamp": "20260421_120000",
                "jobs": [],
            }
        ],
    )

    response = client.get("/pipelines/pipeline_20260101_120000")

    assert response.status_code == 200
    assert response.json()["pipeline_id"] == "pipeline_20260101_120000"


def test_download_pipeline_with_jobs_returns_zip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, zip_stream_stub: None
) -> None:
    monkeypatch.setattr(
        pipelines_router,
        "build_pipeline_with_jobs_bundle",
        lambda pipeline_id: _bundle("pipeline-with-jobs.zip"),
    )

    response = client.get("/pipelines/pipeline_20260101_120000/download/with-jobs")

    _assert_zip_response(response, "pipeline-with-jobs.zip")


def test_download_pipeline_folder_returns_zip(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, zip_stream_stub: None
) -> None:
    monkeypatch.setattr(
        pipelines_router,
        "build_full_pipeline_bundle",
        lambda pipeline_id: _bundle("pipeline.zip"),
    )

    response = client.get("/pipelines/pipeline_20260101_120000/download")

    _assert_zip_response(response, "pipeline.zip")


def test_cancel_pipeline_marks_job_cancelled(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipelines_router, "PIPELINES_DIR", str(tmp_path))
    monkeypatch.setattr(pipelines_router, "request_cancel", lambda pipeline_id: None)
    _write_json(
        tmp_path / "pipeline_20260101_120000" / pipelines_router.PIPELINE_CARD_FILENAME,
        {"status": "in_progress"},
    )

    response = client.post("/pipelines/pipeline_20260101_120000/cancel")

    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_delete_pipeline_returns_deleted_ids(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pipelines_router,
        "delete_pipeline_catalog",
        lambda pipeline_id: SimpleNamespace(
            found=True,
            deleted_model_ids=["model_20260101_120000"],
            deleted_simulation_ids=["simulation_20260101_120000"],
        ),
    )

    response = client.delete("/pipelines/pipeline_20260101_120000")

    assert response.status_code == 200
    assert response.json() == {
        "deleted_id": "pipeline_20260101_120000",
        "deleted_model_ids": ["model_20260101_120000"],
        "deleted_simulation_ids": ["simulation_20260101_120000"],
    }


def test_download_model_generator_returns_409_when_bundle_is_incomplete(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        models_router,
        "build_generator_essentials_bundle",
        lambda model_id: (_ for _ in ()).throw(
            GeneratorEssentialsIncompleteError("missing files")
        ),
    )

    response = client.get("/models/model_20260101_120000/download/generator")

    assert response.status_code == 409
    assert response.json()["detail"] == "missing files"


def test_download_inspection_returns_404_when_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        inspections_router,
        "build_full_inspection_bundle",
        lambda inspection_id: (_ for _ in ()).throw(InspectionNotFoundError("missing")),
    )

    response = client.get("/inspections/inspection_20260102_120000/download")

    assert response.status_code == 404


def test_download_inspection_profiling_returns_404_when_reports_are_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        inspections_router,
        "build_inspection_profiling_bundle",
        lambda inspection_id: (_ for _ in ()).throw(
            InspectionProfilingNotFoundError("profiling missing")
        ),
    )

    response = client.get("/inspections/inspection_20260101_120000/download/profiling")

    assert response.status_code == 404
    assert response.json()["detail"] == "profiling missing"


def test_download_model_returns_404_when_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        models_router,
        "build_full_model_bundle",
        lambda model_id: (_ for _ in ()).throw(ModelNotFoundError("missing")),
    )

    response = client.get("/models/model_20260102_120000/download")

    assert response.status_code == 404


def test_download_simulation_synthetic_dataset_returns_404_when_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        simulations_router,
        "build_synthetic_data_bundle",
        lambda simulation_id: (_ for _ in ()).throw(
            SyntheticDataNotFoundError("missing synthetic")
        ),
    )

    response = client.get(
        "/simulations/simulation_20260101_120000/download/synthetic-dataset"
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "missing synthetic"


def test_download_simulation_returns_404_when_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        simulations_router,
        "build_full_simulation_bundle",
        lambda simulation_id: (_ for _ in ()).throw(SimulationNotFoundError("missing")),
    )

    response = client.get("/simulations/simulation_20260102_120000/download")

    assert response.status_code == 404


def test_download_pipeline_returns_404_when_missing(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        pipelines_router,
        "build_full_pipeline_bundle",
        lambda pipeline_id: (_ for _ in ()).throw(PipelineNotFoundError("missing")),
    )

    response = client.get("/pipelines/pipeline_20260102_120000/download")

    assert response.status_code == 404
