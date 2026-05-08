"""Helpers to package catalog folders as in-memory zip downloads.

Each ``build_*_bundle`` function resolves the absolute paths and the
``arcname`` (path inside the resulting archive) for a download case, and
returns a :class:`DownloadBundle`. The router layer turns the bundle
into a streaming HTTP response via :func:`build_zip_stream`.

Bundles are intentionally side-effect-free: they raise typed errors when
folders or required files are missing so the API layer can map each case
to a specific HTTP status.
"""

import io
import os
import zipfile
from dataclasses import dataclass

from backend.src.config.general import (
    EVALUATIONS_DIR,
    GENERATOR_ZIP_NAME,
    INSPECTIONS_DIR,
    METADATA_FILENAME,
    MODELS_DIR,
    PIPELINES_DIR,
    PROFILING_REPORTS_DIRNAME,
    SIMULATIONS_DIR,
)
from backend.src.core.catalog.pipelines import get_pipeline_artifact_ids
from backend.src.core.errors import (
    EvaluationNotFoundError,
    GeneratorEssentialsIncompleteError,
    InspectionNotFoundError,
    InspectionProfilingNotFoundError,
    ModelNotFoundError,
    PipelineNotFoundError,
    SimulationNotFoundError,
    SyntheticDataNotFoundError,
)

RULE_MANAGER_FILENAME = "rule_manager.json"
SYNTHETIC_DATA_DIRNAME = "synthetic_data"


@dataclass(frozen=True)
class DownloadBundle:
    """A set of files to be packaged into a single zip download.

    Attributes:
        archive_name: Suggested filename for the resulting zip
            (``Content-Disposition`` value).
        members: ``(absolute_path, arcname)`` pairs to include. ``arcname``
            is the relative path stored inside the archive.
    """

    archive_name: str
    members: list[tuple[str, str]]


def build_zip_stream(bundle: DownloadBundle) -> io.BytesIO:
    """Build an in-memory zip from a bundle and return a seekable buffer.

    The buffer is rewound to position 0 so it can be passed straight to a
    ``StreamingResponse``.
    """
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, arcname in bundle.members:
            archive.write(path, arcname)
    buffer.seek(0)
    return buffer


def _walk_folder_members(folder: str, root_arcname: str) -> list[tuple[str, str]]:
    """Collect every file under ``folder`` with arcnames rooted at ``root_arcname``."""
    members: list[tuple[str, str]] = []
    for dirpath, _, filenames in os.walk(folder):
        for fname in filenames:
            abs_path = os.path.join(dirpath, fname)
            relative = os.path.relpath(abs_path, folder)
            members.append((abs_path, os.path.join(root_arcname, relative)))
    return members


def build_full_model_bundle(model_id: str) -> DownloadBundle:
    """Bundle the entire model folder."""
    folder = os.path.join(MODELS_DIR, model_id)
    if not os.path.isdir(folder):
        raise ModelNotFoundError(f"Model folder not found: {folder}")
    return DownloadBundle(
        archive_name=f"{model_id}.zip",
        members=_walk_folder_members(folder, model_id),
    )


def build_generator_essentials_bundle(model_id: str) -> DownloadBundle:
    """Bundle the minimum files needed to simulate from a trained model.

    Includes ``generator.zip``, ``metadata.json`` and ``rule_manager.json``
    (the same artifacts loaded by ``services.artifacts.load_generator_artifacts``).
    """
    folder = os.path.join(MODELS_DIR, model_id)
    if not os.path.isdir(folder):
        raise ModelNotFoundError(f"Model folder not found: {folder}")

    essentials = [GENERATOR_ZIP_NAME, METADATA_FILENAME, RULE_MANAGER_FILENAME]
    members: list[tuple[str, str]] = []
    missing: list[str] = []
    for name in essentials:
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            missing.append(name)
            continue
        members.append((path, os.path.join(model_id, name)))

    if missing:
        raise GeneratorEssentialsIncompleteError(
            f"Model '{model_id}' is missing required files to simulate: {missing}"
        )

    return DownloadBundle(
        archive_name=f"{model_id}_generator.zip",
        members=members,
    )


def build_full_simulation_bundle(simulation_id: str) -> DownloadBundle:
    """Bundle the entire simulation folder."""
    folder = os.path.join(SIMULATIONS_DIR, simulation_id)
    if not os.path.isdir(folder):
        raise SimulationNotFoundError(f"Simulation folder not found: {folder}")
    return DownloadBundle(
        archive_name=f"{simulation_id}.zip",
        members=_walk_folder_members(folder, simulation_id),
    )


def build_synthetic_data_bundle(simulation_id: str) -> DownloadBundle:
    """Bundle just the ``synthetic_data/`` subfolder of a simulation."""
    sim_folder = os.path.join(SIMULATIONS_DIR, simulation_id)
    if not os.path.isdir(sim_folder):
        raise SimulationNotFoundError(f"Simulation folder not found: {sim_folder}")

    synthetic_folder = os.path.join(sim_folder, SYNTHETIC_DATA_DIRNAME)
    if not os.path.isdir(synthetic_folder):
        raise SyntheticDataNotFoundError(f"Synthetic data folder not found: {synthetic_folder}")

    members = _walk_folder_members(synthetic_folder, SYNTHETIC_DATA_DIRNAME)
    if not members:
        raise SyntheticDataNotFoundError(f"Synthetic data folder is empty: {synthetic_folder}")

    return DownloadBundle(
        archive_name=f"{simulation_id}_synthetic_data.zip",
        members=members,
    )


def build_evaluation_bundle(evaluation_id: str) -> DownloadBundle:
    """Bundle the evaluation folder.

    The evaluation folder is created by the evaluate stage and contains the
    evaluation report CSV plus auxiliary JSONs and synthcity logs.
    """
    evaluation_folder = os.path.join(EVALUATIONS_DIR, evaluation_id)
    if not os.path.isdir(evaluation_folder):
        raise EvaluationNotFoundError(f"Evaluation folder not found: {evaluation_folder}")

    members = _walk_folder_members(evaluation_folder, evaluation_id)
    if not members:
        raise EvaluationNotFoundError(f"Evaluation folder is empty: '{evaluation_id}'.")

    return DownloadBundle(
        archive_name=f"{evaluation_id}.zip",
        members=members,
    )


def build_full_pipeline_bundle(pipeline_id: str) -> DownloadBundle:
    """Bundle the entire pipeline folder."""
    folder = os.path.join(PIPELINES_DIR, pipeline_id)
    if not os.path.isdir(folder):
        raise PipelineNotFoundError(f"Pipeline folder not found: {folder}")
    return DownloadBundle(
        archive_name=f"{pipeline_id}.zip",
        members=_walk_folder_members(folder, pipeline_id),
    )


def build_pipeline_with_jobs_bundle(pipeline_id: str) -> DownloadBundle:
    """Bundle the pipeline folder plus every model and simulation it produced.

    The archive is laid out as ``<pipeline_id>/`` for the pipeline folder,
    ``models/<model_id>/`` for each produced model, and
    ``simulations/<simulation_id>/`` for each produced simulation. Artifact
    folders that no longer exist on disk are silently skipped — the
    pipeline card is the source of truth for what *should* be there.
    """
    pipeline_folder = os.path.join(PIPELINES_DIR, pipeline_id)
    if not os.path.isdir(pipeline_folder):
        raise PipelineNotFoundError(f"Pipeline folder not found: {pipeline_folder}")

    artifact_ids = get_pipeline_artifact_ids(pipeline_id)
    model_ids, simulation_ids = artifact_ids if artifact_ids is not None else ([], [])

    members = _walk_folder_members(pipeline_folder, pipeline_id)

    for model_id in model_ids:
        model_folder = os.path.join(MODELS_DIR, model_id)
        if os.path.isdir(model_folder):
            members.extend(_walk_folder_members(model_folder, os.path.join("models", model_id)))

    for simulation_id in simulation_ids:
        sim_folder = os.path.join(SIMULATIONS_DIR, simulation_id)
        if os.path.isdir(sim_folder):
            members.extend(
                _walk_folder_members(sim_folder, os.path.join("simulations", simulation_id))
            )

    return DownloadBundle(
        archive_name=f"{pipeline_id}_with_jobs.zip",
        members=members,
    )


def build_full_inspection_bundle(inspection_id: str) -> DownloadBundle:
    """Bundle the entire inspection folder."""
    folder = os.path.join(INSPECTIONS_DIR, inspection_id)
    if not os.path.isdir(folder):
        raise InspectionNotFoundError(f"Inspection folder not found: {folder}")
    return DownloadBundle(
        archive_name=f"{inspection_id}.zip",
        members=_walk_folder_members(folder, inspection_id),
    )


def build_inspection_profiling_bundle(inspection_id: str) -> DownloadBundle:
    """Bundle just the ``profiling_reports/`` subfolder of an inspection.

    Raises ``InspectionNotFoundError`` if the inspection itself is missing and
    ``InspectionProfilingNotFoundError`` if the profiling reports were never
    produced (``enable_data_profiling`` was off) or the folder is empty.
    """
    inspection_folder = os.path.join(INSPECTIONS_DIR, inspection_id)
    if not os.path.isdir(inspection_folder):
        raise InspectionNotFoundError(f"Inspection folder not found: {inspection_folder}")

    profiling_folder = os.path.join(inspection_folder, PROFILING_REPORTS_DIRNAME)
    if not os.path.isdir(profiling_folder):
        raise InspectionProfilingNotFoundError(
            f"Profiling reports not found for inspection '{inspection_id}'. "
            "Was the inspection run with enable_data_profiling=True?"
        )

    members = _walk_folder_members(profiling_folder, PROFILING_REPORTS_DIRNAME)
    if not members:
        raise InspectionProfilingNotFoundError(
            f"Profiling reports folder is empty: {profiling_folder}"
        )

    return DownloadBundle(
        archive_name=f"{inspection_id}_profiling_reports.zip",
        members=members,
    )
