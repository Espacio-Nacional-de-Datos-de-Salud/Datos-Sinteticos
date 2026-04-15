[<-- Back to Setup](setup_and_execution.md)

# Quick Setup on WSL (Recommended over PowerShell)

If you are on Windows, we recommend running this project from **WSL** instead of PowerShell to get a Linux-like environment and avoid shell/path inconsistencies.

## 1. Install WSL and Ubuntu

Open **PowerShell as Administrator**.

Run:

```powershell
wsl --install -d Ubuntu
```

Then restart your machine if prompted, open Ubuntu, and finish the initial Linux user setup.

## 2. Clone the Repository inside WSL

For GitLab authentication details (PAT creation and credential persistence), see [GitLab Access and Usage Guide](gitlab.md).

```bash
git clone https://umane.emeal.nttdata.com/git/analytics/projects/health/ends-pt/herramienta-datos-sinteticos.git
cd herramienta-datos-sinteticos
```

## 3. Run Automated Linux Setup

```bash
make setup
```

This installs uv (if missing), Python 3.12.3, and creates `.venv_core` and `.venv_eval`.

## 4. Run

```bash
make train
```

Replace `train` with `inspect`, `simulate`, `eval`, or `pipeline` depending on your execution mode. Run `make help` to see all available targets.

[<-- Back to Setup](setup_and_execution.md)
