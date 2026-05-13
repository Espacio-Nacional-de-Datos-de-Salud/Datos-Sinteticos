[<-- Back to Main Index](../../README.md)

# Adding a Feature — End-to-End Walkthrough

This doc traces **one concrete change** through every backend layer
and into the frontend, so a new dev sees exactly where things live.
Once you've done this once, every future feature is a variation of it.

> Read [Backend Layout](backend_layout.md) first if you haven't. It
> explains the layers; this doc shows what touching all of them looks
> like in practice.

---

## The example

> **Feature.** Let the user attach a free-text `notes` field when they
> launch a simulation. Store it on the simulation card, return it from
> the API, and show it in the frontend's simulation detail view.

It's small but it crosses every layer:

```
frontend (form input)
    └── api/  (schema + router accept the field)
            └── sessions/   (session wrapper forwards it to the tracker)
                    └── runs/tracking/  (tracker writes it onto sim_card.json)
                                            ▲
                                            │
              api/schemas (response)  ──────┘
              api/routers  (GET returns it)
              frontend (detail page renders it)
```

We'll write the changes in the **direction the request travels**:
schema → router → session wrapper → tracker. Then add it to the read path
in reverse and finally wire the frontend.

---

## 1. API: extend the request schema

File: `backend/src/api/schemas/simulations.py`

Add an optional `notes` field to `SimulationCreateRequest` and to the
catalog summary so it round-trips:

```python
class SimulationCreateRequest(BaseModel):
    model_id: str = Field(..., pattern=MODEL_ID_PATTERN)
    sample_size: int | None = Field(default=None, gt=0)
    synthetic_data_file_format: str | None = Field(default=None, ...)
    notes: str | None = Field(                           # ← new
        default=None,
        max_length=2000,
        description="Optional free-text note attached to this simulation run.",
    )


class SimulationSummary(BaseModel):
    simulation_id: str
    simulation_name: str | None = None
    status: str = ""
    ...
    notes: str | None = None                              # ← new
```

**Why here first.** Pydantic schemas are the contract. Validation
errors land at the boundary, not deep inside the engine.

---

## 2. API: pass it through the router

File: `backend/src/api/routers/simulations.py` — `create_simulation`:

```python
session = initialize_simulation_session(
    model_id=request.model_id,
    synthetic_data_file_format=request.synthetic_data_file_format,
    notes=request.notes,                                  # ← new
)
```

The router stays **thin**. No business logic, no I/O — just hand the
validated payload to the session wrapper.

---

## 3. Sessions: thread it through the session wrapper

File: `backend/src/sessions/simulation.py`

Add `notes` to `initialize_simulation_session(...)` and to the
`SimulationSession` dataclass, then pass it to the tracker when the
card is saved:

```python
def initialize_simulation_session(
    model_id: str,
    synthetic_data_file_format: str | None,
    notes: str | None = None,                             # ← new
) -> SimulationSession:
    ...
    sim_tracker = SimulationTracker(
        simulation_id=simulation_id,
        model_id=model_id,
        notes=notes,                                       # ← new
        ...
    )
    sim_tracker.save_sim_card(sample_size=None)
    ...
```

**Why this layer.** Anything that needs to live on the run folder
(card fields, status transitions, cancel events) belongs in
`sessions/`. Engines (`domain/`) shouldn't know there's a card.

---

## 4. Runs/tracking: persist it to the card

File: `backend/src/runs/tracking/simulation_tracker.py`

Add `notes` to `__init__` and include it in `save_sim_card`:

```python
def __init__(
    self,
    simulation_id: str,
    model_id: str,
    notes: str | None = None,                              # ← new
    ...
) -> None:
    self.notes = notes
    ...

def save_sim_card(self, sample_size: int | None = None) -> None:
    card = {
        ...
        "notes": self.notes,                               # ← new
    }
    write_card(self.card_path, card)
```

After this step, a freshly launched simulation has `"notes": "..."`
visible in its `sim_card.json` on disk. Read path comes next.

---

## 5. Catalog: surface it in the listing

File: `backend/src/runs/catalog/simulations.py`

Catalog functions read the card and project it into `SimulationSummary`
shape. Add `notes` to the projected dict so `GET /simulations` and
`GET /simulations/{id}` include it.

(The schema added in step 1 will drop the field if you forget; that's
intentional, but the field needs to be present in the projected dict
for the schema to surface it.)

---

## 6. Frontend: render it

The frontend follows the API contract. Two places:

- **Launch form** (where the user types the note): the page that calls
  `POST /simulations`. Add a textarea bound to a `notes` state, include
  it in the request body.
- **Detail view**: the page that calls `GET /simulations/{id}`. Read
  `summary.notes` from the response and render it.

The frontend has its own internal layout doc — `frontend/README.md`
plus [Frontend](../deployment/frontend.md). For a new dev, the
fastest entry point is to grep:

```bash
rg "POST.*simulations" frontend/src        # who calls create
rg "simulation_id" frontend/src/app        # which page reads it
```

---

## 7. Test it

Add a unit test under `tests/`:

```python
def test_create_simulation_persists_notes(tmp_path, ...):
    session = initialize_simulation_session(
        model_id="model_20260101_000000",
        synthetic_data_file_format=None,
        notes="smoke test from onboarding",
    )
    card = json.loads(Path(session.card_path).read_text())
    assert card["notes"] == "smoke test from onboarding"
```

Run the full suite:

```bash
make format && make lint && make ty && make test
```

[<-- Back to Main Index](../../README.md)
