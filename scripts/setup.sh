#!/bin/bash
# Install uv if missing
echo "🔍 Checking for uv (faster package installer for python [pip])..."
command -v uv >/dev/null 2>&1 || { echo "Installing uv..."; curl -kLsSf https://astral.sh/uv/install.sh | sh; source $HOME/.local/bin/env; }

echo "🐍 Installing Python 3.12.3..."
uv python install 3.12.3

echo "📦 Building Core Environment (.venv_core)..."
uv venv .venv_core --python 3.12.3
uv pip install -r requirements_core.txt --python .venv_core/bin/python

echo "📊 Building Evaluation Environment (.venv_eval)..."
uv venv .venv_eval --python 3.12.3
uv pip install -r requirements_evaluation.txt --python .venv_eval/bin/python

echo "✅ Setup complete!"
