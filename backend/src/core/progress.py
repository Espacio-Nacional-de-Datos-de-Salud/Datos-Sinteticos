"""Job progress catalog and card update helpers.

Long-running flows (inspection, training, simulation, evaluation) write a
``progress`` dict into their session card while ``status`` is ``in_progress``.
The frontend reads it through the catalog summaries and renders a coarse
"step X of N — label" indicator with a progress bar.

Semantics: ``step`` is the number of phases ALREADY COMPLETED. So step=0 with
total=4 means the run is starting work on phase 1, and step=3 with total=4
means three phases are done and the fourth is in progress. The card never
needs to be stamped with step==total — when the run finishes, ``status``
flips to ``completed`` and the indicator is hidden.

Phase definitions for every flow live in this module so the full progress
contract for the UI can be reviewed and edited in one place. Adding,
renaming, or reordering phases happens here; call sites only reference
named members.
"""

from __future__ import annotations

import json
import os
from enum import StrEnum

INITIAL_LABEL = "Initializing"


class InspectionPhase(StrEnum):
    LOADING = "Loading files"
    PREPROCESSING = "Preprocessing and auto-detecting schema"
    SAVING_PROCESSED = "Saving processed data"
    PROFILING_REPORTS = "Writing profiling reports"


class TrainingPhase(StrEnum):
    PREPARING = "Preparing data and metadata"
    TRAINING = "Training generator"
    SAVING_REPORTS = "Saving reports and statistics"


class SimulationPhase(StrEnum):
    LOADING_GENERATOR = "Loading generator"
    GENERATING = "Generating synthetic data"
    APPLYING_RULES = "Applying rules and saving data"
    VALIDATION = "Validation and metadata"


class EvaluationPhase(StrEnum):
    RESOLVING_INPUTS = "Resolving inputs"
    RUNNING = "Running evaluation"


INSPECTION_PHASES: list[str] = list(InspectionPhase)
# Profiling is the optional final phase; drop it when the user disables it
# so the progress bar reflects the real number of phases that will run.
INSPECTION_PHASES_NO_PROFILING: list[str] = [
    InspectionPhase.LOADING,
    InspectionPhase.PREPROCESSING,
    InspectionPhase.SAVING_PROCESSED,
]
TRAINING_PHASES: list[str] = list(TrainingPhase)
SIMULATION_PHASES: list[str] = list(SimulationPhase)
EVALUATION_PHASES: list[str] = list(EvaluationPhase)


def initial_progress(phases: list[str]) -> dict:
    """Build the ``progress`` payload for a session card at creation time."""
    return {"step": 0, "total": len(phases), "label": INITIAL_LABEL}


def advance_progress(card_path: str, phases: list[str], current_phase: str) -> None:
    """Mark ``current_phase`` as the phase now in progress on the card.

    ``step`` is set to the index of ``current_phase`` (i.e. the count of
    phases completed before it) and ``total`` to ``len(phases)``.
    """
    index = phases.index(current_phase)
    _write_progress(card_path, index, len(phases), current_phase)


def _write_progress(card_path: str, step: int, total: int, label: str) -> None:
    if not os.path.exists(card_path):
        return
    try:
        with open(card_path, encoding="utf-8") as handle:
            card = json.load(handle)
        card["progress"] = {"step": step, "total": total, "label": label}
        with open(card_path, "w", encoding="utf-8") as handle:
            json.dump(card, handle, indent=2, ensure_ascii=False, default=str)
    except Exception:
        pass
