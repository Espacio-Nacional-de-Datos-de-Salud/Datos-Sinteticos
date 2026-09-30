"""Tests for `backend.src.sessions.inspection` rules config path resolution.

Verifies that `resolve_inspection_rules_config_path` prefers the snapshot
rules file (captured during inspection creation) over the global rules config,
ensuring that legacy inspections without a snapshot can still fall back to
the global config path without breaking.
"""

from pathlib import Path

import pytest

from backend.src.sessions import inspection as inspection_service


@pytest.fixture
def scoped_inspection_dir(tmp_path, monkeypatch):
    """Create and scope an inspection directory for path resolution tests."""
    inspections_dir = tmp_path / "inspections"
    inspection_dir = inspections_dir / "inspection_1"
    inspection_dir.mkdir(parents=True)
    monkeypatch.setattr(inspection_service, "INSPECTIONS_DIR", str(inspections_dir))
    return inspection_dir


def test_resolve_inspection_rules_prefers_snapshot(scoped_inspection_dir):
    snapshot = scoped_inspection_dir / inspection_service.RULES_SNAPSHOT_FILENAME
    snapshot.write_text("rules: []\n", encoding="utf-8")

    path = inspection_service.resolve_inspection_rules_config_path(
        "inspection_1",
        {"rules_config_path": "/global/rules.yaml"},
    )

    assert Path(path) == snapshot


def test_resolve_inspection_rules_falls_back_for_legacy_inspections(scoped_inspection_dir, tmp_path):
    legacy_rules_path = tmp_path / "rules.yaml"
    legacy_rules_path.write_text("rules: []\n", encoding="utf-8")

    path = inspection_service.resolve_inspection_rules_config_path(
        "inspection_1",
        {"rules_config_path": str(legacy_rules_path)},
    )

    assert Path(path) == legacy_rules_path
