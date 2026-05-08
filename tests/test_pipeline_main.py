"""Tests for `backend.src.pipeline.__main__` — the pipeline CLI entry point.

The module's logic lives entirely under the ``if __name__ == "__main__":``
guard, so we drive it with ``runpy.run_module(..., run_name="__main__")``
after stubbing the loader and executor.
"""

from __future__ import annotations

import runpy
import sys
from unittest.mock import MagicMock

import pytest


def _run_pipeline_main(monkeypatch: pytest.MonkeyPatch, argv_extra: list[str]) -> None:
    monkeypatch.setattr(sys, "argv", ["pipeline", *argv_extra])
    runpy.run_module("backend.src.pipeline", run_name="__main__")


def test_pipeline_main_invokes_loader_and_runner(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    config_file = tmp_path / "p.yaml"
    config_file.write_text("jobs: []\n", encoding="utf-8")

    fake_config = object()
    fake_loader = MagicMock(return_value=fake_config)
    fake_runner = MagicMock()

    import backend.src.pipeline as pipeline_pkg

    monkeypatch.setattr(pipeline_pkg, "load_pipeline_config", fake_loader)
    monkeypatch.setattr(pipeline_pkg, "run_pipeline", fake_runner)

    # The __main__ module re-imports these by name from their submodules,
    # so we also need to patch the submodule-level symbols.
    import backend.src.pipeline.loader as loader_mod
    import backend.src.pipeline.executor as executor_mod

    monkeypatch.setattr(loader_mod, "load_pipeline_config", fake_loader)
    monkeypatch.setattr(executor_mod, "run_pipeline", fake_runner)

    _run_pipeline_main(monkeypatch, ["--config", str(config_file)])

    fake_loader.assert_called_once_with(str(config_file))
    fake_runner.assert_called_once()
    assert fake_runner.call_args.args[0] is fake_config
    assert fake_runner.call_args.kwargs["config_path"] == str(config_file)


def test_pipeline_main_exits_when_loader_raises(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    import backend.src.pipeline.loader as loader_mod

    monkeypatch.setattr(
        loader_mod,
        "load_pipeline_config",
        MagicMock(side_effect=FileNotFoundError("missing")),
    )

    with pytest.raises(SystemExit) as exc:
        _run_pipeline_main(monkeypatch, ["--config", str(tmp_path / "missing.yaml")])
    assert "Failed to load pipeline config" in str(exc.value)
