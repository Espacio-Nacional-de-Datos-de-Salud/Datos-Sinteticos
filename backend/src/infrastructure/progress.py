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

Phase titles for the time profiler (``profiler.phase(...)``) are also
centralized here in :class:`ProfilerPhase` so every user-visible phase
label — both the UI progress strings and the profiling report titles —
shares a single Spanish source of truth.
"""

from __future__ import annotations

import json
import os
from enum import StrEnum

INITIAL_LABEL = "Inicializando"


class InspectionPhase(StrEnum):
    LOADING = "Cargando ficheros"
    PREPROCESSING = "Preprocesando y autodetectando esquema"
    SAVING_PROCESSED = "Guardando datos procesados"
    PROFILING_REPORTS = "Generando informes de profiling"


class TrainingPhase(StrEnum):
    PREPARING = "Preparando datos y metadatos"
    TRAINING = "Entrenando generador"
    SAVING_REPORTS = "Guardando informes y estadísticas"


class SimulationPhase(StrEnum):
    LOADING_GENERATOR = "Cargando generador"
    GENERATING = "Generando datos sintéticos"
    APPLYING_RULES = "Aplicando reglas y guardando datos"
    VALIDATION = "Validación y metadatos"


class EvaluationPhase(StrEnum):
    RESOLVING_INPUTS = "Resolviendo entradas"
    RUNNING = "Ejecutando evaluación"


class ProfilerPhase(StrEnum):
    """Centralized titles for every ``profiler.phase(...)`` block.

    Edit a label here and every profiling report — across inspection,
    training, simulation, evaluation, and pipelines — picks it up. A few
    profiler blocks build their label dynamically (per-job and per-metric
    prefixes); see :data:`PROFILER_JOB_PREFIX` and
    :data:`PROFILER_CUSTOM_METRIC_PREFIX` for those.
    """

    # --- Inspection
    INSPECT = "Inspeccionar"
    LOAD_FILES = "Cargar ficheros"
    PREPROCESS_AUTODETECT = "Preprocesar y autodetectar"
    SAVE_PROCESSED_DATA = "Guardar datos procesados"
    WRITE_METADATA = "Escribir metadatos"
    WRITE_PROFILING_REPORTS = "Escribir informes de profiling"

    # --- Training
    SAVE_METADATA_AND_REPORTS = "Guardar metadatos e informes"
    MOSTLYAI_TRAIN = "MostlyAI: entrenamiento"
    SAVE_ARTIFACTS = "Guardar artefactos"

    # --- Simulation
    LOAD_GENERATOR_ARTIFACTS = "Cargar artefactos del generador"
    MOSTLYAI_SIMULATE = "MostlyAI: simulación"
    APPLY_RULES = "Aplicar reglas"
    SAVE_RESULTS = "Guardar resultados"
    SANITY_CHECKS = "Comprobaciones de validez"
    SAVE_METADATA = "Guardar metadatos"

    # --- Evaluation
    LOAD_REAL_DATA = "Cargar datos reales"
    LOAD_SYNTHETIC_DATA = "Cargar datos sintéticos"
    PREPROCESS_REAL_DATA = "Preprocesar datos reales"
    PREPROCESS_SYNTHETIC_DATA = "Preprocesar datos sintéticos"
    ALIGN_DATASETS = "Alinear datasets"
    RUN_METRICS = "Ejecutar métricas"
    SYNTHCITY_METRICS = "Métricas synthcity"
    SAVE_REPORT = "Guardar informe"

    # --- CLI flows (legacy aliases that mirror the high-level steps)
    TRAIN = "Entrenar"
    TRAIN_FROM_INSPECTION = "Entrenar (desde inspección)"
    SIMULATE = "Simular"
    EVALUATE = "Evaluar"


# Prefixes for dynamically-named profiler phases. Kept here so the Spanish
# wording stays alongside its friends and call sites only join with the
# variable bit.
PROFILER_JOB_PREFIX = "Trabajo"  # e.g. "Trabajo[name]: entrenar"
PROFILER_CUSTOM_METRIC_PREFIX = "Métrica personalizada"
PROFILER_SYNTHCITY_METRIC_PREFIX = "Métrica synthcity"


def job_phase_label(job_name: str, action: str) -> str:
    """Render the per-job profiler label (``"Trabajo[<name>]: <action>"``)."""
    return f"{PROFILER_JOB_PREFIX}[{job_name}]: {action}"


def custom_metric_phase_label(metric_name: str) -> str:
    """Render the per-metric profiler label."""
    return f"{PROFILER_CUSTOM_METRIC_PREFIX}: {metric_name}"


def synthcity_metric_phase_label(group: str, metric_name: str) -> str:
    """Render the per-synthcity-metric profiler label.

    Example: ``"Métrica synthcity: stats/jensenshannon_dist"``.
    """
    return f"{PROFILER_SYNTHCITY_METRIC_PREFIX}: {group}/{metric_name}"


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
