"""Tests for the evaluation subprocess runner.

`_run_subprocess` launches `.venv_eval` to run the evaluation as a child
process. These tests stub `subprocess.Popen` so we can verify:

- stdout lines are streamed to the project logger and to ``subprocess.log``
- a non-zero exit code marks the eval card as failed and attaches the tail
  of stdout to the card as ``error_traceback``
- a zero exit code leaves the card untouched
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from backend.src.config.general import EVAL_CARD_FILENAME
from backend.src.core.card_io import write_json
from backend.src.services import evaluation as evaluation_service


class FakePopen:
    """Minimal stand-in for `subprocess.Popen` returned object."""

    def __init__(self, lines: list[str], returncode: int) -> None:
        self.stdout = iter(f"{line}\n" for line in lines)
        self._returncode = returncode

    def wait(self) -> int:
        return self._returncode


def _seed_card(eval_dir: Path, evaluation_id: str) -> Path:
    """Write an initial eval card to the eval directory."""
    card_path = eval_dir / EVAL_CARD_FILENAME
    write_json(
        str(card_path),
        {"evaluation_id": evaluation_id, "status": "in_progress"},
    )
    return card_path


@pytest.fixture
def seeded_eval_dir(tmp_path: Path) -> Path:
    """Create and seed an eval directory with an in-progress card."""
    eval_dir = tmp_path / "eval"
    eval_dir.mkdir()
    _seed_card(eval_dir, "eval_1")
    return eval_dir


def _invoke(
    monkeypatch: pytest.MonkeyPatch,
    eval_dir: Path,
    lines: list[str],
    returncode: int,
) -> bool:
    """Run `_run_subprocess` with mocked Popen, capturing the subprocess call.

    The call arguments are stored in `_invoke.captured` dict with keys `cmd`
    and `kwargs`, allowing tests to inspect what subprocess.Popen was called with.
    """
    monkeypatch.setattr(evaluation_service, "EVAL_PYTHON_PATH", "/fake/python")

    captured: dict = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return FakePopen(lines, returncode)

    import subprocess

    monkeypatch.setattr(subprocess, "Popen", fake_popen)

    succeeded = evaluation_service._run_subprocess(
        real_data=["/data/real.csv"],
        synthetic_files=["/data/synth.csv"],
        eval_dir=str(eval_dir),
        simulation_dir="/sims/sim_1",
        model_id="model_1",
        simulation_id="sim_1",
        evaluation_id="eval_1",
    )
    _invoke.captured = captured  # type: ignore[attr-defined]
    return succeeded


def test_run_subprocess_streams_stdout_to_log_file(
    seeded_eval_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_dir = seeded_eval_dir

    captured_records: list[logging.LogRecord] = []

    class _ListHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured_records.append(record)

    handler = _ListHandler(level=logging.INFO)
    service_logger = logging.getLogger("backend.src.services.evaluation")
    service_logger.addHandler(handler)
    try:
        succeeded = _invoke(monkeypatch, eval_dir, ["hello", "world"], returncode=0)
    finally:
        service_logger.removeHandler(handler)

    assert succeeded is True
    log_contents = (eval_dir / "subprocess.log").read_text()
    assert "hello" in log_contents and "world" in log_contents
    messages = [record.getMessage() for record in captured_records]
    assert "[eval] hello" in messages and "[eval] world" in messages


def test_run_subprocess_non_zero_marks_card_failed_with_traceback(
    seeded_eval_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_dir = seeded_eval_dir
    card_path = eval_dir / EVAL_CARD_FILENAME

    succeeded = _invoke(
        monkeypatch,
        eval_dir,
        ["loading data", "Traceback (most recent call last):", "ValueError: boom"],
        returncode=1,
    )

    assert succeeded is False
    card = json.loads(card_path.read_text())
    assert card["status"] == "failed"
    assert "exited with code 1" in card["error_message"]
    assert "ValueError: boom" in card["error_traceback"]


def test_run_subprocess_builds_expected_command(
    seeded_eval_dir: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    eval_dir = seeded_eval_dir

    _invoke(monkeypatch, eval_dir, [], returncode=0)
    cmd = _invoke.captured["cmd"]  # type: ignore[attr-defined]

    assert cmd[0] == "/fake/python"
    assert cmd[1:4] == ["-m", "backend.src.evaluation", "--real-data"]
    assert "/data/real.csv" in cmd
    assert "/data/synth.csv" in cmd
    assert "--simulation-id" in cmd and "sim_1" in cmd
    assert "--model-id" in cmd and "model_1" in cmd
