[<-- Back to Main Index](../../README.md)

# API Documentation

This section provides a technical overview of the tool's REST API, its internal architecture, and how to interact with it programmatically.


## 1. Overview: What is a REST API?

An **Application Programming Interface (API)** is a set of defined rules that allows different software applications to communicate with each other. Our API follows the **REST (Representational State Transfer)** architectural style, which uses standard web protocols to access and manipulate resources.

In this context, the API acts as a formal contract. You send a request to a specific "Endpoint", and the system returns a structured response (usually in JSON format) containing the requested data.

### Standard HTTP Methods
To interact with our resources, the API uses standard HTTP methods:
*   **GET**: Used to retrieve information from the server (Read-only).
*   **POST**: Used to create new resources or trigger jobs (e.g. launch a training run).
*   **PUT/PATCH**: Used to update existing resources.
*   **DELETE**: Used to remove resources.


## 2. Internal Architecture

Our API is built using **FastAPI** and is organized to ensure modularity, scalability, and strict data validation.

### Routers (Resource Modularization)
We use **Routers** to split the API into logical modules based on the resource type. Each file in `src/api/routers/` handles a specific domain:
*   `health.py`: System status monitoring.
*   `inspections.py`: Catalog of data inspection sessions.
*   `models.py`: Catalog of trained AI models.
*   `simulations.py`: Catalog of synthetic data generation runs (plus evaluation sub-resource).
*   `pipelines.py`: Catalog of multi-job pipeline sessions.

Route order matters when a router defines both static paths like `/cleanup` or `/download/generator` and dynamic paths like `/{model_id}` or `/{model_id}/download`. The more specific static route must be declared first so FastAPI does not treat the literal word as a path parameter.

### Schemas (Data Contracts)
We use **Pydantic Schemas** (`src/api/schemas/`) to define the exact data structure a caller sends or receives:

*   **Response schemas** (output): define what the API returns. E.g. `ModelSummary` guarantees every model entry has `model_id`, `status`, and optional accuracy/size fields. Internal filesystem paths are intentionally excluded.
*   **Request schemas** (input): define what the client must send in the body of a `POST`. E.g. `TrainingCreateRequest` enforces that exactly one of `file_paths` or `inspection_id` is provided; `SimulationCreateRequest` requires `model_id` and accepts an optional `sample_size` (or a `table_sample_sizes` map for per-table overrides on subject tables — context-child entries are ignored, see below).
*   **Job schemas** (async ack): lightweight handles like `TrainingJob`, `SimulationJob`, `EvaluationJob`, `PipelineJob` returned on `202`.

> [!NOTE]
> **What about path parameters like `/models/{model_id}`?** FastAPI validates those too (as typed function arguments); Pydantic schemas are reserved for complex structured body/response payloads.

*   **Validation**: If the body doesn't match the schema, FastAPI automatically returns `422 Unprocessable Entity`.
*   **Filtering**: Fields present internally but not declared in the response schema are silently dropped — this is how filesystem paths are kept out of the API output.
*   **Documentation**: Schemas automatically populate the interactive docs at `/docs`.

### Separation of Layers
The API is a **thin interface layer**. It does not contain business logic; it delegates to `src/sessions/` (training, simulation, inspection, pipeline, evaluation session wrappers) and `src/runs/catalog/` (listing, deletion, cleanup, download bundles). The sessions layer in turn wraps the engines in `src/domain/`. This keeps the engines decoupled from the delivery mechanism.


## 3. Available Endpoints

### System Status (`/health`)
Verifies that the API process is running and reachable. Returns `{"status": "ok"}`.

### Inspections (`/inspections`)
*   **GET `/`**: Lists all inspection sessions (including `in_progress`).
*   **POST `/`**: Launches an inspection asynchronously. Body: `file_paths`, optional `mostly_config_path`, `rules_config_path`, `enable_data_profiling`, `csv_delimiter`, `excluded_columns`, `composite_pks`. Returns `202` with `inspection_id`.
    *   `composite_pks`: per-table composite primary keys, `{table_name: [col, ...]}`. For each listed table a single unique PK column is synthesized by concatenating the named columns (separator `::`) — use it for datasets whose natural key spans several columns (e.g. `patient_id` + `year`). Falls back to heuristic single-column detection if the named columns are missing or do not form a unique key.
*   **GET `/{id}`**: Returns details for a specific inspection.
*   **GET `/{id}/download`**: Downloads the inspection folder as a zip.
*   **DELETE `/{id}`**: Permanently deletes an inspection and all its artifacts.
*   **DELETE `/cleanup`**: Bulk-deletes inspection runs classified as `empty` or `orphans`.

### Models (`/models`)
*   **GET `/`**: Lists all trained models (including `in_progress`).
*   **POST `/`**: Launches a training run asynchronously. Body: exactly one of `file_paths` (train from raw data) **or** `inspection_id` (train from a completed inspection), plus optional `mostly_config_path`, `rules_config_path`, `enable_data_profiling`, `csv_delimiter`. Returns `202` with `model_id`. Server-side `422` if both or neither of `file_paths`/`inspection_id` are set.
*   **GET `/{id}`**: Returns metadata and training details for a model.
*   **GET `/{id}/download/generator`**: Downloads only the minimum files required to simulate from this model (`generator.zip`, `metadata.json`, `rule_manager.json`). Returns `409` if any of those are missing.
*   **GET `/{id}/download`**: Downloads the entire model folder as a zip.
*   **DELETE `/{id}`**: Deletes a model. Returns `409` if the model has linked simulations; the response lists their IDs so they can be deleted first.
*   **DELETE `/cleanup`**: Bulk-deletes model runs classified as `empty` or `orphans`. Includes `skipped_ids` for candidates that were not deleted due to linked simulations.

### Simulations (`/simulations`)
*   **GET `/`**: Lists all simulation runs (including `in_progress`, with `sample_size`).
*   **POST `/`**: Launches a simulation asynchronously from a trained model. Body: `model_id` (required), optional `sample_size`, optional `table_sample_sizes` (per-subject-table overrides; entries for context children are accepted but ignored, since Mostly AI cascades their counts from the parent). Returns `202` with `simulation_id`.
*   **GET `/{id}`**: Returns details for a simulation run.
*   **POST `/{id}/evaluate`**: Launches evaluation for a completed simulation asynchronously. **No body** — `real_data` and `model_id` are traced back from the sim card → model card chain. Returns `202`. Poll completion via `GET /{id}/download/evaluation` (404 while running, 200 once done).
*   **GET `/{id}/download/synthetic-dataset`**: Downloads only the `synthetic_data/` subfolder.
*   **GET `/{id}/download/evaluation`**: Downloads only the `evaluation/` subfolder. `404` if evaluation has not run (or is still running).
*   **GET `/{id}/download`**: Downloads the entire simulation folder as a zip.
*   **DELETE `/{id}`**: Permanently deletes a simulation run.
*   **DELETE `/cleanup`**: Bulk-deletes simulation runs classified as `empty` or `orphans`.

### Pipelines (`/pipelines`)
*   **GET `/`**: Lists all pipeline sessions.
*   **POST `/`**: Launches a pipeline asynchronously from a YAML config. Body: `config_path` (filesystem path to the pipeline YAML). Returns `202` with `pipeline_id`.
*   **GET `/{id}`**: Returns the pipeline card, including per-job status and references to the models/simulations it produced.
*   **GET `/{id}/download/with-jobs`**: Downloads the pipeline folder **plus** every model and simulation it produced, laid out as `<pipeline_id>/`, `models/<model_id>/`, `simulations/<simulation_id>/`. Artifacts no longer on disk are silently skipped.
*   **GET `/{id}/download`**: Downloads the pipeline folder alone as a zip.
*   **DELETE `/{id}`**: **Cascading delete**. Removes the pipeline folder **and** every model and simulation referenced in its card. The response includes `deleted_model_ids` and `deleted_simulation_ids`. Unlike `DELETE /models/{id}`, this does not return `409` — a pipeline represents a grouped batch and deletion is designed to wipe it all. Only artifacts the pipeline itself produced are listed in its card, so the cascade never touches externally-created ones.

### Cleanup Candidate Logic

All `/cleanup` endpoints call a `find_cleanup_candidates(stale_hours)` helper in their corresponding catalog module and classify folders into:

*   **empty**: The run folder tree has no files.
*   **orphans**: The folder has files, but the run is considered dead:
	* `status` is `failed`, or
	* the card file is missing/unreadable and the run start time (parsed from folder name) is older than `stale_hours` (to avoid deleting recent experiments still running), or
	* `status` is `in_progress` and the start time is older than `stale_hours` (24h by default).


## 5. Interactive Documentation (Swagger UI)

The API includes a built-in interactive documentation interface that allows you to test endpoints without writing code.

1.  Ensure the API server is running (typically at `http://localhost:8000`).
2.  Navigate to: **`http://localhost:8000/docs`**
3.  Expand any endpoint, click **"Try it out"**, fill in the body/params, and then **"Execute"**.
4.  The interface will show the exact command used, the response status code, and the JSON data returned.



## 6. REST Conventions Used Here

Two practical questions come up constantly when reading the endpoint list:

1. **Why does this endpoint have a body while that one doesn't?**
2. **Why is this ID in the URL path while that other ID is in the body?**

Both answers come from the same two REST rules.

### 6.1 GET vs POST — and why GET has no body

| | **GET** | **POST** |
|---|---|---|
| Purpose | Read existing state | Create a new resource or trigger a job |
| Side effects | None (safe, idempotent) | Yes (creates a new run, writes to disk) |
| Inputs | URL path (`/models/{id}`) and query string (`?mode=both`) | URL path + **JSON body** |
| Typical response | `200 OK` with the resource | `202 Accepted` with a job handle |

A GET endpoint doesn't need a body because it isn't creating anything — the URL itself (`/models/abc123`) fully identifies what you want to read. Anything GET needs that isn't an ID of an existing resource goes in the query string (filters, paging, cleanup `mode`).

A POST creates something new; the body carries the **input data** that describes the new resource (file paths, model id to simulate from, sample size, etc.). If a POST has no body (like `POST /simulations/{id}/evaluate`) it is because the server can derive every input it needs from the path parameter alone.

### 6.2 Path params vs body — what goes where?

The rule is:

*   **Path param** answers *"which existing resource am I acting on?"*
*   **Body** carries *"the data describing the new resource I want to create"*.

A reference to another existing resource that is **consumed as input** (e.g. the `model_id` you want to simulate from) is **data for the new resource**, so it belongs in the body — not in the path. The path is reserved for the resource that this specific URL identifies.

Concrete comparison of two endpoints that both involve an existing simulation:

*   `POST /simulations/{simulation_id}/evaluate` → path param. The URL identifies the existing simulation you want to evaluate. No body because every input (real data paths, model id) is traced back automatically from the sim card.
*   `POST /simulations/` with body `{"model_id": "...", "sample_size": 1000}` → body param. The URL identifies the collection (`/simulations/`). The `model_id` is **input data for the new simulation**, not the target resource, so it goes in the body. Same for `POST /models/` accepting either `file_paths` or `inspection_id` in its body.

The nested alternative `POST /models/{model_id}/simulations` is equally valid REST — moving `model_id` into the path would express the same intent. We deliberately kept the flatter `POST /simulations/` with `model_id` in the body so that all ways of creating a simulation (today only "from a model", later possibly others) live under a single endpoint with a single request schema.

### 6.3 Async jobs — 202 Accepted and polling

Training, simulations, inspections, pipelines and evaluations are long-running. Our POST endpoints for those return **`202 Accepted`** immediately with a small job handle like:

```json
{ "model_id": "model_2026-04-17_10-32-15", "status": "in_progress" }
```

The session folder and an `in_progress` card are created **synchronously** before the response returns, so the returned ID is immediately queryable via the corresponding GET endpoint. The actual work runs in a FastAPI `BackgroundTask`. Clients **poll** the GET endpoint to observe the `status` transition to `completed` or `failed`, then call the corresponding download endpoint to pull the artifacts.

[<-- Back to Main Index](../../README.md)
