[<-- Back to Main Index](../README.md)

# Onboarding Guide

Welcome. This document is the **mental model** for the repository: what
lives where, which entry point to use when, and which config file
controls which behavior. For coding standards, commit style, and
docstring format see [Repository Guidelines](repository_guidelines.md).
For step-by-step setup, see [Setup & Execution](setup_and_config/setup_and_execution.md).


## 1. What This Tool Does

Generates synthetic tabular health data for the ENDS (Espacio Nacional
de Datos de Salud). The core workflow is:

```
raw tables ──► inspect ──► train ──► simulate ──► evaluate
   (CSV/Parquet/XLSX)    (generator)  (synthetic)   (metrics)
```

The generator is the [Mostly AI SDK](concepts/mostly_ai.md); logical
constraints on the output are enforced through
[Logical Rules](concepts/logical_rules.md); experiment lineage is
written to [MLflow](concepts/tracking_and_mlflow.md).

## 2. Repository Map

| Path | What you'll find | When you edit it |
| :--- | :--- | :--- |
| `src/main.py` | Entry point for single-run inspect/train/simulate | Rarely — behavior is driven by `execution_config.py` |
| `src/pipeline.py` | Entry point for multi-step YAML-driven runs | When adding pipeline features |
| `src/evaluation/__main__.py` | Entry point for standalone evaluation (`python -m src.evaluation`) | Rarely |
| `src/core/` | Business logic: preprocessing, synthesis, tracking, rules, sanity checks | Where most day-to-day work happens |
| `src/evaluation/` | Evaluation orchestration, metric runners, statistics, and synthcity-facing helpers (isolated — runs in `.venv_eval`) | When adding/fixing metrics |
| `src/api/`, `src/cli/` | Reserved for future REST API / CLI front-ends | Not yet implemented  |
| `config/` | All configuration (see section 4) | Whenever you change defaults or add a rule |
| `data/` | Input datasets (usually a symlink) | git-ignored |
| `outputs/` | Artifacts: `models/`, `simulations/`, `inspections/`, `pipelines/` | Generated, not edited (only `autodetect.json`) |
| `docs/` | Documentation (Markdown) | When behavior changes |
| `scripts/` | Windows PowerShell helpers (`setup.ps1`, `run.ps1`), data converters | Rarely |
| `notebooks/` | Exploratory analyses | Not required for execution |


## 3. Three Entry Points — Which One Do I Use?

This is the single biggest source of confusion. Use this matrix:

| Scenario | Command | Underlying script | Venv |
| :--- | :--- | :--- | :--- |
| I want to inspect/train/simulate **one** dataset, one-off | `make inspect` / `make train` / `make simulate` | `src/main.py` | `.venv_core` |
| I only want to **evaluate** an existing simulation (ad hoc) | `make eval` | `python -m src.evaluation` | `.venv_eval` |
| I want to run **many combinations** (sweeps, experiments, reruns) | `make pipeline CONFIG=...` | `src/pipeline.py` | `.venv_core` (+ `.venv_eval` for eval step) environment sorted automatically by the pipeline |

Tips:
- Prefer `pipeline` for anything repeatable. It logs a combined session,
  writes a `pipeline_summary.json`, and ties every child run to a
  single `pipeline_id` in MLflow.
- Use `make inspect` → edit `autodetect.json` → `make train` when you
  need to fix autodetected PKs/FKs or encoding types. See
  [Setup & Execution Section 4](setup_and_config/setup_and_execution.md#4-recommended-end-to-end-flow).
- Use `python -m src.evaluation` for a quick standalone evaluation outside
  any pipeline. The pipeline's `evaluate:` step calls the same
  `run_evaluation(...)` orchestration internally.


## 4. Configuration

Full reference: [Setup & Execution Section 2](setup_and_config/setup_and_execution.md#2-the-config-directory).
Quick map:

| File | Controls | Typical newcomer edit |
| :--- | :--- | :--- |
| `config/general_config.py` | Paths, MLflow URIs, system-wide defaults | Set `DEFAULT_DATA_PATH` |
| `config/execution_config.py` | Parameters for a `src/main.py` run: mode, file paths, IDs | Set `FILE_PATHS`, `MODEL_ID`, `INSPECTION_ID` before `make <mode>` |
| `config/mostly_ai_config.yaml` | Mostly AI hyperparameters (epochs, batch, DP) | Tweak for memory / speed / privacy |
| `config/rules.yaml` | Global logical rules | Add per-dataset constraints |
| `config/pipelines/*.yaml` | Pipeline job definitions | See `example_pipeline.yaml` |
| `config/pipelines/rules/*.yaml` | Per-job rules referenced from a pipeline's `rules_config` override | Create one per experiment with custom constraints |
| `config/evaluation/evaluation_config.py` | Metrics, bootstrap size, eval subprocess interpreter | Disable heavy metrics (`DomiasMIA_BNAF`) while iterating |
| `config/evaluation/statistics.yaml` | Custom per-column statistics | When validating transformations |

### Config cascade in a pipeline

```
global defaults  (general_config.py, mostly_ai_config.yaml, rules.yaml)
        │
        ▼  deep-merged at job start, per job
per-job config:  (rules_config / mostly_ai / general in the YAML)
        │
        ▼
step inputs      (train.files, simulate.sample_size, evaluate.real_data)
```

Overrides apply **only to the job that defines them**. See
`config/pipelines/example_pipeline.yaml` for annotated cases.


## 5. The Two Virtual Environments

Evaluation depends on `synthcity`, `torch`, and related packages that conflict directly with the training dependencies, so the repo ships **two** isolated venvs:

| Venv | Contents | Used by |
| :--- | :--- | :--- |
| `.venv_core` | Mostly AI SDK, pandas, MLflow, ruff, pytest (`requirements_core.txt`) | `make inspect` / `train` / `simulate` / `pipeline`, all lint/format, tests |
| `.venv_eval` | synthcity, torch, opacus, evaluation utilities (`requirements_evaluation.txt`) | `make eval`, pipeline's `evaluate:` step when `EVAL_PYTHON_PATH` is set |

**How the pipeline bridges them:** when `EVAL_PYTHON_PATH` is exported,
`src/pipeline.py` launches `python -m src.evaluation` as a
**subprocess** using that interpreter. stdout/stderr are forwarded to
the pipeline log, so from the user's side it looks like a single run.

> If you are writing code that imports `synthcity`, `torch`, or anything
> from `requirements_evaluation.txt`, it lives in `src/evaluation/` and
> must be runnable under `.venv_eval`. The rest of the repo must stay
> clean of those imports.

`make setup` builds both venvs automatically.


## 6. Output Structure

Every run writes under `outputs/`:

```
outputs/
├── inspections/inspection_<ts>/      # schema + cached parquet, pre-training
├── models/model_<ts>/                # generator.zip + model_card.json
├── simulations/simulation_<ts>/      # synthetic CSVs + sim_card.json
├── pipelines/pipeline_<ts>/          # session.log + pipeline_summary.json
└── mostlyai/                         # Mostly AI local server scratch space
```

`outputs/mostlyai/` is created automatically by the library, its not a directory we are working with. Ignore it.

All IDs are `<prefix>_YYYYMMDD_HHMMSS`. Discover them with:

```bash
make inspections
make models
make simulations
```


## 7. First Steps

In order, to build familiarity:

1. Read [Setup & Execution](setup_and_config/setup_and_execution.md). Run `make setup`, then `make help`.
2. Point `DEFAULT_DATA_PATH` at a small dataset, then
   `make inspect` → `make train` → `make simulate`.
3. Copy `config/pipelines/example_pipeline.yaml` to a new file and run
   `make pipeline CONFIG=config/pipelines/<your_file>.yaml`.
4. Open the generated `outputs/pipelines/pipeline_<ts>/session.log` and
   `pipeline_summary.json` to see the end-to-end trace.
5. Browse `docs/concepts/` to learn how each stage works internally.


[<-- Back to Main Index](../README.md)
