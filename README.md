# Synthetic Data Tool for the ENDS (National Health Data Space)

<div style="display: flex; gap: 20px; align-items: center;">
    <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Logotipo_del_Ministerio_para_la_Transformaci%C3%B3n_Digital_y_de_la_Funci%C3%B3n_P%C3%BAblica.svg/960px-Logotipo_del_Ministerio_para_la_Transformaci%C3%B3n_Digital_y_de_la_Funci%C3%B3n_P%C3%BAblica.svg.png" alt="drawing" width="200"/>
        <img src="https://www.seguritecnia.es/wp-content/uploads/2024/07/ntt-data.jpg" alt="drawing" width="200"/>
        </div>

## Description
This tool is designed to facilitate the generation of synthetic data for the National Health Data Space (ENDS) in Spain.

This repository's documentation is divided into three main areas: Setup, Core Concepts, and Deployment.


---

## 0. Before starting

- **[Onboarding Guide](docs/setup/onboarding.md)**: Mental model of the repo: entry points, config cascade, venv split, and first steps.
- **[AWS SageMaker Setup](docs/setup/sagemaker.md)**: Guide to create your SageMaker user profile, use Code Editor with SSH from local VS Code, and optimize cost/storage usage.

## 1. Setup

This block covers how to install the tool, set up your development environment, and configure the project parameters for your basic runs.

- **[Setup](docs/setup/setup.md)**: Setup scripts, virtual environments, `config/` reference, and quickly lift the frontend and backend.
- **[Execution Details](docs/setup/execution.md)**: Run the tool with more fine-grained control, using the CLI and the recommended end-to-end run flow (inspect → train → simulate → evaluate), or lifting the API and frontend separately.

---

## 2. Concepts

- **[Repository Guidelines](docs/setup/repository_guidelines.md)**: This document is vital. It establishes the coding standards, repository structure, and development protocols.

### 2.1 Preprocessing
- **[Logical Rules](docs/concepts/logical_rules.md)**: Details on enforcing date inequalities, numeric constraints, and semantic consistency.
- **[OMOP Data](docs/concepts/omop.md)**: Definition of model, issues that we face, recommended preprocessing.

### 2.2 Training
- **[Pipelines](docs/concepts/pipelines.md)**: Explanation of the core training and generation pipelines.
- **[Tracking & MLFlow](docs/concepts/tracking_and_mlflow.md)**: Experiment tracking, session logging, and generating model/simulation cards.
- **[Mostly AI](docs/concepts/mostly_ai.md)**: How the Mostly AI tabular generation engine is customized and triggered.



### 2.3 Simulation
- **[Conditional Generation](docs/concepts/conditional_generation.md)**: How to generate data based on existing column values and its differences with logical rules.

### 2.4 Evaluation
- **[Evaluation & Metrics](docs/concepts/evaluation.md)**: How fidelity, privacy, and detection metrics measure the quality of synthetic data versus the original records.
---

## 3. Deployment

- **[API](docs/deployment/api.md)**: Explanation for our REST API.
- **[Frontend](docs/deployment/frontend.md)**: Explanation for our frontend, from the basic concepts to its execution.
- **[Docker Setup](docs/deployment/docker.md)**: Instructions for building and running images/containers.
- **[Testing Guide](docs/setup/testing.md)**: How and why to use tests to ensure all endpoints work as expected with a single command.

---

## 4. Troubleshooting

- **[Batch Size Errors](docs/concepts/batch_size_errors.md)**: Troubleshooting guidelines regarding memory and mostly AI batch size constraints.
