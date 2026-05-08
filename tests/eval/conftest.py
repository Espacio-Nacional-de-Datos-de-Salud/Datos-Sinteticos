"""Skip the eval test suite entirely when running under an interpreter that
lacks the evaluation dependencies (e.g. ``.venv_core`` / VSCode default).
These tests are designed to run under ``.venv_eval`` via ``make test-eval``.
"""

from __future__ import annotations

import importlib.util

import pytest

if importlib.util.find_spec("synthcity") is None:
    collect_ignore_glob = ["test_*.py"]
    pytest.skip(
        "synthcity not installed — run `make test-eval` under .venv_eval",
        allow_module_level=True,
    )
