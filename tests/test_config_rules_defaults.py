"""Tests for `backend.src.services.configs` rules configuration defaults.

Verifies that `rules.yaml` is initialized empty (rule definitions are only
loaded from `rules.example.yaml`) during bootstrap and reset operations.
Ensures the system does not accidentally include stale or duplicate rules from
example files in the active runtime configuration.
"""

from pathlib import Path

import pytest

from backend.src.services import configs as configs_service


@pytest.fixture
def seeded_config_root(tmp_path, monkeypatch):
    """Create and seed a config root with rules.example.yaml, and monkeypatch _CONFIG_ROOT."""
    config_root = tmp_path / "backend" / "config"
    config_root.mkdir(parents=True)
    (config_root / "rules.example.yaml").write_text(
        "rules:\n  - type: date_inequality\n", encoding="utf-8"
    )
    monkeypatch.setattr(configs_service, "_CONFIG_ROOT", config_root)
    return config_root


def test_bootstrap_keeps_rules_runtime_config_empty(seeded_config_root, tmp_path, monkeypatch):
    monkeypatch.setattr(configs_service, "_FRONTEND_ENV_EXAMPLE", tmp_path / "missing.env")
    monkeypatch.setattr(configs_service, "_FRONTEND_ENV_LOCAL", tmp_path / ".env.local")

    configs_service.bootstrap_configs()

    assert (seeded_config_root / "rules.yaml").read_text(encoding="utf-8").endswith("rules: []\n")


def test_reset_keeps_rules_runtime_config_empty(seeded_config_root):
    (seeded_config_root / "rules.yaml").write_text("rules:\n  - type: numeric_bucket\n", encoding="utf-8")

    configs_service.reset_config("rules")

    assert (seeded_config_root / "rules.yaml").read_text(encoding="utf-8").endswith("rules: []\n")
