.PHONY: help setup inspect train simulate eval pipeline format lint models simulations inspections clean

SHELL := /bin/bash
.ONESHELL:

DEFAULT_GOAL := help

CONFIG ?= config/pipelines/my_pipeline.yaml
EXEC_CONFIG := config/execution_config.py

CORE_PYTHON := .venv_core/bin/python
EVAL_PYTHON := .venv_eval/bin/python
RUFF := $(CORE_PYTHON) -m ruff

define set_mode
$(CORE_PYTHON) -c "import re, pathlib; p = pathlib.Path('$(EXEC_CONFIG)'); p.write_text(re.sub(r'EXECUTION_MODE:\s*str\s*=\s*\".*\"', 'EXECUTION_MODE: str = \"$(1)\"', p.read_text()))"
endef

help:
	@printf "Available targets:\n"
	@printf "  make setup        Install uv, Python 3.12.3, and both virtual environments\n"
	@printf "  make inspect      Run inspection mode (MODE=i): load+autodetect, persist session for review\n"
	@printf "  make train        Run training mode (MODE=t); set INSPECTION_ID in execution_config to train from an inspection\n"
	@printf "  make simulate     Run simulation mode (MODE=s)\n"
	@printf "  make eval         Run evaluation mode (MODE=e)\n"
	@printf "  make pipeline     Run the full pipeline mode (MODE=p, CONFIG=path/to.yaml)\n"
	@printf "  make format       Format Python code with ruff\n"
	@printf "  make lint         Run ruff check\n"
	@printf "  make inspections  List available inspection sessions\n"
	@printf "  make models       List available trained models\n"
	@printf "  make simulations  List available simulations\n"
	@printf "  make clean        Remove common local build caches\n"

setup:
	@echo "Checking for uv..."
	command -v uv >/dev/null 2>&1 || { echo "Installing uv..."; curl -kLsSf https://astral.sh/uv/install.sh | sh; source "$$HOME/.local/bin/env"; }
	uv python install 3.12.3
	echo "Building core environment (.venv_core)..."
	uv venv .venv_core --python 3.12.3
	uv pip install -r requirements_core.txt --python .venv_core/bin/python
	echo "Building evaluation environment (.venv_eval)..."
	uv venv .venv_eval --python 3.12.3
	uv pip install -r requirements_evaluation.txt --python .venv_eval/bin/python
	@echo "Setup complete."

inspect:
	$(call set_mode,i)
	$(CORE_PYTHON) -m src.main

train:
	$(call set_mode,t)
	$(CORE_PYTHON) -m src.main

simulate:
	$(call set_mode,s)
	$(CORE_PYTHON) -m src.main

eval:
	$(EVAL_PYTHON) -m src.evaluation

pipeline:
	$(CORE_PYTHON) -m src.pipeline --config $(CONFIG)

format:
	$(RUFF) format .

lint:
	$(RUFF) check .

models:
	$(CORE_PYTHON) -m src.core.list_available_models --format table

simulations:
	$(CORE_PYTHON) -m src.core.list_available_simulations --format table

inspections:
	$(CORE_PYTHON) -m src.core.list_available_inspections --format table

clean:
	find . -type d -name '__pycache__' -prune -exec rm -rf {} + && rm -rf .ruff_cache .pytest_cache
