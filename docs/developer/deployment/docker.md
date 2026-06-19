[<-- Back to Main Index](../../README.md)

# Docker

Docker is a containerization tool that lets you package the application with all its dependencies, ensuring it runs the same way regardless of what machine you're using. Docker Compose orchestrates multiple containers (in our case: backend and frontend) to work together.

## 0. Quickstart

If you have never used Docker before, follow these steps to get up and running.


### Step 1 — Install Docker and Docker Compose

Docker Desktop requires an enterprise license for business use (paid subscription). We use free alternatives — **Rancher Desktop** (Windows) and **Colima** (macOS) — which provide the same `docker` commands without licensing fees.

#### **Windows (PowerShell)**
```powershell
winget install -e --id SUSE.RancherDesktop
```
Restart after installation. Rancher Desktop runs as a background service and exposes the same `docker` and `docker compose` commands in PowerShell.

- Open the Rancher Desktop application from your Start Menu (if you previously had Docker Desktop installed, right-click and select Run as Administrator to avoid pipe permission conflicts).

- Go to Preferences > Container Engine and ensure dockerd (moby) is selected.

- Look at the bottom right corner of the Rancher Desktop window. You will see a progress bar indicating "Starting WSL environment".

- Wait completely for this progress bar to disappear. The background Docker daemon will not be available until it finishes booting and the status shows as online/idle.

- If you used to have an old Docker Desktop instance, ensure your terminal is talking to Rancher Desktop instead by running:
```ps
docker context use default
```

A better alternative is to use **WSL** — open your WSL terminal and follow the Linux steps below, or set it up first if you still don't have it [Quick Setup on WSL](wsl_setup.md).


#### **macOS**
```bash
brew install colima docker docker-compose
colima start --cpu 4 --memory 10
```
> Colima must be started every time you reboot the computer before running Docker commands.

#### **Linux / WSL**
```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin libsecret-1-0
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# close the terminal and open a new one back after this
```

> ⚠️ Warning: This might not work properly if you are serving the Docker deamon from somewhere else (for example if you are in WSL and you previously installed Rancher Desktop for the Windows setup).


> On older distros the compose plugin may be called `docker-compose` (with a dash). If `docker compose` (no dash) gives an error, try `docker-compose` instead.

### Step 2 — Verify the installation

Open a terminal and run:
```bash
docker --version
docker compose version   # or: docker-compose --version
```
Both commands should print version numbers without errors. sTo verify that the Docker server (the daemon) is actually running, connected, and responding, run:

```bash
docker ps
```

Should correctly show processes table, in your case you just installed docker so no process will appear:

```bash
obustosm@NTTD-HG072R269J herramienta-datos-sinteticos % docker ps
CONTAINER ID   IMAGE     COMMAND   CREATED   STATUS    PORTS     NAMES
```
### Step 3 — Run the project

From the root of this repository:

```bash
# Linux / WSL / Windows (in WSL terminal)
docker compose up --build

# macOS with Colima (note the dash)
docker-compose up --build

# Or use the project shortcut if you have make installed
make compose
```

The first run downloads/builds images and can take several minutes. Subsequent runs are much faster. Once it says `Application startup complete`, open your browser at `http://localhost:3000`.

---

Docker provides a simple way to achieve code portability and isolation. A Docker container is lighter than a full virtual machine because it uses the host's kernel but implements its own operating system, called a container. This container starts from an image, which is created using the instructions included in a Dockerfile. Using Docker ensures consistent execution across different environments.


## 1. Dockerfile Structure

Our Dockerfile uses a two-stage build process to reduce the image size. However, due to the large size of our dependencies, the total image size remains considerable, around 8 GB. This Docker image contains only the requirements for training and simulation (`requirements_core.txt`). Evaluation depends on `synthcity` and `torch`, so it is intentionally kept out of this image and runs separately in `.venv_eval`.

### Stage 1 (Builder)
Base: `python:3.12.3-slim-bookworm`

Installs `uv` (a fast Python package manager).

Creates a virtual environment in `/opt/venv`.

Installs dependencies from `requirements_core.txt`.

Creates a separate virtual environment for evaluation in `/opt/venv_eval`. 

Installs dependencies from `requirements_evaluation_docker.txt`

### Stage 2 (Final)
Same base image but with a clean start.

Copies both pre-built virtual environmenta from the builder stage.

Configures environment variables and copies the application code `backend/src` from the local repository.

Runs `python -m backend.src.cli` as a non-root user.

The `.dockerignore` file defines the files and directories that Docker should not copy

Since the tabular data we will work with is quite large, it should not be copied inside the container. For development, either a bind mount or a volume can be used. A bind mount allows the container to access specific files on the host machine, while a volume creates a persistent storage location for the container(s) to access. A volume is the method that will be used in production, as it better isolates the containers. Either option can be used with command-line parameters in `docker run`, but the prefered method is through `docker compose`, which is already configured in `compose.yaml`.



## 2. Docker Compose
The preferred method for deployment is Docker Compose. This facilitates the connection between the user interface (UI) and the backend, which run in separate containers. Additionally, manual build and run processes can be be omitted with a single command, ensuring a consistent start. Currently, Docker Compose is **not** working within Sagemaker. We have found success with within an independent EC2 instance, as well as on our local machines. Installation instructions for Docker Compose within a Linux EC2 instance, which should also apply to Linux/WSL local machines, can be found in **[EC2](ec2.md)**.

### compose.yaml
The docker compose configuration file. Defines two services: `backend` and `frontend`, and declares one named volume: `outputs`.

You will notice the keyword `volumes` appears three times in the file. This is because it means different things depending on where it sits in the YAML hierarchy:

- `services.backend.volumes` — declares what is mounted *into* the backend container.
- `services.frontend.volumes` — declares what is mounted *into* the frontend container.
- Top-level `volumes` — a registry that tells Docker Compose to create and manage a named volume. Any named volume referenced inside a service must be declared here, or the file will fail to validate. Bind mounts (paths starting with `./`) do **not** need a top-level entry.

There are three types of mounts used across the two services:

| Type | Example | Owned by | Survives `down`? | Survives `down --volumes`? |
|---|---|---|---|---|
| Named volume | `outputs:/app/backend/outputs` | Docker | Yes | No |
| Bind mount | `./backend/data:/app/backend/data` | Your local disk | Yes | Yes |
| Anonymous volume | `/app/node_modules` | Docker | Yes | No |

A **bind mount** is simply your local folder mirrored into the container in real time. Docker does not store anything — it reads and writes your actual files directly. Because the data lives on your disk, it is untouched by any `docker compose down` variant.

A **named volume** is storage created and managed internally by Docker (typically under `/var/lib/docker/volumes/`). It is not visible as a folder in your project. It survives a plain `docker compose down`, but is deleted by `docker compose down --volumes`.

An **anonymous volume** is the same as a named volume but without an explicit name, so Docker generates one. It is used as a scoping mechanism (explained below).

#### Backend Service
Tells Docker to use the Dockerfile within `backend` for building. Runs the API using `uvicorn`, forwarding port 8000 outside the container to allow other services on the host, or users on the same network, to connect.

The `outputs` named volume is mounted at `/app/backend/outputs`. Because it is Docker-managed, generated output files (pipeline results, inspection outputs, etc.) persist across container restarts without being tied to any folder on your machine. However, they are cleared if you run `docker compose down --volumes` or `docker compose down -v`.

The remaining mounts — `backend/data` and `backend/config` — are bind mounts, meaning changes you make to those folders on your machine are reflected inside the container immediately without a rebuild. In the future, these bind mounts should be removed.

#### Frontend Service
Tells Docker to use the Dockerfile within `frontend` for building. Runs Next.js, forwarding port 3000.

The entire `./frontend` folder is bind-mounted into `/app`, which enables live code reloading. However, this creates a conflict: the bind mount would overwrite `/app/node_modules` with whatever is in your local `./frontend` folder — which may be empty or outdated. To prevent this, two anonymous volumes are declared:

```yaml
- /app/node_modules
- /app/.next
```

These tell Docker to keep the container's own copy of those two directories and not let the bind mount touch them. The `node_modules` inside the container are populated during the image build step (`RUN npm install` in the Dockerfile), so they are always correct and fully installed regardless of what is on your local disk.

### Running Docker Compose
Run `make compose` (or `docker compose up --build`) within the root of the project for the simplest usage. This should automatically rebuild the image if any changes have been made to the source code, otherwise it will just start it. 

However, there are several options that you may want to use. Running with `--build` forces a rebuild, which is useful when docker doesnt detect changes you made. `--force-rm` can be used to remove intermediate images, which can become quite large (>20 GB). This will slow down later builds, but is useful if you are limited by space. Either way, you may occasionally want to run `docker image` to check storage usage. Dangling images can be removed with `docker prune`, and specific images with `docker rmi <image id>`. If you encounter an issue with the build failing due to buildx, you may need to run `export DOCKER_BUILDKIT=0`.

## 3. CLI Wizard and Isolated Services

If you prefer to work with the terminal rather than the frontend, or if you want to run only specific services to save memory, you can use the interactive CLI Wizard directly from Docker.

### Running only the Backend
To run only the backend without starting the Next.js frontend, use the `-d` (detached) flag specifying the backend service:

```bash
docker-compose up -d backend
```

This launches the backend as a "detached" (background) container.

### Running the Interactive CLI
Once the backend container is running, you can execute the interactive CLI wizard inside it:

```bash
docker-compose exec backend python -m backend.src.cli
```

You can now run the interactive CLI wizard as many times as needed.

Since the services were started in detached mode, they will continue running in the background even after you exit the CLI. To shut everything down when you are finished, run:

```bash
docker-compose down
```


## 4. Troubleshooting

Issues most commonly seen on bare-metal Linux installs (native Docker Engine) rather than on Colima/Rancher Desktop.

### `E: Unable to locate package docker-compose-plugin`

Stock Ubuntu's APT sources don't include Docker's official repository, so the `docker-compose-plugin` package isn't visible. Two options:

- **Recommended** — add Docker's official APT repo and install from there. Follow [Install Docker Engine on Ubuntu](https://docs.docker.com/engine/install/ubuntu/) (the GPG key + `/etc/apt/sources.list.d/docker.list` block), then re-run `sudo apt-get install docker-compose-plugin`.
- **Fallback** — on older distros the plugin ships under the legacy name `docker-compose` (with a dash). Install it with `sudo apt-get install docker-compose` and use `docker-compose up` (with the dash) instead of `docker compose`.

### `error getting credentials … org.freedesktop.secrets was not provided by any .service files`

The Docker CLI's default credential helper (`secretservice`) talks to a D-Bus secret service (gnome-keyring / KWallet). On a headless or minimal Linux box, no such service is registered and `docker compose build` fails before it even starts pulling. Pick one:

- **Easiest** — disable the credential helper. Edit `~/.docker/config.json` and either remove the `"credsStore"` line or set it to `""`. Docker will then store registry credentials in plaintext inside `config.json`. This project doesn't push to a private registry, so it's harmless.
- **Switch helper** — `sudo apt install gnupg2 pass`, then set `"credsStore": "pass"` in `~/.docker/config.json` and initialise `pass` once (`pass init <gpg-id>`).
- **Install a keyring daemon** — `sudo apt install gnome-keyring` and run inside a desktop session.

### `PermissionError: [Errno 13] Permission denied: '/app/backend/outputs/inspections'` (HTTP 500 on `POST /inspections/`)

If you built an image from a commit before the `outputs` mountpoint was pre-created in the Dockerfile, Docker initialised the named volume as `root:root` and the non-root container user can't write to it. Drop the stale volume and rebuild:

```bash
docker compose down -v
docker compose up --build
```

`-v` removes the named volume so it's re-initialised from the image (now owned by `runuser`). Note that this also clears any previous inspection outputs.

[<-- Back to Main Index](../../README.md)
