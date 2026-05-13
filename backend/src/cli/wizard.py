"""Interactive terminal wizard for common backend workflows."""

from __future__ import annotations

import shlex

from backend.src.cli._aliases import (
    _BACK_ALIASES,
    _EVALUATE_ALIASES,
    _EXECUTE_ALIASES,
    _HELP_ALIASES,
    _MODE_ALIASES,
    _QUIT_ALIASES,
    _RESULTS_ALIASES,
    INTERACTIVE_EXIT,
)
from backend.src.cli.catalog import _print_catalog, _select_catalog
from backend.src.cli.config_editor import config_menu, maybe_review_configs
from backend.src.cli.detail_views import inspect_catalog_item
from backend.src.cli.pipeline_wizard import pipeline_menu


def print_session_banner() -> None:
    """Print the interactive CLI session header once."""
    print("\n" + "=" * 48)
    print("  Herramienta de Datos Sinteticos ENDS")
    print("=" * 48)
    print("Estas dentro de la CLI interactiva.")
    print("Escribe 'ayuda' para ver comandos, o 'salir' para terminar.\n")


def print_session_help() -> None:
    """Print available commands for the persistent CLI session."""
    print("Comandos:")
    print("  ejecutar     Abrir el menu de ejecucion")
    print("  resultados   Ver ejecuciones y resultados anteriores")
    print("  configurar   Editar reglas, entrenamiento, simulacion y evaluacion")
    print("  pipelines    Disenar y ejecutar pipelines automatizadas")
    print("  ayuda        Mostrar esta ayuda")
    print("  salir        Salir de la CLI")
    print("\nDentro de un submenu puedes usar 'volver'.")
    print("Tambien puedes pegar flags directamente, por ejemplo:")
    print("  --mode s --model-id MODELO --sample-size 1000")
    print("O usar un atajo de flujo:")
    print("  simulate --model-id MODELO --sample-size 1000")


# ── menus ────────────────────────────────────────────────────────────────────


def _print_main_menu() -> None:
    print("\nQue quieres hacer?")
    print("  1. ejecutar      Iniciar una inspeccion, entrenamiento o simulacion")
    print("  2. resultados    Ver ejecuciones y resultados anteriores")
    print("  3. configurar    Editar reglas, entrenamiento, simulacion y evaluacion")
    print("  4. pipelines     Disenar y ejecutar pipelines automatizadas")
    print("  q. salir")


def _print_workflow_menu() -> None:
    print("\nQue quieres ejecutar?")
    print("  1. inspeccionar   Detectar esquema desde CSV/Parquet")
    print("  2. entrenar       Entrenar un generador Mostly AI")
    print("  3. simular        Generar datos sinteticos")
    print("  4. evaluar        Ver como lanzar evaluacion de una simulacion")
    print("  b. volver")
    print("  q. salir")


def _print_results_menu() -> None:
    print("\nQue quieres consultar?")
    print("  1. inspecciones")
    print("  2. modelos")
    print("  3. simulaciones")
    print("  4. evaluaciones")
    print("  5. pipelines")
    print("  b. volver")
    print("  q. salir")


# ── inline command parser ────────────────────────────────────────────────────


def _parse_inline_command(command: str) -> list[str] | None:
    """Translate direct interactive input into normal CLI args when possible."""
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        print(f"No se pudo interpretar el comando: {exc}")
        return None

    if not parts:
        return None

    if parts[0].startswith("-"):
        return parts

    mode = _MODE_ALIASES.get(parts[0].lower())
    if mode and len(parts) > 1:
        return ["--mode", mode, *parts[1:]]

    return None


# ── data-file selector ───────────────────────────────────────────────────────


def _select_data_files() -> list[str]:
    from backend.src.sessions.files import list_data_files

    files = list_data_files()
    if not files:
        print("\nNo se encontraron archivos de datos en el directorio por defecto.")
        return []

    print("\nArchivos de datos disponibles:")
    for idx, file in enumerate(files, 1):
        print(f"  [{idx}] {file.name} ({file.size_bytes} bytes)")

    while True:
        selection = (
            input(
                "\nIntroduce los numeros de los archivos "
                "(separados por espacios) o 'q' para cancelar: "
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
            print(f"Seleccion no valida. Introduce numeros entre 1 y {len(files)}.")
        except ValueError:
            print("Entrada no valida. Introduce numeros validos separados por espacios.")


# ── workflow arg builders ────────────────────────────────────────────────────


def _workflow_args_for_choice(choice: str) -> list[str] | None:
    mode = _MODE_ALIASES.get(choice)

    if mode == "i":
        files = _select_data_files()
        if not files:
            return None
        maybe_review_configs("i")
        return ["--mode", "i", "--files", *files]

    if mode == "t":
        inspection_id = _select_catalog("inspections", allow_empty=True)
        if inspection_id == "CANCEL":
            return None
        if inspection_id:
            try:
                review = (
                    input("\n¿Quieres revisar o editar el esquema antes de entrenar? [s/N]: ")
                    .strip()
                    .lower()
                )
            except (EOFError, KeyboardInterrupt):
                review = ""
            if review in ("s", "si", "y", "yes"):
                from backend.src.runs.catalog.inspections import list_available_inspections

                insp_item = next(
                    (
                        i
                        for i in list_available_inspections()
                        if i.get("inspection_id") == inspection_id
                    ),
                    None,
                )
                if insp_item:
                    inspect_catalog_item("inspections", insp_item)
                else:
                    print("  No se encontro la inspeccion seleccionada.")
            maybe_review_configs("t")
            return ["--mode", "t", "--inspection-id", inspection_id]

        files = _select_data_files()
        if not files:
            return None
        maybe_review_configs("t")
        return ["--mode", "t", "--files", *files]

    if mode == "s":
        model_id = _select_catalog("models")
        if not model_id or model_id == "CANCEL":
            return None
        while True:
            size = input("\nIntroduce el tamano de muestra (por defecto 1000): ").strip() or "1000"
            if size.isdigit() and int(size) > 0:
                break
            print("El tamano de muestra debe ser un entero positivo.")
        maybe_review_configs("s")
        return ["--mode", "s", "--model-id", model_id, "--sample-size", size]

    if choice in _EVALUATE_ALIASES:
        simulation_id = _select_catalog("simulations")
        if not simulation_id or simulation_id == "CANCEL":
            return None
        print(f"\nEjecuta: make eval SIMULATION_ID={simulation_id}")
        return None

    print("Opcion no reconocida. Escribe 'volver' para regresar o 'salir' para terminar.")
    return None


# ── sub-menu loops ───────────────────────────────────────────────────────────


def _prompt_execution_menu() -> list[str] | str | None:
    while True:
        _print_workflow_menu()

        try:
            raw_choice = input("\nends/ejecutar> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return INTERACTIVE_EXIT

        choice = raw_choice.lower()
        if not choice or choice in _BACK_ALIASES:
            return None
        if choice in _QUIT_ALIASES:
            return INTERACTIVE_EXIT
        if choice in _HELP_ALIASES:
            continue

        inline_args = _parse_inline_command(raw_choice)
        if inline_args:
            return inline_args

        workflow_args = _workflow_args_for_choice(choice)
        if workflow_args:
            return workflow_args


_CATALOG_BY_CHOICE: dict[str, str] = {
    "1": "inspections",
    "inspecciones": "inspections",
    "i": "inspections",
    "2": "models",
    "modelos": "models",
    "m": "models",
    "3": "simulations",
    "simulaciones": "simulations",
    "s": "simulations",
    "4": "evaluations",
    "evaluaciones": "evaluations",
    "e": "evaluations",
    "5": "pipelines",
    "p": "pipelines",
}


def _prompt_results_menu() -> str | None:
    while True:
        _print_results_menu()

        try:
            raw_choice = input("\nends/resultados> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return INTERACTIVE_EXIT

        choice = raw_choice.lower()
        if not choice or choice in _BACK_ALIASES:
            return None
        if choice in _QUIT_ALIASES:
            return INTERACTIVE_EXIT
        if choice in _HELP_ALIASES:
            continue

        catalog_type = _CATALOG_BY_CHOICE.get(choice)
        if not catalog_type:
            print("Opcion no reconocida. Escribe 'volver' para regresar o 'salir' para terminar.")
            continue

        items = _print_catalog(catalog_type)
        if not items:
            continue

        while True:
            try:
                sel = (
                    input("\n  Introduce un numero para ver detalles, o 'volver': ").strip().lower()
                )
            except (EOFError, KeyboardInterrupt):
                print()
                return INTERACTIVE_EXIT
            if not sel or sel in _BACK_ALIASES:
                break
            if sel in _QUIT_ALIASES:
                return INTERACTIVE_EXIT
            try:
                sel_idx = int(sel) - 1
                if 0 <= sel_idx < len(items):
                    inspect_catalog_item(catalog_type, items[sel_idx])
                    items = _print_catalog(catalog_type)
                    if not items:
                        break
                else:
                    print(f"  Numero fuera de rango (1-{len(items)}).")
            except ValueError:
                print("  Introduce un numero o 'volver'.")


# ── main entry points ────────────────────────────────────────────────────────


def prompt_for_workflow() -> list[str] | str | None:
    """Prompt for one workflow in an already-open interactive session."""
    _print_main_menu()

    try:
        raw_choice = input("\nends> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return INTERACTIVE_EXIT

    choice = raw_choice.lower()
    if not choice:
        print_session_help()
        return None
    if choice in _QUIT_ALIASES:
        return INTERACTIVE_EXIT
    if choice in _HELP_ALIASES:
        print_session_help()
        return None

    inline_args = _parse_inline_command(raw_choice)
    if inline_args:
        return inline_args

    if choice in _EXECUTE_ALIASES:
        return _prompt_execution_menu()
    if choice in _RESULTS_ALIASES:
        return _prompt_results_menu()
    if choice in ("3", "configurar", "config", "settings", "ajustes"):
        config_menu()
        return None
    if choice in ("4", "pipelines", "pipeline", "pipe"):
        pipeline_menu()
        return None

    mode = _MODE_ALIASES.get(choice)
    if mode or choice in _EVALUATE_ALIASES:
        return _workflow_args_for_choice(choice)

    print("Comando no reconocido. Escribe 'ayuda' para ver opciones.")
    return None


def run_interactive_wizard() -> list[str] | None:
    """Collect a common workflow from the user and return equivalent CLI args."""
    print_session_banner()
    result = prompt_for_workflow()
    return None if result == INTERACTIVE_EXIT else result
