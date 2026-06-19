[<-- Back to Main Index](../../README.md)

# Training Failure Diagnostics

Before a training job is submitted to the engine, the tool runs a set of **pre-flight checks** (`run_preflight_checks` in `backend/src/domain/synthesis/training_diagnostics.py`). These checks catch known failure modes immediately, before the engine starts and before the user waits minutes for an opaque crash. When the engine does fail, `summarize_training_failure` collapses the per-step cascade into one readable message and maps it to known guidance when possible.


## Pre-flight Checks

Pre-flight checks run against the prepared tables, the metadata, and the model settings. The following conditions are detected:

### 1. Batch Size Too Small

MostlyAI halves the batch size for the validation split (`val_batch_size //= 2`). A configured `batch_size` of 1 underflows to 0 and training crashes. The minimum safe value is **2**.

**Symptom:** `"batch_size should be a positive integer value, but got batch_size=0"` in the engine logs.

**Fix:** Set `batch_size` to at least 2 in `mostly_ai.yaml`, or leave it unset to let the engine pick automatically.

### 2. Undersized Sequential (Child) Table

For sequential/relational training, MostlyAI splits the **parent (subject) table** 80/20 for validation, then halves the validation batch size again for the child table. With fewer than **8 parent rows** the validation batch underflows to 0.

**Symptom:** Same `batch_size=0` crash, but caused by data size, not a setting.

**Fix:** Provide at least 8 rows in the parent table, or remove the affected child tables from the training set.

### 3. Differential Privacy with Multi-Level Context Chain

The Opacus/PyTorch DP implementation cannot handle **three or more** tables that are (a) trained with differential privacy and (b) connected through context-key relationships. The engine crashes with a `NotImplementedError` on `NestedTensorCPU`.

This is detected by a union-find over the foreign-key graph: if more than 2 DP-enabled tables form a connected context-key group, training is blocked.

**Symptom:** `"NestedTensor"` / `"nested tensor"` / `"new_empty"` in the engine error.

**Fix (pick one):**
- Use `per_table` overrides in `mostly_ai.yaml` to disable DP on the deeper tables:
  ```yaml
  model_settings:
    differential_privacy:
      max_epsilon: 10
    per_table:
      measurement:
        differential_privacy: null  # disable DP for this table only
  ```
- Disable DP globally.
- Remove the relationship that connects the third table to the context chain.


## Post-failure Summarisation

When a training job fails, `summarize_training_failure` is called on the completed (failed) generator object. It:

1. Collects every step that reported `failed` status and deduplicates the affected table names.
2. Looks for known-issue signatures in the engine's error messages and appends the matching guidance.
3. Falls back to `"El motor no informó un detalle; revisa el log para más contexto."` when the engine gave no error text.

The result is stored on the model card's `error_message` field and surfaced in the UI.


## Batch Size Heuristic (Reference)

When `batch_size` is `null` (auto), MostlyAI picks it using:

```python
def _physical_batch_size_heuristic(
    mem_available_gb, no_of_records, no_tgt_data_points, no_ctx_data_points, no_of_model_params
) -> int:
    data_points = no_tgt_data_points + no_ctx_data_points
    min_batch_size = 8
    if mem_available_gb >= 32: mem_scale = 2.0
    elif mem_available_gb >= 8: mem_scale = 1.0
    else: mem_scale = 0.5
    if no_of_model_params > 1_000_000_000 or data_points > 100_000:
        max_batch_size = int(8 * mem_scale)
    elif no_of_model_params > 100_000_000 or data_points > 10_000:
        max_batch_size = int(32 * mem_scale)
    elif no_of_model_params > 10_000_000 or data_points > 1_000:
        max_batch_size = int(128 * mem_scale)
    elif no_of_model_params > 1_000_000 or data_points > 100:
        max_batch_size = int(512 * mem_scale)
    else:
        max_batch_size = int(2048 * mem_scale)
    min_batches = 64
    batch_size = 2 ** int(np.log2(no_of_records / min_batches)) if no_of_records > 0 else min_batch_size
    return int(np.clip(a=batch_size, a_min=min_batch_size, a_max=max_batch_size))
```

Range: **8 to 4096** depending on available RAM, record count, number of columns, and model parameters.

[<-- Back to Main Index](../../README.md)
