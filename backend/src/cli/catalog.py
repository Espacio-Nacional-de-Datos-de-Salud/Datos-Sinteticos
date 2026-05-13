"""Catalog registry, loading, listing, and selection helpers."""

from __future__ import annotations

_CATALOGS: dict[str, dict[str, str]] = {
    "inspections": {
        "label": "inspecciones",
        "id_key": "inspection_id",
        "name_key": "inspection_name",
    },
    "models": {
        "label": "modelos",
        "id_key": "model_id",
        "name_key": "model_name",
    },
    "simulations": {
        "label": "simulaciones",
        "id_key": "simulation_id",
        "name_key": "simulation_name",
    },
    "evaluations": {
        "label": "evaluaciones",
        "id_key": "evaluation_id",
        "name_key": "evaluation_name",
    },
    "pipelines": {
        "label": "pipelines",
        "id_key": "pipeline_id",
        "name_key": "pipeline_id",
    },
}


def _load_catalog(catalog_type: str) -> list[dict]:
    items: list[dict] = []
    try:
        if catalog_type == "inspections":
            from backend.src.runs.catalog.inspections import list_available_inspections

            items = list_available_inspections()
        elif catalog_type == "models":
            from backend.src.runs.catalog.models import list_available_models

            items = list_available_models()
        elif catalog_type == "simulations":
            from backend.src.runs.catalog.simulations import list_available_simulations

            items = list_available_simulations()
        elif catalog_type == "evaluations":
            from backend.src.runs.catalog.evaluations import list_available_evaluations

            items = list_available_evaluations()
        elif catalog_type == "pipelines":
            from backend.src.runs.catalog.pipelines import list_available_pipelines

            items = list_available_pipelines()
    except Exception as exc:
        label = _CATALOGS[catalog_type]["label"]
        print(f"No se pudieron cargar {label}: {exc}")
        return []
    return items


def _print_catalog(catalog_type: str) -> list[dict]:
    """Print a numbered list for *catalog_type* and return the items."""
    catalog = _CATALOGS[catalog_type]
    items = _load_catalog(catalog_type)
    label = catalog["label"]
    id_key = catalog["id_key"]
    name_key = catalog["name_key"]

    if not items:
        print(f"\nNo hay {label}.")
        return []

    print(f"\n{label.capitalize()} disponibles:")
    for idx, item in enumerate(items, 1):
        item_id = item.get(id_key, "")
        name = item.get(name_key) or item_id
        details = [str(item_id)]
        status = item.get("status")
        timestamp = item.get("timestamp")
        if status:
            details.append(f"estado: {status}")
        if timestamp:
            details.append(str(timestamp))
        print(f"  [{idx}] {name} ({' | '.join(details)})")

    return items


def _select_catalog(catalog_type: str, allow_empty: bool = False) -> str:
    """Prompt the user to pick one item from *catalog_type*.

    Returns the selected ID, ``""`` when *allow_empty* and the user skips,
    or ``"CANCEL"`` when the user aborts.
    """
    catalog = _CATALOGS[catalog_type]
    items = _load_catalog(catalog_type)
    id_key = catalog["id_key"]
    name_key = catalog["name_key"]
    label = catalog["label"]

    if not items:
        print(f"\nNo hay {label}.")
        return ""

    print(f"\n{label.capitalize()} disponibles:")
    for idx, item in enumerate(items, 1):
        name = item.get(name_key) or item.get(id_key)
        print(f"  [{idx}] {name} ({item.get(id_key)})")

    empty_prompt = " (deja vacio para omitir)" if allow_empty else ""
    while True:
        selection = (
            input(
                f"\nIntroduce el numero del elemento de {label} a seleccionar"
                f"{empty_prompt} o 'q' para cancelar: "
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
            print(f"Seleccion no valida. Introduce un numero entre 1 y {len(items)}.")
        except ValueError:
            print("Entrada no valida. Introduce un numero valido.")
