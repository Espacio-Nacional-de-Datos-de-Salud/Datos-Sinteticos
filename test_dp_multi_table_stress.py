"""Repro harness: DP + 3-level context-key chain crash in MostlyAI local SDK.

Trains persons -> visits -> drugs (both links are is_context FKs) with
differential privacy enabled on all tables. With opacus 1.5.4 the grandchild
table (drugs) crashes inside DPDataLoader with NotImplementedError on
NestedTensorCPU. Run after upgrading opacus to check whether the crash is gone:

    .venv_core/bin/python test_dp_multi_table_stress.py

Exit code 0 = training finished (DONE); 1 = training failed.
"""

import sys
import tempfile

import numpy as np
import pandas as pd

RNG = np.random.default_rng(7)

N_PERSONS = 300

DP_CONFIG = {
    "max_epsilon": None,
    "delta": 1e-5,
    "noise_multiplier": 1.5,
    "max_grad_norm": 1.0,
    "value_protection_epsilon": 1.0,
}

MODEL_SETTINGS = {
    "max_epochs": 4,
    "batch_size": 32,
    "model": "MOSTLY_AI/Small",
    "value_protection": False,
    "differential_privacy": DP_CONFIG,
}


def build_data() -> dict[str, pd.DataFrame]:
    persons = pd.DataFrame(
        {
            "person_id": range(N_PERSONS),
            "age": RNG.integers(18, 90, N_PERSONS),
            "sex": RNG.choice(["M", "F"], N_PERSONS),
        }
    )
    # Variable-length sequences: the engine only builds nested tensors when
    # context sequence lengths differ across subjects.
    visits_per_person = RNG.integers(1, 10, N_PERSONS)
    n_visits = int(visits_per_person.sum())
    visits = pd.DataFrame(
        {
            "visit_id": range(n_visits),
            "person_id": np.repeat(persons["person_id"].values, visits_per_person),
            "ward": RNG.choice(["ER", "ICU", "GEN"], n_visits),
            "cost": RNG.normal(500, 100, n_visits).round(2),
            "admitted_at": pd.Timestamp("2024-01-01")
            + pd.to_timedelta(RNG.integers(0, 365 * 24, n_visits), unit="h"),
        }
    )
    drugs_per_visit = RNG.integers(0, 6, n_visits)
    n_drugs = int(drugs_per_visit.sum())
    drugs = pd.DataFrame(
        {
            "drug_id": range(n_drugs),
            "visit_id": np.repeat(visits["visit_id"].values, drugs_per_visit),
            "name": RNG.choice(["aspirin", "ibuprofen", "amoxicillin"], n_drugs),
            "dose_mg": RNG.integers(50, 500, n_drugs),
            "given_at": pd.Timestamp("2024-01-01")
            + pd.to_timedelta(RNG.integers(0, 365 * 24, n_drugs), unit="h"),
        }
    )
    return {"persons": persons, "visits": visits, "drugs": drugs}


def main() -> int:
    from mostlyai.sdk import MostlyAI

    data = build_data()
    local_dir = tempfile.mkdtemp(prefix="mostly_dp_stress_")
    mostly = MostlyAI(local=True, local_dir=local_dir)

    config = {
        "name": "dp-3level-context-chain",
        "tables": [
            {
                "name": "persons",
                "data": data["persons"],
                "primary_key": "person_id",
                "tabular_model_configuration": MODEL_SETTINGS,
            },
            {
                "name": "visits",
                "data": data["visits"],
                "primary_key": "visit_id",
                "foreign_keys": [
                    {"column": "person_id", "referenced_table": "persons", "is_context": True}
                ],
                "tabular_model_configuration": MODEL_SETTINGS,
            },
            {
                "name": "drugs",
                "data": data["drugs"],
                "primary_key": "drug_id",
                "foreign_keys": [
                    {"column": "visit_id", "referenced_table": "visits", "is_context": True}
                ],
                "tabular_model_configuration": MODEL_SETTINGS,
            },
        ],
    }

    generator = mostly.generators.create(config=config)
    generator.training.start()
    try:
        generator.training.wait()
    except Exception as exc:  # noqa: BLE001
        print(f"wait() raised: {exc}")

    generator = mostly.generators.get(generator.id)
    status = generator.training_status.value
    print(f"\n=== training_status: {status} ===")
    for step in generator.training.progress().steps or []:
        if str(step.status.value) == "FAILED" or step.error_message:
            print(f"FAILED step: {step.model_label} {step.step_code} :: {step.error_message}")
    return 0 if status == "DONE" else 1


if __name__ == "__main__":
    sys.exit(main())
