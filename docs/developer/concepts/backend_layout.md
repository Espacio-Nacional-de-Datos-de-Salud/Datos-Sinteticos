[<-- Back to Main Index](../../README.md)

# Backend Layout — Plain-Language Tour

This is a map of `backend/src/`. It is written for someone who is **not**
expected to be a backend developer: a data engineer, ML person, or
analyst who wants to know *where to go when I want to change X*.

If you only read one section, read [Section 2](#2-the-seven-folders-at-a-glance).

---

## 1. Mental model — five layers, one direction

When a user clicks "Train model" in the UI, the request travels through
the backend like this:

```
┌──────────┐   HTTP    ┌────────┐   call    ┌────────┐   call   ┌─────────┐
│ Frontend │─────────► │  api/  │─────────► │ sessions  │────────► │ domain/ │
└──────────┘           └────────┘           └────────┘          └─────────┘
                                                │                    │
                                                ▼                    ▼
                                          ┌─────────┐       ┌─────────────────┐
                                          │  runs/  │       │ infrastructure/ │
                                          └─────────┘       └─────────────────┘
                                       (writes run on disk)  (logging, errors,
                                                              helpers)
```

The arrow goes **one way**: outer layers know about inner ones, never the
reverse. `domain/` doesn't know an HTTP request exists. `api/` doesn't
know what a DataFrame is.

That single rule — "calls only go left-to-right" — is what makes the
layout predictable.

---

## 2. The seven folders at a glance

| Folder | One-line job | When you go here |
|---|---|---|
| `api/` | Receives HTTP requests, validates input, returns JSON. | You're adding a new endpoint or changing what a response looks like. |
| `cli/` | Command-line entry points (the interactive CLI, `make train`, etc.). | You want a new `make` target or to tweak the terminal UX. |
| `config/` | Python-side constants and env-driven settings. | You're adding a new config knob the code reads at startup. |
| `sessions/` | **Async session wrappers** for the API/CLI: create the run folder, write the `*_card.json` in `in_progress`, spawn the background thread, mark `success`/`failed`. *No* algorithm logic of its own. | You're adding a new long-running user action, or you need a job's session lifecycle/cancellation to behave differently. |
| `domain/` | The actual data work *and* the coordination of algorithm steps — loading, preprocessing, training, simulating, evaluating, **plus the pipeline engine that chains those steps**. Importable from a notebook with no FastAPI process. | You're changing what the tool computes, or how steps are chained inside a pipeline run. This is where most data-eng work happens. |
| `runs/` | How runs live on disk: the timestamped folders, the `*_card.json` descriptors, the listing/cleanup CLIs, the tracking helpers. | You're changing what gets saved per run, how runs are catalogued, or the cleanup policy. |
| `infrastructure/` | Cross-cutting plumbing used everywhere: logging, custom exceptions, cancellation tokens, progress objects, timing helpers, misc utilities. | You're adding a helper that nothing in particular owns. Rarely. |

---

## 3. Each folder in detail

### `backend/src/api/`

**What it is.** A FastAPI app. One Python file per resource
(`inspections.py`, `models.py`, `simulations.py`, `pipelines.py`,
`evaluations.py`, `files.py`, `configs.py`, `health.py`, `admin.py`).
Plus a `schemas/` subfolder of Pydantic models that describe the
**shape** of every request and response.

**What it must NOT do.** Open files. Call pandas. Train anything. If a
router function is more than ~10 lines, it should be delegating to a
`sessions/` module.

**Folders inside:**
- `routers/` — one file per URL prefix.
- `schemas/` — one file per resource, holding the request/response
  dataclass-like types.

---

### `backend/src/cli/`

**What it is.** Everything you can launch with `python -m backend.src.cli` or `make cli`. Includes the persistent interactive CLI (wizard, parser, command dispatch, detail views, summaries).

**Relation to other layers.** The CLI calls `sessions/` for anything that
runs as a job, and `domain/` for things it can do synchronously
(catalog browsing, config edits).

---

### `backend/src/config/`

**What it is.** Python constants resolved at import time:
- `general.py` — output paths, filenames, default delimiters.
- `evaluation.py` — eval-specific resolvers (venv path, metric defaults).
- `execution.py` — the `ExecutionConfig` dataclass loaded from
  `backend/config/general.yaml` at runtime.
- `field_schemas.py` — shared field titles/descriptions used by both
  the CLI and the frontend so config UIs stay in sync.

**Note.** This is *not* the same as `backend/config/` (the YAML files
the user edits). `src/config/` is the Python that **reads** those YAMLs.

---

### `backend/src/sessions/` — "session wrappers for the API/CLI"

**What it is.** One Python file per long-running user action:
`training.py`, `inspection.py`, `simulation.py`, `evaluation.py`,
`pipeline.py`, `business_rules_configurations.py`. Plus helpers (`configs.py` for bootstrap/clean,
`files.py` for upload handling, `artifacts.py` for download bundles).

**The narrow job.** A `sessions/<x>.py` module does **exactly five
things** and nothing else:

1. **Create the run folder** under `backend/outputs/<kind>/`.
2. **Write `*_card.json` in `in_progress` state synchronously** — so
   the HTTP `202` response can return a valid ID the client can poll.
3. **Spawn a background thread / register a cancel event**.
4. **Call into `domain/`** to do the actual computation.
5. **Catch any exception → mark the card `failed`.** On success →
   mark `success`.

**The "is this sessions/?" test.** Ask:

- *"Could a Jupyter notebook user reasonably want to call this
  directly?"* → if yes, it belongs in `domain/`, not here.
- *"Does this exist only to give the HTTP layer an ID to return, or to
  manage a card, thread, or cancel token?"* → if yes, it belongs here.

**Why this layer exists at all.** `domain/` engines are stateless
("pandas in, artifacts out"). Sessions are the ones who know a run
exists, has on-disk state, can be cancelled, and writes to a specific
folder. Keep them thin — most files here are a couple hundred lines of
session plumbing wrapping one or two engine calls.

> **Naming note for the new dev.** The folder is called `sessions/`,
> not `orchestration/` — because the English word "orchestration" is
> overloaded. `domain/pipeline/` *also* orchestrates things (it
> orchestrates *algorithm steps* of one pipeline run). To avoid the
> word collision, the **API/CLI session-wrapping layer** is named
> `sessions/`. If you see code or docs referring to an
> "orchestration layer", that's pre-rename terminology for `sessions/`.

---

### `backend/src/domain/` — "the actual business logic that processes the data"

**What it is.** Pure logic. Pandas in, pandas (or artefacts on disk) out.
No HTTP, no threading, no card files.

| Subpath | What it does |
|---|---|
| `domain/loader.py` | Reads CSV / Parquet / Excel into a `{table_name: DataFrame}` dict. |
| `domain/preprocessing/` | Cleans data, infers metadata, applies logical/derived rules, builds profiling reports. |
| `domain/synthesis/` | Engine-agnostic synthesis package. `base.py` defines the `SynthesisEngine` protocol; `factory.py` builds an engine by name; `registry.py` registers available engines; `mostly.py` is the Mostly AI implementation; `training_diagnostics.py` has pre-flight checks and failure summarisation. |
| `domain/modeling_configuration.py` | Helpers for recording modeling-mode intent (flat vs sequential) without leaking local fields to the engine. |
| `domain/general_sanity_checks.py` + `preprocessing_contextual_sanity_checks.py` | Cross-table referential and contextual checks. |
| `domain/id_validation.py` | Validates `inspection_id`, `model_id`, etc. (the format and existence). |
| `domain/rules_config.py` | Loads/merges the user-facing rules YAML. Centralises the `RULE_MAP` type registry. |
| `domain/pipeline/` | The **pipeline execution engine**. Reads a pipeline YAML, deep-merges per-job config, and sequentially runs each step (`inspect` / `train` / `simulate` / `evaluate`) by calling the matching `sessions/<step>.py`. Runnable on its own: `python -m backend.src.domain.pipeline --config <yaml>`. This is the one place `domain/` reaches *back* into `sessions/` — see § 5 for why. |
| `domain/evaluation/` | The evaluation engine. Loads real & synthetic data, runs synthcity metrics, runs custom metrics, computes bootstrap statistics. Runs in `.venv_eval` because it depends on torch/synthcity. |

If your change is "I need the model to handle dates differently", "I want a new sanity check", "I want a new metric" — you almost certainly work here.

---

### `backend/src/runs/` — "how a run is stored on disk"

The tool is built around one strong convention:

> Every run (inspection, model, simulation, evaluation, pipeline) is a
> timestamped folder under `backend/outputs/<kind>/` containing exactly
> one `*_card.json` file that describes it, plus artefacts.

Everything that knows about that convention lives here.

| Subpath | What it does |
|---|---|
| `runs/card_io.py` | Read/write the JSON descriptors. Functions like `update_card_status`, `mark_card_failed`, `read_json`, `write_json`. |
| `runs/catalog/` | One module per run-type that lists, classifies (active / empty / orphan), deletes, and bundles for download. Each is also runnable as a CLI (`python -m backend.src.runs.catalog.models --format table`). |
| `runs/tracking/` | Per-run trackers that accumulate metadata while a run is in progress (training metrics, evaluation metrics, pipeline job index). |

If your change touches "what's inside the card", "how do we list models",
"how do we clean up empty folders" — work here.

---

### `backend/src/infrastructure/` — "the transversal common helpers other folders use"

Cross-cutting helpers. Every folder above imports from `infrastructure/`,
and nothing in `infrastructure/` imports back. Contents:

| File | Purpose |
|---|---|
| `logging_config.py` | Project-wide logger setup. Every other module calls `get_logger(__name__)`. |
| `errors.py` | Custom exception classes (`DataLoadError`, etc.) so the API can translate them to HTTP status codes. |
| `cancellation.py` | `CancellableThread` + cooperative cancel-event helpers used by every flow. |
| `progress.py` | The phase/progress dataclasses the frontend polls to render progress bars. |
| `time_profiling.py` | "Total elapsed time per phase" report writer. |
| `utils.py` | Small generic helpers that don't belong to any one engine. |


## 5. Logical direction of imports

`api/` → `sessions/` → `domain/`  
`sessions/` and `domain/` may use `runs/` and `infrastructure/`  
`runs/` may use `infrastructure/`  
`infrastructure/` imports nothing from above, but rather it is used by above modules.

If you find yourself wanting `domain/` to import from `sessions/` or
`api/`, the abstraction is wrong — promote the shared piece down, not up.

### The one documented exception: `domain/pipeline/` → `sessions/`

`domain/pipeline/executor.py` imports from `sessions/training.py`,
`sessions/simulation.py`, and `sessions/evaluation.py`. This **breaks
the rule on purpose**, and you should understand why before adding any
similar import.

A pipeline is itself an orchestrator — but of *algorithm steps*, not
of API sessions. When the pipeline engine runs the `train` step of a
job, it wants the same session machinery the API would give that
training run: its own `model_<ts>/` folder, its own `model_card.json`,
its own thread of failure handling. Reaching into `sessions/training.py`
gives it that for free. The alternative would be duplicating the
session lifecycle inside the pipeline engine.

The trade-off: `domain/pipeline/` is no longer importable from
contexts that haven't initialized `sessions/`'s side-effects (logging,
config paths, etc.). In practice that's fine — `domain/pipeline/` only
runs from `make pipeline` or from the API, both of which load the same
process state anyway.

**Do not generalize this exception.** No other `domain/` subpackage
should import from `sessions/`. If you find yourself wanting that,
either (a) move the shared helper *down* into `domain/` or `runs/`, or
(b) split your new feature into a domain-side engine plus a
sessions-side wrapper, the same way every other action is split.
