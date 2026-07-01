[<-- Back to Main Index](../../README.md)

# Installation

The single reference for getting the environment ready on your machine.
Whatever path you're following (UI, CLI, developer), every doc that
needs "install the tool" points here.

For **Docker-only** UI usage you don't need this page — go to
[Use the UI](use_ui.md) and pick the Docker path.

---

## 1. Prerequisites

| Platform | What you need |
| :--- | :--- |
| Linux / macOS / WSL | `make`, `git`, `curl` (everything else is installed automatically) |
| Windows native | Use **WSL** — almost every script assumes a Linux-like shell. Install it from an **admin PowerShell** with `wsl --install -d Ubuntu`, then run everything from the Ubuntu shell. |

If `make` is missing on Debian/Ubuntu: `sudo apt install make`.

> To avoid re-entering Git credentials on every push/pull, run once:
> `git config --global credential.helper store`.

---

## 2. Clone

```bash
git clone <repository-url>
cd herramienta-datos-sinteticos
```

---

## 3. Install everything

```bash
make setup
```

This single command:

- installs **uv** (fast `pip` replacement),
- installs an isolated **Python 3.12.3**,
- builds the **two backend venvs** (`.venv_core` and `.venv_eval`) from
  `backend/requirements_core.txt` and `backend/requirements_evaluation.txt`,
- installs the frontend's Node dependencies (auto-installs Node 20+ via
  nvm if it's missing),
- bootstraps every `backend/config/**/*.example.yaml` into its real
  `*.yaml` counterpart (skipping anything that already exists — safe to
  re-run).

**Windows native (no WSL)**: `.\scripts\setup.ps1` does the equivalent
in PowerShell.

> Why two venvs? `synthcity` + `torch` + `opacus` (evaluation) conflict
> with the training stack. They live in `.venv_eval`; everything else
> lives in `.venv_core`. `make` targets pick the right one
> automatically — you almost never activate them by hand.

---

## 4. Verify

```bash
ls .venv_core/bin/python .venv_eval/bin/python
ls backend/config/*.yaml          # real YAMLs, not just .example
```

Both lines should print existing files. If a real `*.yaml` is missing
later, the backend fails fast and tells you to run `make config`
(re-runs only the bootstrap step).

---

## 5. Configure your first run

Edit `backend/config/general.yaml` (the real, gitignored file —
**never** edit `*.example.yaml`):

1. `settings.data_subpath` — set this if your input data lives under
   a subfolder of `<project_root>/data/`. Leave empty to use `data/`
   directly.
2. (Optional) tune `mostly_ai.yaml`, `evaluation.yaml`, `rules.yaml`.

Full per-file reference: [Configuration](configuration.md).

[<-- Back to Main Index](../../README.md)
