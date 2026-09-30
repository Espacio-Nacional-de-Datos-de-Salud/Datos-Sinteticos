"""Run tracking package for the synthetic data pipeline.

Exposes one context-manager tracker per pipeline stage plus the file-hashing
helper used for dataset provenance:

- ``InspectionTracker``: load + preprocess + autodetect runs (inspections/).
- ``ModelTracker``: training runs (models/).
- ``SimulationTracker``: generation runs (simulations/), linked to a parent model.
- ``EvaluationTracker``: synthetic-vs-real metric runs (evaluations/).
- ``PipelineTracker``: overarching multi-job pipelines (pipelines/). Standalone —
  does not inherit from :class:`BaseRunTracker` because its session-log setup
  attaches a single shared file handler across multiple sub-job runs.
- ``BaseRunTracker``: shared lifecycle scaffolding (folder, card, session log,
  exit status) used by the four step trackers.
- ``compute_file_sha256``: SHA-256 digest helper used in model cards.
"""

from backend.src.runs.tracking.base_tracker import BaseRunTracker
from backend.src.runs.tracking.evaluation_tracker import EvaluationTracker
from backend.src.runs.tracking.helpers import compute_file_sha256
from backend.src.runs.tracking.inspection_tracker import InspectionSession, InspectionTracker
from backend.src.runs.tracking.model_tracker import ModelTracker
from backend.src.runs.tracking.pipeline_tracker import PIPELINE_CARD_FILENAME, PipelineTracker
from backend.src.runs.tracking.simulation_tracker import SimulationTracker

__all__ = [
    "PIPELINE_CARD_FILENAME",
    "BaseRunTracker",
    "EvaluationTracker",
    "InspectionSession",
    "InspectionTracker",
    "ModelTracker",
    "PipelineTracker",
    "SimulationTracker",
    "compute_file_sha256",
]
