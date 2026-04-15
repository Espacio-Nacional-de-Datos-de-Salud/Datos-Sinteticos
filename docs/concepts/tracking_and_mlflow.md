[<-- Back to Main Index](../../README.md)

# Experiment Tracking: MLflow and the Tracking System

This document explains in a simple way how the tool records and organizes everything that happens each time a model is trained or a synthetic dataset is generated.

---

## Why do we need a tracking system?

Every time we run the tool, many things can change: the input data, the configuration parameters, the number of records generated, the rules applied... Without a recording system, it would be impossible to answer questions like:

- With what data was this synthetic set generated?
- What configuration was used in this model?
- How many quality checks failed in the last simulation?
- Was this synthetic set generated before or after changing the rules?

The tracking system solves exactly that: **it leaves a trace of everything automatically**, without anyone having to do anything extra.

---

## The logbook: what is saved in each execution

The tool distinguishes between two types of execution, and in each one it saves different information.

### When a model is trained

When training, a folder named `model_YYYYMMDD_HHMMSS` (exact date and time) is created inside `outputs/models/`. Inside that folder, the following are saved:

| File | What it contains |
|---|---|
| `model_card.json` | Model identifier, date, a digital fingerprint (SHA-256) of each input data file, and model-level Mostly AI statistics computed from an internal sample sized to the training data |
| `metadata.json` | Description of the tables and columns used |
| `generator.zip` | The trained model, ready to generate data |
| `rule_manager.pkl` | The logical rules applied during training |
| `train.log` | The complete record of everything that happened during training |
| `configs/` | An exact copy of all configuration files used |

> **What is the SHA-256 digital fingerprint?**
> It is like a unique mathematical signature of the file. If the file changes even by a single character, the fingerprint changes completely. This way we can know with certainty if the input data was exactly the same in two different executions.

> **Why are Mostly AI statistics stored in the model card?**
> These statistics describe the trained model itself, not any specific synthetic dataset. Mostly AI computes them internally by simulating a dataset whose size matches the training set. Values stay tied to the model and do not change when you generate different synthetic outputs from that same model.

### When a simulation is generated

When simulating, a folder named `simulation_YYYYMMDD_HHMMSS` is created inside `outputs/simulations/`. It contains:

| File | What it contains |
|---|---|
| `sim_card.json` | Simulation identifier, **reference to the parent model that generated it**, and sample size |
| `sim_config.json` | Configuration used for this specific simulation |
| `sim.log` | Complete record of the generation |
| `sanity_checks_report.csv` | Result of all quality checks |
| `synthetic_data/` | The CSV files with the generated synthetic data |

---

## MLflow: The Control Panel (Hybrid)

While the `outputs/` folders save the actual files, **MLflow is the dashboard** that allows you to visualize and compare everything from a web interface.

**The tool automatically detects where it is running:**

1. **In AWS SageMaker**: It uses the managed service via a special URI (ARN) and the `sagemaker-mlflow` library. Data is shared with the entire team in the cloud.
2. **Locally**: If you run the code on your computer, MLflow automatically saves the data in a local folder called `mlruns/`.

### What information appears in MLflow?

Each execution appears with:
- **Parameters**: configuration values (epochs, sample size, etc.).
- **Metrics**: numerical quality results.
- **Tags**: extra information like `run_status: SUCCESS` or `model_id`.
- **Artifacts**: copies of the most important files available for download.

---

## How to open the MLflow panel

Depending on where you executed the tool, you have two ways to see the results:

### Option A: If you have executed in AWS SageMaker Studio
The server is always active in AWS.
1. In the **SageMaker Studio** side menu, go to **MLflow** > **Tracking Servers**.
2. Select the server (e.g., `app-WOVA56CVVLL2`) and click **"Open MLflow UI"**.

### Option B: If you have executed locally (Your computer)
You must launch the interface yourself from the terminal:
1. Activate the environment: `source .venv_core/bin/activate`
2. Launch the UI:
    ```bash
    mlflow ui --backend-store-uri ./mlruns --port 5001
    ```
3. Open in your browser: **http://127.0.0.1:5001**

---

## How to read the MLflow interface

When opening the URL, you will see something like this:

```text
Experiments (left sidebar)
├── SyntheticData-Training
│     run_name: model_20260226_113921      ← each row is a training run
│     run_status: SUCCESS
│     mostly.epochs: 100
│
└── SyntheticData-Simulation
      run_name: simulation_20260226_114500  ← each row is a simulation
      model_id: model_20260226_113921       ← which model generated it
      sanity_failed_checks: 0
```

By clicking on any run, you can see:
- All the parameters it ran with
- Downloadable artifacts (configs, CSVs, logs)

[<-- Back to Main Index](../../README.md)

