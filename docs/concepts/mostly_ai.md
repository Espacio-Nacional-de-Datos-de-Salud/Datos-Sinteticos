[<-- Back to Main Index](../../README.md)

# MOSTLY AI Engine Internals - Analysis

> Analysis based on reading the actual source code of `mostlyai==5.10.1` (SDK) and `mostlyai-engine==2.4.0` (engine).


## 1. Architecture: TabularARGN

The model is called **TabularARGN** (Any-order Auto-Regressive Generative Network) [Mostly-AI-TabARGN](https://mostly.ai/blog/introducing-tabularargn-a-flexible-and-efficient-auto-regressive-framework-for-generating-high-fidelity-synthetic-data), . It is a custom architecture build by Mostly AI'şdev team, open-sourced and disseminated in an arxiv paper [TabularARGN: A Flexible and Efficient Auto-Regressive Framework for
Generating High-Fidelity Synthetic Data](https://arxiv.org/pdf/2501.12012).

There are two variants:
- **FlatModel**: For non-sequential tabular data (one row at a time)
- **SequentialModel**: For sequential/time-series data (coherent sequences), adds LSTM layers on top

Source: `mostlyai/engine/_tabular/argn.py`

### Model Sizes

Three sizes available via the `model` parameter:

| Size | Embedding | Column Embedding | Regressor Layers | Flat Context | Seq Context | History |
|------|-----------|-----------------|------------------|-------------|-------------|---------|
| `MOSTLY_AI/Small` | `2 * ceil(d^0.15)` | `4 + n_sub_cols` | `[4]` | `[2*coeff]` | `[4*coeff]` | `[16*coeff]` |
| `MOSTLY_AI/Medium` | `3 * ceil(d^0.25)` | `10 + n_sub_cols` | `[16]` | `[8*coeff]` | `[16*coeff]` | `[64*coeff]` |
| `MOSTLY_AI/Large` | `4 * ceil(d^0.33)` | `16 + n_sub_cols` | `[16, 16]` | `[32*coeff]` | `[64, 64*coeff]` | `[128, 128*coeff]` |

Column embedding quantified how much space the model gives to representing each unique value in the data. A higher embedding space leds to a much richer, high-dimensional map of data values, allowing it to capture more detaield relationships.

Regressor layers: standard feed-forward layers. More layers, more parameters, in turn leading to more capacity to model complex mathematical relationships.

Flat / Seq context used by either the Flat / Sequential - Model. Sequential are larger as they need to encode info from historical rows.

History: Memory for the LSTM layers.

Where `coeff = round(ln(max(dim_input, e)))`, dim input is the number of features or columns in the dataset, and e is eulers numbers, which is used as a floor or minimum. 

and `d = cardinality`, cardinality is a value that quantifies the amount of unique values for each column.

**Default is `MOSTLY_AI/Medium`.**


## 2. Loss Function: CrossEntropyLoss

Source: `mostlyai/engine/_tabular/training.py`, function `_calculate_sample_losses` (line 255)

```python
criterion = nn.CrossEntropyLoss(reduction="none")
```

**What it means:**
- Each column is treated as a classification task over its discretized values
- The model predicts a probability distribution over all possible values for each column, using softmax not just a single category.
    - Example: [Doctor: 0.1, Engineer: 0.7, Artist: 0.2]
- Loss = sum of Cross-Entropy (CE) losses across ALL columns per sample
    - CE cares about the probability assigned to the correct answer. If Engineer was the correct one, we'd compute:
        - CE Loss = -ln(Probability of Truth) = -ln(0.7)  = 0.35. Low loss, good prediction
    - If a prob of 0.01 was given to Engineer then:
        - CE Loss = -ln(0.01) = 4.6. Very high loss, very bad prediction.

Usually we use MSE for numbers and Cross-Entropy for categories. However here everything is computed using CE, as numerical valeus are discretized.

For **sequential models**, masking is applied so padded positions don't contribute to the loss.

The reported `trn_loss` and `val_loss` are **averages of per-sample cross-entropy sums** over the training/validation sets.

When we have the final validation loss, we can undo the logarithm to find the geometric mean probability the model assigned to the true values. If the final validation is 0.2, P_val_avg = e**-0.2 = 0.82, meaning the model was 82% confident in the true value. This however does not equal accuracy, since that would be measuring "how often was the correct answer the #1 highest-ranked guess?". In practice, if is P = 82%, the accuracy will be higher, as the model only needs the correct answer to be higher than the other options to be accurate, even if confidence is not at a 100%.

## 3. Early Stopping

Source: `mostlyai/engine/_training_utils.py`, class `EarlyStopper` (line 65)
Source: `mostlyai/engine/_language_/training.py`, function `train` (line 281)

```python
early_stopper = EarlyStopper(val_loss_patience=4)
```

**How it works:**
- After EVERY completed epoch, validation loss is computed
- If val_loss does NOT improve for **>4 consecutive epochs**, training stops, this is hardcoded within mostly's library and cannot be changed easily from the outside.
- The model weights from the **best validation loss epoch** are saved (checkpoint)
- Patience counter resets whenever val_loss improves

**Three stopping conditions run in parallel:**
1. **Early stopping**: val_loss not improving for >4 epochs
2. **max_epochs**: epoch count exceeds `max_epochs`
3. **max_training_time**: total elapsed time exceeds `max_training_time` (in **minutes**, converted to seconds internally), this is by default 10 days.

Additionally, if differential privacy is enabled:
4. **DP epsilon exceeded**: if cumulative epsilon > `max_epsilon`, stop


## 4. Learning Rate Schedule

Source: `mostlyai/engine/_tabular/training.py` (lines 595-601)

```python
optimizer = torch.optim.AdamW(params=argn.parameters(), lr=initial_lr)
lr_scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
    optimizer=optimizer,
    factor=0.5,
    patience=2,
    min_lr=0.1 * initial_lr,
)
```

- **Optimizer**: AdamW
- **Initial LR**: `0.001 * sqrt(batch_size / 32)` (heuristic)
- **LR reduces by 0.5x** after **2 epochs** without val_loss improvement
- **Minimum LR**: 10% of initial LR
- LR scheduler is checked at the end of each epoch

## 5. Batch Size

Source: `mostlyai/engine/_tabular/training.py`, function `_physical_batch_size_heuristic` (line 79)

If you pass `batch_size=None`, it is calculated automatically based on:
- Available RAM
- Number of training records
- Number of data points per sample (number of columns)
- Number of model parameters

**Ranges: 8 to 4096** depending on these factors.

If you pass a specific `batch_size` (like `12` in your config), it is used directly but clipped to `max(1, min(batch_size, trn_cnt))`.

## 6. Parameters You CAN Tune

### High Impact

| Parameter | What it does | Recommendation |
|-----------|-------------|----------------|
| `differential_privacy` | Deleting it eliminates gradient noise | Known balance between privacy and utility / fidelity. |
| `model` | Model capacity (Small/Medium/Large) | Try `MOSTLY_AI/Large` for more complex datasets |
| `batch_size` | Gradient estimation quality | Decreasing it increases fidelity potential, decreasing memory use, but at the cost of a slower training speed and more noisy / unstable gradients. |
| `enable_flexible_generation` | Random column order vs fixed | Set to `False` if you don't need conditional generation - gives extra accuracy |

### Medium Impact

| Parameter | What it does | Recommendation |
|-----------|-------------|----------------|
| `max_epochs` | Training duration | `100` is the engine default. `1000000` is excessive but harmless (early stopping triggers first) |
| `max_training_time` | Time cap | Set explicitly (e.g., `60` for 1 hour) instead of `null` |
| `max_sample_size` | Subset of data for training | Keep `null` unless dataset is huge |
| `gradient_accumulation_steps` | Effective batch size multiplier, allows to sum the gradient over several steps instead of doing so at each step. This artificially increases the batch size. | Try `2` or `4` to increase effective batch size without more memory |

### Low Impact / Advanced

| Parameter | What it does | Recommendation |
|-----------|-------------|----------------|
| `max_sequence_window` | For sequential/time-series data only | Only relevant if you have linked tables |
| `value_protection` | Rare category protection. If in a 10k dataset only 1 person is an Astronaut, that person could be easily identifiable. Mostly can be enabled to replace rare valeus with the token _RARE_. | Default `True` is fine |
| `enable_model_report` | QA report | Set `True` during experimentation to see accuracy metrics |

## 7. Privacy Configuration

Privacy settings in `mostly_ai.yaml` operate in two independent layers: **Value Protection** (on by default) and **Differential Privacy** (opt-in). They differ in where they act: value protection shapes the data before and after training; differential privacy modifies the training process itself by injecting noise into gradients.

### Layer 1 — Value Protection

Active by default. Applied during training preprocessing and at simulation output. No formal DP guarantee, but prevents the model from memorizing rare or extreme values.

| Parameter | Default | What it does |
|---|---|---|
| `value_protection` | `true` | Master switch. Enables rare category, extreme value, and sequence length protection. Rare values are masked before the model sees them — it cannot memorize them. **Affects learning quality**: removing rare values simplifies the distribution the model must learn, which can slightly improve accuracy on common values. No effect on convergence speed. |
| `rare_category_replacement_method` | `CONSTANT` | How rare categories are substituted during training. `CONSTANT` replaces with a `_RARE_` token (the model learns to reproduce it, never the original). `SAMPLE` replaces with a draw from non-rare categories (distribution is better preserved, slightly weaker protection). **Affects learning quality** only: `SAMPLE` can give a more accurate marginal distribution; `CONSTANT` may introduce a visible `_RARE_` artifact in outputs. |

### Layer 2 — Differential Privacy

Disabled by default (the `differential_privacy` block is commented out). When enabled, formal (ε, δ)-DP guarantees are applied to the training loop via gradient clipping and Gaussian noise injection. All parameters below interact: epsilon accumulates as noise is added each step, and the training halts when `max_epsilon` is reached.

| Parameter | Default | What it does |
|---|---|---|
| `max_epsilon` | `10.0` | The privacy budget cap (ε). Training terminates early once the cumulative epsilon would exceed this value. Lower ε = stronger privacy, but training can stop far before convergence. **Affects both learning quality and convergence time**: a very low cap (e.g., ε=1) often stops training after a few epochs, producing a poorly converged model. |
| `delta` | `0.00001` | The failure probability (δ) — the probability that the DP guarantee does not hold for a given record. Should be much smaller than 1/(dataset size). Increasing it slightly relaxes the guarantee and allows more training budget. **Affects learning quality indirectly**: a higher δ allows the optimizer to spend more epsilon budget per step, which can mean reaching a better loss before the cap is hit. Rarely needs changing. |
| `noise_multiplier` | `1.5` | The ratio of the standard deviation of the Gaussian noise injected into gradients relative to their L2-sensitivity. Higher values = more noise per step = stronger privacy. **Affects both learning quality and convergence time**: more noise makes gradients less informative, the model learns more slowly and may plateau at a higher loss. A high multiplier (e.g., 3.0) on a small dataset often produces noticeably degraded synthetic data. |
| `max_grad_norm` | `1.0` | Gradient clipping threshold. Each per-sample gradient is clipped to this L2-norm before noise is added, bounding the maximum influence any single training record can have on the model weights. **Affects learning quality and convergence time**: too low a value (e.g., 0.1) over-clips most gradients, slowing convergence and reducing the signal-to-noise ratio. Too high a value weakens the privacy guarantee because the noise added becomes relatively smaller. |
| `value_protection_epsilon` | `1.0` | A separate DP epsilon budget spent during the pre-training analysis step to compute value ranges and histograms (bounds for numeric columns, noisy thresholds for categorical). This budget is split evenly across all columns. Only active when `value_protection: true`. **Affects learning quality**: a very small budget forces the analysis to use noisier bounds, which may cause the model to encode some columns with incorrect or clipped value ranges. No effect on training convergence speed directly. |

### Interaction between the two layers

When `value_protection: false`, the `value_protection_epsilon` is automatically ignored — no budget is spent on pre-training analysis. When `value_protection: true` and DP is enabled, the total effective privacy cost is `value_protection_epsilon + training epsilon`. This means the value protection step consumes part of the overall privacy budget before any model training begins.

### Privacy vs. accuracy trade-off

```
More privacy  ←────────────────────────────────→  More accuracy / faster convergence

Lower max_epsilon    |  Higher max_epsilon (or no DP)
Higher noise_mult.   |  Lower noise_mult.
Lower max_grad_norm  |  Higher max_grad_norm
value_protection ON  |  value_protection OFF
CONSTANT method      |  SAMPLE method
```

## 8. What You CANNOT Control

These are hardcoded in Mostly's engine:
- **Early stopping patience**: 4 epochs (hardcoded)
- **LR reduction patience**: 2 epochs (hardcoded)
- **LR reduction factor**: 0.5 (hardcoded)
- **Minimum LR**: 10% of initial (hardcoded)
- **Train/Val split**: built into the encoding step, not configurable from config
- **Optimizer**: Always AdamW
- **Model architecture**: Always TabularARGN (no CTGAN, no other option)
- **Embedding dimensions, regressor dimensions**: Determined by heuristics per model size
- **Column encoding**: Determined by analysis step (AUTO resolves to specific types)

[<-- Back to Main Index](../../README.md)
