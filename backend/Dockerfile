# TODO: update to specifc digest
# Build stage - core API dependencies
FROM python:3.12.3-slim-bookworm AS builder

RUN apt-get update && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends build-essential python3-dev \
    && apt-get clean \
    && apt-get autoclean \
    && apt-get autoremove --purge  -y \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip uv && uv venv /opt/venv

COPY requirements_core.txt /tmp/requirements_core.txt

RUN uv pip install --python /opt/venv/bin/python -r /tmp/requirements_core.txt 

# Now evaluation dependencies

RUN uv venv /opt/venv_eval

COPY requirements_evaluation_docker.txt /tmp/requirements_evaluation_docker.txt

# synthcity and decaf are installed without deps to avoid the
# decaf -> torchtext dependency (no aarch64 wheel for torchtext>=0.10).
# All other synthcity deps are covered by requirements_evaluation_docker.txt.
RUN uv pip install --python /opt/venv_eval/bin/python --no-deps synthcity==0.2.12 decaf-synthetic-data==0.1.7 \
    && uv pip install --python /opt/venv_eval/bin/python -r /tmp/requirements_evaluation_docker.txt


#### Final Stage

FROM python:3.12.3-slim-bookworm

RUN useradd -m runuser

COPY --from=builder /opt/venv /opt/venv
COPY --from=builder /opt/venv_eval /opt/venv_eval

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    GIT_PYTHON_REFRESH=quiet \
    EVAL_PYTHON_PATH=/opt/venv_eval/bin/python

WORKDIR /app
COPY src ./backend/src
COPY config ./backend/config
RUN touch ./backend/__init__.py
# pycox crea su carpeta datasets/data en site-packages al importarse,
# solo hay que dar permisos a esa ruta (no a todo el venv_eval, que es lentísimo).
# /app/backend/outputs se crea y chown-ea explícitamente para que, cuando el
# named volume `outputs` se inicialice por primera vez en Docker nativo de Linux,
# herede la propiedad de runuser (si no, Docker lo crea root:root y los escritos
# desde la API fallan con PermissionError).
RUN mkdir -p /opt/venv_eval/lib/python3.12/site-packages/pycox/datasets/data \
    && mkdir -p /app/backend/outputs \
    && chown -R runuser:runuser /app /opt/venv_eval/lib/python3.12/site-packages/pycox/datasets
USER runuser
CMD ["python", "-m", "backend.src.cli"]
