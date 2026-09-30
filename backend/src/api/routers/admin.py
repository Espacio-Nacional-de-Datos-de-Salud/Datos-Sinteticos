"""Cross-resource admin endpoints (e.g. global purge)."""

import os
import signal
from pathlib import Path

import psutil
from fastapi import APIRouter
from pydantic import BaseModel

from backend.src.config.general import SIM_CARD_FILENAME, SIMULATIONS_DIR
from backend.src.infrastructure.logging_config import get_logger
from backend.src.runs.card_io import read_json, update_card_status
from backend.src.runs.catalog.evaluations import purge_all_evaluations
from backend.src.runs.catalog.inspections import purge_all_inspections
from backend.src.runs.catalog.models import purge_all_models
from backend.src.runs.catalog.simulations import purge_all_simulations
from backend.src.sessions.business_rules_configurations import purge_all_brcs
from backend.src.sessions.configs import bootstrap_configs, clean_configs

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["Admin"])

_REPO_ROOT = str(Path(__file__).resolve().parents[4])
_VENV_PYTHON = os.path.join(_REPO_ROOT, ".venv_core", "bin", "python")
_SAFE_PATTERNS = [
    "uvicorn backend.src.api.main",
    "ruff server",
    "next dev",
    "next-server",
]


def _cmd(proc: psutil.Process) -> str:
    try:
        return " ".join(proc.cmdline())
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def _exe(proc: psutil.Process) -> str:
    try:
        return proc.exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return ""


def _is_safe(proc: psutil.Process) -> bool:
    cmd = _cmd(proc)
    return any(pat in cmd for pat in _SAFE_PATTERNS)


def _has_live_safe_parent(proc: psutil.Process) -> bool:
    try:
        parent = proc.parent()
        return parent is not None and parent.is_running() and _is_safe(parent)
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


def _is_orphaned_bg_process(proc: psutil.Process) -> bool:
    try:
        if proc.pid == os.getpid():
            return False
        if _is_safe(proc):
            return False

        cmd = _cmd(proc)
        exe = _exe(proc)

        # Category A: explicit cmdline match (repo path or mostlyai)
        if cmd and (_REPO_ROOT in cmd or "mostlyai" in cmd.lower()):
            return not _has_live_safe_parent(proc)

        # Category B: orphaned multiprocessing child using our venv interpreter.
        if exe and exe.startswith(_VENV_PYTHON):
            return not _has_live_safe_parent(proc)

        return False
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False


class KillBgResult(BaseModel):
    killed_pids: list[int]
    cancelled_simulations: list[str]


class PurgeAllResult(BaseModel):
    inspections: list[str]
    business_rules: list[str]
    models: list[str]
    simulations: list[str]
    evaluations: list[str]
    configs_removed: list[str]
    configs_created: list[str]


@router.post("/kill-bg", response_model=KillBgResult)
def kill_bg_processes() -> KillBgResult:
    """Kill orphaned SDK / generation background processes.

    Terminates any background process that belongs to this repo's Python
    environment (or has 'mostlyai' in its command line) but is NOT the
    uvicorn API server, the Next.js frontend, or the ruff LSP.

    Also marks every in-progress simulation card as cancelled so the UI
    reflects the clean state immediately.
    """
    killed: list[int] = []
    for proc in psutil.process_iter():
        if _is_orphaned_bg_process(proc):
            try:
                os.kill(proc.pid, signal.SIGKILL)
                logger.info("kill-bg: killed PID %d (%s)", proc.pid, _cmd(proc)[:80])
                killed.append(proc.pid)
            except ProcessLookupError:
                pass

    cancelled: list[str] = []
    sims_dir = Path(SIMULATIONS_DIR)
    if sims_dir.is_dir():
        for card_path in sims_dir.glob(f"*/{SIM_CARD_FILENAME}"):
            try:
                card = read_json(str(card_path))
                if card.get("status") == "in_progress":
                    update_card_status(str(card_path), "cancelled")
                    sim_id = card.get("simulation_id", card_path.parent.name)
                    logger.info("kill-bg: marked simulation %s as cancelled", sim_id)
                    cancelled.append(sim_id)
            except Exception:
                pass

    return KillBgResult(killed_pids=killed, cancelled_simulations=cancelled)


@router.delete("/purge-all", response_model=PurgeAllResult)
def purge_all() -> PurgeAllResult:
    """Wipe every inspection/model/simulation/evaluation folder and reset configs.

    Destructive — deletes completed runs too. The configs directory is reset
    from templates so the app keeps a working baseline.
    """
    inspections = purge_all_inspections()
    business_rules = purge_all_brcs()
    models = purge_all_models()
    simulations = purge_all_simulations()
    evaluations = purge_all_evaluations()
    clean_result = clean_configs()
    bootstrap_result = bootstrap_configs()
    return PurgeAllResult(
        inspections=inspections,
        business_rules=business_rules,
        models=models,
        simulations=simulations,
        evaluations=evaluations,
        configs_removed=clean_result["removed"],
        configs_created=bootstrap_result["created"],
    )
