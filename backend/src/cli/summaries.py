"""Terminal summaries for completed backend runs."""

from __future__ import annotations


def print_run_summary(mode: str, result_id: str, output_dir: str) -> None:
    """Print a prominent summary of the run results."""
    mode_map = {"i": "INSPECTION", "t": "TRAINING", "s": "SIMULATION"}
    mode_name = mode_map.get(mode, mode.upper())

    print("\n" + "╔" + "═" * 78 + "╗")
    print(f"║ {mode_name} COMPLETE".center(78) + " ║")
    print("╠" + "═" * 78 + "╣")
    print(f"║  ID:         {result_id}".ljust(78) + " ║")
    print(f"║  Location:   {output_dir}".ljust(78) + " ║")
    if mode == "i":
        print(f"║  Next Step:  make train INSPECTION_ID={result_id}".ljust(78) + " ║")
    elif mode == "t":
        print(
            f"║  Next Step:  make simulate MODEL_ID={result_id} SAMPLE_SIZE=1000".ljust(78)
            + " ║"
        )
    elif mode == "s":
        print(f"║  Next Step:  make eval SIMULATION_ID={result_id}".ljust(78) + " ║")
    print("╚" + "═" * 78 + "╝\n")
