"""Lightweight time profiling for pipeline phases.

A single ``profiler`` instance collects elapsed time for arbitrary phases via
the ``phase()`` context manager. Phases can be nested; the report indents
sub-phases under their parent and computes percentages against the sum of
top-level phases.

Typical use::

    from backend.src.core.time_profiling import profiler

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
"""

import os
import time
from contextlib import contextmanager
from threading import Lock

from backend.src.core.logging_config import get_logger

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
        """Log a formatted timing report, optionally persisting it to ``output_path``.

        When profiling is disabled or no phases were recorded, this method still
        writes a small explanatory artifact if ``output_path`` is provided.
        """
        report_text = self._build_report_text(header)
        if report_text is None:
            if output_path:
                reason = (
                    "Profiling disabled via DISABLE_PROFILING"
                    if not self._enabled
                    else "No profiling phases were recorded"
                )
                self._write_report_file(output_path, f"{header}:\n{reason}\n")
            return

        logger.info("%s", report_text)
        if output_path:
            self._write_report_file(output_path, report_text + "\n")
        self.reset()

    def _build_report_text(self, header: str) -> str | None:
        """Render the current records as a text table."""
        if not self._enabled or not self._records:
            return None

        records = list(self._records)
        total = sum(secs for depth, _, secs in records if depth == 0)

        name_width = max(len("Phase"), max(len("  " * d + n) for d, n, _ in records))
        sep = "  " + "-" * (name_width + 20)
        lines = [f"  {'Phase':<{name_width}} {'Time (s)':>9}  {'%':>6}", sep]
        for depth, name, secs in records:
            label = "  " * depth + name
            pct = (secs / total * 100) if total and depth == 0 else None
            pct_str = f"{pct:>5.1f}%" if pct is not None else ""
            lines.append(f"  {label:<{name_width}} {secs:>9.2f}  {pct_str:>6}")
        lines.append(sep)
        lines.append(f"  {'TOTAL':<{name_width}} {total:>9.2f}")
        return f"{header}:\n" + "\n".join(lines)

    def _write_report_file(self, output_path: str, content: str) -> None:
        """Persist the profiling report to disk without crashing the caller."""
        try:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as handle:
                handle.write(content)
        except OSError as error:
            logger.warning("Could not write profiling report to %s: %s", output_path, error)

    def reset(self) -> None:
        """Drop all recorded phases."""
        with self._lock:
            self._records.clear()
            self._depth = 0


profiler = Profiler()
