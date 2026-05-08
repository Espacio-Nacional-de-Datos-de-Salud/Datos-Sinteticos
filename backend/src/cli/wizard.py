"""Interactive terminal wizard for common backend workflows."""

from __future__ import annotations


def _select_data_files() -> list[str]:
    from backend.src.services.files import list_data_files

    files = list_data_files()
    if not files:
        print("\nNo data files found in default directory.")
        return []

    print("\nAvailable data files:")
    for idx, file in enumerate(files, 1):
        print(f"  [{idx}] {file.name} ({file.size_bytes} bytes)")

    while True:
        selection = (
            input(
                "\nEnter the numbers of the files to select "
                "(separated by space) or 'q' to cancel: "
            )
            .strip()
            .lower()
        )
        if selection == "q":
            return []

        try:
            indices = [int(item) - 1 for item in selection.split()]
            if all(0 <= index < len(files) for index in indices) and indices:
                return [files[index].path for index in indices]
            print(f"Invalid selection. Please enter numbers between 1 and {len(files)}.")
        except ValueError:
            print("Invalid input. Please enter valid numbers separated by space.")


def _select_catalog(catalog_type: str, allow_empty: bool = False) -> str:
    items = []
    id_key = ""
    name_key = ""
    try:
        if catalog_type == "inspections":
            from backend.src.core.catalog.inspections import list_available_inspections

            items = list_available_inspections()
            id_key = "inspection_id"
            name_key = "inspection_name"
        elif catalog_type == "models":
            from backend.src.core.catalog.models import list_available_models

            items = list_available_models()
            id_key = "model_id"
            name_key = "model_name"
        elif catalog_type == "simulations":
            from backend.src.core.catalog.simulations import list_available_simulations

            items = list_available_simulations()
            id_key = "simulation_id"
            name_key = "simulation_name"
    except Exception as exc:
        print(f"Could not load {catalog_type}: {exc}")
        return ""

    if not items:
        print(f"\nNo {catalog_type} found.")
        return ""

    print(f"\nAvailable {catalog_type}:")
    for idx, item in enumerate(items, 1):
        name = item.get(name_key) or item.get(id_key)
        print(f"  [{idx}] {name} ({item.get(id_key)})")

    empty_prompt = " (leave empty to skip)" if allow_empty else ""
    while True:
        selection = (
            input(
                f"\nEnter the number of the {catalog_type[:-1]} to select"
                f"{empty_prompt} or 'q' to cancel: "
            )
            .strip()
            .lower()
        )

        if selection == "q":
            return "CANCEL"

        if not selection and allow_empty:
            return ""

        try:
            idx = int(selection) - 1
            if 0 <= idx < len(items):
                return items[idx][id_key]
            print(f"Invalid selection. Please enter a number between 1 and {len(items)}.")
        except ValueError:
            print("Invalid input. Please enter a valid number.")


def run_interactive_wizard() -> list[str] | None:
    """Collect a common workflow from the user and return equivalent CLI args."""
    print("\n" + "=" * 40)
    print("  ENDS Synthetic Data Tool CLI  ")
    print("=" * 40)
    print("1. [i] Inspect Data (Autodetect schema from CSV/Parquet)")
    print("2. [t] Train Model (Mostly AI engine)")
    print("3. [s] Simulate (Generate synthetic data)")
    print("4. [e] Evaluate (Compare results)")
    print("q. Quit")

    try:
        choice = input("\nSelect an option (1-4, q): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return None

    if choice in ("1", "i"):
        files = _select_data_files()
        if not files:
            return None
        return ["--mode", "i", "--files", *files]

    if choice in ("2", "t"):
        inspection_id = _select_catalog("inspections", allow_empty=True)
        if inspection_id == "CANCEL":
            return None
        if inspection_id:
            return ["--mode", "t", "--inspection-id", inspection_id]

        files = _select_data_files()
        if not files:
            return None
        return ["--mode", "t", "--files", *files]

    if choice in ("3", "s"):
        model_id = _select_catalog("models")
        if not model_id or model_id == "CANCEL":
            return None
        size = input("\nEnter sample size (default 1000): ").strip() or "1000"
        return ["--mode", "s", "--model-id", model_id, "--sample-size", size]

    if choice in ("4", "e"):
        simulation_id = _select_catalog("simulations")
        if not simulation_id or simulation_id == "CANCEL":
            return None
        print(f"\nRun: make eval SIMULATION_ID={simulation_id}")
        return None

    return None
