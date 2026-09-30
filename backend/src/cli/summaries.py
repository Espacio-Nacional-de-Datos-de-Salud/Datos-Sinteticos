"""Terminal summaries for completed backend runs."""

from __future__ import annotations


def print_run_summary(mode: str, result_id: str, output_dir: str) -> None:
    """Print a prominent summary of the run results."""
    mode_map = {"i": "CARGA DE DATOS", "t": "ENTRENAMIENTO", "s": "GENERACION"}
    mode_name = mode_map.get(mode, mode.upper())

    print("\n" + "╔" + "═" * 78 + "╗")
    print(f"║ {mode_name} COMPLETADA".center(78) + " ║")
    print("╠" + "═" * 78 + "╣")
    print(f"║  ID:         {result_id}".ljust(78) + " ║")
    print(f"║  Ubicacion:  {output_dir}".ljust(78) + " ║")
    if mode == "i":
        print(f"║  Siguiente:  make train INSPECTION_ID={result_id}".ljust(78) + " ║")
    elif mode == "t":
        print(
            f"║  Siguiente:  make simulate MODEL_ID={result_id} SAMPLE_SIZE=1000".ljust(78) + " ║"
        )
    elif mode == "s":
        print(f"║  Siguiente:  make eval SIMULATION_ID={result_id}".ljust(78) + " ║")
    print("╚" + "═" * 78 + "╝\n")
