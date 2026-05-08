"""Runtime settings package.

This package exposes Python-level settings consumed directly by application
code (constants, dataclasses, and yaml-backed values), for example from
``general.py``, ``execution.py``, and ``evaluation.py``.

Important distinction:
- ``backend.src.config`` resolves *runtime values* for the app.
- ``backend.src.services.configs`` manages *config files* on disk
        (list/read/write/reset real ``*.yaml`` files under ``backend/config``,
        each of which is bootstrapped from a committed ``*.example.yaml``
        template via ``make config``).
"""
