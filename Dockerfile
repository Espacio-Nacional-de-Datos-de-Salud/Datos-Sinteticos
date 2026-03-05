# TODO: update to specifc digest
# Build stage
FROM python:3.12.3-slim-bookworm AS builder
COPY --from=ghcr.io/astral-sh/uv:0.10.3 /uv /uvx /bin/

RUN apt-get update && apt-get upgrade -y \
    && apt-get clean \
    && apt-get autoclean \
    && apt-get autoremove --purge  -y \
    && rm -rf /var/lib/apt/lists/*

RUN uv venv /opt/venv --python 3.12.3
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements_core.txt /tmp/requirements_core.txt

RUN uv pip install -r /tmp/requirements_core.txt


#### Final Stage

FROM python:3.12.3-slim-bookworm

RUN useradd -m runuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    GIT_PYTHON_REFRESH=quiet

WORKDIR /app
COPY . .
RUN chown -R runuser:runuser /app

USER runuser
CMD ["python", "-m", "src.main"]