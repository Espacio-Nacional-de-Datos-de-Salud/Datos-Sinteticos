"""Tests for the rule library (presets) API.

Exercises the full save → list → get → rename → delete lifecycle plus the
validation/404 error paths, with the on-disk library isolated to a tmp dir.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.src.api.main import app
from backend.src.sessions import rule_presets as rule_presets_session


@pytest.fixture
def client() -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def isolated_library(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    library_dir = tmp_path / "rules_library"
    library_dir.mkdir(parents=True)
    monkeypatch.setattr(rule_presets_session, "RULES_LIBRARY_DIR", str(library_dir))
    return library_dir


_RULES_YAML = "rules:\n  - type: date_inequality\n  - type: numeric_inequality\n"


def test_save_then_list_get_rename_delete(
    client: TestClient, isolated_library: Path
) -> None:
    # Save (with bundled column deletions)
    created = client.post(
        "/rule-presets/",
        json={
            "content": _RULES_YAML,
            "name": "demo",
            "excluded_columns": {"patients": ["ssn", "name"]},
        },
    )
    assert created.status_code == 201
    body = created.json()
    preset_id = body["preset_id"]
    assert body["preset_name"] == "demo"
    assert body["rules_count"] == 2
    assert body["excluded_columns"] == {"patients": ["ssn", "name"]}

    # List
    listing = client.get("/rule-presets/")
    assert listing.status_code == 200
    items = listing.json()
    assert [p["preset_id"] for p in items] == [preset_id]
    assert items[0]["excluded_columns"] == {"patients": ["ssn", "name"]}

    # Get raw rules YAML
    rules = client.get(f"/rule-presets/{preset_id}/rules")
    assert rules.status_code == 200
    assert rules.text == _RULES_YAML

    # Rename
    renamed = client.patch(
        f"/rule-presets/{preset_id}/name", json={"name": "renamed"}
    )
    assert renamed.status_code == 200
    assert renamed.json()["preset_name"] == "renamed"

    # Delete
    deleted = client.delete(f"/rule-presets/{preset_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"preset_id": preset_id, "deleted": True}
    assert client.get("/rule-presets/").json() == []


def test_save_auto_names_when_blank(client: TestClient, isolated_library: Path) -> None:
    created = client.post("/rule-presets/", json={"content": "rules: []\n"})
    assert created.status_code == 201
    assert created.json()["preset_name"]  # non-empty auto name
    assert created.json()["rules_count"] == 0


def test_save_rejects_invalid_yaml(client: TestClient, isolated_library: Path) -> None:
    response = client.post("/rule-presets/", json={"content": "rules: [unterminated\n"})
    assert response.status_code == 400


def test_get_rules_missing_returns_404(
    client: TestClient, isolated_library: Path
) -> None:
    assert client.get("/rule-presets/preset_does_not_exist/rules").status_code == 404


def test_delete_missing_returns_404(client: TestClient, isolated_library: Path) -> None:
    assert client.delete("/rule-presets/preset_does_not_exist").status_code == 404
