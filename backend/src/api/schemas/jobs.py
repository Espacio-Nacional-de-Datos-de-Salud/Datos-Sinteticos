"""Shared Pydantic schemas for job lifecycle fields used across catalogs."""

from pydantic import BaseModel


class JobProgress(BaseModel):
    """Coarse progress indicator written by long-running flows.

    ``step`` counts phases COMPLETED so far (0..total). ``label`` describes
    the phase currently in progress. Surfaced only while the owning job's
    ``status`` is ``in_progress``; once it flips to ``completed`` the field
    is no longer relevant.
    """

    step: int = 0
    total: int = 0
    label: str = ""
