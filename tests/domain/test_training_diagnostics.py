from types import SimpleNamespace
from unittest.mock import MagicMock

import pandas as pd
import pytest

from backend.src.domain.synthesis.training_diagnostics import (
    MIN_BATCH_SIZE,
    MIN_SEQUENTIAL_SUBJECT_ROWS,
    run_preflight_checks,
    summarize_training_failure,
    table_differential_privacy,
)
from backend.src.infrastructure.errors import (
    InsufficientTrainingDataError,
    InvalidBatchSizeError,
    UnsupportedTrainingConfigurationError,
)

# -----------------------------------------------------------------------------
# Pre-flight checks
# -----------------------------------------------------------------------------


def _omop_metadata():
    return {
        "tables": [
            {"name": "person", "primary_key": "person_id"},
            {
                "name": "condition_occurrence",
                "foreign_keys": [
                    {"column": "person_id", "referenced_table": "person"}
                ],
            },
        ]
    }


def test_preflight_passes_for_flat_table_regardless_of_size():
    data = {"users": pd.DataFrame({"id": [1]})}
    metadata = {"tables": [{"name": "users", "primary_key": "id"}]}
    # No foreign keys → not sequential → never flagged, even with a single row.
    run_preflight_checks(data, metadata)


def test_preflight_passes_when_parent_has_enough_rows():
    n = MIN_SEQUENTIAL_SUBJECT_ROWS
    data = {
        "person": pd.DataFrame({"person_id": range(n)}),
        "condition_occurrence": pd.DataFrame({"person_id": range(n)}),
    }
    run_preflight_checks(data, _omop_metadata())


def test_preflight_raises_when_parent_too_small():
    data = {
        "person": pd.DataFrame({"person_id": [1, 2, 3, 4, 5]}),  # 5 < 8
        "condition_occurrence": pd.DataFrame({"person_id": [1, 2, 3, 4, 5]}),
    }
    with pytest.raises(InsufficientTrainingDataError) as exc:
        run_preflight_checks(data, _omop_metadata())
    assert "condition_occurrence" in str(exc.value)
    assert str(MIN_SEQUENTIAL_SUBJECT_ROWS) in str(exc.value)


def test_preflight_falls_back_to_child_fk_when_parent_absent():
    # Parent frame not part of the job → count distinct FK values in the child.
    data = {
        "condition_occurrence": pd.DataFrame({"person_id": [1, 1, 2, 2, 3]}),  # 3 subjects
    }
    with pytest.raises(InsufficientTrainingDataError):
        run_preflight_checks(data, _omop_metadata())


def test_preflight_rejects_batch_size_below_minimum_even_with_enough_data():
    # Plenty of data; the *setting* is the problem (batch_size=1 underflows the
    # halved validation batch to 0). This is the real-world case the row-count
    # check never modelled.
    n = MIN_SEQUENTIAL_SUBJECT_ROWS
    data = {
        "person": pd.DataFrame({"person_id": range(n)}),
        "condition_occurrence": pd.DataFrame({"person_id": range(n)}),
    }
    with pytest.raises(InvalidBatchSizeError) as exc:
        run_preflight_checks(data, _omop_metadata(), {"batch_size": 1})
    assert str(MIN_BATCH_SIZE) in str(exc.value)


def test_preflight_accepts_batch_size_at_minimum():
    data = {"users": pd.DataFrame({"id": range(100)})}
    metadata = {"tables": [{"name": "users", "primary_key": "id"}]}
    run_preflight_checks(data, metadata, {"batch_size": MIN_BATCH_SIZE})


def test_preflight_ignores_unset_or_blank_batch_size():
    data = {"users": pd.DataFrame({"id": range(100)})}
    metadata = {"tables": [{"name": "users", "primary_key": "id"}]}
    run_preflight_checks(data, metadata, {})
    run_preflight_checks(data, metadata, {"batch_size": ""})
    run_preflight_checks(data, metadata, None)


# -----------------------------------------------------------------------------
# Differential privacy + context-key chains
# -----------------------------------------------------------------------------

DP = {"delta": 1e-5, "noise_multiplier": 1.5, "max_grad_norm": 1.0}
N = MIN_SEQUENTIAL_SUBJECT_ROWS * 4


def _chain_metadata(context_flags: list[bool]):
    """persons → t1 → t2 … linked by FKs with the given is_context flags."""
    tables = [{"name": "t0", "primary_key": "id"}]
    for i, is_context in enumerate(context_flags, start=1):
        tables.append(
            {
                "name": f"t{i}",
                "primary_key": "id",
                "foreign_keys": [
                    {
                        "column": "parent_id",
                        "referenced_table": f"t{i - 1}",
                        "is_context": is_context,
                    }
                ],
            }
        )
    return {"tables": tables}


def _chain_data(n_tables: int):
    frames = {"t0": pd.DataFrame({"id": range(N)})}
    for i in range(1, n_tables):
        frames[f"t{i}"] = pd.DataFrame({"id": range(N), "parent_id": range(N)})
    return frames


def test_dp_with_two_context_tables_passes():
    metadata = _chain_metadata([True])
    run_preflight_checks(_chain_data(2), metadata, {"differential_privacy": DP})


def test_dp_with_three_context_chained_tables_raises():
    metadata = _chain_metadata([True, True])
    with pytest.raises(UnsupportedTrainingConfigurationError) as exc:
        run_preflight_checks(_chain_data(3), metadata, {"differential_privacy": DP})
    message = str(exc.value)
    assert "t0" in message and "t1" in message and "t2" in message
    assert "per_table" in message


def test_dp_context_pairs_bridged_by_plain_fk_raise():
    # CK between t0-t1 and t2-t3, plain FK between t1-t2: still crashes the
    # engine, so it must be blocked too.
    metadata = _chain_metadata([True, False, True])
    with pytest.raises(UnsupportedTrainingConfigurationError):
        run_preflight_checks(_chain_data(4), metadata, {"differential_privacy": DP})


def test_dp_chain_without_context_keys_passes():
    metadata = _chain_metadata([False, False, False])
    run_preflight_checks(_chain_data(4), metadata, {"differential_privacy": DP})


def test_dp_chain_without_dp_passes():
    metadata = _chain_metadata([True, True, True])
    run_preflight_checks(_chain_data(4), metadata, {})


def test_dp_chain_passes_when_per_table_disables_deep_tables():
    metadata = _chain_metadata([True, True])
    settings = {
        "differential_privacy": DP,
        "per_table": {"t2": {"differential_privacy": None}},
    }
    run_preflight_checks(_chain_data(3), metadata, settings)


def test_disconnected_context_pairs_pass():
    # t0-t1 and t2-t3 are CK pairs with no FK between t1 and t2.
    metadata = {
        "tables": [
            {"name": "t0", "primary_key": "id"},
            {
                "name": "t1",
                "primary_key": "id",
                "foreign_keys": [
                    {"column": "parent_id", "referenced_table": "t0", "is_context": True}
                ],
            },
            {"name": "t2", "primary_key": "id"},
            {
                "name": "t3",
                "primary_key": "id",
                "foreign_keys": [
                    {"column": "parent_id", "referenced_table": "t2", "is_context": True}
                ],
            },
        ]
    }
    run_preflight_checks(_chain_data(4), metadata, {"differential_privacy": DP})


def test_table_differential_privacy_resolves_per_table_overrides():
    settings = {
        "differential_privacy": DP,
        "per_table": {
            "off": {"differential_privacy": None},
            "custom": {"differential_privacy": {"noise_multiplier": 3.0}},
        },
    }
    assert table_differential_privacy(settings, "plain") == DP
    assert table_differential_privacy(settings, "off") is None
    assert table_differential_privacy(settings, "custom") == {"noise_multiplier": 3.0}
    assert table_differential_privacy({}, "plain") is None
    assert table_differential_privacy(None, "plain") is None


# -----------------------------------------------------------------------------
# Failure summary
# -----------------------------------------------------------------------------


def _step(label, status, error_message=None):
    return SimpleNamespace(
        model_label=label,
        step_code="TRAIN_MODEL",
        status=status,
        error_message=error_message,
    )


def _generator_with_steps(steps, status_value="failed"):
    from mostlyai.sdk.domain import ProgressStatus

    gen = MagicMock()
    gen.training_status = SimpleNamespace(value=status_value)
    gen.training.progress.return_value = SimpleNamespace(steps=steps)
    return gen, ProgressStatus


def test_summary_collapses_repeated_failing_steps():
    from mostlyai.sdk.domain import ProgressStatus

    # Same table reported failed across several steps → one entry, not many.
    steps = [_step("condition_occurrence:tabular", ProgressStatus.failed) for _ in range(6)]
    steps += [_step("drug_exposure:tabular", ProgressStatus.failed) for _ in range(6)]
    gen, _ = _generator_with_steps(steps)

    message = summarize_training_failure(gen)

    assert message.count("condition_occurrence:tabular") == 1
    assert message.count("drug_exposure:tabular") == 1
    assert "Tablas afectadas (2)" in message
    assert "no error message" not in message


def test_summary_appends_guidance_on_known_signature():
    from mostlyai.sdk.domain import ProgressStatus

    steps = [
        _step(
            "condition_occurrence:tabular",
            ProgressStatus.failed,
            error_message="ValueError: batch_size should be a positive integer value, but got batch_size=0",
        )
    ]
    gen, _ = _generator_with_steps(steps)

    message = summarize_training_failure(gen)

    assert "Datos insuficientes para entrenar" in message


def test_summary_points_to_log_when_engine_gives_no_detail():
    from mostlyai.sdk.domain import ProgressStatus

    steps = [_step("person:tabular", ProgressStatus.failed)]
    gen, _ = _generator_with_steps(steps)

    message = summarize_training_failure(gen)

    assert "revisa el log" in message
