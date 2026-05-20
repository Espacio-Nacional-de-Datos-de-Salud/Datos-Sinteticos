"""Interactive CLI for designing and running pipelines.

Shares the same execution path as the API (initialize_pipeline_session +
run_pipeline_from_config) so behaviour is identical between the web UI and
the terminal.  YAML authoring uses the same schema and folder as the frontend
dev-mode designer (backend/config/pipelines/).
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml
from backend.src.cli._aliases import _BACK_ALIASES, _QUIT_ALIASES
from backend.src.config.general import CONFIG_DIR

# ── background pipeline registry ──────────────────────────────────────────────

# label → Popen object for background pipeline processes
_RUNNING: dict[str, subprocess.Popen[bytes]] = {}

# ── config folder (shared with frontend dev-mode designer) ────────────────────

_PIPELINE_CONFIG_DIR = Path(str(CONFIG_DIR)) / "pipelines"


def _ensure_dir() -> None:
    _PIPELINE_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# ── list / select saved pipeline configs ──────────────────────────────────────


def _list_pipeline_configs() -> list[Path]:
    if not _PIPELINE_CONFIG_DIR.exists():
        return []
    return sorted(
        p
        for p in _PIPELINE_CONFIG_DIR.iterdir()
        if p.is_file() and p.suffix == ".yaml" and not p.name.endswith(".example.yaml")
    )


def _print_pipeline_configs(configs: list[Path]) -> None:
    print("\n  Pipelines guardados:")
    if not configs:
        print("  (ninguno todavia)")
        return
    for i, p in enumerate(configs, 1):
        size = p.stat().st_size
        print(f"  {i:2d}. {p.stem:<32s}  ({size} bytes)")


def _select_pipeline_config() -> Path | None:
    """Let user pick an existing pipeline YAML or return None."""
    configs = _list_pipeline_configs()
    _print_pipeline_configs(configs)
    if not configs:
        return None
    try:
        sel = input("\n  Número (o Enter para cancelar): ").strip()
    except (EOFError, KeyboardInterrupt):
        return None
    if not sel:
        return None
    try:
        idx = int(sel) - 1
        if 0 <= idx < len(configs):
            return configs[idx]
        print("  Fuera de rango.")
    except ValueError:
        print("  Introduce un número.")
    return None


# ── job builder ────────────────────────────────────────────────────────────────


def _select_files() -> list[str]:
    """Wrapper around wizard's file selector logic, returns list of paths."""
    from backend.src.sessions.files import list_data_files

    files = list_data_files(extensions={"csv", "parquet"})
    if not files:
        print("  No hay archivos de datos disponibles.")
        return []
    print("\n  Archivos disponibles:")
    for i, f in enumerate(files, 1):
        print(f"  {i:3d}. {f.name}")
    try:
        sel = input("  Números separados por espacios (Enter=ninguno): ").strip()
    except (EOFError, KeyboardInterrupt):
        return []
    if not sel:
        return []
    selected: list[str] = []
    for part in sel.split():
        try:
            idx = int(part) - 1
            if 0 <= idx < len(files):
                selected.append(files[idx].path)
        except ValueError:
            pass
    return selected


def _select_from_catalog(catalog_type: str, label: str) -> str:
    """Return selected id or empty string."""
    from backend.src.cli.catalog import _print_catalog

    items = _print_catalog(catalog_type)
    if not items:
        return ""
    id_field = {
        "inspections": "inspection_id",
        "models": "model_id",
        "simulations": "simulation_id",
    }.get(catalog_type, "id")
    try:
        sel = input(f"  {label} (número, o Enter para omitir): ").strip()
    except (EOFError, KeyboardInterrupt):
        return ""
    if not sel:
        return ""
    try:
        idx = int(sel) - 1
        if 0 <= idx < len(items):
            return items[idx].get(id_field, "")
    except ValueError:
        return sel
    return ""


def _build_job_interactive(job_num: int) -> dict | None:
    """Interactively build one pipeline job dict.

    Returns a dict ready to embed in a pipeline YAML jobs list, or None if
    the user cancels.
    """
    print(f"\n{'─' * 60}")
    print(f"  JOB {job_num}")
    print(f"{'─' * 60}")

    try:
        name = input(f"  Nombre del job [job_{job_num}]: ").strip() or f"job_{job_num}"
    except (EOFError, KeyboardInterrupt):
        return None

    job: dict = {"name": name}

    # ── step toggles ──────────────────────────────────────────────────────────
    print("\n  Pasos a incluir (s = sí, Enter = no):")

    def _yn(prompt: str) -> bool:
        try:
            return input(f"  {prompt} [s/N]: ").strip().lower() in ("s", "si", "y", "yes")
        except (EOFError, KeyboardInterrupt):
            return False

    do_train = _yn("¿Entrenar?")
    do_simulate = _yn("¿Simular?")
    do_evaluate = _yn("¿Evaluar?")

    if not any([do_train, do_simulate, do_evaluate]):
        print("  Al menos un paso es obligatorio. Cancelando job.")
        return None

    # ── train step ────────────────────────────────────────────────────────────
    if do_train:
        train: dict = {}
        print("\n  PASO TRAIN")
        use_inspection = _yn("  ¿Reanudar desde inspección existente?")
        if use_inspection:
            insp_id = _select_from_catalog("inspections", "Inspección")
            if insp_id:
                train["inspection_id"] = insp_id
            else:
                print("  Sin inspección seleccionada; se usarán archivos.")
        if not train.get("inspection_id"):
            files = _select_files()
            if not files:
                print("  Sin archivos; se saltará el entrenamiento.")
                do_train = False
            else:
                train["files"] = files
        if do_train:
            job["train"] = train

    # ── simulate step ─────────────────────────────────────────────────────────
    if do_simulate:
        sim: dict = {}
        print("\n  PASO SIMULATE")
        if not do_train:
            model_id = _select_from_catalog("models", "Modelo a usar")
            if model_id:
                sim["model_id"] = model_id
        try:
            size_raw = input("  Tamaño de muestra [1000]: ").strip() or "1000"
            sim["sample_size"] = int(size_raw)
        except (ValueError, EOFError, KeyboardInterrupt):
            sim["sample_size"] = 1000
        print("  Formato de salida:")
        print("    1. csv (por defecto)")
        print("    2. parquet")
        try:
            fmt_sel = input("  Selecciona [1-2]: ").strip()
        except (EOFError, KeyboardInterrupt):
            fmt_sel = "1"
        sim["synthetic_data_file_format"] = "parquet" if fmt_sel == "2" else "csv"
        job["simulate"] = sim

    # ── evaluate step ─────────────────────────────────────────────────────────
    if do_evaluate:
        ev: dict = {}
        print("\n  PASO EVALUATE")
        if not do_train:
            use_existing_sim = _yn("  ¿Evaluar simulación existente?")
            if use_existing_sim:
                sim_id = _select_from_catalog("simulations", "Simulación a evaluar")
                if sim_id:
                    ev["simulation_id"] = sim_id
        # The eval flow auto-binds real_data to the model's preprocessed
        # training data (see resolve_model_real_data_paths). Only prompt when
        # this job has no model lineage and no train step.
        has_lineage = bool(ev.get("simulation_id")) or bool(job.get("train"))
        if not has_lineage:
            print("  Datos reales para comparar (override opcional):")
            real_files = _select_files()
            if real_files:
                ev["real_data"] = real_files
        else:
            print(
                "  Datos reales: se usarán automáticamente los del modelo "
                "entrenado (postprocesados con las reglas lógicas)."
            )
        job["evaluate"] = ev

    # ── per-job config overrides ───────────────────────────────────────────────
    do_overrides = _yn("\n  ¿Añadir overrides de configuración (epochs, DP, etc.)?")
    if do_overrides:
        cfg: dict = {}
        print("  Overrides disponibles (Enter = usar valor global):")
        fields = [
            ("max_epochs", "max_epochs (entero)"),
            ("batch_size", "batch_size (entero)"),
            ("model", "model size [S/M/L]"),
            ("enable_flexible_generation", "flexible_generation [true/false]"),
            ("dp_max_epsilon", "DP max_epsilon (float)"),
            ("dp_noise_multiplier", "DP noise_multiplier (float)"),
        ]
        ma_overrides: dict = {"model_settings": {}}
        dp_overrides: dict = {}
        for key, label in fields:
            try:
                val = input(f"    {label}: ").strip()
            except (EOFError, KeyboardInterrupt):
                val = ""
            if not val:
                continue
            if key.startswith("dp_"):
                try:
                    dp_overrides[key[3:]] = float(val)
                except ValueError:
                    pass
            elif key in ("max_epochs", "batch_size"):
                try:
                    ma_overrides["model_settings"][key] = int(val)
                except ValueError:
                    pass
            elif key == "model":
                if val.upper() in ("S", "M", "L"):
                    ma_overrides["model_settings"]["model"] = val.upper()
            elif key == "enable_flexible_generation":
                if val.lower() in ("true", "false"):
                    ma_overrides["model_settings"]["enable_flexible_generation"] = (
                        val.lower() == "true"
                    )
        if dp_overrides:
            ma_overrides["model_settings"]["differential_privacy"] = dp_overrides
        # Prune empty nesting
        if not ma_overrides["model_settings"]:
            ma_overrides.pop("model_settings")
        if ma_overrides:
            cfg["mostly_ai"] = ma_overrides
        if cfg:
            job["config"] = cfg

    return job


# ── pipeline composer ──────────────────────────────────────────────────────────


def _compose_pipeline() -> dict | None:
    """Interactively build a full pipeline dict (ready to dump as YAML)."""
    print("\n  DISEÑAR NUEVA PIPELINE")
    jobs: list[dict] = []
    job_num = 1
    while True:
        job = _build_job_interactive(job_num)
        if job is None:
            if not jobs:
                print("  Pipeline cancelada.")
                return None
            break
        jobs.append(job)
        job_num += 1
        try:
            more = input("\n  ¿Añadir otro job? [s/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            # Ctrl+C here means "stop, don't execute" — cancel the whole composition.
            print("\n  Cancelado.")
            return None
        if more not in ("s", "si", "y", "yes"):
            break
    if not jobs:
        return None
    return {"jobs": jobs}


def _save_pipeline(doc: dict, name: str) -> Path:
    """Persist a pipeline doc to YAML and return the saved path."""
    _ensure_dir()
    path = _PIPELINE_CONFIG_DIR / f"{name}.yaml"
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(doc, fh, default_flow_style=False, allow_unicode=True, sort_keys=False)
    return path


# ── runner ────────────────────────────────────────────────────────────────────


def _run_pipeline_path(config_path: str) -> str:
    """Launch a pipeline in a background subprocess and return immediately.

    Pre-creates the pipeline session (folder + card) so the pipeline_id is
    known before the subprocess starts — enabling cancel/status lookup.

    The subprocess runs in its own session (start_new_session=True) so
    Ctrl+C in the terminal does NOT reach it.  All output (including the
    rich progress bars from the mostlyai SDK) is redirected to a log file
    so the CLI terminal stays clean.

    Returns:
        The pipeline_id of the newly created session.
    """
    import os

    from backend.src.config.general import PIPELINES_DIR
    from backend.src.sessions.pipeline import initialize_pipeline_session

    # Create folder + in_progress card BEFORE the subprocess starts.
    session = initialize_pipeline_session(config_path)
    pipeline_id = session.pipeline_id

    log_dir = Path(PIPELINES_DIR)
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{pipeline_id}.log"

    cmd = [
        sys.executable,
        "-m",
        "backend.src.cli._pipeline_runner",
        config_path,
        "--pipeline-id",
        pipeline_id,
    ]
    # start_new_session puts the child in its own process group so it is
    # immune to SIGINT/SIGHUP delivered to our terminal.
    log_file = open(log_path, "w", encoding="utf-8")  # noqa: WPS515
    proc = subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=log_file,
        start_new_session=True,
        env={**os.environ},  # inherit env (venv, etc.)
    )
    _RUNNING[pipeline_id] = proc
    print(f"\n  Pipeline iniciada: {pipeline_id} (PID {proc.pid}).")
    print(f"  Log: {log_path}")
    print("  La CLI sigue disponible.")
    return pipeline_id


# ── cancel / delete / log helpers ─────────────────────────────────────────────


def _is_running(pipeline_id: str) -> bool:
    """True if pipeline_id is tracked and its subprocess is still alive."""
    proc = _RUNNING.get(pipeline_id)
    return proc is not None and proc.poll() is None


def _cancel_running(pipeline_id: str) -> None:
    """Send SIGTERM to the entire process group of a running pipeline."""
    import json
    import os
    import signal

    from backend.src.config.general import PIPELINE_CARD_FILENAME, PIPELINES_DIR

    proc = _RUNNING.get(pipeline_id)
    if proc is None or proc.poll() is not None:
        print("  No hay proceso activo para esta pipeline.")
        return

    try:
        os.killpg(proc.pid, signal.SIGTERM)
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    except ProcessLookupError:
        pass

    _RUNNING.pop(pipeline_id, None)

    # Manually update the card — the subprocess won't finish gracefully.
    card_path = os.path.join(PIPELINES_DIR, pipeline_id, PIPELINE_CARD_FILENAME)
    if os.path.exists(card_path):
        with open(card_path, encoding="utf-8") as fh:
            card = json.load(fh)
        card["status"] = "cancelled"
        card.pop("progress", None)
        with open(card_path, "w", encoding="utf-8") as fh:
            json.dump(card, fh, indent=4)

    print(f"  Pipeline {pipeline_id} cancelada.")


def _delete_pipeline_interactive(pipeline_id: str) -> None:
    """Confirm and delete a pipeline folder plus its cascade artifacts."""
    from backend.src.runs.catalog.pipelines import delete_pipeline

    if _is_running(pipeline_id):
        print("  La pipeline está en ejecución. Cancélala primero antes de eliminar.")
        return

    try:
        confirm = input(f"  ¿Eliminar {pipeline_id} y sus artefactos? [s/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return

    if confirm not in ("s", "si", "y", "yes"):
        print("  Eliminación cancelada.")
        return

    outcome = delete_pipeline(pipeline_id)
    if not outcome.found:
        print("  Pipeline no encontrada.")
        return

    msgs = [f"  Eliminado: {pipeline_id}"]
    if outcome.deleted_model_ids:
        msgs.append(f"    + modelos: {', '.join(outcome.deleted_model_ids)}")
    if outcome.deleted_simulation_ids:
        msgs.append(f"    + simulaciones: {', '.join(outcome.deleted_simulation_ids)}")
    print("\n".join(msgs))


def _view_pipeline_log(pipeline_id: str) -> None:
    """Print the last 40 lines of the pipeline log file."""
    import os

    from backend.src.config.general import PIPELINES_DIR

    log_path = Path(PIPELINES_DIR) / f"{pipeline_id}.log"
    if not log_path.exists():
        print("  Log no encontrado.")
        return

    lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-40:]
    print(f"\n  — últimas {len(tail)} líneas de {log_path.name} —")
    for line in tail:
        print("  " + line)
    print()


# ── results viewer ─────────────────────────────────────────────────────────────


def _show_pipeline_results() -> None:
    """Interactive list of recent pipeline runs with cancel/delete/log actions."""
    from backend.src.runs.catalog.pipelines import (
        cleanup_pipelines,
        list_available_pipelines,
    )

    while True:
        runs = list_available_pipelines()
        if not runs:
            print("  Sin ejecuciones previas.")
            return

        display = runs[:25]
        print(f"\n  {'#':<4} {'ID':<40s}  {'Estado':<14s}  {'Timestamp'}")
        print("  " + "─" * 76)
        for idx, r in enumerate(display, 1):
            pid = r.get("pipeline_id", "?")
            status = r.get("status", "?")
            ts = r.get("timestamp", "")
            jobs = r.get("jobs", [])
            n_jobs = len(jobs)
            completed = sum(1 for j in jobs if j.get("status") == "completed")
            job_info = f" ({completed}/{n_jobs})" if n_jobs else ""
            live = " ◉" if _is_running(pid) else ""
            print(f"  {idx:<4} {pid:<40s}  {status:<14s}  {ts}{job_info}{live}")

        print("\n  [número] ver acciones   l. limpiar vacías   Enter. volver")
        try:
            sel = input("  > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return

        if not sel or sel in _BACK_ALIASES:
            return

        if sel in ("l", "limpiar"):
            deleted, _ = cleanup_pipelines(mode="empty")
            if deleted:
                print(f"  Eliminadas {len(deleted)} pipeline(s) vacía(s).")
            else:
                print("  No hay pipelines vacías.")
            continue

        try:
            idx = int(sel) - 1
        except ValueError:
            print("  Opción no reconocida.")
            continue

        if not (0 <= idx < len(display)):
            print(f"  Número fuera de rango (1-{len(display)}).")
            continue

        item = display[idx]
        pipeline_id = item.get("pipeline_id", "")
        status = item.get("status", "?")
        is_live = _is_running(pipeline_id)

        print(f"\n  Pipeline: {pipeline_id}  [{status}]")
        if is_live:
            print("    c. cancelar   Terminar proceso en background")
        print("    d. eliminar   Borrar carpeta y artefactos asociados")
        print("    g. log        Ver últimas líneas del log")
        print("    volver")
        try:
            action = input("  acción> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            continue

        if action in ("c", "cancelar") and is_live:
            _cancel_running(pipeline_id)
        elif action in ("d", "eliminar", "borrar"):
            _delete_pipeline_interactive(pipeline_id)
        elif action in ("g", "log"):
            _view_pipeline_log(pipeline_id)
        elif action and action not in _BACK_ALIASES:
            print("  Opción no reconocida.")


def running_pipelines_hint() -> str:
    """Return a one-liner if any pipelines are still running; empty string otherwise."""
    alive = [lbl for lbl, p in _RUNNING.items() if p.poll() is None]
    if not alive:
        return ""
    n = len(alive)
    return (
        f"  [{n} pipeline(s) ejecutándose en background — 'pipelines > resultados' para ver estado]"
    )


# ── top-level pipeline menu ────────────────────────────────────────────────────


def pipeline_menu() -> None:
    """Interactive pipeline menu: design, run, or view results.

    Ctrl+C at the menu prompt propagates up to the session loop (re-raised)
    so a single ^C always brings the user back to the main menu.
    """
    while True:
        hint = running_pipelines_hint()
        if hint:
            print(hint)
        print("\n" + "─" * 60)
        print("  PIPELINES")
        print("─" * 60)
        print("  1. diseñar   Componer y guardar una nueva pipeline")
        print("  2. ejecutar  Seleccionar y lanzar una pipeline guardada")
        print("  3. nueva     Diseñar y ejecutar en un solo paso")
        print("  4. resultados  Ver ejecuciones anteriores")
        print("  b. volver  (o Ctrl+C)")

        try:
            raw = input("\n  pipelines> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            raise KeyboardInterrupt from None  # propagate to session loop

        if not raw or raw in _BACK_ALIASES or raw in _QUIT_ALIASES:
            return

        if raw in ("1", "diseñar", "disenar", "design", "crear"):
            doc = _compose_pipeline()
            if doc is None:
                continue
            print("\n  Vista previa YAML:")
            print("  " + "-" * 56)
            preview = yaml.dump(doc, default_flow_style=False, allow_unicode=True, sort_keys=False)
            for line in preview.splitlines():
                print("  " + line)
            print("  " + "-" * 56)
            try:
                name = input("\n  Nombre para guardar (Enter=cancelar): ").strip()
            except (EOFError, KeyboardInterrupt):
                continue
            if not name:
                continue
            # Basic sanitisation (same rule as API router)
            import re

            if not re.match(r"^[A-Za-z0-9_-]+$", name):
                print("  Nombre inválido (usa letras, números, guiones y guiones bajos).")
                continue
            saved = _save_pipeline(doc, name)
            print(f"  Guardado: {saved}")

        elif raw in ("2", "ejecutar", "run", "lanzar"):
            cfg_path = _select_pipeline_config()
            if cfg_path is None:
                continue
            _run_pipeline_path(str(cfg_path))
            _show_pipeline_results()

        elif raw in ("3", "nueva"):
            doc = _compose_pipeline()
            if doc is None:
                continue
            # Auto-name with timestamp
            from backend.src.config.general import refresh_run_timestamp

            ts = refresh_run_timestamp()
            name = f"pipeline_{ts}"
            saved = _save_pipeline(doc, name)
            print(f"  Pipeline guardada como: {name}")
            _run_pipeline_path(str(saved))
            _show_pipeline_results()

        elif raw in ("4", "resultados", "ver"):
            _show_pipeline_results()

        else:
            print("  Opción no reconocida.")
