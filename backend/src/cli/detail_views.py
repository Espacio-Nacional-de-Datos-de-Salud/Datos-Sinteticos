"""Detail-panel printers for each catalog type."""

from __future__ import annotations

import os

from backend.src.cli._aliases import _BACK_ALIASES, _QUIT_ALIASES
from backend.src.cli.inspection_editor import (
    _edit_encoding_types,
    _edit_relationships,
    _load_inspection_metadata_for,
    _shorten_type,
)


def _print_inspection_detail(item: dict) -> None:
    inspection_id = item.get("inspection_id", "")
    name = item.get("inspection_name") or inspection_id
    status = item.get("status", "?")
    timestamp = item.get("timestamp", "")
    tables = item.get("tables", {})
    file_paths = item.get("file_paths", [])
    folder = item.get("folder", "")

    print("\n" + "─" * 64)
    print(f"  CARGA DE DATOS: {name}")
    print(f"  ID:     {inspection_id}")
    print(f"  Estado: {status}    Fecha: {timestamp}")
    print("─" * 64)

    if file_paths:
        print("  Archivos de origen:")
        for p in file_paths:
            print(f"    • {os.path.basename(p)}")

    if tables and isinstance(tables, dict):
        print("  Tablas:")
        for tname, rows in tables.items():
            print(f"    • {tname} ({rows} filas)")

    meta = _load_inspection_metadata_for(folder)
    if meta:
        rels = meta.get("relationships", {})
        pks = rels.get("pks", {})
        fks = rels.get("fks", [])
        enc = meta.get("encoding_types", {})

        if pks:
            print("  Claves Primarias:")
            for t, col in pks.items():
                print(f"    • {t} → {col}")

        if fks:
            print("  Claves Foraneas:")
            for fk in fks:
                ctx = " [ctx]" if fk.get("is_context") else ""
                print(
                    f"    • {fk.get('child')}.{fk.get('fk_column')}"
                    f" → {fk.get('parent')}.{fk.get('pk_column')}{ctx}"
                )
        elif pks:
            print("  (sin claves foraneas detectadas)")

        if enc:
            total_cols = sum(len(cols) for cols in enc.values())
            print(f"  Tipos de codificacion: {total_cols} columna(s) en {len(enc)} tabla(s)")
            for tname, cols in enc.items():
                pairs = "  ".join(f"{c}:{_shorten_type(t)}" for c, t in cols.items())
                print(f"    [{tname}] {pairs}")
    else:
        print("  (metadatos de esquema no disponibles)")

    print("─" * 64)


def _print_model_detail(item: dict) -> None:
    model_id = item.get("model_id", "")
    name = item.get("model_name") or model_id
    status = item.get("status", "?")
    timestamp = item.get("timestamp", "")
    tables = item.get("tables", "")
    train_size = item.get("train_size")
    accuracy = item.get("accuracy")
    inspection_id = item.get("inspection_id")
    training_table_sizes = item.get("training_table_sizes", {})

    print("\n" + "─" * 64)
    print(f"  MODELO: {name}")
    print(f"  ID:     {model_id}")
    print(f"  Estado: {status}    Fecha: {timestamp}")
    if inspection_id:
        print(f"  Carga de datos origen: {inspection_id}")
    print("─" * 64)

    if accuracy is not None:
        print(f"  Precision global: {accuracy:.1%}")

    if training_table_sizes:
        print("  Tablas entrenadas:")
        for tname, rows in training_table_sizes.items():
            print(f"    • {tname}: {rows:,} filas")
    elif tables:
        print(f"  Tablas: {tables}")

    if train_size is not None:
        print(f"  Total filas entrenadas: {train_size:,}")

    print("─" * 64)


def _print_simulation_detail(item: dict) -> None:
    simulation_id = item.get("simulation_id", "")
    name = item.get("simulation_name") or simulation_id
    status = item.get("status", "?")
    timestamp = item.get("timestamp", "")
    model_id = item.get("model_id")
    sample_size = item.get("sample_size")
    tables = item.get("tables", "")
    accuracy = item.get("model_accuracy")
    folder = item.get("folder", "")

    print("\n" + "─" * 64)
    print(f"  GENERACION: {name}")
    print(f"  ID:     {simulation_id}")
    print(f"  Estado: {status}    Fecha: {timestamp}")
    if model_id:
        print(f"  Modelo: {model_id}")
    print("─" * 64)

    if sample_size is not None:
        print(f"  Filas solicitadas (sample_size): {sample_size:,}")
    if accuracy is not None:
        print(f"  Precision del modelo: {accuracy:.1%}")
    if tables:
        print(f"  Tablas sinteticas: {tables}")

    synthetic_dir = os.path.join(folder, "synthetic_data")
    if os.path.isdir(synthetic_dir):
        files = sorted(os.listdir(synthetic_dir))
        if files:
            print("  Archivos generados:")
            for fname in files:
                full = os.path.join(synthetic_dir, fname)
                try:
                    size = os.path.getsize(full)
                    print(f"    • {fname} ({size:,} bytes)")
                except OSError:
                    print(f"    • {fname}")

    print("─" * 64)


def _print_evaluation_detail(item: dict) -> None:
    evaluation_id = item.get("evaluation_id", "")
    name = item.get("evaluation_name") or evaluation_id
    status = item.get("status", "?")
    timestamp = item.get("timestamp", "")
    simulation_id = item.get("simulation_id")
    model_id = item.get("model_id")
    metrics = item.get("metrics_evaluated", [])
    folder = item.get("folder", "")

    print("\n" + "─" * 64)
    print(f"  AUDITORIA: {name}")
    print(f"  ID:     {evaluation_id}")
    print(f"  Estado: {status}    Fecha: {timestamp}")
    if simulation_id:
        print(f"  Generacion: {simulation_id}")
    if model_id:
        print(f"  Modelo:     {model_id}")
    print("─" * 64)

    if metrics:
        print(f"  Metricas evaluadas: {', '.join(metrics)}")

    if os.path.isdir(folder):
        reports = [
            f for f in os.listdir(folder) if f.endswith(".html") or f.endswith("metrics.json")
        ]
        if reports:
            print("  Reportes:")
            for rep in sorted(reports):
                print(f"    • {os.path.join(folder, rep)}")

    print("─" * 64)


def inspect_catalog_item(catalog_type: str, item: dict) -> None:
    """Show full detail for a catalog item; offer edit actions for inspections."""
    if catalog_type == "inspections":
        _print_inspection_detail(item)
        folder = item.get("folder", "")
        inspection_id = item.get("inspection_id", "")
        while True:
            print("  Acciones:")
            print("    e. Editar tipos de codificacion")
            print("    r. Editar relaciones (PKs/FKs)")
            print("    d. eliminar  Borrar carga de datos")
            print("    volver")
            try:
                raw = input("\n  carga> ").strip().lower()
            except EOFError:
                print()
                return
            if not raw or raw in _BACK_ALIASES or raw in _QUIT_ALIASES:
                return
            if raw in ("e", "tipos", "encoding", "t"):
                meta = _load_inspection_metadata_for(folder)
                if meta:
                    _edit_encoding_types(folder, meta)
                    _print_inspection_detail(item)
                else:
                    print("  No se pudo cargar inspection_metadata.json.")
            elif raw in ("r", "relaciones", "rels"):
                meta = _load_inspection_metadata_for(folder)
                if meta:
                    _edit_relationships(folder, meta)
                    _print_inspection_detail(item)
                else:
                    print("  No se pudo cargar inspection_metadata.json.")
            elif raw in ("d", "eliminar", "borrar"):
                _delete_inspection_interactive(inspection_id)
                return
            else:
                print("  Opcion no reconocida. Usa 'e', 'r', 'd' o 'volver'.")

    elif catalog_type == "models":
        _print_model_detail(item)
        model_id = item.get("model_id", "")
        while True:
            print("  Acciones:")
            print("    d. eliminar  Borrar modelo y sus generaciones vinculadas")
            print("    volver")
            try:
                raw = input("\n  modelo> ").strip().lower()
            except EOFError:
                print()
                return
            if not raw or raw in _BACK_ALIASES or raw in _QUIT_ALIASES:
                return
            if raw in ("d", "eliminar", "borrar"):
                _delete_model_interactive(model_id)
                return

    elif catalog_type == "simulations":
        _print_simulation_detail(item)
        simulation_id = item.get("simulation_id", "")
        while True:
            print("  Acciones:")
            print("    d. eliminar  Borrar generación y auditorías vinculadas")
            print("    volver")
            try:
                raw = input("\n  generacion> ").strip().lower()
            except EOFError:
                print()
                return
            if not raw or raw in _BACK_ALIASES or raw in _QUIT_ALIASES:
                return
            if raw in ("d", "eliminar", "borrar"):
                _delete_simulation_interactive(simulation_id)
                return

    elif catalog_type == "evaluations":
        _print_evaluation_detail(item)
        evaluation_id = item.get("evaluation_id", "")
        while True:
            print("  Acciones:")
            print("    d. eliminar  Borrar auditoría")
            print("    volver")
            try:
                raw = input("\n  auditoria> ").strip().lower()
            except EOFError:
                print()
                return
            if not raw or raw in _BACK_ALIASES or raw in _QUIT_ALIASES:
                return
            if raw in ("d", "eliminar", "borrar"):
                _delete_evaluation_interactive(evaluation_id)
                return

    else:
        print("  (detalle no disponible para este tipo)")


# ── delete helpers ─────────────────────────────────────────────────────────────


def _confirm_delete(label: str) -> bool:
    try:
        ans = input(f"  ¿Eliminar {label}? [s/N]: ").strip().lower()
    except EOFError:
        return False
    return ans in ("s", "si", "y", "yes")


def _delete_inspection_interactive(inspection_id: str) -> None:
    from backend.src.runs.catalog.inspections import delete_inspection

    if not _confirm_delete(inspection_id):
        print("  Cancelado.")
        return
    outcome = delete_inspection(inspection_id)
    if outcome.status == "not_found":
        print("  Carga de datos no encontrada.")
    elif outcome.status == "has_linked_models":
        linked = ", ".join(outcome.linked_model_ids)
        print(f"  No se puede eliminar: tiene modelos vinculados ({linked}).")
        print("  Elimina primero esos modelos.")
    else:
        print(f"  Eliminada: {inspection_id}")


def _delete_model_interactive(model_id: str) -> None:
    from backend.src.runs.catalog.models import delete_model

    if not _confirm_delete(model_id):
        print("  Cancelado.")
        return
    outcome = delete_model(model_id)
    if outcome.status == "not_found":
        print("  Modelo no encontrado.")
    elif outcome.status == "has_linked_simulations":
        linked = ", ".join(outcome.linked_simulation_ids)
        print(f"  No se puede eliminar: tiene generaciones vinculadas ({linked}).")
        print("  Elimina primero esas generaciones.")
    else:
        print(f"  Eliminado: {model_id}")


def _delete_simulation_interactive(simulation_id: str) -> None:
    from backend.src.runs.catalog.simulations import delete_simulation

    if not _confirm_delete(simulation_id):
        print("  Cancelado.")
        return
    outcome = delete_simulation(simulation_id)
    if outcome.status == "not_found":
        print("  Generación no encontrada.")
    elif outcome.status == "has_linked_evaluations":
        linked = ", ".join(outcome.linked_evaluation_ids)
        print(f"  No se puede eliminar: tiene auditorías vinculadas ({linked}).")
        print("  Elimina primero esas auditorías.")
    else:
        print(f"  Eliminada: {simulation_id}")


def _delete_evaluation_interactive(evaluation_id: str) -> None:
    from backend.src.runs.catalog.evaluations import delete_evaluation

    if not _confirm_delete(evaluation_id):
        print("  Cancelado.")
        return
    if delete_evaluation(evaluation_id):
        print(f"  Eliminada: {evaluation_id}")
    else:
        print("  Auditoría no encontrada.")
