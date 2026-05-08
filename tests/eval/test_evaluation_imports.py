"""Smoke test: every module under backend/src/evaluation/ imports cleanly.

Runs under .venv_eval (where synthcity, KeOps, pycanon, etc. are installed).
Catches breakage from renamed symbols, moved modules, or stale imports
before they reach the frontend through a subprocess crash.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

EVAL_PKG_ROOT = Path(__file__).resolve().parents[2] / "backend" / "src" / "evaluation"


def _discover_modules() -> list[str]:
    modules: list[str] = []
    for path in sorted(EVAL_PKG_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(EVAL_PKG_ROOT.parents[2])
        parts = list(rel.with_suffix("").parts)
        if parts[-1] == "__init__":
            parts = parts[:-1]
        if parts[-1] == "__main__":
            # __main__ runs argparse on import side effects only via if __name__ guard
            pass
        modules.append(".".join(parts))
    return modules


@pytest.mark.parametrize("module_name", _discover_modules())
def test_module_imports(module_name: str) -> None:
    importlib.import_module(module_name)
