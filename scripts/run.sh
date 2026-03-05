#!/bin/bash

# 1. HANDLE INTERACTIVE MODE (No arguments provided)
if [ -z "$1" ]; then
    echo "-------------------------------------------------------------------------"
    echo "--- Starting Tool in Train/Simulation Mode with Interactive Assistant ---"
    echo "-------------------------------------------------------------------------"
    echo "(if you want a specific mode specify 'train', 'sim' or 'eval' as the first argument)"
    # Check if env exists
    if [ ! -f ".venv_core/bin/activate" ]; then
        echo "❌ Error: Environment .venv_core not found. Run ./scripts/setup.sh first."
        exit 1
    fi
    source .venv_core/bin/activate
    python -m src.main
    exit 0
fi

# Capture the command
CMD="$1"
shift

# 2. HANDLE SCRIPT MODES
if [ "$CMD" == "train" ]; then
    source .venv_core/bin/activate
    echo "--- Running train mode ---"
    # Map 'train' command to '--mode train' flag + remaining args
    python -m src.main --mode t "$@"

elif [ "$CMD" == "sim" ]; then
    source .venv_core/bin/activate
    echo "--- Running simulation mode ---"
    # Map 'sim' command to '--mode simulation' flag + remaining args
    python -m src.main --mode s "$@"

elif [ "$CMD" == "eval" ]; then
    source .venv_eval/bin/activate
    echo "--- Running evaluation mode ---"
    # Eval usually doesn't need the mapped mode flag, just pass args through
    python -m src.eval "$@"

else
    echo "Usage: $0 {train|sim|eval}"
    echo "Or run without arguments for the Interactive Assistant."
    exit 1
fi
