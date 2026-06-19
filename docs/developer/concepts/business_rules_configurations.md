[<-- Back to Main Index](../../README.md)

# Business Rules Configurations (BRC)

A **Business Rules Configuration (BRC) run** is an optional staging step that sits between *Carga de Datos* (an upload / inspection) and *Entrenamiento* (model training). It applies the logical rules' **PRE phase** on top of the inspection's preprocessed data and persists the result in its own versioned folder, so:

- The user can **preview the transformed data** before committing to a long training run.
- The training step reads from the BRC output instead of reprocessing raw files, making training faster and reproducible.
- Multiple BRC runs can be created from the same upload (different rule sets, different exclusion configurations) without touching the original parquet files.


## Why This Layer Exists

Logical rules remove, replace, and derive columns during PRE (see [Logical Rules](logical_rules.md)). Without a staging step:

- The user has no visibility into what the model will actually see.
- If a rule produces unexpected auxiliary columns or breaks a column, the training job fails after potentially minutes of preprocessing.

BRC short-circuits that loop: run the PRE phase cheaply, inspect the result, then decide whether to proceed with training.


## Lifecycle

```
Carga de Datos (upload / inspection)
        │
        │  preprocessed_data/*.parquet (cleaned, type-normalised)
        ▼
  BRC run (optional)
        │  1. Applies rules PRE phase
        │  2. Applies excluded_columns union (Carga de Datos + BRC-scoped)
        │  3. Saves new processed_data/*.parquet
        │  4. Saves rule_manager snapshot (JSON)
        │  5. Profiles new/auxiliary columns (optional)
        ▼
  Model training  ──reads from──►  BRC processed_data/
                                   (skips re-applying PRE)
```

The training session detects that its input comes from a BRC run and loads the pre-serialised rule manager from the BRC folder, skipping the PRE phase entirely.


## Folder Structure

```
outputs/business_rules_configurations/
└── brc_20260611_143000/
    ├── brc_card.json           # Status, metadata, warnings, new_columns
    ├── rules_snapshot.yaml     # Copy of rules.yaml used — never changes
    ├── rule_manager.json       # Serialised LogicalRuleManager state
    ├── new_columns.json        # {table: [col, ...]} columns added by rules
    ├── processed_data/
    │   ├── person.parquet
    │   └── visits.parquet
    └── profiling_reports/      # Only when enable_profiling=true
        └── person_profiling_report.html
```

- **`brc_card.json`** records the run status (`in_progress` / `completed` / `failed`), `inspection_id`, `rules_count`, `tables` (row counts), `new_columns`, `warnings`, and whether profiling was enabled.
- **`rules_snapshot.yaml`** is an immutable copy of the rules YAML at launch time. Editing the global `rules.yaml` later does not change what this BRC run represents.
- **`rule_manager.json`** is the serialised state of the `LogicalRuleManager` after PRE (including the semantic interval maps). Training reads this directly to skip re-applying PRE.
- **`new_columns.json`** lists the auxiliary/derived columns that rules added. The UI uses this to render "new column" badges and to restrict profiling reports to just those columns.


## Column Exclusion Scoping

Two sources of column exclusions are kept **strictly separate** until materialisation time:

| Field | Set by | Scope |
|---|---|---|
| `excluded_columns` | *Carga de Datos* (upload step) | Upload-level; never changes once the upload is complete |
| `rules_excluded_columns` | BRC request or per-run configuration | Rule-run-level; only applies within this BRC run and downstream training |

The BRC run unions both sets and drops the result **at materialisation time** (during `SAVING_PROCESSED`). Neither field leaks back into the other. This means:

- Changing your rule exclusions never silently changes what the upload stores.
- Training from a BRC run gets the combined exclusion set without re-running the upload.


## Profiling

When `enable_profiling=true` (the default), the BRC run generates a `ydata-profiling` HTML report **for the new columns only** (the auxiliary/derived columns produced by the rules). This avoids redundant re-profiling of columns that were already profiled during the upload.

If a table has no new columns, its profiling is skipped entirely.


## New Columns

Rules can produce entirely new columns during PRE:
- **Auxiliary columns**: duration, age, score columns used internally (e.g. `procedure_duration_days`, `disease_score`).
- **Derived columns**: explicitly computed from a source column (e.g. `age` from `dob`, `is_adult` from `age`).

These are recorded in `new_columns.json` and surfaced through the API (`GET /business-rules-configurations/{brc_id}/new-columns`). The training job's model card also carries them for lineage.


## Relation to Training

When `POST /models` receives a `brc_id` instead of raw `file_paths` or `inspection_id`, training reads from `brc_id/processed_data/` and skips the PRE phase. The serialised rule manager is restored from `brc_id/rule_manager.json` so POST reconstruction and sanity checks work correctly.

> **Note on reproducibility.** A BRC run is a snapshot. Even if you later edit `rules.yaml`, training from an old BRC run uses the rule set that was active when that BRC was created (captured in `rules_snapshot.yaml`).

[<-- Back to Main Index](../../README.md)
