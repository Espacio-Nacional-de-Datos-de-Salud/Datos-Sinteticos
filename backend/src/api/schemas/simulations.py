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
    tables: str = ""
    training_table_sizes: dict[str, int] = {}
    relationships: list[SimulationRelationship] = []
    model_accuracy: float | None = None
    progress: JobProgress | None = None
    duration_seconds: float | None = None
    started_at_ms: int | None = None


class RenameRequest(BaseModel):
    """Body of a rename PATCH endpoint."""

    name: str


class SimulationCreateRequest(BaseModel):
    """Body of ``POST /simulations``: inputs required to launch a simulation run."""

    name: str | None = Field(
        default=None,
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
