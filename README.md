# Synthetic Data Tool for the ENDS (Espacio Nacional de Datos de Salud)

<p align="center">
  <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/e/e4/Logotipo_del_Ministerio_para_la_Transformaci%C3%B3n_Digital_y_de_la_Funci%C3%B3n_P%C3%BAblica.svg/960px-Logotipo_del_Ministerio_para_la_Transformaci%C3%B3n_Digital_y_de_la_Funci%C3%B3n_P%C3%BAblica.svg.png" alt="Ministerio" width="200"/>
  &nbsp;&nbsp;&nbsp;&nbsp;
  <img src="https://www.seguritecnia.es/wp-content/uploads/2024/07/ntt-data.jpg" alt="NTT Data" width="200"/>
</p>

This tool generates synthetic tabular health data for the National Health Data Space (ENDS) in Spain.

## Pick your path

| If you want to… | Read |
| :--- | :--- |
| 🚀 **Use the tool from a browser** (Docker or `make local`) | **[Use the UI](docs/setup/use_ui.md)** |
| 💻 **Use the tool from the terminal** (interactive wizard or `make` one-shots) | **[Use the CLI](docs/setup/use_cli.md)** |
| 🛠 **Maintain or extend the codebase** | **[Developer Onboarding](docs/setup/onboarding.md)** |


## Setup & reference

- **[Installation](docs/setup/install.md)** — `make setup`, the two venvs, config bootstrap. The single source of install steps.
- **[Configuration](docs/setup/configuration.md)** — every YAML knob under `backend/config/`.
- **[Contributing](CONTRIBUTING.md)** — coding standards, commit style, docstring format.
- **[Testing](docs/setup/testing.md)** — `make test` (core venv) and `make test-eval` (eval venv).


## Deployment & runtime

- **[Docker](docs/deployment/docker.md)** — compose files, image structure, volume model.
- **[API](docs/deployment/api.md)** — REST endpoints and schemas (the UI is a client of this API).


## Complete & final documentation

The markdown guides in this repository cover only practical setup and usage. The
**complete and final documentation** (which goes far deeper) lives as the
project deliverables under [`docs/documentacion-completa/`](docs/documentacion-completa):

| Document | What it covers |
| :--- | :--- |
| [Documentación técnica](<docs/documentacion-completa/Documentación técnica 20260630.docx>) | The authoritative technical reference: layered backend architecture, OMOP data model, logical/business rules, conditional generation, the Mostly AI generator, evaluation methodology, and the pipeline engine. |
| [Manual de instrucciones (manual de usuario)](<docs/documentacion-completa/Manual de instrucciones de la herramienta de generación de datos sintéticos 20260630.docx>) | Full end-user manual for operating the tool. |
| [Informe de validación de la herramienta](<docs/documentacion-completa/Informe de validación de la herramienta 20260630.docx>) | Validation report for the tool. |
| [Documento de cierre del proyecto](<docs/documentacion-completa/Documento de cierre del proyecto - Datos sintéticos 20260630.docx>) | Project closure document. |

These `.docx` files are a snapshot of the final documents handed-in as deliverables, the markdown here is a quick-start layer on top of them.
