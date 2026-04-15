"""MLOps tracking package for the synthetic data pipeline.

Exposes three context-manager trackers — one per pipeline stage (training, simulation, evaluation)
 — plus the file-hashing helper used for dataset provenance:

- ``ModelTracker``: training runs (models/).
- ``SimulationTracker``: generation runs (simulations/), linked to a parent model.
- ``PipelineTracker``: overarching multi-job pipelines (pipelines/).
- ``compute_file_sha256``: SHA-256 digest helper used in model cards.
"""

from src.core.tracking.evaluation_tracker import EvaluationTracker
from src.core.tracking.helpers import compute_file_sha256
from src.core.tracking.model_tracker import ModelTracker
from src.core.tracking.pipeline_tracker import PIPELINE_SUMMARY_FILENAME, PipelineTracker
from src.core.tracking.simulation_tracker import SimulationTracker

__all__ = [
    "PIPELINE_SUMMARY_FILENAME",
    "EvaluationTracker",
    "ModelTracker",
    "PipelineTracker",
    "SimulationTracker",
    "compute_file_sha256",
]
