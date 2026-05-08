"""MLOps tracking package for the synthetic data pipeline.

Exposes three context-manager trackers — one per pipeline stage (training, simulation, evaluation)
 — plus the file-hashing helper used for dataset provenance:

- ``ModelTracker``: training runs (models/).
- ``SimulationTracker``: generation runs (simulations/), linked to a parent model.
- ``PipelineTracker``: overarching multi-job pipelines (pipelines/).
- ``compute_file_sha256``: SHA-256 digest helper used in model cards.
"""

from backend.src.core.tracking.evaluation_tracker import EvaluationTracker
from backend.src.core.tracking.helpers import compute_file_sha256
from backend.src.core.tracking.model_tracker import ModelTracker
from backend.src.core.tracking.pipeline_tracker import PIPELINE_CARD_FILENAME, PipelineTracker
from backend.src.core.tracking.simulation_tracker import SimulationTracker

__all__ = [
    "PIPELINE_CARD_FILENAME",
    "EvaluationTracker",
    "ModelTracker",
    "PipelineTracker",
    "SimulationTracker",
    "compute_file_sha256",
]
