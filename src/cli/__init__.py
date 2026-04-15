"""CLI layer placeholder.

Future home of interactive I/O helpers used by the command-line entry points
(main.py, pipeline.py). Isolating this layer keeps src/services/ and
src/synthesis.py free of user-interaction code, making them API-safe.

Example future structure:
    src/cli/
    ├── __init__.py
    ├── interactive.py       ← file selection prompts, user confirmations
    └── generator_selector.py  ← interactive model picker (extracted from synthesis.py)
"""
