[<-- Back to Main Index](../../README.md)

# Use the UI

For users who want to **drive the tool from a browser**: launch
inspections, train models, simulate, and evaluate by clicking — no
terminal workflows beyond starting the services.

You have two ways to bring the UI up. Pick the one that matches your
machine.

| Path | When to pick it | What you need |
| :--- | :--- | :--- |
| **A. Docker Compose** | You don't want to install Python / Node yourself; or you want a clean, isolated environment; or you're on Windows without WSL. | Docker + Docker Compose (cross-platform). |
| **B. `make local`** | You have a Linux / macOS / WSL shell and you'd rather avoid the Docker layer (faster reload, simpler logs). | A local install via `make setup`. |

Both serve the **same** frontend at `http://localhost:3000` and the
same API at `http://localhost:8000`.

---

## Path A — Docker Compose (cross-platform)

### A.1 Install Docker

| OS | Recommendation |
| :--- | :--- |
| **Windows** | Install [Rancher Desktop](https://rancherdesktop.io/) (free) — or use WSL and follow the Linux instructions. |
| **macOS** | `brew install colima docker docker-compose` then `colima start --cpu 4 --memory 10`. Restart Colima after every reboot. |
| **Linux / WSL** | `sudo apt-get install -y docker.io docker-compose-plugin` then `sudo usermod -aG docker $USER` and open a new shell. |

Full install steps, troubleshooting, and the structure of our compose
files: [Docker](../deployment/docker.md).

Verify:

```bash
docker --version
docker compose version
docker ps                 # should print an empty table, not an error
```

### A.2 Run

```bash
git clone <repository-url>
cd herramienta-datos-sinteticos
make compose              # equivalent to: docker compose up --build
```

The first build takes several minutes. Once the log says
`Application startup complete`, open `http://localhost:3000`.

To stop everything: `make compose-stop`.

> **No `make setup` needed** on this path — the Docker image bakes in
> the venvs. You only need a local `make setup` if you also intend to
> develop on the code.

---

## Path B — `make local` (Linux / macOS / WSL)

Best if you already work in a Unix-like shell. Faster startup than
Docker, real hot reload, native logs.

### B.1 Install

Do the one-time setup from [Installation](install.md), then come back.

### B.2 Run

```bash
make local
```

This starts the backend (uvicorn on port 8000) and the frontend
(Next.js on port 3000) in one terminal. Open `http://localhost:3000`.

`Ctrl+C` stops both.

> **Windows users without WSL**: it's possible but you're on your own —
> you'd need to run the backend and frontend manually with native
> Python and Node, no `make`. Strongly prefer **WSL** ([Quick WSL
> Setup](wsl_setup.md)) or Path A (Docker).

---

## What's next?

- **Configure a run** (input file paths, sample sizes, rules) →
  [Configuration](configuration.md).
- **Understand what the buttons do** (inspect / train / simulate /
  evaluate / pipeline) → see the workflow diagram and per-run output
  conventions in the [Developer Onboarding § 0](onboarding.md).
- **Where do my results go?** → `backend/outputs/` (the UI surfaces the
  same files; same folder convention regardless of which entry point
  you used).
- **The UI calls a REST API** — if you want to script the same actions
  from your own code, see [API](../deployment/api.md).

[<-- Back to Main Index](../../README.md)
