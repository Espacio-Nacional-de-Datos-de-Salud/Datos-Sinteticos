# Synthetic Data Tool for the ENDS (National Health Data Space)

<p align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Logotipo_del_Ministerio_para_la_Transformaci%C3%B3n_Digital_y_de_la_Funci%C3%B3n_P%C3%BAblica.svg/960px-Logotipo_del_Ministerio_para_la_Transformaci%C3%B3n_Digital_y_de_la_Funci%C3%B3n_P%C3%BAblica.svg.png" alt="Ministerio" width="200"/>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="https://www.seguritecnia.es/wp-content/uploads/2024/07/ntt-data.jpg" alt="NTT Data" width="200"/>
</p>

This tool generates synthetic tabular health data for the National Health Data Space (ENDS) in Spain.


## 0. Pick your path

| If you want to… | Read |
| :--- | :--- |
| 🚀 **Use the tool from a browser** (Docker or `make local`) | **[Use the UI](docs/developer/setup/use_ui.md)** |
| 💻 **Use the tool from the terminal** (interactive wizard or `make` one-shots) | **[Use the CLI](docs/developer/setup/use_cli.md)** |
| 🛠 **Maintain or extend the codebase** | **[Developer Onboarding](docs/developer/setup/onboarding.md)** |


## 1. Reference docs

- **[Installation](docs/developer/setup/install.md)** — `make setup`, venvs, config bootstrap. The single source of install steps.
- **[Configuration](docs/developer/setup/configuration.md)** — every YAML knob under `backend/config/`.
- **[Contributing](CONTRIBUTING.md)** — coding standards, commit style, docstring format.
- **[Testing](docs/developer/setup/testing.md)** — `make test` (core venv) and `make test-eval` (eval venv).


## 2. Architecture & concepts

### Codebase architecture
- **[Backend Layout](docs/developer/concepts/backend_layout.md)** — tour of `backend/src/`: the five layers and the one-direction import rule.
- **[Adding a Feature](docs/developer/concepts/adding_a_feature.md)** — end-to-end walkthrough of a change crossing every backend layer + the frontend.

### Data-side concepts
- **[OMOP Data](docs/developer/concepts/omop.md)** — common data model, issues, preprocessing.
- **[Logical Rules](docs/developer/concepts/logical_rules.md)** — enforcing date inequalities, numeric constraints, semantic consistency.
- **[Business Rules Configurations](docs/developer/concepts/business_rules_configurations.md)** — staging step that previews rule-transformed data before training.
- **[Conditional Generation](docs/developer/concepts/conditional_generation.md)** — generating data conditioned on existing column values.
- **[Pipelines](docs/developer/concepts/pipelines.md)** — the YAML-driven multi-job engine.
- **[Mostly AI](docs/developer/concepts/mostly_ai.md)** — how the tabular generator is customised.
- **[Evaluation & Metrics](docs/developer/concepts/evaluation.md)** — fidelity, privacy, and detection metrics.

### Deployment & runtime
- **[API](docs/developer/deployment/api.md)** — REST endpoints and schemas.
- **[Frontend](docs/developer/deployment/frontend.md)** — the Next.js app.
- **[Docker](docs/developer/deployment/docker.md)** — compose files, image structure, volume model.
- **[EC2](docs/developer/deployment/ec2.md)** — running on a bare EC2 box.


## 3. Troubleshooting

- **[Training Failure Diagnostics](docs/developer/concepts/batch_size_errors.md)** — pre-flight checks, batch-size errors, DP+context-chain crashes, and failure summarisation.
