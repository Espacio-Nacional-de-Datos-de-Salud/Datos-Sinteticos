"""In-process cancellation registry for background jobs.

Provides a thread-safe per-job cancellation signal using ``threading.Event``.
Jobs register when they start, check the event at natural checkpoints, and
unregister when they finish. The cancel endpoint sets the event and writes
the card status to ``"cancelled"`` before returning, so the card reflects
the intent immediately even if the background thread hasn't polled yet.
"""

import threading


class JobCancelled(Exception):
    """Raised inside a running job to propagate an external cancel request."""


_registry: dict[str, threading.Event] = {}


def register(job_id: str) -> threading.Event:
    """Register a new cancellable job and return its cancellation event."""
    event = threading.Event()
    _registry[job_id] = event
    return event


def request_cancel(job_id: str) -> bool:
    """Signal cancellation for a running job. Returns True if it was registered."""
    event = _registry.get(job_id)
    if event is not None:
        event.set()
        return True
    return False


def unregister(job_id: str) -> None:
    """Remove a completed job from the registry."""
    _registry.pop(job_id, None)
