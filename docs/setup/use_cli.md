[<-- Back to Main Index](../../README.md)

# Use the CLI

For users who want to **drive the tool from a terminal** — no browser,
no Docker. Two flavours, same backend:

| Flavour | When to pick it |
| :--- | :--- |
| **Interactive wizard (`make cli`)** | You don't want to edit YAMLs by hand. A menu walks you through each step and remembers state between flows. |
| **`make` one-shots** (`make inspect`, `make train`, …) | You already know what you want to run; you'd rather edit `general.yaml` and dispatch one mode at a time. Best for scripting and CI. |

You can mix them freely — they read and write the same run folders
under `backend/outputs/`.

> For the complete, in-depth usage guide see the full user manual:
> [Manual de instrucciones](<../documentacion-completa/Manual de instrucciones de la herramienta de generación de datos sintéticos 20260630.docx>).

---

## 0. Install

Do the one-time setup from [Installation](install.md). Verify the
venvs exist before continuing.

---

## 1. Interactive wizard

```bash
make cli
```

A persistent session opens. Pick a flow, follow the prompts. Type
`volver` to step back to the previous menu; type `salir` to exit. When
a flow finishes, the prompt returns so you can chain the next step
without relaunching.

The wizard covers all five flows: `inspect`, `train`, `simulate`,
`evaluate`, `pipeline`. It also lets you browse past runs (catalog
listings, run details).

---

## 2. `make` one-shots (recommended for repeatable workflows)

Each target reads `backend/config/general.yaml`, sets `execution.mode`
for you, and dispatches to the right backend module under the right
venv.

| Flag | Target | Mode | Purpose |
| :--- | :--- | :--- | :--- |
| `i` | `make inspect` | Inspect | Load + preprocess + autodetect metadata. Stops before training so you can review/edit relationships and encoding. |
| `t` | `make train` | Train | Train a generator (from raw files or from a previous inspection). |
| `s` | `make simulate` | Simulate | Generate synthetic data from a trained model. |
| `e` | `make eval` | Evaluate | Compare synthetic data against the original. Runs under `.venv_eval`. |
| `p` | `make pipeline CONFIG=<file>` | Pipeline | Run the full end-to-end pipeline driven by a YAML. |

Discover what's been produced with the catalog targets:

```bash
make inspections    make models    make simulations    make evaluations    make pipelines
```

---

## 3. The recommended workflow (inspect → review → train → simulate → evaluate)

`make pipeline` runs everything end-to-end in one shot. But for a new
dataset the recommended sequence is **inspect → review → train** so
you can fix autodetected primary keys, foreign keys, and encoding
types before paying for a training run.

### Step 1 — Configure your data source

Open `backend/config/general.yaml` and point it at your input:

```yaml
execution:
  file_paths:
    - "data/my_data.csv"   # or wherever your CSV/Parquet/XLSX lives
```

### Step 2 — Inspect

```bash
make inspect
```

Writes a new session under `backend/outputs/inspections/inspection_<ts>/`.

### Step 3 — Pick the inspection

```bash
make inspections
```

Copy the `inspection_id` (looks like `inspection_20260422_143022`).

### Step 4 — Review the autodetected schema

Open `backend/outputs/inspections/<your_inspection_id>/`:

- `profiling_reports/` — open the HTML files in a browser to view data
  distributions, types, and missing values per table.
- `autodetected_inspection_metadata.json` — **read-only historical
  copy**. Don't edit; it's there for the record.
- `inspection_metadata.json` — **source of truth** for training. Edit
  this file if autodetection got something wrong:
  - `relationships.pks` — add/remove/correct primary key columns.
  - `relationships.fks` — add/remove/correct foreign key relationships.
  - `encoding_types.<table>` — change column data types
    (e.g. `TABULAR_NUMERIC_AUTO` → `TABULAR_CATEGORICAL`).

### Step 5 — Train

Set the inspection ID in `general.yaml`:

```yaml
execution:
  inspection_id: "inspection_20260422_143022"
```

```bash
make train
```

Training reads your edited `inspection_metadata.json` and skips
preprocessing.

### Step 6 — Simulate

```bash
make models
```

Pick a `model_id` and set:

```yaml
execution:
  model_id: "model_20260422_144500"
  sample_size: 10000          # optional, overrides the global default
```

```bash
make simulate
```

Results land in `backend/outputs/simulations/simulation_<ts>/`.

### Step 7 — Evaluate

```bash
make simulations
```

Pick a `simulation_id`:

```yaml
execution:
  simulation_id: "simulation_20260422_145000"
```

```bash
make eval
```

Metrics land in `backend/outputs/evaluations/evaluation_<ts>/`.
`make eval` is the one target that runs under `.venv_eval` — you don't
need to activate it yourself, the `Makefile` handles the switch.

---

## 4. Running an end-to-end pipeline

When you want every step in one shot — including for sweeps across
many configs:

```bash
make pipeline CONFIG=backend/config/pipelines/example_pipeline.yaml
```

The pipeline writes
`backend/outputs/pipelines/pipeline_<ts>/pipeline_card.json` and tags
every child run (inspection / model / simulation / evaluation) with
the same `pipeline_id` so you can group them later.

The pipeline YAML format is annotated line-by-line in
`backend/config/pipelines/example_pipeline.example.yaml`. For the
conceptual overview of the pipeline engine, see the
[Documentación técnica](<../documentacion-completa/Documentación técnica 20260630.docx>).

---

## 5. Running the API or frontend on their own

You don't strictly need either for CLI workflows, but for completeness:

```bash
make api          # backend only, exposes http://localhost:8000/docs
make frontend     # frontend only, expects an API already running
make local        # both, in one terminal (UI users — see use_ui.md)
```

## 6. CLI from a Docker

You can also run the CLI in any OS you like with `make compose-cli`. Same goes for the API with `make compose-api`.

[<-- Back to Main Index](../../README.md)
