.PHONY: help setup config clean-config reset-config local cli inspect train simulate eval pipeline format lint ty test test-eval coverage models simulations inspections evaluations pipelines api frontend compose compose-api compose-cli compose-prod compose-stop clean copy-repo

SHELL := /bin/bash

DEFAULT_GOAL := help

CONFIG ?= backend/config/pipelines/my_pipeline.yaml
GENERAL_CONFIG ?= backend/config/general.yaml
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
	DOCKER_COMPOSE = docker-compose
else
	DOCKER_COMPOSE = docker compose
endif


API_HOST ?= 0.0.0.0
API_PORT ?= 8000
FRONTEND_PORT ?= 3000
FRONTEND_DIR := frontend
NODE_MIN_VERSION ?= 20.9.0
NODE_VERSION ?= 20
NVM_VERSION ?= v0.40.3
NVM_DIR ?= $(HOME)/.nvm

CORE_PYTHON := $(CURDIR)/.venv_core/bin/python
EVAL_PYTHON := $(CURDIR)/.venv_eval/bin/python
RUFF := $(CORE_PYTHON) -m ruff
TY := $(CORE_PYTHON) -m ty

# SageMaker instances tend to have weaker single-thread CPU than dev laptops,
# which dominates Next.js dev compile time. Detect via the resource-metadata
# file that only exists inside SageMaker, and drop source maps in dev there
# (errors point to bundled output instead of original source — acceptable
# tradeoff for the speedup). No-op on Mac/WSL/local Linux.
NEXT_DEV_FLAGS := $(shell [ -f /opt/ml/metadata/resource-metadata.json ] && echo "--disable-source-maps" || echo "")

define set_mode
$(CORE_PYTHON) -c "from pathlib import Path; import sys, yaml; path = Path('$(GENERAL_CONFIG)');\
path.exists() or sys.exit(f'Missing {path}. Run make config first.');\
data = yaml.safe_load(path.read_text()) or {};\
data.setdefault('execution', {})['mode'] = '$(1)';\
path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=False))"
endef


define frontend_env
if command -v node >/dev/null 2>&1 && node -e "const [maj, min, patch] = process.versions.node.split('.').map(Number); const [reqMaj, reqMin, reqPatch] = '$(NODE_MIN_VERSION)'.split('.').map(Number); process.exit(maj > reqMaj || (maj === reqMaj && (min > reqMin || (min === reqMin && patch >= reqPatch))) ? 0 : 1)"; then \
	echo "Using Node.js $$(node -p 'process.versions.node')"; \
else \
	echo "Node.js >= $(NODE_MIN_VERSION) is required for the frontend."; \
	if [ ! -s "$(NVM_DIR)/nvm.sh" ]; then \
		echo "Installing nvm $(NVM_VERSION)..."; \
		curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/$(NVM_VERSION)/install.sh | bash; \
	fi; \
	. "$(NVM_DIR)/nvm.sh"; \
	echo "Installing Node.js $(NODE_VERSION) via nvm..."; \
	nvm install $(NODE_VERSION); \
	nvm use $(NODE_VERSION); \
	nvm alias default $(NODE_VERSION) >/dev/null; \
fi; \
$(1)
endef

help:
	@printf "Available targets:\n"
	@printf "\nSetup:\n"
	@printf "  make setup        Install uv, Python 3.12.3, and both virtual environments\n"
	@printf "  make config       Create real backend/config/*.yaml files from *.example.yaml templates (non-destructive)\n"
	@printf "  make clean-config Delete every real backend/config/*.yaml (keeps *.example.yaml templates)\n"
	@printf "\nExecution (backend):\n"
	@printf "  make cli          Open the interactive backend CLI wizard\n"
	@printf "  make inspect      Run inspection mode (MODE=i): load+autodetect, persist session for review\n"
	@printf "  make train        Run training mode (MODE=t); set execution.inspection_id in backend/config/general.yaml to train from an inspection\n"
	@printf "  make simulate     Run simulation mode (MODE=s)\n"
	@printf "  make eval         Run evaluation mode (MODE=e)\n"
	@printf "  make pipeline     Run the full pipeline mode (MODE=p, CONFIG=path/to.yaml)\n"
	@printf "\nCatalogs:\n"
	@printf "  make inspections  List available inspection sessions\n"
	@printf "  make models       List available trained models\n"
	@printf "  make simulations  List available simulations\n"
	@printf "  make evaluations  List available evaluations\n"
	@printf "  make pipelines    List available pipeline configurations\n"
	@printf "\nServices:\n"
	@printf "  make api          Start backend API locally (uvicorn, API_PORT=%s)\n" "$(API_PORT)"
	@printf "  make frontend     Start frontend locally (auto-installs deps if missing)\n"
	@printf "  make local        Start backend + frontend together in one terminal\n"
	@printf "\nDocker / Compose:\n"
	@printf "  make compose          Build and start services in dev mode (auto-merges compose.override.yaml)\n"
	@printf "  make compose-api      Build and start backend only, detached (API on port 8000)\n"
	@printf "  make compose-cli      Build and start backend, then open interactive CLI\n"
	@printf "  make compose-prod     Build and start services in prod mode (no bind mounts, baked config)\n"
	@printf "  make compose-stop     Stop and remove all running compose containers\n"
	@printf "\nDev:\n"
	@printf "  make clean        Remove generated run artifacts and local caches\n"
	@printf "  make copy-repo    Create a clean copy of the repo in the parent folder (excludes venvs, deps, outputs, etc.)\n"
	@printf "  make format       Format Python code with ruff\n"
	@printf "  make lint         Run ruff check\n"
	@printf "  make ty           Run type checking with Ty\n"
	@printf "  make test         Run all tests with pytest (excludes tests/eval/)\n"
	@printf "  make test-eval    Run evaluation tests under .venv_eval\n"
	@printf "  make coverage     Run tests with coverage report (HTML in htmlcov/)\n"

setup:
	@export PATH="$$HOME/.local/bin:$$PATH"; \
	echo "Checking for uv..."; \
	command -v uv >/dev/null 2>&1 || { echo "Installing uv..."; curl -kLsSf https://astral.sh/uv/install.sh | sh; }; \
	uv python install 3.12.3; \
	echo "Building core environment (.venv_core)..."; \
	if [ ! -x .venv_core/bin/python ]; then rm -rf .venv_core; uv venv .venv_core --python 3.12.3; fi; \
	uv pip install -r backend/requirements_core.txt --python .venv_core/bin/python; \
	echo "Building evaluation environment (.venv_eval)..."; \
	if [ ! -x .venv_eval/bin/python ]; then rm -rf .venv_eval; uv venv .venv_eval --python 3.12.3; fi; \
	uv pip install -r backend/requirements_evaluation.txt --python .venv_eval/bin/python
	@echo "Installing frontend dependencies..."
	@$(call frontend_env,cd $(FRONTEND_DIR) && if [ -f package-lock.json ]; then npm ci; else npm install; fi)
	@echo "Creating configuration files..."
	$(CORE_PYTHON) -m backend.src.sessions.configs bootstrap
	@echo "Setup complete."

config:
	$(CORE_PYTHON) -m backend.src.sessions.configs bootstrap

clean-config:
	$(CORE_PYTHON) -m backend.src.sessions.configs clean

cli:
	$(CORE_PYTHON) -m backend.src.cli

inspect:
	$(call set_mode,i)
	$(CORE_PYTHON) -m backend.src.cli --mode i

train:
	$(call set_mode,t)
	$(CORE_PYTHON) -m backend.src.cli --mode t

simulate:
	$(call set_mode,s)
	$(CORE_PYTHON) -m backend.src.cli --mode s

eval:
	$(EVAL_PYTHON) -m backend.src.domain.evaluation

pipeline:
	$(CORE_PYTHON) -m backend.src.domain.pipeline --config $(CONFIG)

format:
	cd backend && $(RUFF) format .

lint:
	cd backend && $(RUFF) check .

ty:
	cd backend && $(TY) check .

test:
	$(CORE_PYTHON) -m pytest tests/ --ignore=tests/eval

test-eval:
	$(EVAL_PYTHON) -m pytest tests/eval/

coverage:
	rm -f .coverage
	$(CORE_PYTHON) -m pytest tests/ --ignore=tests/eval \
		--cov=backend/src --cov-report= --cov-append
	$(EVAL_PYTHON) -m pytest tests/eval/ \
		--cov=backend/src --cov-report=term-missing \
		--cov-report=html:htmlcov --cov-append
	@echo "HTML report: htmlcov/index.html"

inspections:
	$(CORE_PYTHON) -m backend.src.runs.catalog.inspections --format table

models:
	$(CORE_PYTHON) -m backend.src.runs.catalog.models --format table

simulations:
	$(CORE_PYTHON) -m backend.src.runs.catalog.simulations --format table

evaluations:
	$(CORE_PYTHON) -m backend.src.runs.catalog.evaluations --format table

pipelines:
	$(CORE_PYTHON) -m backend.src.runs.catalog.pipelines --format table

api:
	$(CORE_PYTHON) -m uvicorn backend.src.api.main:app --reload --host $(API_HOST) --port $(API_PORT)

frontend:
	@$(call frontend_env,cd $(FRONTEND_DIR) && if [ ! -d node_modules ]; then echo "node_modules not found; installing frontend dependencies..."; if [ -f package-lock.json ]; then npm ci; else npm install; fi; fi && NEXT_PUBLIC_API_URL=/api API_PROXY_TARGET=http://localhost:$(API_PORT) NEXT_PUBLIC_ALLOW_SERVER_FILES=true npm run dev -- --port $(FRONTEND_PORT) $(NEXT_DEV_FLAGS))

local:
	@$(CORE_PYTHON) -m uvicorn backend.src.api.main:app --reload --host $(API_HOST) --port $(API_PORT) & API_PID=$$!; trap 'kill $$API_PID' EXIT INT TERM; $(call frontend_env,cd $(FRONTEND_DIR) && if [ ! -d node_modules ]; then echo "node_modules not found; installing frontend dependencies..."; if [ -f package-lock.json ]; then npm ci; else npm install; fi; fi && NEXT_PUBLIC_API_URL=/api API_PROXY_TARGET=http://localhost:$(API_PORT) NEXT_PUBLIC_ALLOW_SERVER_FILES=true npm run dev -- --port $(FRONTEND_PORT) $(NEXT_DEV_FLAGS))

compose:
	$(DOCKER_COMPOSE) up --build

compose-api:
	$(DOCKER_COMPOSE) up --build -d backend
	@echo "Backend API running at http://localhost:$(API_PORT)/docs"

compose-cli:
	$(DOCKER_COMPOSE) up --build -d backend
	$(DOCKER_COMPOSE) exec backend python -m backend.src.cli

compose-prod:
	$(DOCKER_COMPOSE) -f compose.yaml up --build

compose-stop:
	$(DOCKER_COMPOSE) down

clean:
	$(CORE_PYTHON) -m backend.src.runs.catalog.cleanup
	find . -type d -name '__pycache__' -prune -exec rm -rf {} +
	rm -rf .ruff_cache .pytest_cache backend/.ruff_cache backend/.pytest_cache

DIST_NAME := $(shell basename $(CURDIR))_clean
DIST_PATH := ../$(DIST_NAME)

copy-repo:
	@echo "📦 Creating clean copy in $(DIST_PATH)..."
	@rm -rf $(DIST_PATH)
	@mkdir -p $(DIST_PATH)
	@git archive HEAD | tar -x -C $(DIST_PATH)
	@mkdir -p $(DIST_PATH)/backend/data/uploads
	@echo "📄 Copying selected data files..."
	@cp backend/data/uploads/person.csv $(DIST_PATH)/backend/data/uploads/ 2>/dev/null || echo "⚠️ Warning: person.csv not found"
	@cp backend/data/uploads/condition_occurrence.csv $(DIST_PATH)/backend/data/uploads/ 2>/dev/null || echo "⚠️ Warning: condition_occurrence.csv not found"
	@cp backend/data/uploads/visit_occurrence.csv $(DIST_PATH)/backend/data/uploads/ 2>/dev/null || echo "⚠️ Warning: visit_occurrence.csv not found"
	@cp backend/data/uploads/dataset_prueba_tecnica_v2.csv $(DIST_PATH)/backend/data/uploads/ 2>/dev/null || echo "⚠️ Warning: prueba tecnica dataset not found"
	@echo "✅ Done. Clean copy created at: $(DIST_PATH)"

