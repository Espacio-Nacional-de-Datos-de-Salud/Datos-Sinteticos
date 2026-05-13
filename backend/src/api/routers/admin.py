"""Cross-resource admin endpoints (e.g. global purge)."""

from backend.src.sessions.configs import bootstrap_configs, clean_configs
from backend.src.runs.catalog.evaluations import purge_all_evaluations
from backend.src.runs.catalog.inspections import purge_all_inspections
from backend.src.runs.catalog.models import purge_all_models
from backend.src.runs.catalog.simulations import purge_all_simulations
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/admin", tags=["Admin"])


class PurgeAllResult(BaseModel):
    inspections: list[str]
    models: list[str]
    simulations: list[str]
    evaluations: list[str]
    configs_removed: list[str]
    configs_created: list[str]


@router.delete("/purge-all", response_model=PurgeAllResult)
def purge_all() -> PurgeAllResult:
    """Wipe every inspection/model/simulation/evaluation folder and reset configs.

    Destructive — deletes completed runs too. The configs directory is reset
    from templates so the app keeps a working baseline.
    """
    inspections = purge_all_inspections()
    models = purge_all_models()
    simulations = purge_all_simulations()
    evaluations = purge_all_evaluations()
    clean_result = clean_configs()
    bootstrap_result = bootstrap_configs()
    return PurgeAllResult(
        inspections=inspections,
        models=models,
        simulations=simulations,
        evaluations=evaluations,
        configs_removed=clean_result["removed"],
        configs_created=bootstrap_result["created"],
    )
