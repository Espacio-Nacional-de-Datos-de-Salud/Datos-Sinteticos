[<-- Back to Main Index](../../README.md)

# Developer Onboarding

For someone who will **maintain and extend** the tool, not just run
it. By the end of this doc you'll have the environment installed, the
tool running through all three entry points, a working mental model
of how a request travels through the codebase, and one tiny change
shipped.

The narrative is ordered. Hit each checkpoint before moving on. Where
a step has a standalone reference doc, the body stays short and links
out — you read the long version only when you need it.


## 0 — What this tool does

Generates synthetic tabular health data for the ENDS (Espacio Nacional
de Datos de Salud). The core workflow is:

```
raw tables ──► inspect ──► train ──► simulate ──► evaluate
   (CSV/Parquet/XLSX)    (generator)  (synthetic)   (metrics)
```

The generator is the [Mostly AI SDK](../concepts/mostly_ai.md); logical
constraints on the output are enforced through
[Logical Rules](../concepts/logical_rules.md); every run writes a card
under `backend/outputs/<step>/` recording its lineage, status, and
artifacts.


### Repo structure

Use this when something exists outside `backend/src/` and you want to
know what it is. For the inside of `backend/src/`, go to
[Backend Layout](../concepts/backend_layout.md).

| Path | What you'll find | When you edit it |
| :--- | :--- | :--- |
| `docs/` | Documentation (Markdown) | When behavior changes |
| `scripts/` | Windows PowerShell helpers (`setup.ps1`, `run.ps1`), data converters | Rarely |
| `notebooks/` | Exploratory analyses | Not required for execution |
| `frontend/` | Next.js app | When changing the UI |
| `backend/config/` | All user-editable YAML configuration | Whenever you change defaults or add a rule |
| `backend/data/` | Input datasets (usually a symlink) | git-ignored |
| `backend/outputs/` | Run artifacts: `inspections/`, `models/`, `simulations/`, `evaluations/`, `pipelines/` | Generated, not edited |
| `backend/src/` | Backend source code — see [Backend Layout](../concepts/backend_layout.md) | Everywhere |
| `tests/` | Pytest suite. `tests/eval/` runs under `.venv_eval` | When you add behaviour |
| `Makefile` | Every entry point a dev uses | When you add a new `make` target |
| `compose.yaml` / `compose.override.yaml` | Docker compose for backend + frontend | When changing how the tool is containerised |

---

## 1 — Install the environment

Follow [Installation](install.md). When you come back, both venvs and
real `backend/config/*.yaml` files should exist.

**Checkpoint.** `ls .venv_core/bin/python .venv_eval/bin/python` both
exist; `ls backend/config/*.yaml` shows real (not `.example`) files.

---

## 2 — Run the tool through every entry point

The tool ships three drivers — frontend / interactive CLI / `make`
one-shots — and they all reach the same `src/sessions/` wrappers and
`src/domain/` engines. Going through each at least once is the
fastest way to understand why they're interchangeable.

| Driver | Run it now | Full guide |
| :--- | :--- | :--- |
| Frontend | `make local`, then open `http://localhost:3000`. Inspect → train → simulate → evaluate `data/uploads/dataset_prueba_tecnica_v2.csv` via the UI. | [Use the UI](use_ui.md) |
| Interactive CLI | `make cli`, walk through the wizard for the same dataset. | [Use the CLI § 1](use_cli.md#1-interactive-wizard) |
| `make` one-shots | `make inspect` → `make train` → `make simulate` → `make eval`, editing IDs in `general.yaml` between steps. | [Use the CLI § 3](use_cli.md#3-the-recommended-workflow-inspect--review--train--simulate--evaluate) |
| End-to-end pipeline | `make pipeline CONFIG=backend/config/pipelines/example_pipeline.yaml` | [Use the CLI § 4](use_cli.md#4-running-an-end-to-end-pipeline) |

While you run them, in another terminal:

```bash
ls backend/outputs/inspections/ backend/outputs/models/ \
   backend/outputs/simulations/ backend/outputs/evaluations/ \
   backend/outputs/pipelines/
```

Watch the timestamped folders appear and the `*_card.json` files
transition from `in_progress` → `success`.

**Checkpoint.** You can open any `*_card.json` and recognise the
fields. You can answer: "if I drive this from the UI vs. `make cli`
vs. `make pipeline`, what's the same and what's different?" (Answer:
the resulting run folder and card are identical; only the driver
differs.)

> For sweeps / many config combinations, always prefer
> `make pipeline CONFIG=...` over chaining single-mode targets — one
> session log, one `pipeline_card.json`, and every child run is tagged
> with the same `pipeline_id`.

---

## 3 — The configuration model

The user-editable YAML config surface is documented in
[Configuration](configuration.md). The one structural thing you
should internalise before reading the per-file reference is the
**cascade inside a pipeline**:

```
global defaults  (general.yaml, mostly_ai.yaml, rules.yaml)
        │
        ▼  deep-merged at job start, per job
per-job config:  (rules_config / mostly_ai / general in the YAML)
        │
        ▼
step inputs      (train.files, simulate.sample_size, evaluate.real_data)
```

Overrides apply **only to the job that defines them**. The annotated
reference is `backend/config/pipelines/example_pipeline.example.yaml`
— read its comments line-by-line; most of the pipeline mental model
is in that file. Conceptual overview: [Pipelines](../concepts/pipelines.md).

---

## 4 — Read the code, top to bottom of one slice

Read [Backend Layout](../concepts/backend_layout.md) § 1–2 first — the
five layers (`api/`, `sessions/`, `domain/`, `runs/`,
`infrastructure/`) and the one-direction import rule. Skim § 3 (folder
details) and come back to it when you need a specific subpath.

Then pick **simulation** and trace it end-to-end:

| Layer | File | Read for… |
| :--- | :--- | :--- |
| API | `backend/src/api/routers/simulations.py` | The `POST /simulations` endpoint the frontend calls. |
| Schema | `backend/src/api/schemas/simulations.py` | The Pydantic request/response contracts. |
| Sessions | `backend/src/sessions/simulation.py` | Session creation, background thread, card lifecycle. |
| Engine | `backend/src/domain/synthesis/mostly.py` | The actual call into the Mostly AI SDK that samples rows. |
| Run on disk | `backend/src/runs/tracking/` + `backend/src/runs/catalog/simulations.py` | How the card is written and later listed. |

**Checkpoint.** You can answer: "when the frontend POSTs to
`/simulations`, what is the call chain until rows are written to
disk?" You can also explain why `sessions/` is *not* the same kind of
orchestration as `domain/pipeline/` ([Backend Layout § 5](../concepts/backend_layout.md#5-logical-direction-of-imports)).

---

## 5 — Standards, tests, daily commands

- [Contributing](../../CONTRIBUTING.md) — commit style,
  branch naming, docstring format. Read once, refer to often.
- [Testing](testing.md) — `make test` (core venv) vs `make test-eval`
  (eval venv); when to write each kind.
- `make help` — every Makefile target with one-line descriptions.

[<-- Back to Main Index](../../README.md)
