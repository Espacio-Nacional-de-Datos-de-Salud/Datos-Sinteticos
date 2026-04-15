# TODO: update to specifc digest
# Build stage
FROM python:3.12.3-slim-bookworm AS builder

RUN apt-get update && apt-get upgrade -y \
    && apt-get clean \
    && apt-get autoclean \
    && apt-get autoremove --purge  -y \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY requirements_core.txt /tmp/requirements_core.txt

RUN pip install -r /tmp/requirements_core.txt


#### Final Stage

FROM python:3.12.3-slim-bookworm

RUN useradd -m runuser

COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    GIT_PYTHON_REFRESH=quiet

WORKDIR /app
COPY src ./src
RUN mkdir /app/outputs && chown -R runuser:runuser /app
USER runuser
CMD ["python", "-m", "src.main"]
