[<-- Back to Main Index](../../README.md)

# Onboarding Guide

Welcome. This document is the **mental model** for the repository: what lives where, which entry point to use when, and which config file controls which behavior. For coding standards, commit style, and docstring format see [Repository Guidelines](repository_guidelines.md).

For step-by-step setup, see [Setup & Execution](setup.md).


## 1. What This Tool Does

Generates synthetic tabular health data for the ENDS (Espacio Nacional
de Datos de Salud). The core workflow is:

```
raw tables ──► inspect ──► train ──► simulate ──► evaluate
   (CSV/Parquet/XLSX)    (generator)  (synthetic)   (metrics)
```

The generator is the [Mostly AI SDK](../concepts/mostly_ai.md); logical
constraints on the output are enforced through
[Logical Rules](../concepts/logical_rules.md); experiment lineage is
written to [MLflow](../concepts/tracking_and_mlflow.md).

## 2. Repository Map

| Path | What you'll find | When you edit it |
| :--- | :--- | :--- |
| `docs/` | Documentation (Markdown) | When behavior changes |
| `scripts/` | Windows PowerShell helpers (`setup.ps1`, `run.ps1`), data converters | Rarely |
| `notebooks/` | Exploratory analyses | Not required for execution |
| `backend/config/` | All configuration (see section 4) | Whenever you change defaults or add a rule |
| `backend/data/` | Input datasets (usually a symlink) | git-ignored |
| `backend/outputs/` | Artifacts: `models/`, `simulations/`, `evaluations/`, `inspections/`, `pipelines/` | Generated, not edited (only `autodetect.json`) |
| `backend/src/` | Backend source code | - |
| `backend/src/cli/` | Entry point for single-run inspect/train/simulate, including the interactive CLI | Rarely — usually use `make cli` or the Make targets |
| `backend/src/pipeline/` | The core execution engine for multi-step YAML-driven runs | When modifying how pipelines parse YAMLs or orchestrate jobs |
| `backend/src/services/` | Facade/Integration layer for external interfaces (like APIs) | When adding logic to expose functionality externally with session state |
| `backend/src/evaluation/__main__.py` | Entry point for standalone evaluation (`python -m src.evaluation`) | Rarely |
| `backend/src/core/` | Business logic: preprocessing, synthesis, tracking, rules, sanity checks | Where most day-to-day work happens |
| `backend/src/evaluation/` | Evaluation orchestration, metric runners, statistics, and synthcity-facing helpers (isolated — runs in `.venv_eval`) | When adding/fixing metrics |
| `backend/src/api/`, `src/cli/` | Reserved for future REST API / CLI front-ends | Not yet implemented  |


## 3. Three Entry Points — Which One Do I Use?

This is the single biggest source of confusion. Use this matrix:

| Scenario | Command | Underlying script | Venv |
| :--- | :--- | :--- | :--- |
| I want to inspect/train/simulate **one** dataset, one-off | `make inspect` / `make train` / `make simulate` | `src/main.py` | `.venv_core` |
| I only want to **evaluate** an existing simulation (ad hoc) | `make eval` | `python -m src.evaluation` | `.venv_eval` |
| I want to run **many combinations** (sweeps, experiments, reruns) | `make pipeline CONFIG=...` | `src/pipeline/` (`-m src.pipeline`) | `.venv_core` (+ `.venv_eval` for eval step) environment sorted automatically by the pipeline |

Tips:
- Prefer `pipeline` for anything repeatable. It logs a combined session,
  writes a `pipeline_card.json`, and ties every child run to a
  single `pipeline_id` in MLflow.
- Use `make inspect` → edit `autodetect.json` → `make train` when you
  need to fix autodetected PKs/FKs or encoding types. See
  [Setup & Execution Section 4](setup.md).
- Use `python -m src.evaluation` for a quick standalone evaluation outside
  any pipeline. The pipeline's `evaluate:` step calls the same
  `run_evaluation(...)` orchestration internally.


## 4. Configuration

Full reference: [Setup & Execution Section 2](setup.md).
Quick map:

| File | Controls | Typical newcomer edit |
| :--- | :--- | :--- |
| `backend/src/config/general.py` | Paths, MLflow URIs, non-tunable system defaults | Set `DEFAULT_DATA_PATH` |
| `backend/config/general.yaml` | Runtime settings + per-run execution params (mode, file paths, IDs) | Run `make config` to create it, then edit `execution.*` before `make <mode>` |
| `backend/config/mostly_ai.yaml` | Mostly AI hyperparameters (epochs, batch, DP) | Tweak for memory / speed / privacy |
| `backend/config/rules.yaml` | Global logical rules | Add per-dataset constraints |
| `backend/config/pipelines/*.yaml` | Pipeline job definitions | See `example_pipeline.yaml` |
| `backend/config/pipelines/rules/*.yaml` | Per-job rules referenced from a pipeline's `rules_config` override | Create one per experiment with custom constraints |
| `backend/src/config/evaluation.py` | Env-driven evaluation resolvers (interpreter path, custom stats module) | Rarely touched |
| `backend/config/evaluation.yaml` | Metrics, bootstrap size, CI level, statistics list | Disable heavy metrics (`DomiasMIA_BNAF`) while iterating; add per-column stats |

### Config cascade in a pipeline

```
global defaults  (general.yaml, mostly_ai.yaml, rules.yaml)
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
the pipeline engine launches `python -m src.evaluation` as a
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
├── evaluations/evaluation_<ts>/      # metric reports + eval_card.json
├── pipelines/pipeline_<ts>/          # session.log + pipeline_card.json
└── mostlyai/                         # Mostly AI local server scratch space
```

`outputs/mostlyai/` is created automatically by the library, its not a directory we are working with. Ignore it.

All IDs are `<prefix>_YYYYMMDD_HHMMSS`. Discover them with:

```bash
make inspections
make models
make simulations
```


[<-- Back to Main Index](../../README.md)
