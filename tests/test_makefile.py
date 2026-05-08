"""Tests for Makefile execution targets.

These tests exercise the Makefile directly with a temporary general.yaml and a
stub Python executable so we can validate the shell contract without launching
the real backend.
"""

from __future__ import annotations

import json
import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAKEFILE_PATH = PROJECT_ROOT / "Makefile"


def _write_fake_python(tmp_path: Path) -> tuple[Path, Path]:
    """Create a fake Python executable that logs calls and executes `-c` snippets."""
    log_path = tmp_path / "python_calls.json"
    script_path = tmp_path / "fake_python"
    # Shebang to the test runner's interpreter so `-c` snippets from the
    # Makefile (which import yaml) resolve against the same env where this
    # test imports yaml itself. /usr/bin/env python3 is not guaranteed to
    # have project deps installed.
    script_path.write_text(
        f"#!{sys.executable}\n"
        "from __future__ import annotations\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "from pathlib import Path\n"
        "\n"
        "log_path = Path(os.environ['MAKEFILE_TEST_LOG'])\n"
        "entries = json.loads(log_path.read_text()) if log_path.exists() else []\n"
        "entries.append(sys.argv[1:])\n"
        "log_path.write_text(json.dumps(entries))\n"
        "\n"
        "if len(sys.argv) >= 3 and sys.argv[1] == '-c':\n"
        "    exec(sys.argv[2], {'__name__': '__main__'})\n"
        "    raise SystemExit(0)\n"
        "if len(sys.argv) >= 3 and sys.argv[1] == '-m':\n"
        "    raise SystemExit(0)\n"
        "raise SystemExit(f'Unsupported args: {sys.argv[1:]}')\n",
        encoding="utf-8",
    )
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)
    return script_path, log_path


def _run_make(
    target: str,
    fake_python: Path,
    log_path: Path,
    general_config: Path,
) -> subprocess.CompletedProcess[str]:
    """Run a Makefile target with overridden config and Python executable."""
    env = os.environ.copy()
    env["MAKEFILE_TEST_LOG"] = str(log_path)
    return subprocess.run(
        [
            "make",
            "-f",
            str(MAKEFILE_PATH),
            target,
            f"CORE_PYTHON={fake_python}",
            f"GENERAL_CONFIG={general_config}",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.mark.parametrize(
    ("target", "expected_mode"),
    [("inspect", "i"), ("train", "t"), ("simulate", "s")],
)
def test_make_targets_update_execution_mode_and_invoke_backend(
    tmp_path: Path,
    target: str,
    expected_mode: str,
) -> None:
    fake_python, log_path = _write_fake_python(tmp_path)
    general_config = tmp_path / "general.yaml"
    general_config.write_text(
        yaml.safe_dump(
            {
                "settings": {"data_subpath": ""},
                "execution": {"mode": "x", "file_paths": None},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = _run_make(target, fake_python, log_path, general_config)

    assert result.returncode == 0, result.stderr or result.stdout
    updated = yaml.safe_load(general_config.read_text(encoding="utf-8"))
    assert updated["execution"]["mode"] == expected_mode

    calls = json.loads(log_path.read_text(encoding="utf-8"))
    assert calls[0][0] == "-c"
    assert calls[1] == ["-m", "backend.src.cli", "--mode", expected_mode]


def test_make_cli_invokes_interactive_cli_without_setting_mode(tmp_path: Path) -> None:
    fake_python, log_path = _write_fake_python(tmp_path)
    general_config = tmp_path / "general.yaml"
    general_config.write_text(
        yaml.safe_dump(
            {
                "settings": {"data_subpath": ""},
                "execution": {"mode": "x", "file_paths": None},
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    result = _run_make("cli", fake_python, log_path, general_config)

    assert result.returncode == 0, result.stderr or result.stdout
    updated = yaml.safe_load(general_config.read_text(encoding="utf-8"))
    assert updated["execution"]["mode"] == "x"

    calls = json.loads(log_path.read_text(encoding="utf-8"))
    assert calls == [["-m", "backend.src.cli"]]


def test_make_target_fails_cleanly_when_general_config_is_missing(tmp_path: Path) -> None:
    fake_python, log_path = _write_fake_python(tmp_path)
    missing_config = tmp_path / "missing-general.yaml"

    result = _run_make("inspect", fake_python, log_path, missing_config)

    assert result.returncode != 0
    combined_output = f"{result.stdout}\n{result.stderr}"
    assert "Run make config first" in combined_output

    calls = json.loads(log_path.read_text(encoding="utf-8"))
    assert len(calls) == 1
    assert calls[0][0] == "-c"
