"""Executable CLI entry point for the backend workflows."""

from __future__ import annotations

import sys

from backend.src.config.execution import get_execution_config
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.time_profiling import profiler

from .commands import run_workflow
from .parser import parse_args
from .pipeline_wizard import running_pipelines_hint
from .wizard import INTERACTIVE_EXIT, print_session_banner, prompt_for_workflow

logger = get_logger(__name__)


def _run_args(args_list: list[str], *, exit_on_error: bool) -> None:
    """Parse and run one CLI invocation."""
    args = parse_args(args_list)
    execution_config = get_execution_config()

    mode = args.mode or execution_config.mode
    file_paths = args.files or execution_config.file_paths
    sample_size = args.sample_size if args.sample_size is not None else execution_config.sample_size
    model_id = args.model_id or execution_config.model_id
    inspection_id = args.inspection_id or execution_config.inspection_id

    try:
        run_workflow(
            mode=mode,
            file_paths=file_paths,
            sample_size=sample_size,
            model_id=model_id,
            inspection_id=inspection_id,
        )
    except KeyboardInterrupt:
        logger.info("Herramienta interrumpida por el usuario.")
    except Exception as exc:
        logger.exception("Ha ocurrido un error inesperado: %s", exc)
        if exit_on_error:
            sys.exit(1)
    finally:
        profiler.report("Desglose de tiempos")


def _run_interactive_session() -> None:
    """Keep the terminal inside the tool until the user explicitly exits."""
    print_session_banner()

    while True:
        hint = running_pipelines_hint()
        if hint:
            print(hint)
        try:
            workflow_args = prompt_for_workflow()
        except KeyboardInterrupt:
            print("\n  ^C — escribe 'salir' para salir.")
            continue
        if workflow_args == INTERACTIVE_EXIT:
            print("Hasta luego.")
            return
        if not workflow_args:
            continue

        try:
            _run_args(workflow_args, exit_on_error=False)
        except SystemExit:
            print("El comando no se ejecuto. Escribe 'ayuda' para ver comandos validos.")


def main(argv: list[str] | None = None) -> None:
    """Run the backend CLI."""
    args_list = list(sys.argv[1:] if argv is None else argv)

    if not args_list and sys.stdin.isatty():
        _run_interactive_session()
        return

    _run_args(args_list, exit_on_error=True)


if __name__ == "__main__":
    main()
