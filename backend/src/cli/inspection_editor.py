"""Interactive inspection schema editors: encoding types and relationships."""

from __future__ import annotations

import json
import os

from backend.src.domain.encoding_types import ModelEncodingType

_ENCODING_TYPES: list[str] = [e.value for e in ModelEncodingType]
_ENCODING_TYPE_MAP: dict[str, str] = {chr(ord("A") + i): t for i, t in enumerate(_ENCODING_TYPES)}


def _load_inspection_metadata_for(folder: str) -> dict | None:
    """Load ``inspection_metadata.json`` from *folder*; returns None on failure."""
    from backend.src.config.general import INSPECTION_METADATA_FILENAME

    path = os.path.join(folder, INSPECTION_METADATA_FILENAME)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        print(f"No se pudo leer inspection_metadata.json: {exc}")
        return None


def _save_inspection_metadata_for(folder: str, data: dict) -> bool:
    """Write *data* to ``inspection_metadata.json`` inside *folder*."""
    from backend.src.config.general import INSPECTION_METADATA_FILENAME

    path = os.path.join(folder, INSPECTION_METADATA_FILENAME)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        return True
    except Exception as exc:
        print(f"Error al guardar inspection_metadata.json: {exc}")
        return False


def _shorten_type(typ: str) -> str:
    return typ.replace("TABULAR_", "").replace("LANGUAGE_", "L:")


def _edit_encoding_types(folder: str, metadata: dict) -> None:
    """Interactively change column encoding types and persist to disk."""
    enc = metadata.get("encoding_types", {})
    if not enc:
        print("\n  No hay tipos de codificacion disponibles.")
        return

    while True:
        column_list: list[tuple[str, str, str]] = []
        print()
        for tname, cols in enc.items():
            print(f"  [{tname}]")
            for col, typ in cols.items():
                idx = len(column_list) + 1
                print(f"    [{idx:3d}] {col:<32} {_shorten_type(typ)}")
                column_list.append((tname, col, typ))

        print()
        print("  Tipos disponibles:")
        letters = list(_ENCODING_TYPE_MAP.keys())
        for i, letter in enumerate(letters):
            short = _shorten_type(_ENCODING_TYPE_MAP[letter])
            end = "\n" if i % 2 == 1 or i == len(letters) - 1 else "   "
            print(f"    {letter}: {short:<28}", end=end)
        print()
        print("  Escribe '<num_col> <letra_tipo>' para cambiar tipo.")
        print("  Ejemplo: '3 B' cambia la columna [3] a TABULAR_CATEGORICAL.")
        print("  'listo' para guardar, 'cancelar' para salir sin guardar.")

        try:
            raw = input("\n  tipos> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        lower = raw.lower()
        if lower in ("cancelar", "cancel", "q"):
            return
        if lower in ("listo", "ok", "done", "guardar", "save"):
            metadata["encoding_types"] = enc
            if _save_inspection_metadata_for(folder, metadata):
                print("  Cambios guardados.")
            return

        parts = raw.split()
        if len(parts) == 2:
            num_str, letter = parts[0], parts[1].upper()
            try:
                num = int(num_str)
                if 1 <= num <= len(column_list):
                    new_type = _ENCODING_TYPE_MAP.get(letter)
                    if new_type:
                        tname, col, old_type = column_list[num - 1]
                        enc[tname][col] = new_type
                        print(
                            f"  {col} ({tname}):"
                            f" {_shorten_type(old_type)} → {_shorten_type(new_type)}"
                        )
                        continue
                    valid_end = chr(ord("A") + len(_ENCODING_TYPES) - 1)
                    print(f"  Letra no reconocida: '{letter}'. Usa A-{valid_end}.")
                else:
                    print(f"  Numero fuera de rango. Introduce entre 1 y {len(column_list)}.")
            except ValueError:
                pass
        print("  Formato no valido. Ejemplo: '3 B'  (numero de columna + letra de tipo)")


def _edit_relationships(folder: str, metadata: dict) -> None:
    """Interactively edit PKs and FKs and persist to disk."""
    rels = metadata.setdefault("relationships", {})
    pks: dict[str, str] = rels.setdefault("pks", {})
    fks: list[dict] = rels.setdefault("fks", [])
    enc = metadata.get("encoding_types", {})
    table_list = list(enc.keys()) if enc else list(pks.keys())

    def columns_for(table: str) -> list[str]:
        return list(enc.get(table, {}).keys())

    while True:
        print()
        print("  Claves Primarias:")
        for i, t in enumerate(table_list, 1):
            pk = pks.get(t, "— sin PK —")
            print(f"    [{i}] {t:<32} → {pk}")

        print()
        print("  Claves Foraneas:")
        if fks:
            for i, fk in enumerate(fks, 1):
                ctx = " [ctx]" if fk.get("is_context") else ""
                print(
                    f"    [{i}] {fk.get('child')}.{fk.get('fk_column')}"
                    f" → {fk.get('parent')}.{fk.get('pk_column')}{ctx}"
                )
        else:
            print("    (sin claves foraneas)")

        print()
        print("  Comandos: pk <num>  |  fk add  |  fk rm <num>  |  listo  |  cancelar")

        try:
            raw = input("\n  relaciones> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        cmd = raw.lower().split()
        if not cmd:
            continue

        if cmd[0] in ("cancelar", "cancel", "q"):
            return

        if cmd[0] in ("listo", "ok", "done", "guardar", "save"):
            rels["pks"] = pks
            rels["fks"] = fks
            metadata["relationships"] = rels
            if _save_inspection_metadata_for(folder, metadata):
                print("  Cambios guardados.")
            return

        if cmd[0] == "pk":
            _handle_pk_edit(cmd, table_list, pks, columns_for)
            continue

        if cmd[0] == "fk":
            _handle_fk_edit(cmd, table_list, fks, columns_for)
            continue

        print("  Comandos validos: pk <num> | fk add | fk rm <num> | listo | cancelar")


def _handle_pk_edit(
    cmd: list[str],
    table_list: list[str],
    pks: dict[str, str],
    columns_for: object,
) -> None:
    if len(cmd) < 2:
        print("  Uso: pk <num_tabla>")
        return
    try:
        t_idx = int(cmd[1]) - 1
    except ValueError:
        print("  Numero no valido.")
        return
    if not (0 <= t_idx < len(table_list)):
        print(f"  Numero de tabla fuera de rango (1-{len(table_list)}).")
        return
    t = table_list[t_idx]
    cols = columns_for(t)  # type: ignore[operator]
    if not cols:
        print(f"  No hay columnas disponibles para '{t}'.")
        return
    print(f"\n  Columnas de '{t}':")
    for j, c in enumerate(cols, 1):
        marker = " ← PK actual" if pks.get(t) == c else ""
        print(f"    [{j}] {c}{marker}")
    print("    [0] — sin PK —")
    try:
        col_raw = input("  Selecciona columna: ").strip()
        if col_raw == "0":
            pks.pop(t, None)
            print(f"  PK eliminada de '{t}'.")
        else:
            c_idx = int(col_raw) - 1
            if 0 <= c_idx < len(cols):
                pks[t] = cols[c_idx]
                print(f"  PK de '{t}' → '{cols[c_idx]}'.")
            else:
                print("  Numero fuera de rango.")
    except (ValueError, EOFError, KeyboardInterrupt):
        print("\n  Operacion cancelada.")


def _handle_fk_edit(
    cmd: list[str],
    table_list: list[str],
    fks: list[dict],
    columns_for: object,
) -> None:
    if len(cmd) < 2:
        print("  Uso: fk add | fk rm <num>")
        return

    if cmd[1] == "rm":
        if len(cmd) < 3:
            print("  Uso: fk rm <num>")
            return
        try:
            fk_idx = int(cmd[2]) - 1
        except ValueError:
            print("  Numero no valido.")
            return
        if 0 <= fk_idx < len(fks):
            removed = fks.pop(fk_idx)
            print(
                f"  FK eliminada: {removed.get('child')}.{removed.get('fk_column')}"
                f" → {removed.get('parent')}.{removed.get('pk_column')}"
            )
        else:
            print(f"  Numero fuera de rango (1-{len(fks)}).")
        return

    if cmd[1] == "add":
        if not table_list:
            print("  No hay tablas disponibles.")
            return
        print("\n  Tablas disponibles:")
        for i, t in enumerate(table_list, 1):
            print(f"    [{i}] {t}")
        try:
            parent_idx = int(input("  Tabla PADRE [num]: ").strip()) - 1
            if not (0 <= parent_idx < len(table_list)):
                print("  Numero fuera de rango.")
                return
            parent = table_list[parent_idx]

            child_idx = int(input("  Tabla HIJA [num]: ").strip()) - 1
            if not (0 <= child_idx < len(table_list)):
                print("  Numero fuera de rango.")
                return
            child = table_list[child_idx]

            parent_cols = columns_for(parent)  # type: ignore[operator]
            if not parent_cols:
                print(f"  No hay columnas para '{parent}'.")
                return
            print(f"\n  Columnas PK disponibles en '{parent}':")
            for j, c in enumerate(parent_cols, 1):
                print(f"    [{j}] {c}")
            pk_col = parent_cols[int(input("  Columna PK: ").strip()) - 1]

            child_cols = columns_for(child)  # type: ignore[operator]
            if not child_cols:
                print(f"  No hay columnas para '{child}'.")
                return
            print(f"\n  Columnas FK disponibles en '{child}':")
            for j, c in enumerate(child_cols, 1):
                print(f"    [{j}] {c}")
            fk_col = child_cols[int(input("  Columna FK: ").strip()) - 1]

            is_ctx = input("  ¿Es de contexto? [s/N]: ").strip().lower() in (
                "s",
                "si",
                "y",
                "yes",
            )
            fks.append(
                {
                    "parent": parent,
                    "child": child,
                    "fk_column": fk_col,
                    "pk_column": pk_col,
                    "is_context": is_ctx,
                    "direct": False,
                }
            )
            print(f"  FK añadida: {child}.{fk_col} → {parent}.{pk_col}")
        except (ValueError, IndexError, EOFError, KeyboardInterrupt):
            print("\n  Operacion cancelada.")
        return

    print("  Uso: fk add | fk rm <num>")
