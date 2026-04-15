[<-- Back to Main Index](../../README.md)

# Note on Batch Size Usage

We have encountered several errors like this:

```text
TypeError: zeros() received an invalid combination of arguments - got (tuple, dtype=type), but expected one of:
 * (tuple of ints size, *, tuple of names names, torch.dtype dtype = None, torch.layout layout = None, torch.device device = None, bool pin_memory = False, bool requires_grad = False)
 * (tuple of ints size, *, Tensor out = None, torch.dtype dtype = None, torch.layout layout = None, torch.device device = None, bool pin_memory = False, bool requires_grad = False)
```

After isolating the incident, we discovered that this originated from data loading within Opacus, the differential privacy module used by Mostly AI. Based on reports from the Opacus repository, the error is due to using a batch size that is too small, which creates the possibility of an empty set being returned, causing the program to crash.

Therefore, and also because of the need for a high level of fidelity, we decided to define the batch size instead of using Mostly AI's default.

### Mostly AI's Batch Size Calculation Algorithm

```python
def _physical_batch_size_heuristic(
    mem_available_gb: float,
    no_of_records: int,
    no_tgt_data_points: int,
    no_ctx_data_points: int,
    no_of_model_params: int,
) -> int:
    """
    Calculate the physical batch size.

    Args:
        mem_available_gb (float): Available memory in GB.
        no_of_records (int): Number of records in the training dataset.
        no_tgt_data_points (int): Number of target data points per sample.
        no_ctx_data_points (int): Number of context data points per sample.
        no_of_model_params (int): Number of model parameters.

    Returns:
        Batch size (int)
    """
    data_points = no_tgt_data_points + no_ctx_data_points
    min_batch_size = 8
    # scale batch_size corresponding to available memory
    if mem_available_gb >= 32:
        mem_scale = 2.0
    elif mem_available_gb >= 8:
        mem_scale = 1.0
    else:
        mem_scale = 0.5
    # set max_batch_size corresponding to available memory, model params and data points
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
    # ensure a minimum number of batches to avoid excessive padding
    min_batches = 64
    batch_size = 2 ** int(np.log2(no_of_records / min_batches)) if no_of_records > 0 else min_batch_size
    return int(np.clip(a=batch_size, a_min=min_batch_size, a_max=max_batch_size))
```

For simplicity, we have conducted several manual experiments to find a functional batch size. Using the `person.csv` table from Amazon's `synthea1k`, we found that a size of 12 works well. This ensuring we maintain the maximum level of accuracy without the program crashing. If you wish to expedite training, a larger size can be used.

[<-- Back to Main Index](../../README.md)

