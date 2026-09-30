"""Pydantic schemas for the configs discovery and editing endpoints.

This module defines API payload shapes used by the ``/configs`` router.

Important terminology:
- ``ConfigScope`` means config category/grouping in this project.
- It does NOT mean OAuth scope, permission scope, or programming-variable
  scope.

Why this exists:
- The frontend can filter large config lists by functional area.
- The backend can expose a stable, explicit grouping field in responses.
- Both sides avoid re-implementing folder-classification logic ad hoc.
"""

from enum import Enum
from typing import Literal

from pydantic import BaseModel


class ConfigScope(str, Enum):
    """Category label used to group config files in the API.

    - It answers: "what functional area does this config belong to?"

    Folder-based mapping used by the backend classifier:
    - ``all``:
      include every supported config file under ``backend/config/``.
    - ``pipeline``:
      include pipeline-level config files under ``backend/config/pipelines/``
      except the dedicated rules subfolder.
    - ``evaluation``:
      include ``evaluation.yaml`` (and any future evaluation-focused files).
    - ``rules``:
      include global rules files (for example ``rules.yaml`` / ``rules.py``)
      and pipeline-specific rules under ``backend/config/pipelines/rules/``.

    Practical reason this enum exists:
    - ``GET /configs?scope=...`` needs a canonical filter value.
    - ``ConfigFile.scope`` and ``ConfigContent.scope`` need a consistent,
      machine-readable grouping shared by frontend and backend.
    """

    ALL = "all"
    PIPELINE = "pipeline"
    EVALUATION = "evaluation"
    RULES = "rules"


class ConfigFile(BaseModel):
    """A config file available for the frontend to list/edit.

    ``id`` is the relative path of the real file under ``backend/config/``
    (e.g. ``rules.yaml``, ``pipelines/example_pipeline.yaml``). Pass it
    directly to the ``GET/PUT/DELETE /configs/{id}`` endpoints — friendly
    aliases like ``rules`` or ``mostly_ai`` are accepted there too, but the
    id returned here is always the canonical path form.

    ``exists`` is ``True`` when the real ``*.yaml`` file has been created
    (by ``make config`` or by editing through the API). When ``False``, the
    user still needs to bootstrap the file from its ``*.example.yaml``
    template.
    """

    id: str
    path: str
    name: str
    size_bytes: int
    scope: ConfigScope
    exists: bool


class ConfigContent(BaseModel):
    """Full content payload for a single config, returned by ``GET /configs/{id}``."""

    id: str
    scope: ConfigScope
    exists: bool
    example_path: str
    path: str
    content: str
    example_content: str
    format: Literal["yaml", "json", "python", "toml"]


class ConfigUpdate(BaseModel):
    """Request body for ``PUT /configs/{id}``."""

    content: str


class ConfigBulkResult(BaseModel):
    """Response for bulk config operations (bootstrap / clean / reset)."""

    created: list[str] = []
    skipped: list[str] = []
    removed: list[str] = []
