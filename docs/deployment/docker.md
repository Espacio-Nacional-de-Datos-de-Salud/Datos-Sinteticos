[<-- Back to Main Index](../../README.md)

# Docker

Docker provides a simple way to achieve code portability and isolation. A Docker container is lighter than a full virtual machine because it uses the host's kernel but implements its own operating system, called a container. This container starts from an image, which is created using the instructions included in a Dockerfile. Using Docker ensures consistent execution across different environments.

## Dockerfile Structure

Our Dockerfile uses a two-stage build process to reduce the image size. However, due to the large size of our dependencies, the total image size remains considerable, around 8 GB. This Docker image contains only the requirements for training and simulation (`requirements_core.txt`) and, therefore, cannot be used for evaluation. This is because the current plan is to move away from `synthcity` to avoid maintaining two separate environments.

### Stage 1 (Builder)
Base: `python:3.12.3-slim-bookworm`

~~Installs `uv` (a fast Python package manager).~~
UV is no longer used in Docker because of issues within our EC2 instance.

Creates a virtual environment in `/opt/venv`.

Installs dependencies from `requirements_core.txt`.

### Stage 2 (Final)
Same base image but with a clean start.

Copies the pre-built virtual environment from the builder stage.

Configures environment variables and copies the application code from the local repository.

Runs `python -m src.main` as a non-root user.

The `.dockerignore` file defines the files and directories that Docker should not copy to the container when executing `COPY . .`.

Since the tabular data we will work with is quite large, it should not be copied inside the container. Instead, it can be mounted, either through a command-line parameter in `docker run` or as defined in the Docker Compose configuration file. This allows the container to access specific files on the host machine.

## Usage in AWS SageMaker
When executing Docker commands like `docker build` or `docker run`, the option `--network sagemaker` must be included; otherwise, the command will fail. If you decide to use the Container Tools extension, you can update the configuration file to automatically include this option when using the graphical interface (GUI).

Example:

/home/sagemaker-user/sagemaker-code-editor-server-data/data/User/settings.json
```json
{
    "containers.commands.build": "${containerCommand} build --network sagemaker --pull --rm -f \"${dockerfile}\" -t ${tag} \"${context}\"",
    "containers.commands.runInteractive": "${containerCommand} run --network sagemaker --rm -it ${exposedPorts} ${tag}",
    "containers.commands.run": "${containerCommand} run --network sagemaker --rm -d ${exposedPorts} ${tag}"
}
```

This option is included in all commands in this file; however, it must be removed if running in a different environment (e.g., locally).

## Usage Example
Within the repository, you can use the command:

```bash
docker build --network sagemaker -t ds:1.0.0 .
```
to build the image. The `-t` option defines the tag of the image, in this case `ds` (synthetic data) version 1.0.0. An important note is that if multiple images are built, each must have a different tag. Docker will not warn about using the same tag, but this will affect the cache and result in larger image sizes. The version number can simply be incremented in each build to avoid this.

Currently, the program runs interactively on the command line. Therefore, the Docker container must be run in interactive mode. This is achieved through the command:

```bash
docker run --network sagemaker --rm -it \
  -v ./outputs:/app/outputs \
  -v ./data:/app/data \
  -v ./config:/app/config \
  ds:1.0.0
```
replacing `ds:1.0.0` with the tag you used. Alternatively, if you use the Container Tools extension, you can right-click on the image name and select "Run Interactively".

## Docker Compose
Once the application API is configured, the preferred method will be to use Docker Compose. This will facilitate the connection between the user interface (UI) and the backend, which will run in separate containers. Additionally, manual build and run processes will be omitted by simply running `docker compose up`, ensuring a consistent start. Currently, Docker Compose is **not** working within our Sagemaker. We have found success with within an independent EC2 instance. More information and instructions on setup can be found within **[EC2](ec2.md)**.

### compose.yaml
Tells docker to use the default Dockerfile for building. Currently only one service is launched with the name *backend*. Outputs is created/reused as an named independent volume, existing at /app/outputs within the container. Currently, ./data and ./config are used as [bind mounts](https://docs.docker.com/engine/storage/bind-mounts/). Basically, this means that the Docker container has access to these directories on the host filesystem, and therefore any changes you make will be reflected in the container without rebuilding. In the future, data will most likely be an independent volume, and potentially config as well.

### Running Docker Compose
It is very simple. Run `docker compose up` within the root of the project. This should automatically rebuild the image if any changes have been made to the source code, otherwise it will just start it. If you encounter an issue with the build failing, you may need to run `export DOCKER_BUILDKIT=0`.

## MLflow
Currently, the use of an external MLflow server for Docker has not been investigated. Therefore, MLflow will automatically run in local mode inside the container, storing all metadata there. This metadata will be deleted at the end of the program execution. This could be solved by configuring a volume, allowing experiments performed inside Docker to be saved locally on the host machine.




[<-- Back to Main Index](../../README.md)
