"""Path-parameter ID validators.

IDs in this project always have the shape ``{prefix}_YYYYMMDD_HHMMSS`` (see
``backend/src/config/general.py``). Routers expose these as path parameters
that are later concatenated into filesystem paths. Without validation,
strings like ``../../etc/passwd`` would resolve outside the intended
directory. The ``Annotated`` aliases below force FastAPI to reject any value
that does not match the strict pattern before the handler runs.
"""

from typing import Annotated

from fastapi import Path


def _id_pattern(prefix: str) -> str:
    return rf"^{prefix}_\d{{8}}_\d{{6}}$"


INSPECTION_ID_PATTERN = r"^(inspection|upload)_\d{8}_\d{6}$"
MODEL_ID_PATTERN = _id_pattern("model")
SIMULATION_ID_PATTERN = _id_pattern("simulation")
EVALUATION_ID_PATTERN = _id_pattern("evaluation")
PIPELINE_ID_PATTERN = _id_pattern("pipeline")


InspectionId = Annotated[str, Path(pattern=INSPECTION_ID_PATTERN)]
ModelId = Annotated[str, Path(pattern=MODEL_ID_PATTERN)]
SimulationId = Annotated[str, Path(pattern=SIMULATION_ID_PATTERN)]
EvaluationId = Annotated[str, Path(pattern=EVALUATION_ID_PATTERN)]
PipelineId = Annotated[str, Path(pattern=PIPELINE_ID_PATTERN)]
