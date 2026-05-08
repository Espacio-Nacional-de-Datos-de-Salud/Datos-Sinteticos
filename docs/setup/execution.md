[<-- Back to Main Index](../../README.md)

# Execution Details

> If you want a quick start to execute forntend and backend easily, go back to [Setup](../setup/setup.md). This documentation explains how to run each part of the code seaprately and how to use the code from the CLI.

## 1. Running frontend and backend separately
As seen in the setup documentation, frontend and backend can be executed by just using `make local`. But you can run the API by itself as well with:

```bash
make api
```

Actually you could also run the frontend connecting to that already live API, if you open up a new terminal, `cd` into the repo and within it run:

```bash
make frontend
```

This ends in the same outcome as running `make local`.

## 2. CLI

You can run the code from the terminal without using the frontend or API. CLI execution reads parameters from `backend/config/general.yaml` (the file in your project root).

### 2.1 Available Modes

| Flag | Mode | Purpose |
|------|------|---------|
| `i`  | Inspect  | Load + preprocess + autodetect metadata. Stops before training so you can review/edit relationships and encoding. |
| `t`  | Train    | Train a generator (from raw files or from a previous inspection). |
| `s`  | Simulate | Generate synthetic data from a trained model. |
| `e`  | Evaluate | Compare synthetic data against original. |
| `p`  | Pipeline | Run the full end-to-end pipeline. |

### 2.2 Step-by-Step Workflow

The recommended flow is **inspect → review → train** so you can fix autodetected relationships (PKs/FKs) and encoding types before training, saving time over a full pipeline run.

#### Step 1 — Configure your data source

Open `backend/config/general.yaml` and set the `execution.file_paths` field to point to your input data:

```yaml
execution:
  file_paths:
    - "data/my_data.csv"   # or wherever your CSV/Parquet files are
  mode: i  # or t, s, e, p - this parameter is only necessary if you are running from python -m src.cli. If you are using make {type}, it overrides whatever this value is
```

#### Step 2 — Inspect the data

From your project root, run:
```bash
make inspect
```

This loads your data, detects table schemas, and saves the inspection session to `backend/outputs/inspections/inspection_<timestamp>/`. The prompt will show you the path.

#### Step 3 — List and pick an inspection

See all previous inspections:
```bash
make inspections
```

Copy the `inspection_id` (looks like `inspection_20260422_143022`) of the one you want to train.

#### Step 4 — Review and validate the schema

Navigate to `backend/outputs/inspections/<your_inspection_id>/` in your project. You'll find:

- `profiling_reports/` — HTML reports for each table (open in a browser to visualize data distributions, data types, and missing values).

**Editing**
- **`autodetected_inspection_metadata.json`** — The originally detected relationships and encoding types. This file should not be edited as its purpose is only for historic logging and will not be read by the model training module. When created it is copied into `inspection_metadata.json`.
- **`inspection_metadata.json`** — The source of truth for primary keys, foreign keys, and column encoding types. Edit metadata here in this file to fix any wrong detections:
  - Under `relationships.pks`: add/remove/correct primary key column names
  - Under `relationships.fks`: add/remove/correct foreign key relationships between tables
  - Under `encoding_types.<table>`: change column data types if autodetection got them wrong (e.g., `TABULAR_NUMERIC_AUTO` → `TABULAR_CATEGORICAL`)

#### Step 5 — Train from the inspection

Open `backend/config/general.yaml` again and set:

```yaml
execution:
  inspection_id: "inspection_20260422_143022"  # paste the ID from Step 3
```

Then run:
```bash
make train
```

Training skips preprocessing and uses your edited schema from `inspection_metadata.json`.

#### Step 6 — Generate synthetic data

List all trained models:
```bash
make models
```

Pick a model ID, then open `backend/config/general.yaml` and set:

```yaml
execution:
  model_id: "model_20260422_144500"  # your model ID from above
  sample_size: 10000  # how many rows to generate (optional)
```

Run:
```bash
make simulate
```

Your synthetic data appears in `backend/outputs/simulations/`.

#### Step 7 — Evaluate results (optional)

List simulations:
```bash
make simulations
```

Pick a simulation ID, update `backend/config/general.yaml`:

```yaml
execution:
  simulation_id: "simulation_20260422_145000"  # your simulation ID
```

Run:
```bash
make eval
```

Evaluation metrics go to `backend/outputs/evaluations/`.

[<-- Back to Main Index](../../README.md)
