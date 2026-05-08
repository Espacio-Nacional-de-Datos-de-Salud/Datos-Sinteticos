"""pytest configuration and initialization.

Adds the project root directory to sys.path so that test imports resolve
relative to the project root (e.g., `from backend.src.core import ...`).
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
