"""Turn raw MostlyAI training failures into concise, actionable messages.

The local SDK reports a failed job as a *cascade*: one entry per failing step
per table, most of them with no engine error message attached. Surfacing that
verbatim forces the user to scan dozens of near-identical lines (or the raw
logs) to guess what went wrong. This module replaces that with two entry points:

* :func:`run_preflight_checks` — inspect the prepared training tables *before*
  a job starts and fail fast with a clear reason when a known precondition is
  violated. This is the only reliable way to catch failures the engine raises
  *without* a step error message (e.g. the ``batch_size=0`` crash on small
  sequential tables).
* :func:`summarize_training_failure` — after a job reports ``failed``, collapse
  the per-step cascade into one line per affected table and, when the engine's
  error text matches a known issue, append guidance on how to fix it.

Known failure modes live in :data:`KNOWN_ISSUES`, so adding a new one (a new
``detect`` rule and/or new error ``signatures`` plus guidance) is a single-place
change that needs no edits to the engine wrapper.
"""

from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from backend.src.infrastructure.errors import (
    InsufficientTrainingDataError,
    InvalidBatchSizeError,
    TrainingJobFailedError,
    UnsupportedTrainingConfigurationError,
)

# MostlyAI halves the batch size for the validation split (``val_batch_size
# //= 2``). A configured ``batch_size`` of 1 underflows that to 0 and training
# dies with "batch_size should be a positive integer value, but got
# batch_size=0" — independent of how many rows are available. Two is the
# smallest value that survives the halving. This guards the *setting*; the
# row-count check below guards the *data* (where an auto-derived batch can be
# tiny). They are distinct causes of the same engine crash.
MIN_BATCH_SIZE = 2

# MostlyAI splits subjects 80/20 (``engine/splitting.py``, default
# ``trn_val_split=0.8``) and, for sequential tables, *halves* the validation
# batch size (``engine/_tabular/training.py``: ``val_batch_size //= 2``). With
# fewer than this many subject rows the validation split rounds down to a single
# record, the halved batch size underflows to 0, and training dies with
# "batch_size should be a positive integer value, but got batch_size=0". Eight
# is the first subject count that survives that arithmetic.
MIN_SEQUENTIAL_SUBJECT_ROWS = 8


@dataclass(frozen=True)
class KnownIssue:
    """A recognized MostlyAI failure mode paired with user-facing guidance.

    ``detect`` runs *before* training against the prepared tables, metadata and
    model settings, and returns the names of offending tables (empty when the
    issue does not apply). ``signatures`` are substrings matched against the
    engine's post-failure error text, so the same issue is still recognized when
    it slips past the pre-flight check (e.g. on data shapes the detector does not
    model). An issue may define either or both; at least one is required to be
    useful. ``error_cls`` is the exception raised when ``detect`` fires.
    """

    id: str
    title: str
    guidance: str
    detect: Callable[[dict[str, pd.DataFrame], dict, dict], list[str]] | None = None
    signatures: tuple[str, ...] = field(default_factory=tuple)
    error_cls: type[TrainingJobFailedError] = InsufficientTrainingDataError


def _subject_row_count(
    data: dict[str, pd.DataFrame], metadata_table: dict, foreign_key: dict
) -> int | None:
    """Number of subjects (parent rows) MostlyAI would split for this child.

    For a context (sequential) relationship the validation split is taken over
    the *parent* rows, so the parent's row count is what governs the val batch
    size. Falls back to the distinct foreign-key values present in the child when
    the parent frame is not part of this job.
    """
    parent_name = foreign_key.get("referenced_table")
    parent_df = data.get(parent_name or "")
    if parent_df is not None:
        return len(parent_df)

    child_df = data.get(metadata_table.get("name", ""))
    child_key = foreign_key.get("column")
    if child_df is None or child_key not in getattr(child_df, "columns", []):
        return None
    return int(child_df[child_key].nunique())


def _detect_undersized_sequential_tables(
    data: dict[str, pd.DataFrame], metadata: dict, model_settings: dict
) -> list[str]:
    """Child tables whose parent has too few rows to train a sequential model."""
    offending: list[str] = []
    for table in metadata.get("tables", []):
        name = table.get("name")
        foreign_keys = table.get("foreign_keys") or []
        if not name or not foreign_keys:
            # Flat (non-sequential) tables don't hit the val-batch halving.
            continue
        for foreign_key in foreign_keys:
            subjects = _subject_row_count(data, table, foreign_key)
            if subjects is not None and subjects < MIN_SEQUENTIAL_SUBJECT_ROWS:
                offending.append(name)
                break
    return offending


def table_differential_privacy(model_settings: dict | None, table_name: str) -> dict | None:
    """Effective differential-privacy config for one table.

    The global ``model_settings.differential_privacy`` applies to every table
    unless ``model_settings.per_table.<table>.differential_privacy`` overrides
    it — a dict replaces the global config, an explicit null/false disables DP
    for that table only.
    """
    settings = model_settings or {}
    per_table = settings.get("per_table") or {}
    overrides = per_table.get(table_name)
    if isinstance(overrides, dict) and "differential_privacy" in overrides:
        dp = overrides["differential_privacy"]
    else:
        dp = settings.get("differential_privacy")
    return dp if isinstance(dp, dict) else None


# How many DP-trained tables touching a context key can coexist in one group of
# related tables before the engine crashes (see ``dp_context_chain`` below).
MAX_DP_CONTEXT_TABLES = 2


def _detect_dp_context_chain(
    data: dict[str, pd.DataFrame], metadata: dict, model_settings: dict
) -> list[str]:
    """DP-trained tables forming a context-key group the engine cannot train.

    Stress testing (June 2026) showed the engine crashes with
    ``NotImplementedError`` on ``NestedTensorCPU`` (Opacus's ``DPDataLoader``
    cannot handle the nested tensors built for multi-level sequential context)
    whenever **three or more** tables that (a) train with differential privacy
    and (b) participate in at least one context-key relationship are connected
    through foreign keys — directly chained by context keys or two context
    pairs bridged by a plain foreign key alike. Two such tables are fine, and
    so is any layout once DP is disabled on the extra tables.
    """
    tables = [t for t in metadata.get("tables", []) if t.get("name")]
    trained = {t["name"] for t in tables if t["name"] in data}

    # Union-find over the FK graph (any FK connects, context or not).
    component: dict[str, str] = {name: name for name in trained}

    def find(name: str) -> str:
        while component[name] != name:
            component[name] = component[component[name]]
            name = component[name]
        return name

    context_tables: set[str] = set()
    for table in tables:
        name = table["name"]
        if name not in trained:
            continue
        for foreign_key in table.get("foreign_keys") or []:
            parent = foreign_key.get("referenced_table")
            if parent not in trained:
                continue
            component[find(name)] = find(parent)
            if foreign_key.get("is_context"):
                context_tables.update((name, parent))

    groups: dict[str, list[str]] = {}
    for name in trained:
        if name in context_tables and table_differential_privacy(model_settings, name):
            groups.setdefault(find(name), []).append(name)

    offending: list[str] = []
    for members in groups.values():
        if len(members) > MAX_DP_CONTEXT_TABLES:
            offending.extend(members)
    return offending


KNOWN_ISSUES: tuple[KnownIssue, ...] = (
    KnownIssue(
        id="undersized_sequential_table",
        title="Datos insuficientes para entrenar",
        guidance=(
            "Las tablas dependientes necesitan al menos "
            f"{MIN_SEQUENTIAL_SUBJECT_ROWS} registros en su tabla principal. "
            "Aporta más datos en la tabla principal o quita las tablas afectadas "
            "antes de entrenar."
        ),
        detect=_detect_undersized_sequential_tables,
        signatures=("batch_size should be a positive integer", "batch_size=0"),
    ),
    KnownIssue(
        id="dp_context_chain",
        title="Privacidad diferencial incompatible con esta estructura de tablas",
        guidance=(
            "El motor falla cuando más de "
            f"{MAX_DP_CONTEXT_TABLES} tablas relacionadas con claves de contexto "
            "entrenan con privacidad diferencial (limitación conocida de "
            "Opacus/PyTorch con tablas anidadas en varios niveles). Para "
            "entrenar puedes: (1) desactivar la privacidad diferencial en las "
            "tablas más profundas con 'model_settings.per_table' (por ejemplo "
            "per_table.<tabla>.differential_privacy: null), (2) desactivarla "
            "globalmente, o (3) eliminar la relación que une las tablas "
            "afectadas."
        ),
        detect=_detect_dp_context_chain,
        signatures=("NestedTensor", "nested tensor", "new_empty"),
        error_cls=UnsupportedTrainingConfigurationError,
    ),
)


def _configured_batch_size(model_settings: dict | None) -> int | None:
    """The user-configured ``batch_size``, or None when unset / not a number."""
    if not model_settings:
        return None
    raw = model_settings.get("batch_size")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class PreflightIssue:
    """One detected precondition violation, ready to show to the user."""

    id: str
    title: str
    guidance: str
    tables: list[str]
    error_cls: type[TrainingJobFailedError]


def collect_preflight_issues(
    data: dict[str, pd.DataFrame],
    metadata: dict,
    model_settings: dict | None = None,
) -> list[PreflightIssue]:
    """Evaluate every known precondition and return the violations found.

    Non-raising twin of :func:`run_preflight_checks`, so the API can warn the
    user *before* a training run is even launched. The batch-size check comes
    first (setting-level), then every registered known issue with a ``detect``
    hook (data/metadata-level).
    """
    issues: list[PreflightIssue] = []
    batch_size = _configured_batch_size(model_settings)
    if batch_size is not None and batch_size < MIN_BATCH_SIZE:
        issues.append(
            PreflightIssue(
                id="invalid_batch_size",
                title="Tamaño de batch demasiado pequeño",
                guidance=(
                    f"El tamaño de batch configurado ({batch_size}) es demasiado pequeño "
                    "para entrenar: el motor lo reduce a la mitad para la validación y "
                    f"queda en 0. Usa un tamaño de batch de al menos {MIN_BATCH_SIZE}, o "
                    "déjalo vacío para que se calcule automáticamente."
                ),
                tables=[],
                error_cls=InvalidBatchSizeError,
            )
        )

    for issue in KNOWN_ISSUES:
        if issue.detect is None:
            continue
        offending = issue.detect(data, metadata, model_settings or {})
        if offending:
            issues.append(
                PreflightIssue(
                    id=issue.id,
                    title=issue.title,
                    guidance=issue.guidance,
                    tables=sorted(set(offending)),
                    error_cls=issue.error_cls,
                )
            )
    return issues


def run_preflight_checks(
    data: dict[str, pd.DataFrame],
    metadata: dict,
    model_settings: dict | None = None,
) -> None:
    """Fail fast with a clear reason when a known precondition is violated.

    Raises with a concise, actionable message instead of letting the job crash
    opaquely minutes later. The batch-size problem is raised on its own (it is
    a pure setting error); detected data/metadata issues are joined into one
    message typed after the first issue found.
    """
    issues = collect_preflight_issues(data, metadata, model_settings)
    if not issues:
        return
    first = issues[0]
    if first.id == "invalid_batch_size":
        raise InvalidBatchSizeError(first.guidance)
    messages = [
        f"{issue.title} ({', '.join(issue.tables)}). {issue.guidance}" for issue in issues
    ]
    raise first.error_cls(" ".join(messages))


def _collect_failed_steps(generator) -> tuple[list[str], list[str]]:
    """Deduplicated affected tables and any distinct engine error messages."""
    tables: list[str] = []
    error_texts: list[str] = []
    try:
        steps = generator.training.progress().steps or []
    except Exception:  # pragma: no cover - best-effort detail
        return tables, error_texts

    from mostlyai.sdk.domain import ProgressStatus

    for step in steps:
        if step.status != ProgressStatus.failed:
            continue
        label = step.model_label or step.step_code
        if label and label not in tables:
            tables.append(str(label))
        message = (step.error_message or "").strip()
        if message and message not in error_texts:
            error_texts.append(message)
    return tables, error_texts


def _match_known_issue(error_texts: list[str]) -> str | None:
    """Guidance for the first known issue whose signature appears in the errors."""
    if not error_texts:
        return None
    haystack = " ".join(error_texts).lower()
    for issue in KNOWN_ISSUES:
        if any(signature.lower() in haystack for signature in issue.signatures):
            return f"{issue.title}: {issue.guidance}"
    return None


def summarize_training_failure(generator) -> str:
    """Build a concise, actionable message for a failed training job.

    Collapses the per-step cascade to one entry per affected table and appends
    guidance when the engine's error text matches a known issue. Falls back to a
    pointer to the logs only when the engine reported no detail at all.
    """
    status = generator.training_status.value
    tables, error_texts = _collect_failed_steps(generator)

    parts = [f"El entrenamiento finalizó con estado '{status}'."]
    if tables:
        parts.append(f"Tablas afectadas ({len(tables)}): {', '.join(tables)}.")

    guidance = _match_known_issue(error_texts)
    if guidance:
        parts.append(guidance)
    elif error_texts:
        parts.append(f"Detalle del motor: {error_texts[0]}")
    else:
        parts.append("El motor no informó un detalle; revisa el log para más contexto.")

    return " ".join(parts)
