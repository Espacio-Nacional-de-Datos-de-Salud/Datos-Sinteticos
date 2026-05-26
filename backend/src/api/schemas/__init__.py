from pydantic import BaseModel, Field


class CancelResponse(BaseModel):
    """Response returned by any ``POST /{resource}/{id}/cancel`` endpoint."""

    id: str
    status: str
    message: str = ""


class TimeProfilingPhase(BaseModel):
    """One phase entry in a structured time-profiling report."""

    name: str
    depth: int = 0
    seconds: float
    percent: float | None = None


class TimeProfilingReport(BaseModel):
    """Structured timing breakdown emitted by the profiler at the end of a run."""

    header: str = ""
    total_seconds: float = 0.0
    phases: list[TimeProfilingPhase] = []
    note: str | None = Field(
        default=None,
        description="Set when profiling was disabled or no phases were recorded.",
    )


def load_time_profiling_report(folder: str) -> TimeProfilingReport | None:
    """Read ``time_profiling_report.json`` from a run folder.

    Returns ``None`` when the file is missing or unreadable; the empty (no-phases)
    payload is returned as-is so callers can surface the explanatory ``note``.
    """
    import json
    import os

    from backend.src.config.general import TIME_PROFILING_REPORT_FILENAME

    path = os.path.join(folder, TIME_PROFILING_REPORT_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            payload = json.load(fh)
    except (OSError, ValueError):
        return None
    return TimeProfilingReport.model_validate(payload)
