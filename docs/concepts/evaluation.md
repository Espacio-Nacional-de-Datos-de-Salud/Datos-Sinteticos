[<-- Back to Main Index](../../README.md)

# Evaluation System - Complete Documentation

## Introduction

The evaluation system is a multi-layer architecture designed to assess the quality of generated synthetic data. The system uses **three layers of evaluation engines** working together:

```text
MLflowEvaluationEngine (tracks results in MLflow)
    ↓
SynthCityEvaluationEngine (coordinates metric execution)
    ↓
AbstractEvaluationEngine (defines the base interface)
```

The system provides:
- **Custom Metrics**: In-house high-level implementations for privacy, correlation, and statistical fidelity.
- **SynthCity Metrics**: Integration with the `synthcity` external library.
- **Bootstrap Statistics**: A flexible statistical base with 9 built-in statistics and support for custom extensions.
- **MLflow Tracking**: Automatically logs all metrics and artifacts in MLflow.

The evaluation system must run in a **separate virtual environment** to avoid dependency conflicts. This is especially important because `synthcity` has significant computational requirements and may conflict with other project dependencies.

---

## File Organization

### Directory Structure

```text
src/evaluation/
├── __init__.py                          # Module initialization
├── abstract_evaluation_engine.py        # Base abstract interface
├── synthcity_evaluation_engine.py       # Main orchestrator
├── mlflow_evaluation_engine.py          # MLflow tracking
├── metrics.py                           # Custom metrics
├── statistics.py                        # Base bootstrap statistics
├── custom_statistics.py                 # Custom statistical extensions
├── eval_cli.py                          # CLI entry point for subprocess
└── utils.py                             # Utility functions

config/
├── evaluation/
│   ├── evaluation_config.py             # Evaluation parameters & logic
│   └── statistics.yaml                  # Statistics configuration
├── general_config.py                    # Global system paths & tracking
└── ...
```

### File Descriptions

| File | Purpose | Main Classes/Functions |
| :--- | :--- | :--- |
| **abstract_evaluation_engine.py** | Defines the base interface for all engines | `AbstractEvaluationEngine` (ABC) |
| **synthcity_evaluation_engine.py** | Orchestrates the execution of all metrics, loads data, coordinates with SynthCity | `SynthCityEvaluationEngine`, `_run_custom_metrics()` |
| **mlflow_evaluation_engine.py** | Wraps SynthCityEvaluationEngine with MLflow tracking | `MLflowEvaluationEngine` |
| **metrics.py** | Implements custom evaluation metrics | `DCR`, `NNDR`, `CorrelationMatrixDistance`, `ConfidenceIntervalOverlap`, `AverageComplementaryTVD`, `KAnonymity` |
| **statistics.py** | Implements built-in statistics with bootstrap CI | `Statistic` (ABC), `create_statistic()`, `statistic_map` |
| **custom_statistics.py** | Allows custom statistical extensions | `AgeStatistic`, `CUSTOM_STATISTIC_MAP` |
| **eval_cli.py** | Entry point for subprocess execution | `main()` |
| **config/evaluation/evaluation_config.py** | Evaluation parameters, defaults, and Python path resolution | `EVAL_DEFAULT_METRICS`, `CONFIDENCE_INTERVAL_LEVEL`, `NUM_BOOTSTRAP_SAMPLES`, `EVAL_PYTHON_PATH` |
| **config/evaluation/statistics.yaml** | Configuration of which statistics to calculate on which columns | YAML statistical definitions |
| **config/general_config.py** | Global system parameters, output paths, and tracking namespaces | `PROJECT_ROOT`, `MODELS_DIR`, `MLFLOW_TRACKING_URI` |

---

## System Architecture

### Execution Flow

```text
MLflowEvaluationEngine.run(real_data, synthetic_data, ..., model_id, simulation_id, ...)
    ↓
1. Find/create simulation run in MLflow by `simulation_id`
    ↓
2. SynthCityEvaluationEngine.run(real_data, synthetic_data, ..., model_id, simulation_id, ...)
    ↓
    a. Load real and synthetic data as GenericDataLoader
    b. Execute SynthCity metrics via Metrics.evaluate()
    c. For each custom metric in ["custom"]:
        - Instantiate metric class
        - Call evaluate(real_data, synthetic_data)
        - Parse results:
          * `score` → single row
          * `scores` → multiple rows (.real, .syn, etc.)
          * `additional` → serializable JSON detail
        - Add rows to report DataFrame
    d. Return DataFrame with results
    ↓
3. Log metrics/artifacts in MLflow
4. Save report as CSV
```

## Privacy Metrics

### 1. Distance to Closest Record (DCR)

**Code name:** `dcr`  
**Type:** Custom metric  
**Report rows:** `dcr.real`, `dcr.syn`  
**Range:** values >= 0  
**Desired:** `dcr.syn` should not be significantly below `dcr.real`. Generally, the higher the value, the greater the separation from real records.

**What does it measure?**

It measures the Euclidean distance to the nearest record after scaling and encoding the variables. It is used in two directions:

- `dcr.real`: For each real row, distance to its own nearest real row (excluding itself). This is the **natural density baseline** of the real dataset.
- `dcr.syn`: For each synthetic row, distance to the nearest real record. It serves to detect if synthetic records are too close to specific real records.

**Interpretation:**

- **`dcr.syn` << `dcr.real`:** Risk signal. Synthetic records are closer to specific real records than the real records themselves are to each other.
- **`dcr.syn` ≈ `dcr.real`:** Reasonable behavior. Synthetic data exists in density zones similar to real data.
- **`dcr.syn` > `dcr.real`:** Greater separation and, therefore, more protection, though values that are too high may suggest a loss of fidelity.
- **Values near 0:** There are almost identical or very close records.

---

### 2. Nearest Neighbor Distance Ratio (NNDR)

**Code name:** `nndr`  
**Type:** Custom metric  
**Report rows:** `nndr.real`, `nndr.syn`  
**Range:** 0 to 1  
**Desired:** Maximize, especially `nndr.syn`, and compare it with `nndr.real`

**What does it measure?**

It measures the ratio between the distance to the nearest neighbor and the second nearest neighbor. It detects if a record is "anchored" to a single real point or if it falls into an area where there are several similar real ones.

- `nndr.syn`: For each synthetic record, `d1/d2` against the two nearest real ones.
- `nndr.real`: Same calculation, but using real data as a baseline.

**Interpretation:**

- **Near 0:** The first neighbor is much closer than the second. This suggests anchoring to a specific record → higher risk.
- **Near 1:** The two neighbors are at similar distances. Suggests better generalization and less dependence on a single real record.
- **`nndr.syn` below `nndr.real`:** Warning that synthetic records are "stuck" closer to individual points than the real data itself.

---

### 3. K-Anonymity

**Code name:** `k-anonymization`  
**Type:** Custom metric  
**Report rows:** `k_anonymity.real`, `k_anonymity.syn`  
**Associated artifact:** `k_anonymity_report.json`  
**Range:** integer values >= 1  
**Desired:** `syn_k` should be, at minimum, similar to `real_k`, and both should move away from 1 (typically k > 5 is good).

**What does it measure?**

It measures the minimum size of indistinguishable groups defined by combinations of quasi-identifiers. A k-anonymity of 5 means that, for the subset of columns analyzed, each combination of values appears at least 5 times.

The current implementation:
- Evaluates several **subsets of quasi-identifiers**.
- Compares real and synthetic results.
- Saves **equivalence class** statistics.
- Calculates **column granularity**.
- Estimates the **marginal contribution** of each column to reducing k.

---

### 4. Distinct L-Diversity

**SynthCity report name:** `privacy.distinct l-diversity.gt` and `privacy.distinct l-diversity.syn`  
**Type:** SynthCity metric  
**Range:** values >= 1  
**Desired:** Maximize

**What does it measure?**

Complements k-anonymity: it not only requires several records per group but also that within each group, there is sufficient diversity in other sensitive columns.

It measures how many distinct values exist in a sensitive column within each group of similar people. It prevents an attacker from guessing a private attribute if everyone in the group has the same value (e.g., the same disease).

---

### 5. Membership Inference Attack (MIA) - DomiasMIA_BNAF

**Code name:** `DomiasMIA_BNAF`  
**Type:** SynthCity metric  
**Source:** [DOMIAS](https://arxiv.org/pdf/2302.12580) implementation  
**Range:** 0 to 1  
**Desired:** 0.5

**What does it measure?**

Evaluates if it can be determined if a specific record was part of the training set. It measures model "memorization."

**Interpretation:**

- **Near 0.5:** Indistinguishable (cannot determine membership) → STRONG PRIVACY.
- **Near 0 or 1:** Attack can determine membership → WEAK PRIVACY.
- **Ideal:** 0.5 (random behavior).

**Technical Specifications:**
- **Algorithm:** DOMIAS (Density-based Membership Inference Attack via Sampling).
- **Density Estimation:** BNAF (Block Neural Autoregressive Flows).
- **BNAF Advantage:** Works well with high-dimensional data.
- **Computational Cost:** VERY HIGH - Recommended to run only on powerful SageMaker instances (e.g., `ml.m5.4xlarge`).

---

## Fidelity Metrics

### 6. Jensen-Shannon Divergence (JSD)

**Config/report name:** `jensenshannon_dist`  
**Type:** SynthCity metric  
**Range:** 0 to 1  
**Desired:** Minimize (near 0)

**What does it measure?**

Measures the divergence (distance) between the probability distributions of real and synthetic variables.

**Interpretation:**

- **0:** Identical distributions → Perfect fidelity.
- **1:** Completely different distributions → Zero fidelity.
- **0.1-0.3:** Good fidelity.
- **0.3-0.5:** Moderate fidelity.
- **> 0.5:** Poor fidelity.

---

### 7. Inverse KL Divergence

**Code name:** `inv_kl_divergence`  
**Type:** SynthCity metric  
**Range:** 0 to 1  
**Desired:** Maximize (near 1)

**What does it measure?**

The inverse of the Kullback-Leibler (KL) distance between distributions. Measures how well the synthetic distribution approximates the real one. Especially sensitive to outliers.

---

### 8. Average Complementary Total Variation Distance (Complementary TVD)

**Code name:** `average_complementary_tvd`  
**Type:** Custom metric  
**Range:** ~0 to 1  
**Desired:** Maximize

**What does it measure?**

Measures the average similarity of probability distributions between real and synthetic data using Total Variation Distance (TVD). Specifically, it calculates the complement of TVD (1 - TVD) for each feature and averages them. A high score indicates that marginal distributions are similar.

---

### 9. Correlation Matrix Distance (CMD)

**Code name:** `correlation_matrix_distance`  
**Type:** Custom metric  
**Range:** 0 to 1  
**Desired:** Minimize

**What does it measure?**

Measures the distance between the correlation matrices of real and synthetic data. Evaluates if multivariate relationships and dependencies are maintained.

**Calculated methods included:**
1. **SRMSE (Scaled Root Mean Square Error)** - Main metric.
2. **L1 Distance** - Manhattan distance.
3. **Frobenius Distance (L2)** - Matrix Euclidean norm.

---

## Utility Metrics

### 10. TSTR - Linear Classification Model

**Code name:** `performance.linear_model`  
**Type:** SynthCity metric  
**Range:** 0 to 1  
**Desired:** Similar values between Gt and Syn_ood

**What does it measure?**

Train Synthetic Test Real (TSTR) evaluates utility using a linear classifier. Measures if a model trained on synthetic data generalizes well to new real data.

**Variants returned:**
1. **Gt (Ground Truth):** Trained on real data, tested on real data. Sets the baseline.
2. **Syn_id (In-distribution):** Trained on synthetic, tested on real training data.
3. **Syn_ood (Out-of-distribution):** Trained on synthetic, tested on real test data. Measures true generalization.

---

### 11. TSTR - MLP Classification Model

**Code name:** `performance.mlp`  
**Type:** SynthCity metric  
**Range:** 0 to 1  
**Desired:** Similar values between Gt and Syn_ood

Same as TSTR Linear, but using a Multi-Layer Perceptron (neural network) to capture more complex relationships.

---

### 12. Detection (Differentiation)

**Config name:** `detection_mlp`  
**Report name:** `detection.detection_mlp.mean`  
**Type:** SynthCity metric  
**Range:** 0 to 1  
**Desired:** 0.5

Entrains an MLP classifier to distinguish between real and synthetic data. Returns the AUC-ROC. Measures indistinguishability.

---

### 13. Confidence Interval Overlap (CIO)

**Code name:** `confidence_interval_overlap`  
**Type:** Custom metric  
**Range:** 0 to 1  
**Desired:** Maximize

Calculates 95% confidence intervals for configurable statistics (mean, median, etc.) and measures their overlap.

See [confidence_interval_overlap.md](./confidence_interval_overlap.md) for more information.

[<-- Back to Main Index](../../README.md)
