"""Interactive CLI config editors driven by backend.src.config.field_schemas.

A generic form-builder renders any ConfigSchema as a numbered terminal menu;
special-case logic only exists for rules.yaml (which is a list of objects,
not a flat YAML document).
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from backend.src.cli._aliases import _BACK_ALIASES, _QUIT_ALIASES
from backend.src.config.field_schemas import (
    CONFIG_SCHEMAS,
    PRE_EXECUTION_SCHEMAS,
    ConfigSchema,
    FieldSchema,
    GroupToggle,
)
from backend.src.sessions.configs import resolve_config_path

# ── data-directory introspection ─────────────────────────────────────────────


def _load_columns_from_data() -> dict[str, list[str]]:
    """Return {table_name: [col, ...]} by reading CSV/parquet headers in data/.

    Delegates to the existing services.files layer (list_data_files + preview_file)
    so there is a single code path for header discovery shared with the API.
    Falls back silently to an empty dict on any error.
    """
    try:
        from pathlib import Path

        from backend.src.sessions.files import FilePreviewError, list_data_files, preview_file

        result: dict[str, list[str]] = {}
        for f in list_data_files(extensions={"csv", "parquet"}):
            try:
                preview = preview_file(f.path, sample_rows=0)
                table_name = Path(f.path).stem
                result[table_name] = preview.columns
            except FilePreviewError:
                pass
        return result
    except Exception:
        return {}


# ── low-level I/O ─────────────────────────────────────────────────────────────


def _load_cfg(name: str) -> dict:
    path = resolve_config_path(name)
    try:
        with open(path) as f:
            return yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}


def _save_cfg(name: str, data: dict) -> bool:
    path = resolve_config_path(name)
    try:
        with open(path, "w") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
        return True
    except OSError as exc:
        print(f"  Error al guardar: {exc}")
        return False


# ── dotpath helpers ───────────────────────────────────────────────────────────


def _get(d: dict, dotpath: str) -> Any:
    node: Any = d
    for key in dotpath.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(key)
        if node is None:
            return None
    return node


def _set(d: dict, dotpath: str, val: Any) -> dict:
    parts = dotpath.split(".")
    node = d
    for key in parts[:-1]:
        if key not in node or not isinstance(node[key], dict):
            node[key] = {}
        node = node[key]
    node[parts[-1]] = val
    return d


def _del(d: dict, dotpath: str) -> dict:
    parts = dotpath.split(".")
    node = d
    for key in parts[:-1]:
        if not isinstance(node, dict) or key not in node:
            return d
        node = node[key]
    node.pop(parts[-1], None)
    return d


# ── value display helpers ──────────────────────────────────────────────────────


def _yn(val: Any) -> str:
    if val is True:
        return "sí"
    if val is False:
        return "no"
    return str(val) if val is not None else "(vacío)"


def _parse_bool(s: str) -> bool | None:
    if s.lower() in ("s", "si", "sí", "y", "yes", "true", "1"):
        return True
    if s.lower() in ("n", "no", "false", "0"):
        return False
    return None


def _parse_nullable_int(s: str) -> int | None | str:
    if s.strip().lower() in ("null", "none", "-", ""):
        return None
    try:
        return int(s.strip())
    except ValueError:
        return "INVALID"


def _parse_nullable_float(s: str) -> float | None | str:
    if s.strip().lower() in ("null", "none", "-", ""):
        return None
    try:
        return float(s.strip())
    except ValueError:
        return "INVALID"


def _display_value(cfg: dict, f: FieldSchema) -> str:
    val = _get(cfg, f.path)
    if f.kind == "boolean":
        return _yn(val)
    if f.kind == "checklist":
        if isinstance(val, list):
            return ", ".join(val) if val else "(ninguna)"
        return "(ninguna)"
    if f.kind == "json":
        return json.dumps(val)[:40] if val else "(vacío)"
    if val is None:
        return "(vacío)"
    # For select, show label if available
    if f.kind == "select" and f.options:
        for opt in f.options:
            if opt.value == str(val):
                return opt.label
    return str(val)


# ── field-type renderers ───────────────────────────────────────────────────────


def _prompt_select(label: str, options: list, current: Any) -> Any:
    print(f"\n  {label} (actual: {current}):")
    for i, opt in enumerate(options, 1):
        mark = " *" if opt.value == str(current) else "  "
        print(f"  {i}.{mark} {opt.label}")
    try:
        sel = input(f"  Selecciona [1-{len(options)}] o Enter para conservar: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return current
    if not sel:
        return current
    try:
        idx = int(sel) - 1
        if 0 <= idx < len(options):
            return options[idx].value
        print("  Fuera de rango.")
    except ValueError:
        print("  Entrada no válida.")
    return current


def _edit_checklist(title: str, options: list, current: list[str]) -> list[str] | None:
    active: set[str] = set(current or [])
    while True:
        print(f"\n  {title}:")
        for i, opt in enumerate(options, 1):
            mark = "x" if opt.value in active else " "
            print(f"    [{mark}] {i:2d}. {opt.label}")
        print("  <numero> activar/desactivar  |  listo  |  volver")
        try:
            raw = input("    > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None
        if raw in ("listo", "ok", "done"):
            order = [o.value for o in options]
            return sorted(active, key=lambda x: order.index(x) if x in order else 999)
        if not raw or raw in _BACK_ALIASES or raw in _QUIT_ALIASES:
            return None
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(options):
                v = options[idx].value
                active.discard(v) if v in active else active.add(v)
            else:
                print(f"  Fuera de rango (1-{len(options)}).")
        except ValueError:
            print("  Entrada no reconocida.")


def _edit_field(cfg: dict, f: FieldSchema) -> bool:
    """Prompt user to edit a single field in-place.  Returns True if changed."""
    cur = _get(cfg, f.path)
    null_hint = ", null=vacío" if f.nullable else ""
    prefix = f"  {f.label}"
    if f.help:
        print(f"    ({f.help})")

    if f.kind == "boolean":
        v = input(f"{prefix} [s/n] (actual: {_yn(cur)}): ").strip()
        b = _parse_bool(v)
        if b is None:
            print("  Introduce 's' o 'n'.")
            return False
        _set(cfg, f.path, b)
        return True

    if f.kind == "select" and f.options:
        new = _prompt_select(f.label, f.options, cur)
        if new != cur:
            _set(cfg, f.path, new)
            return True
        return False

    if f.kind == "checklist":
        result = _edit_checklist(f.label, f.options, cur or [])
        if result is not None:
            _set(cfg, f.path, result)
            return True
        return False

    if f.kind == "number":
        v = input(f"{prefix} (actual: {cur}{null_hint}): ").strip()
        if not v:
            return False
        # Try int first, then float
        res: Any = _parse_nullable_int(v)
        if res == "INVALID":
            res = _parse_nullable_float(v)
        if res == "INVALID":
            print("  Introduce un número.")
            return False
        if res is None and not f.nullable:
            print("  Este campo no puede ser vacío.")
            return False
        _set(cfg, f.path, res)
        return True

    if f.kind == "json":
        cur_json = json.dumps(cur, ensure_ascii=False) if cur is not None else "null"
        print(f"{prefix} (actual: {cur_json})")
        print("  Introduce JSON en una sola línea (Enter=conservar):")
        try:
            v = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if not v:
            return False
        try:
            parsed = json.loads(v)
        except json.JSONDecodeError as exc:
            print(f"  JSON inválido: {exc}")
            return False
        _set(cfg, f.path, parsed)
        return True

    # text / fallback
    v = input(f"{prefix} (actual: {cur}{null_hint}, Enter=conservar): ").strip()
    if not v:
        return False
    _set(cfg, f.path, None if (v.lower() in ("null", "none") and f.nullable) else v)
    return True


# ── toggle-group handler ───────────────────────────────────────────────────────


def _handle_toggle(cfg: dict, toggle: GroupToggle) -> bool:
    current_on = isinstance(_get(cfg, toggle.path), dict)
    if current_on:
        confirm = input(f"  '{toggle.label}' está activo. ¿Desactivar? [s/n]: ").strip().lower()
        if _parse_bool(confirm):
            _del(cfg, toggle.path)
            return True
    else:
        confirm = (
            input(f"  '{toggle.label}' está desactivado. ¿Activar con valores por defecto? [s/n]: ")
            .strip()
            .lower()
        )
        if _parse_bool(confirm):
            _set(cfg, toggle.path, dict(toggle.defaults))
            return True
    return False


# ── generic form builder ───────────────────────────────────────────────────────


def _build_flat_rows(
    schema: ConfigSchema, cfg: dict
) -> list[tuple[str, FieldSchema | GroupToggle]]:
    """Flatten schema groups+fields into a numbered list for the menu."""
    rows: list[tuple[str, FieldSchema | GroupToggle]] = []
    for group in schema.groups:
        if group.toggle:
            tog = group.toggle
            is_on = isinstance(_get(cfg, tog.path), dict)
            rows.append(
                (
                    f"[ACTIVAR/DESACTIVAR] {tog.label}  ({'activo' if is_on else 'desactivado'})",
                    tog,
                )
            )
            if is_on:
                for f in group.fields:
                    rows.append((f.label, f))
        else:
            for f in group.fields:
                rows.append((f.label, f))
    return rows


def edit_config(config_id: str) -> None:
    """Generic interactive editor for any config registered in CONFIG_SCHEMAS."""
    schema = CONFIG_SCHEMAS.get(config_id)
    if schema is None:
        print(f"  Esquema no definido para '{config_id}'.")
        return

    cfg = _load_cfg(config_id)
    modified = False

    while True:
        rows = _build_flat_rows(schema, cfg)

        print("\n" + "─" * 64)
        print(f"  {schema.title.upper()}")
        if schema.description:
            print(f"  {schema.description}")
        print("─" * 64)

        for i, (label, item) in enumerate(rows, 1):
            if isinstance(item, FieldSchema):
                disp = _display_value(cfg, item)
                short = disp if len(disp) <= 32 else disp[:29] + "..."
                print(f"  {i:2d}.  {label:<38s} {short}")
            else:
                # GroupToggle row
                print(f"  {i:2d}.  {label}")

        if modified:
            print("\n  * Cambios pendientes de guardar")
        print("\n  <numero> editar  |  listo guardar  |  volver cancelar")

        try:
            raw = input(f"\n  {config_id}> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        cmd = raw.lower()
        if not cmd or cmd in _BACK_ALIASES or cmd in _QUIT_ALIASES:
            return
        if cmd == "listo":
            if _save_cfg(config_id, cfg):
                print("  Guardado.")
            return

        try:
            idx = int(cmd) - 1
        except ValueError:
            print("  Introduce un número o 'listo'/'volver'.")
            continue
        if not (0 <= idx < len(rows)):
            print(f"  Fuera de rango (1-{len(rows)}).")
            continue

        _, item = rows[idx]
        if isinstance(item, GroupToggle):
            if _handle_toggle(cfg, item):
                modified = True
        else:
            if _edit_field(cfg, item):
                modified = True


# ── rules.yaml (special-case: list of objects) ────────────────────────────────

_RULE_TYPES = [
    ("date_inequality", "Relación entre fechas"),
    ("numeric_inequality", "Relación entre números"),
    ("semantic_ranking_consistency", "Consistencia semántica (ranking)"),
    ("semantic_proportional_consistency", "Consistencia semántica (proporcional)"),
    ("foreign_keys_consistency_rule", "Consistencia de claves foráneas"),
]

_RULE_FIELD_SPECS: dict[str, list[tuple[str, str, bool]]] = {
    "date_inequality": [
        ("table_target", "Tabla objetivo", True),
        ("target_col", "Columna objetivo", True),
        ("table_origin", "Tabla origen (o vacío→constante)", False),
        ("origin_col", "Columna origen", False),
        ("constraint", "Constante (si no hay origen)", False),
        ("constraint_operator", "Operador (>= o <=)", True),
    ],
    "numeric_inequality": [
        ("table_target", "Tabla objetivo", True),
        ("target_col", "Columna objetivo", True),
        ("table_origin", "Tabla origen (o vacío)", False),
        ("origin_col", "Columna origen", False),
        ("constraint", "Constante numérica", False),
        ("constraint_operator", "Operador (>= o <=)", True),
    ],
    "semantic_ranking_consistency": [
        ("table_origin", "Tabla origen", True),
        ("origin_col", "Columna origen", True),
        ("table_target", "Tabla objetivo", True),
        ("target_col", "Columna objetivo", True),
    ],
    "semantic_proportional_consistency": [
        ("table_origin", "Tabla origen", True),
        ("origin_col", "Columna origen", True),
        ("table_target", "Tabla objetivo", True),
        ("target_col", "Columna objetivo", True),
    ],
    "foreign_keys_consistency_rule": [
        ("table_origin", "Tabla padre (contexto)", True),
        ("source_col", "Columna fuente en padre", True),
        ("table_target", "Tabla hijo", True),
        ("target_col", "Columna hijo a rellenar", True),
        ("referenced_table", "Tabla referenciada (opcional)", False),
    ],
}

_OP_OPTIONS = [(">=", "mayor o igual (>=)"), ("<=", "menor o igual (<=)")]


def _summarize_rule(r: dict) -> str:
    rtype = r.get("type", "?")
    left = ".".join(
        filter(None, [r.get("table_origin"), r.get("origin_col") or r.get("source_col")])
    )
    right = ".".join(filter(None, [r.get("table_target"), r.get("target_col")]))
    op = r.get("constraint_operator", ">=")
    if rtype in ("date_inequality", "numeric_inequality"):
        bound = left or str(r.get("constraint", "?"))
        return f"{right} {op} {bound}"
    if rtype == "foreign_keys_consistency_rule":
        return f"{right} ← {left}"
    return f"{left} → {right}"


def _prompt_rule_field(
    key: str,
    label: str,
    required: bool,
    columns_by_table: dict[str, list[str]] | None,
    current: str | None = None,
    current_table: str | None = None,
) -> str | None:
    if key == "constraint_operator":
        opts_objs = [type("O", (), {"value": v, "label": l})() for v, l in _OP_OPTIONS]
        print(f"\n  {label}:")
        for i, o in enumerate(opts_objs, 1):
            mark = " *" if o.value == (current or ">=") else "  "
            print(f"  {i}.{mark} {o.label}")
        try:
            sel = input("  Selecciona [1-2] o Enter para conservar: ").strip()
        except (EOFError, KeyboardInterrupt):
            return current
        if not sel:
            return current or ">="
        try:
            return opts_objs[int(sel) - 1].value
        except (ValueError, IndexError):
            return current or ">="

    is_table = "table" in key
    is_col = "col" in key

    if is_table and columns_by_table:
        tables = sorted(columns_by_table.keys())
        print(f"\n  {label}:")
        for i, t in enumerate(tables, 1):
            print(f"    {i}. {t}")
        try:
            sel = input("  Número o nombre: ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if not sel:
            return current if not required else None
        try:
            t_idx = int(sel) - 1
            return tables[t_idx] if 0 <= t_idx < len(tables) else sel
        except ValueError:
            return sel

    if is_col and columns_by_table:
        # Prefer columns from the table already selected in this rule.
        if current_table and current_table in columns_by_table:
            all_cols = list(columns_by_table[current_table])
        else:
            # Flatten all columns as fallback (no table context).
            seen: list[str] = []
            for cols in columns_by_table.values():
                seen.extend(c for c in cols if c not in seen)
            all_cols = seen
        if all_cols:
            print(f"\n  {label}" + (f" (tabla: {current_table})" if current_table else "") + ":")
            for i, c in enumerate(all_cols, 1):
                print(f"    {i:3d}. {c}")
            try:
                sel = input("  Número o nombre: ").strip()
            except (EOFError, KeyboardInterrupt):
                return None
            if not sel:
                return current if not required else None
            try:
                c_idx = int(sel) - 1
                return all_cols[c_idx] if 0 <= c_idx < len(all_cols) else sel
            except ValueError:
                return sel

    hint = (
        f" (actual: {current})"
        if current
        else (" (obligatorio)" if required else " (opcional, Enter=vacío)")
    )
    try:
        val = input(f"  {label}{hint}: ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    return val if val else (current or None)


def edit_rules(columns_by_table: dict[str, list[str]] | None = None) -> None:
    if columns_by_table is None:
        columns_by_table = _load_columns_from_data() or None
    cfg = _load_cfg("rules")
    rules: list[dict] = list(cfg.get("rules", []))
    modified = False

    while True:
        print("\n" + "─" * 64)
        print("  REGLAS DE PREPROCESAMIENTO")
        print("─" * 64)
        if not rules:
            print("  (sin reglas definidas)")
        else:
            for i, r in enumerate(rules, 1):
                print(f"  {i:2d}. [{r.get('type', '?')}] {_summarize_rule(r)}")

        print("\n  add       Añadir regla")
        print("  rm <n>    Eliminar regla n")
        print("  edit <n>  Editar regla n")
        print("  listo     Guardar y salir")
        print("  volver    Cancelar sin guardar")

        try:
            raw = input("\n  reglas> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        parts = raw.split()
        if not parts:
            continue
        cmd = parts[0].lower()

        if cmd in _BACK_ALIASES or cmd in _QUIT_ALIASES:
            return
        if cmd == "listo":
            if _save_cfg("rules", {"rules": rules}):
                print("  Guardado.")
            return

        if cmd == "add":
            print("\n  Tipo de regla:")
            for i, (_, lbl) in enumerate(_RULE_TYPES, 1):
                print(f"    {i}. {lbl}")
            try:
                sel = input("  Selecciona [1-5]: ").strip()
                type_idx = int(sel) - 1
                if not (0 <= type_idx < len(_RULE_TYPES)):
                    print("  Fuera de rango.")
                    continue
            except (ValueError, EOFError, KeyboardInterrupt):
                continue

            rtype, _ = _RULE_TYPES[type_idx]
            new_rule: dict = {"type": rtype}
            ok = True
            for key, label, required in _RULE_FIELD_SPECS[rtype]:
                # Determine which table is already known for column prompts.
                _tbl_key = "table_origin" if "origin" in key or "source" in key else "table_target"
                _ctx_table = new_rule.get(_tbl_key) if "col" in key else None
                val = _prompt_rule_field(
                    key,
                    label,
                    required,
                    columns_by_table,
                    current_table=_ctx_table,
                )
                if val:
                    new_rule[key] = val
                elif required:
                    print(f"  Campo '{label}' es obligatorio. Cancelando.")
                    ok = False
                    break
            if ok:
                rules.append(new_rule)
                modified = True
                print(f"  Regla añadida: {_summarize_rule(new_rule)}")

        elif cmd == "rm":
            if len(parts) < 2:
                print("  Uso: rm <n>")
                continue
            try:
                n = int(parts[1]) - 1
                if 0 <= n < len(rules):
                    removed = rules.pop(n)
                    modified = True
                    print(f"  Eliminada: {_summarize_rule(removed)}")
                else:
                    print(f"  Fuera de rango (1-{len(rules)}).")
            except ValueError:
                print("  Uso: rm <n>")

        elif cmd == "edit":
            if len(parts) < 2:
                print("  Uso: edit <n>")
                continue
            try:
                n = int(parts[1]) - 1
                if not (0 <= n < len(rules)):
                    print(f"  Fuera de rango (1-{len(rules)}).")
                    continue
            except ValueError:
                print("  Uso: edit <n>")
                continue

            rule = dict(rules[n])
            rtype = rule.get("type", "")
            print(f"\n  Editando: {_summarize_rule(rule)}  (Enter conserva valor actual)")
            for key, label, required in _RULE_FIELD_SPECS.get(rtype, []):
                cur = rule.get(key)
                _tbl_key = "table_origin" if "origin" in key or "source" in key else "table_target"
                _ctx_table = rule.get(_tbl_key) if "col" in key else None
                val = _prompt_rule_field(
                    key,
                    label,
                    required,
                    columns_by_table,
                    current=cur,
                    current_table=_ctx_table,
                )
                if val:
                    rule[key] = val
                elif not required and key in rule:
                    try:
                        rem = input(f"  Eliminar '{label}'? [s/n]: ").strip().lower()
                    except (EOFError, KeyboardInterrupt):
                        rem = "n"
                    if _parse_bool(rem):
                        rule.pop(key, None)
            rules[n] = rule
            modified = True
            print(f"  Actualizada: {_summarize_rule(rule)}")
        else:
            print("  Uso: add | rm <n> | edit <n> | listo | volver")


# ── top-level config menu ──────────────────────────────────────────────────────

_MENU_ENTRIES = [
    ("1", "general", "Configuración general     (general.yaml)"),
    ("2", "mostly_ai", "Configuración Mostly AI   (mostly_ai.yaml)"),
    ("3", "evaluation", "Configuración evaluación  (evaluation.yaml)"),
    ("4", "rules", "Reglas de preprocesamiento(rules.yaml)"),
]


def config_menu(columns_by_table: dict[str, list[str]] | None = None) -> None:
    """Top-level settings router shown from the main wizard menu."""
    while True:
        print("\n" + "─" * 64)
        print("  CONFIGURACIÓN")
        print("─" * 64)
        for key, _, label in _MENU_ENTRIES:
            print(f"  {key}. {label}")
        print("  b. volver")

        try:
            raw = input("\n  config> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not raw or raw in _BACK_ALIASES or raw in _QUIT_ALIASES:
            return
        for key, cid, _ in _MENU_ENTRIES:
            aliases = {key, cid}
            if raw in aliases:
                if cid == "rules":
                    edit_rules(columns_by_table)
                else:
                    edit_config(cid)
                break
        else:
            print("  Opción no reconocida.")


# ── pre-execution review helper (used by wizard.py) ───────────────────────────


def maybe_review_configs(mode: str, columns_by_table: dict[str, list[str]] | None = None) -> None:
    """Ask before a workflow run whether the user wants to tweak relevant config."""
    config_ids = PRE_EXECUTION_SCHEMAS.get(mode, [])
    labels = {
        "general": "configuración general",
        "mostly_ai": "configuración del modelo (Mostly AI)",
        "evaluation": "configuración de evaluación",
    }
    for cid in config_ids:
        label = labels.get(cid, cid)
        try:
            ans = input(f"\n  ¿Revisar {label} antes de continuar? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if _parse_bool(ans) is True:
            edit_config(cid)

    # Always offer rules for inspect+train
    if mode in ("i", "t"):
        try:
            ans = input("\n  ¿Revisar reglas de preprocesamiento? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if _parse_bool(ans) is True:
            edit_rules(columns_by_table)
