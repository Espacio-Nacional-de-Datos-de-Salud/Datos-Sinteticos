[<-- Back to Main Index](../../README.md)

# Setup

This document covers everything you need to **run the code on your local machine**.

Depending on your goal, you can use the code in two different ways:

### 1. As a User (Generate Synthetic Data)
If you just want to use the tool to generate synthetic data, you can choose between two interfaces:
- **Visual UI (Recommended for non-technical users):** The easiest way to get started is by launching the user-friendly frontend via Docker. If you choose this, you don't need to read the rest of this page. Go straight to:
  - 👉 [Docker Quick Start Guide](../deployment/docker.md)
- **Command Line Interface (CLI):** If you prefer running the process via terminal, you will need to set up the environment locally as described in this document.

### 2. As a Developer (Maintain or Improve the Tool)
If you want to modify, maintain, or improve the codebase, you need to set up the local development environment detailed below. The `Makefile` automation steps in the following sections apply specifically for this local CLI/Dev setup.

---

In the rest of this document, we explain how to set up the local environment in order to:
- Install the dependencies
- Prepare your environment
- Configure the parameters
- Run the pipeline end-to-end.

> **Recommendation for Windows users:** We recommend using **WSL** over PowerShell as all scripts are originally designed for Linux-like environment. See:

- [Quick WSL Setup](wsl_setup.md).

## 1. Installation

### 1.1 Clone and Access the Repository

For GitLab authentication details (PAT creation, clone from VS Code, and credential persistence), see:

- [GitLab Access and Usage Guide](gitlab.md).

```bash
git clone <repository-url>
cd herramienta-datos-sinteticos
```


### 1.2 Makefile automation

On Linux-like systems, `make` is the easy-to-use entry point: it bundles several commands into a simple user friendly list of make orders.

> In order to be able to use `make` commands you need to be on a Linux-like OS. If you are in Windows and want to take advantadge of `make`, you can use WSL ([Quick Setup on WSL](wsl_setup.md)).

You will first need to install `make` by running:

```bash
sudo apt install make
```
Once you have it you can use to easily run most parts of the code. You can see the available `make` commands running:

```bash
make help
```

### 1.3 Automated Setup

The repository provides automated scripts that: 
- Install **uv** (an improved version of `pip`, the package installer for python).
- Install an isolated **Python 3.12.3**.
- Construct two python virtual environments (`.venv_core` and `.venv_eval`) for the backend.
- Install the frontend dependencies.
- Copies `{name}.example.yaml` configuration files into real `{name}.yaml` config files ready to be read by the code.


#### Linux / macOS / WSL
```bash
make setup
```

#### Windows (PowerShell)
```powershell
.\scripts\setup.ps1
```

### 1.4 Configuration
Amongst other things, `make setup` copies every `backend/config/**/*.example.yaml` to its `*.yaml`
counterpart (skipping any that already exist — safe to re-run). If the
real file is missing when the backend starts, it fails fast with a message
telling you to run `make config`.

Then define the required values for your first run by editing the real files:

1. In `backend/config/general.yaml` set `settings.data_subpath` if your data
   lives in a subfolder of `<project_root>/data/` (leave empty to use `data/`).
2. Optionally tune training/evaluation/rules in:
   - `backend/config/mostly_ai.yaml`
   - `backend/config/evaluation.yaml`
   - `backend/config/rules.yaml`

> ！Do not edit any `*.example.yaml` — they are read-only templates committed to git. You should edit only `*.yaml` files.

In [Configuration](configuration.md) is a detail of each configuration file and what it controls.

### 1.5 Quick Start

Once the setup is done, you can run both the backend and frontend using

```bash
make local
```

which will run both the backend (+ expose its API locally) and frontend.

The backend runs on `http://localhost:8000` and frontend on `http://localhost:3000`, access them on your browser.

You can also run the code by parts, getting more fine-gained control on what is going on behind the curtains. --> See [Execution](execution.md).


[<-- Back to Main Index](../../README.md)
