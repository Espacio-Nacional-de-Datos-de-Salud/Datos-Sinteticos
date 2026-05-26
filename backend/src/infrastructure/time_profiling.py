"""Lightweight time profiling for pipeline phases.

A single ``profiler`` instance collects elapsed time for arbitrary phases via
the ``phase()`` context manager. Phases can be nested; the report indents
sub-phases under their parent and computes percentages against the sum of
top-level phases.

Typical use::

    from backend.src.infrastructure.time_profiling import profiler

    with profiler.phase("load data"):
        ...
    with profiler.phase("evaluate"):
        with profiler.phase("synthcity metrics"):
            ...
        with profiler.phase("custom: dcr"):
            ...

    profiler.report("Run timing")

Disable globally with the ``DISABLE_PROFILING=1`` environment variable: phases
become no-ops and ``report()`` does nothing.

The structured report written to disk is JSON with this shape::

    {
        "header": "Training timing breakdown",
        "total_seconds": 12.34,
        "phases": [
            {"name": "load files", "depth": 0, "seconds": 1.2, "percent": 9.7},
            {"name": "preprocess",  "depth": 0, "seconds": 4.5, "percent": 36.5},
            {"name": "autodetect",  "depth": 1, "seconds": 2.1, "percent": null},
            ...
        ]
    }

The ``percent`` field is populated for top-level (``depth == 0``) phases and
``null`` for nested ones.
"""

import json
import os
import time
from contextlib import contextmanager
from threading import Lock

from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)


class Profiler:
    """Collects timing records for nested phases and prints a summary."""

    def __init__(self) -> None:
        self._records: list[tuple[int, str, float]] = []
        self._depth: int = 0
        self._lock = Lock()
        self._enabled: bool = os.environ.get("DISABLE_PROFILING", "") not in ("1", "true", "yes")

    @contextmanager
    def phase(self, name: str):
        """Context manager that records the elapsed time of the wrapped block."""
        if not self._enabled:
            yield
            return

        depth = self._depth
        self._depth += 1
        t0 = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - t0
            self._depth -= 1
            with self._lock:
                self._records.append((depth, name, elapsed))

    def report(self, header: str = "Timing breakdown", output_path: str | None = None) -> None:
        """Log a formatted timing report, optionally persisting JSON to ``output_path``.

        When profiling is disabled or no phases were recorded, this method still
        writes a small explanatory JSON artifact if ``output_path`` is provided.
        """
        payload = self.to_dict(header)
        if payload is None:
            if output_path:
                reason = (
                    "Profiling disabled via DISABLE_PROFILING"
                    if not self._enabled
                    else "No profiling phases were recorded"
                )
                empty = {
                    "header": header,
                    "total_seconds": 0.0,
                    "phases": [],
                    "note": reason,
                }
                self._write_json(output_path, empty)
            return

        text = self._format_text(payload)
        logger.info("%s", text)
        if output_path:
            self._write_json(output_path, payload)
        self.reset()

    def to_dict(self, header: str = "Timing breakdown") -> dict | None:
        """Return the current records as a JSON-serializable dict, or None."""
        if not self._enabled or not self._records:
            return None
        return self._records_to_payload(list(self._records), header)

    def mark(self) -> int:
        """Return a marker for the current end of the records list.

        Pair with ``write_snapshot(marker, ...)`` to persist only the records
        appended after the marker — used by the pipeline executor to drop a
        per-step JSON into each child run's folder without disturbing the
        pipeline-level report.
        """
        with self._lock:
            return len(self._records)

    def write_snapshot(self, start_index: int, header: str, output_path: str) -> None:
        """Write a JSON report of records appended since ``start_index``.

        Records are re-rooted: the smallest depth in the slice becomes depth 0
        so the snapshot renders as a self-contained tree even though it lived
        inside a larger phase stack. Silently skips when profiling is disabled,
        the slice is empty, or the path cannot be written.
        """
        if not self._enabled:
            return
        with self._lock:
            slice_records = list(self._records[start_index:])
        if not slice_records:
            return
        base_depth = min(depth for depth, _, _ in slice_records)
        rerooted = [(depth - base_depth, name, secs) for depth, name, secs in slice_records]
        payload = self._records_to_payload(rerooted, header)
        if payload is not None:
            self._write_json(output_path, payload)

    @staticmethod
    def _records_to_payload(records: list[tuple[int, str, float]], header: str) -> dict | None:
        if not records:
            return None
        total = sum(secs for depth, _, secs in records if depth == 0)
        phases = []
        for depth, name, secs in records:
            pct = (secs / total * 100) if total and depth == 0 else None
            phases.append(
                {
                    "name": name,
                    "depth": depth,
                    "seconds": round(secs, 4),
                    "percent": round(pct, 2) if pct is not None else None,
                }
            )
        return {
            "header": header,
            "total_seconds": round(total, 4),
            "phases": phases,
        }

    @staticmethod
    def _format_text(payload: dict) -> str:
        """Render a payload (from ``to_dict``) as the legacy text table for logs."""
        header = payload["header"]
        phases = payload["phases"]
        total = payload["total_seconds"]

        if not phases:
            return f"{header}:\n  (no phases recorded)"

        name_width = max(len("Phase"), max(len("  " * p["depth"] + p["name"]) for p in phases))
        sep = "  " + "-" * (name_width + 20)
        lines = [f"  {'Phase':<{name_width}} {'Time (s)':>9}  {'%':>6}", sep]
        for p in phases:
            label = "  " * p["depth"] + p["name"]
            pct_str = f"{p['percent']:>5.1f}%" if p["percent"] is not None else ""
            lines.append(f"  {label:<{name_width}} {p['seconds']:>9.2f}  {pct_str:>6}")
        lines.append(sep)
        lines.append(f"  {'TOTAL':<{name_width}} {total:>9.2f}")
        return f"{header}:\n" + "\n".join(lines)

    def _write_json(self, output_path: str, payload: dict) -> None:
        """Persist the profiling report to disk without crashing the caller."""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except OSError as error:
            logger.warning("Could not write profiling report to %s: %s", output_path, error)

    def reset(self) -> None:
        """Drop all recorded phases."""
        with self._lock:
            self._records.clear()
            self._depth = 0


profiler = Profiler()
