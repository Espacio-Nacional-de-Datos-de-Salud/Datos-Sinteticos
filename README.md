# Synthetic Data Tool for the ENDS (National Health Data Space)

<div style="display: flex; gap: 20px; align-items: center;">
    <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Logotipo_del_Ministerio_para_la_Transformaci%C3%B3n_Digital_y_de_la_Funci%C3%B3n_P%C3%BAblica.svg/960px-Logotipo_del_Ministerio_para_la_Transformaci%C3%B3n_Digital_y_de_la_Funci%C3%B3n_P%C3%BAblica.svg.png" alt="drawing" width="200"/>
        <img src="https://www.seguritecnia.es/wp-content/uploads/2024/07/ntt-data.jpg" alt="drawing" width="200"/>
        </div>

This tool generates synthetic tabular health data for the National Health Data Space (ENDS) in Spain.

---

## 0. Pick your path

Each path is a **single ordered doc**. Start with the one that
matches what you'll do — the deep-reference docs (Configuration,
API, Backend Layout, etc.) are linked from inside each path, not read
front-to-back.

| If you want to… | Read |
| :--- | :--- |
| 🚀 **Use the tool from a browser** (Docker or `make local`) | **[Use the UI](docs/setup/use_ui.md)** |
| 💻 **Use the tool from the terminal** (interactive wizard or `make` one-shots) | **[Use the CLI](docs/setup/use_cli.md)** |
| 🛠 **Maintain or extend the codebase** | **[Developer Onboarding](docs/setup/onboarding.md)** |
| ☁️ **Run on AWS SageMaker** | **[SageMaker Setup](docs/setup/sagemaker.md)** (in addition to one of the above) |

---

## 1. Reference docs (linked from the paths above)

- **[Installation](docs/setup/install.md)** — `make setup`, venvs, config bootstrap. The single source of install steps.
- **[Configuration](docs/setup/configuration.md)** — every YAML knob under `backend/config/`.
- **[Repository Guidelines](docs/setup/repository_guidelines.md)** — coding standards, commit style, docstring format.
- **[Testing](docs/setup/testing.md)** — `make test` (core venv) and `make test-eval` (eval venv).
- **[WSL Quick Setup](docs/setup/wsl_setup.md)** · **[GitLab Access](docs/setup/gitlab.md)**.

---

## 2. Architecture & concepts (week-2 reading)

Read these when you need them — not before.

### Codebase architecture
- **[Backend Layout](docs/concepts/backend_layout.md)** — tour of `backend/src/`: the five layers and the one-direction import rule.
- **[Adding a Feature](docs/concepts/adding_a_feature.md)** — end-to-end walkthrough of a change crossing every backend layer + the frontend.

### Data-side concepts
- **[OMOP Data](docs/concepts/omop.md)** — common data model, issues, preprocessing.
- **[Logical Rules](docs/concepts/logical_rules.md)** — enforcing date inequalities, numeric constraints, semantic consistency.
- **[Conditional Generation](docs/concepts/conditional_generation.md)** — generating data conditioned on existing column values.
- **[Pipelines](docs/concepts/pipelines.md)** — the YAML-driven multi-job engine.
- **[Mostly AI](docs/concepts/mostly_ai.md)** — how the tabular generator is customised.
- **[Evaluation & Metrics](docs/concepts/evaluation.md)** — fidelity, privacy, and detection metrics.

### Deployment & runtime
- **[API](docs/deployment/api.md)** — REST endpoints and schemas.
- **[Frontend](docs/deployment/frontend.md)** — the Next.js app.
- **[Docker](docs/deployment/docker.md)** — compose files, image structure, volume model.
- **[EC2](docs/deployment/ec2.md)** — running on a bare EC2 box.

---

## 3. Troubleshooting

- **[Batch Size Errors](docs/concepts/batch_size_errors.md)** — memory and Mostly AI batch-size constraints.
