"""Build Mostly AI ``sample_seed`` tables for conditional generation.

A conditional spec constrains selected columns of a subject table. Each
constraint becomes one column of a seed DataFrame whose row count equals the
requested sample size; Mostly AI then generates the remaining columns
conditioned on the seeded ones.

Four constraint modes are supported:

* ``fixed`` — every row gets the same constant value.
* ``categorical`` — values are allocated to match target proportions.
* ``numeric`` — values are synthesized by a parameterized generator
  (``uniform`` over a range, or ``normal`` with a mean/std clamped to a range).
* ``daterange`` — datetime values drawn uniformly between two dates.
"""

import copy

import numpy as np
import pandas as pd

from backend.src.config.general import DEFAULT_SAMPLE_SIZE
from backend.src.infrastructure.logging_config import get_logger

logger = get_logger(__name__)

_DEFAULT_RANDOM_STATE = 42


def _allocate_categorical(weights: dict[str, float], n_rows: int, rng) -> list:
    """Allocate ``n_rows`` values across categories matching ``weights``.

    Uses the largest-remainder method so proportions are honored as exactly as
    integer counts allow, then shuffles so the seed rows are not value-ordered.
    """
    total = sum(weights.values())
    values = list(weights.keys())
    exact = [n_rows * (weights[v] / total) for v in values]
    counts = [int(np.floor(x)) for x in exact]
    remainder = n_rows - sum(counts)
    # Hand out the leftover rows to the categories with the largest fractions.
    fractional_order = sorted(
        range(len(values)), key=lambda i: exact[i] - counts[i], reverse=True
    )
    for i in range(remainder):
        counts[fractional_order[i % len(values)]] += 1

    column: list = []
    for value, count in zip(values, counts, strict=True):
        column.extend([value] * count)
    rng.shuffle(column)
    return column


def _generate_numeric(cond: dict, n_rows: int, rng) -> np.ndarray:
    """Synthesize ``n_rows`` numeric values for a ``numeric`` constraint."""
    low, high = float(cond["min"]), float(cond["max"])
    generator = cond.get("generator", "uniform")

    if generator == "normal":
        mean = float(cond["mean"])
        std = float(cond["std"])
        values = rng.normal(mean, std, n_rows)
        values = np.clip(values, low, high)
    else:
        values = rng.uniform(low, high, n_rows)

    if cond.get("integer"):
        values = np.rint(values).astype("int64")
    return values


def _generate_daterange(cond: dict, n_rows: int, rng) -> pd.DatetimeIndex:
    """Synthesize ``n_rows`` datetimes drawn uniformly between two dates."""
    lo, hi = sorted((pd.Timestamp(cond["start"]).value, pd.Timestamp(cond["end"]).value))
    if lo == hi:
        draws = np.full(n_rows, lo, dtype="int64")
    else:
        draws = rng.integers(lo, hi + 1, n_rows, dtype="int64")
    return pd.to_datetime(draws)


def build_sample_seed(
    conditions: list[dict],
    n_rows: int,
    random_state: int = _DEFAULT_RANDOM_STATE,
) -> pd.DataFrame:
    """Build a ``sample_seed`` DataFrame of ``n_rows`` from column constraints.

    Args:
        conditions: List of per-column constraint dicts (``fixed`` / ``categorical``
            / ``numeric`` / ``daterange``), as produced by the conditional-generation
            API schema.
        n_rows: Number of seed rows — equals the synthetic row count.
        random_state: Seed for the RNG so results are reproducible.

    Returns:
        A DataFrame with one column per constraint and ``n_rows`` rows.
    """
    rng = np.random.default_rng(random_state)
    data: dict[str, object] = {}

    for cond in conditions:
        column = cond["column"]
        mode = cond["mode"]
        if mode == "fixed":
            data[column] = [cond["value"]] * n_rows
        elif mode == "categorical":
            data[column] = _allocate_categorical(cond["weights"], n_rows, rng)
        elif mode == "numeric":
            data[column] = _generate_numeric(cond, n_rows, rng)
        elif mode == "daterange":
            data[column] = _generate_daterange(cond, n_rows, rng)
        else:
            raise ValueError(f"Unknown conditional mode: {mode!r}")

    return pd.DataFrame(data, index=range(n_rows))


def _first_subject_table(metadata: dict) -> str | None:
    """Return the name of the first subject table (no ``is_context`` FK)."""
    for table in metadata.get("tables", []):
        fks = table.get("foreign_keys") or []
        if not any(fk.get("is_context") for fk in fks):
            return table.get("name")
    return None


def _datetime_columns(metadata: dict, table_name: str) -> set[str]:
    """Return the names of datetime-encoded columns in ``table_name``."""
    for table in metadata.get("tables", []):
        if table.get("name") != table_name:
            continue
        return {
            str(col.get("name"))
            for col in table.get("columns", [])
            if isinstance(col, dict)
            and col.get("name")
            and "DATETIME" in str(col.get("model_encoding_type", "")).upper()
        }
    return set()


def attach_sample_seeds(
    simulation_config: dict,
    conditional: dict | None,
    metadata: dict,
    random_state: int = _DEFAULT_RANDOM_STATE,
) -> dict:
    """Return a copy of ``simulation_config`` with a ``sample_seed`` injected.

    When ``conditional`` carries constraints, the target subject table's
    configuration gets a ``sample_seed_data`` DataFrame and its ``sample_size``
    is dropped — with a seed present, the seed's row count governs generation.
    The input config is left untouched (it is the JSON-safe one persisted to
    disk; the returned copy carries the non-serializable DataFrame).

    Args:
        simulation_config: Base config ``{tables: [{name, configuration}, ...]}``.
        conditional: Conditional spec dict, or ``None`` for unconditional runs.
        metadata: Model metadata, used to resolve the default subject table and
            to coerce datetime-encoded seed columns to a datetime dtype.
        random_state: Seed for the seed-DataFrame RNG.

    Returns:
        A config dict ready to hand to the Mostly AI engine.
    """
    if not conditional or not conditional.get("conditions"):
        return simulation_config

    target_table = conditional.get("table") or _first_subject_table(metadata)
    if not target_table:
        logger.warning("Conditional generation requested but no subject table found; ignoring.")
        return simulation_config

    config = copy.deepcopy(simulation_config)
    table_entry = next(
        (t for t in config.get("tables", []) if t.get("name") == target_table), None
    )
    if table_entry is None:
        logger.warning(
            "Conditional generation targets table '%s' which is not in the simulation "
            "config; ignoring.",
            target_table,
        )
        return simulation_config

    table_configuration = table_entry.setdefault("configuration", {})
    n_rows = table_configuration.get("sample_size") or DEFAULT_SAMPLE_SIZE
    seed_df = build_sample_seed(conditional["conditions"], n_rows, random_state)

    # Date strings entered for fixed / categorical constraints must reach the
    # engine as a real datetime dtype so Mostly AI conditions the column correctly.
    for column in _datetime_columns(metadata, target_table) & set(seed_df.columns):
        seed_df[column] = pd.to_datetime(seed_df[column], errors="coerce")

    table_configuration.pop("sample_size", None)
    table_configuration["sample_seed_data"] = seed_df
    logger.info(
        "Conditional generation: built %d-row sample_seed for table '%s' on columns %s.",
        n_rows,
        target_table,
        list(seed_df.columns),
    )
    return config
