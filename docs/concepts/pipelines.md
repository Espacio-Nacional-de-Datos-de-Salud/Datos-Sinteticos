[<-- Back to Main Index](../../README.md)

# Pipelines

Run multiple synthetic-data jobs in sequence from a single YAML file.

```bash
python -m src.pipeline --config backend/config/pipelines/my_pipeline.yaml
```

## How It Works

A pipeline YAML defines a list of **jobs**. Each job can include any
combination of three steps that execute in order:

1. **train** — load raw data, preprocess, train a Mostly AI generator
2. **simulate** — generate synthetic records from a generator
3. **evaluate** — compare synthetic data against real data

### Execution Modes

The pipeline is highly modular. Steps can be combined in several ways depending on your needs:

#### Full Sequential (Standard)
Includes all three steps. Artifacts (model, metadata, rules) flow automatically from one step to the next.
```yaml
train: [files...]
simulate: {sample_size: 1000}
evaluate: {real_data: [files...]}
```

#### Resume from Model
Skip training and generate new data from an existing model folder. The model artifacts are loaded automatically from `outputs/models/`.
```yaml
simulate:
  model_id: "model_20260311_143001"
  sample_size: 2000
evaluate:
  real_data: ["data/person.csv"]
```

#### Resume from Simulation
Perform evaluation on an existing simulation folder. Useful for re-running metrics with new configurations or debugging.
```yaml
evaluate:
  real_data: ["data/person.csv"]
  simulation_id: "simulation_20260311_143001"
  model_id: "model_20260311_143001" # optional; enables MLflow lineage
```

Artifacts flow automatically within a job. Any step can be omitted.

## Pipeline Output

Running a pipeline creates:

```
outputs/
├── pipelines/
│   └── pipeline_20260311_143000/
│       ├── session.log              # combined log of all jobs
│       └── pipeline_card.json    # references to every job's outputs
├── models/
│   ├── model_20260311_143001/       # job 1 training artifacts
│   └── model_20260311_143200/       # job 2 training artifacts
├── simulations/
│   ├── simulation_20260311_143001/   # job 1 simulation artifacts
│   └── simulation_20260311_143200/   # job 2 simulation artifacts
└── evaluations/
    ├── evaluation_20260311_143001/   # job 1 evaluation artifacts
    └── evaluation_20260311_143200/   # job 2 evaluation artifacts
```

- **`pipeline_card.json`** links each job name to its `model_id` and
  `simulation_id` so you can trace which output came from which job.
- **`session.log`** captures the combined log of every job in the pipeline.
- Individual model/simulation folders contain the same artifacts as standalone
  runs (generator.zip, metadata.json, model_card.json, synthetic CSVs, sanity
  reports, etc.).

Every model card and sim card includes a `pipeline_id` field so you can filter
MLflow runs that belong to the same pipeline execution.

### Pipeline Card Lifecycle

The card is rewritten after every job finishes, so the on-disk state always
reflects which jobs have already produced artifacts — even if the process
is killed mid-pipeline. Each job entry includes its own `status`
(`completed` if it produced a model or simulation, `failed` otherwise),
and the top-level `status` field can take four values:

| Status | Meaning |
| :--- | :--- |
| `in_progress` | The tracker is still open, or the process crashed without closing it. |
| `completed` | Exited cleanly and every job finished with `status == "completed"`. |
| `partial` | At least one job produced artifacts and at least one did not (either another job failed or the pipeline was interrupted after some jobs had already succeeded). |
| `failed` | No job produced any artifact. |

This distinction matters for cleanup (see below): only `failed` pipelines
are considered disposable — `partial` runs keep valuable artifacts and
are preserved.


## Full Example

```yaml
jobs:
  # Train + simulate with custom rules and Mostly AI hyperparameters
  - name: "high_privacy_dataset"
    config:
      rules_config: "backend/config/pipelines/rules/rules_pipeline_job1.yaml"
      mostly_ai:
        model_settings:
          max_epochs: 500
          batch_size: 24
          differential_privacy:
            max_epsilon: 5
            noise_multiplier: 2.0
      general:
        enable_data_profiling: true
    train:
      files:
        - "data/person.csv"
        - "data/procedure_occurrence.csv"
    simulate:
      sample_size: 1000
    evaluate:
      real_data:
        - "data/person.csv"
        - "data/procedure_occurrence.csv"

  # Simulate from an already-trained model (no config overrides)
  - name: "resimulate_existing"
    simulate:
      model_id: "model_20260227_092550"
      sample_size: 500

  # Evaluate an existing simulation
  - name: "late_evaluation"
    evaluate:
      real_data:
        - "data/person.csv"
      simulation_id: "simulation_20260304_183943"
      model_id: "model_20260227_092550"
```

## Per-Job Config

Each job can optionally include a `config` section to override global settings
**only for that job**. When omitted, the job uses the defaults from
`backend/config/general.yaml` and `backend/config/mostly_ai.yaml`.

### `rules_config`

Path to a job-specific rules YAML (same format as `backend/config/rules.yaml`).
Defaults to the active `rules` config.

### `mostly_ai`

Deep-merge overrides applied on top of `backend/config/mostly_ai.yaml`. Only
the keys you specify are changed; everything else keeps its default.

```yaml
mostly_ai:
  model_settings:
    max_epochs: 500
    batch_size: 24
    differential_privacy:
      max_epsilon: 10
```

### `general`

```yaml
general:
  enable_data_profiling: true
```

## Evaluation in a Separate Virtual Environment

The evaluation step depends on `synthcity`, `torch`, and other heavy packages
(listed in `requirements_evaluation.txt`) that conflict with the main training
environment. To handle this, the pipeline supports running evaluation as a
**subprocess** using a different Python interpreter.

### Setup

1. Create the evaluation venv and install its dependencies:

```bash
python -m venv venv_eval
venv_eval/bin/pip install -r requirements_evaluation.txt
```

2. Set the `EVAL_PYTHON_PATH` environment variable before running the pipeline:

```bash
export EVAL_PYTHON_PATH=/path/to/venv_eval/bin/python
python -m src.pipeline --config backend/config/pipelines/my_pipeline.yaml
```

When `EVAL_PYTHON_PATH` is set, the pipeline launches `python -m src.evaluation`
as a subprocess using that interpreter. All stdout/stderr from the
evaluation process is captured and forwarded to the pipeline log.

When `EVAL_PYTHON_PATH` is **not** set (default), evaluation runs in-process
as before, which requires `synthcity` to be installed in the active
environment.


[<-- Back to Main Index](../../README.md)
