"""Pydantic schemas for simulation-related API responses."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from backend.src.api.schemas.jobs import JobProgress
from backend.src.config.general import SYNTHETIC_DATA_FILE_FORMATS
from backend.src.domain.id_validation import MODEL_ID_PATTERN


class FixedCondition(BaseModel):
    """Force a column to a single constant value on every generated row."""

    mode: Literal["fixed"] = "fixed"
    column: str = Field(..., min_length=1)
    value: str | float | int


class CategoricalCondition(BaseModel):
    """Force a column to follow target proportions over categorical values.

    ``weights`` are relative — they need not sum to 100; the server normalizes
    them and allocates rows proportionally.
    """

    mode: Literal["categorical"] = "categorical"
    column: str = Field(..., min_length=1)
    weights: dict[str, float] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _check_weights(self):
        if any(w < 0 for w in self.weights.values()):
            raise ValueError("Category weights must be non-negative.")
        if sum(self.weights.values()) <= 0:
            raise ValueError("Category weights must sum to a positive number.")
        return self


class NumericCondition(BaseModel):
    """Synthesize a numeric column with a parameterized generator.

    ``uniform`` draws values evenly in ``[min, max]``. ``normal`` draws from a
    Gaussian with the given ``mean``/``std``, clamped to ``[min, max]``.
    """

    mode: Literal["numeric"] = "numeric"
    column: str = Field(..., min_length=1)
    generator: Literal["uniform", "normal"] = "uniform"
    min: float
    max: float
    mean: float | None = None
    std: float | None = None
    integer: bool = False

    @model_validator(mode="after")
    def _check_bounds(self):
        if self.max < self.min:
            raise ValueError("`max` must be greater than or equal to `min`.")
        if self.generator == "normal":
            if self.mean is None or self.std is None:
                raise ValueError("`mean` and `std` are required for the normal generator.")
            if self.std < 0:
                raise ValueError("`std` must be non-negative.")
        return self


class DateRangeCondition(BaseModel):
    """Synthesize a datetime column with values drawn uniformly between dates.

    ``start`` and ``end`` are ISO date/datetime strings. Setting them equal
    pins the column to a single date.
    """

    mode: Literal["daterange"] = "daterange"
    column: str = Field(..., min_length=1)
    start: str = Field(..., min_length=1)
    end: str = Field(..., min_length=1)


Condition = Annotated[
    FixedCondition | CategoricalCondition | NumericCondition | DateRangeCondition,
    Field(discriminator="mode"),
]


class ConditionalConfig(BaseModel):
    """Conditional-generation spec: per-column constraints applied to one table."""

    table: str | None = Field(
        default=None,
        description="Target subject table. Defaults to the first subject table when omitted.",
    )
    conditions: list[Condition] = Field(default_factory=list)


class FixedTargetConfig(BaseModel):
    """Hold one table at an exact (rule-compliant) row count, letting the rest float.

    The engine only honors sizes on subject tables; context children always
    cascade from their parent. To enforce a child table's row count the server
    oversimulates the mother table adaptively (re-estimating the child-per-mother
    yield each attempt) until ``table`` reaches ``rows`` compliant rows, then
    trims the overflow. The mother and the remaining tables end up with whatever
    size that requires. Runs with or without rejection-sampling rules; when rules
    exist, only compliant rows count toward ``rows``.
    """

    table: str = Field(..., min_length=1)
    rows: int = Field(..., gt=0)


class SimulationRelationship(BaseModel):
    """A foreign-key edge between two tables in a simulation's schema.

    ``parent`` is the referenced table and ``child`` is the table that holds the
    foreign key column. Used by the UI to draw a simplified schema diagram.
    """

    parent: str
    child: str
    column: str
    is_context: bool = False


class SimulationSummary(BaseModel):
    """Summary of a simulation run returned by the catalog."""

    simulation_id: str
    simulation_name: str | None = None
    status: str = ""
    timestamp: str = ""
    model_id: str | None = None
    sample_size: int | None = None
    mother_table: str | None = None
    mother_table_size: int | None = None
    target_table: str | None = None
    target_table_rows: int | None = None
    tables: str = ""
    training_table_sizes: dict[str, int] = {}
    relationships: list[SimulationRelationship] = []
    model_accuracy: float | None = None
    progress: JobProgress | None = None
    duration_seconds: float | None = None
    started_at_ms: int | None = None
    error_message: str | None = None


class RenameRequest(BaseModel):
    """Body of a rename PATCH endpoint."""

    name: str = Field(..., min_length=1, max_length=100)


class SimulationCreateRequest(BaseModel):
    """Body of ``POST /simulations``: inputs required to launch a simulation run."""

    name: str | None = Field(
        default=None,
        max_length=100,
        description="Optional human-readable name for this generation run.",
    )
    model_id: str = Field(
        ...,
        description="ID of the trained model to simulate from.",
        pattern=MODEL_ID_PATTERN,
    )
    sample_size: int | None = Field(
        default=None,
        gt=0,
        description="Number of synthetic records to generate. Uses model default when omitted.",
    )
    synthetic_data_file_format: str | None = Field(
        default=None,
        description="Synthetic output table format for this simulation run.",
        pattern=f"^({'|'.join(SYNTHETIC_DATA_FILE_FORMATS)})$",
    )
    table_sample_sizes: dict[str, int] | None = Field(
        default=None,
        description=(
            "Per-table row-count overrides. Only honored for subject tables "
            "(those without a context foreign key); Mostly AI cascades counts "
            "for context children from their parent, so entries targeting "
            "children are accepted but ignored with a server-side warning. "
            "Falls back to `sample_size` for subject tables not listed here."
        ),
    )
    conditional: ConditionalConfig | None = Field(
        default=None,
        description=(
            "Conditional-generation spec. Builds a `sample_seed` table that fixes "
            "or steers selected columns (constant value, target proportions, or a "
            "numeric generator) so generation is conditioned on them."
        ),
    )
    max_attempts: int | None = Field(
        default=None,
        ge=1,
        le=20,
        description=(
            "Max generate/filter passes for rejection or fixed-target sampling. "
            "Overrides the rules.yaml value. Each retry restarts the engine, "
            "which is far slower than drawing a bigger batch — prefer raising "
            "`overgenerate_factor` over this."
        ),
    )
    overgenerate_factor: float | None = Field(
        default=None,
        ge=1.0,
        le=20.0,
        description=(
            "Overgeneration multiplier applied to each sampling draw. Overrides "
            "the rules.yaml value. Cheaper than retries: one larger batch beats "
            "another engine round-trip."
        ),
    )
    fixed_target: FixedTargetConfig | None = Field(
        default=None,
        description=(
            "Enforce an exact row count on one table (typically a context child) "
            "instead of on the mother table. The mother is oversimulated until the "
            "target table reaches the requested compliant rows; all other tables "
            "are left to whatever size that requires. Mutually exclusive with "
            "`sample_size` and `table_sample_sizes`."
        ),
    )

    @model_validator(mode="after")
    def _check_fixed_target_exclusivity(self):
        if self.fixed_target and (self.sample_size is not None or self.table_sample_sizes):
            raise ValueError(
                "`fixed_target` cannot be combined with `sample_size` or "
                "`table_sample_sizes`: fixing a target table leaves the mother "
                "table's row count unconstrained."
            )
        return self


class SimulationJob(BaseModel):
    """Acknowledgement returned by ``POST /simulations`` (HTTP 202).

    Clients poll ``GET /simulations/{simulation_id}`` to observe progress via
    the ``status`` field.
    """

    simulation_id: str
    status: str = "in_progress"


class EvaluationJob(BaseModel):
    """Acknowledgement returned by ``POST /simulations/{id}/evaluate`` (HTTP 202).

    Results land in ``outputs/simulations/{simulation_id}/evaluation/`` once
    completed. Poll via ``GET /simulations/{simulation_id}/download/evaluation``
    (returns 404 while running, 200 once done).
    """

    simulation_id: str
    status: str = "submitted"


class DeletedSimulation(BaseModel):
    """Confirmation returned after successfully deleting a simulation."""

    deleted_id: str
    deleted_evaluation_ids: list[str] = []


class CleanupResult(BaseModel):
    """Result of a bulk cleanup operation on the simulations catalog."""

    deleted_ids: list[str]
    empty: list[str]
    orphans: list[str]
    skipped_ids: list[str] = []


class SanityReportRow(BaseModel):
    """One entry from a simulation's sanity-checks report.

    Mirrors the unified schema produced by `_build_general_sanity_check_row`
    and `RuleManager.run_rules_sanity_checks`. ``type`` is ``"rule"`` for
    logical-rule checks and ``"general"`` for structural ones (referential
    integrity, contextual FK consistency).

    For ``type="rule"`` rows the identity fields (``origin_col``,
    ``target_col``, etc.) allow the frontend to reconstruct the same label
    the rules banner shows, so each row maps unambiguously to one yaml rule.
    """

    type: Literal["rule", "general"]
    check: str
    rule: str
    table: str
    status: Literal["PASS", "FAIL", "SKIPPED"]
    failed_rows: int
    total_rows: int
    details: str | None = None
    # Identity fields — populated for type="rule" rows only
    table_origin: str | None = None
    origin_col: str | None = None
    target_col: str | None = None
    source_col: str | None = None
    aux_col: str | None = None
    canonical_col: str | None = None
    part_cols: str | None = None
    constraint: str | None = None
    constraint_operator: str | None = None
    threshold: float | None = None
    operator: str | None = None
    bins: str | None = None
    reference_date: str | None = None
    reference_date_col: str | None = None


class SanityReport(BaseModel):
    """Sanity-checks report for a simulation run."""

    simulation_id: str
    rows: list[SanityReportRow] = []


class RejectionSamplingTableStats(BaseModel):
    """Per-table counts from rejection sampling.

    ``rejected`` counts rows discarded for *failing the rule* (the compliance
    signal). ``trimmed`` counts compliant rows discarded only as overflow — i.e.
    rows of subjects not kept by best-subset selection (and their children), so
    the two are not conflated.
    """

    generated: int = 0
    accepted: int = 0
    rejected: int = 0
    trimmed: int = 0


class RejectionSamplingAttemptTableStats(BaseModel):
    """Per-table counts for a single rejection sampling attempt."""

    generated: int = 0
    accepted: int = 0
    rejected: int = 0
    trimmed: int = 0


class RejectionSamplingAttempt(BaseModel):
    """Metrics tracked on a single simulation retry."""

    attempt: int
    multiplier: float
    tables: dict[str, RejectionSamplingAttemptTableStats] = {}
    score: int
    is_best: bool = False
    subject_draw: dict[str, int] | None = None


class RejectionSamplingReport(BaseModel):
    """How rejection sampling performed during a simulation run.

    Written by ``SimulationTracker.save_rejection_sampling_report`` only when at
    least one rejection-sampling rule applied. ``attempts`` is how many
    generate/filter passes ran (capped at ``max_attempts``); ``partial_results``
    is ``True`` when the cap was hit before reaching the subject target or a
    child table's proportional compliance target.

    Subjects are held at exactly their requested size; ``child_targets`` are the
    proportional (real child:subject ratio × subject size) compliance goals the
    engine cannot enforce directly — rejection sampling retries up to
    ``max_attempts`` to close the gap and reports how far it got via the per-table
    ``accepted`` counts.
    """

    simulation_id: str
    enabled: bool = True
    max_attempts: int = 0
    overgenerate_factor: float = 0.0
    attempts: int = 0
    sample_size: int | None = None
    partial_results: bool = False
    selection: str | None = None
    rules: list[str] = []
    tables: dict[str, RejectionSamplingTableStats] = {}
    subject_targets: dict[str, int] = {}
    child_targets: dict[str, int] = {}
    # Per-table row objetivo shown in the report: every table scaled to the real
    # data's proportions at the requested size. Only ``fixed_tables`` are held
    # exactly; the rest are informational goals their cascade may undershoot.
    all_targets: dict[str, int] = {}
    fixed_tables: list[str] = []
    # Fixed-target mode (`selection="fixed_target"`): the table whose compliant
    # row count was enforced while the mother table floated.
    target_table: str | None = None
    target_rows: int | None = None
    attempt_history: list[RejectionSamplingAttempt] | None = None

