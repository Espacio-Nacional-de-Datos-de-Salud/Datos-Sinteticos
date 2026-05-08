"""Executable CLI entry point for the backend workflows."""

from __future__ import annotations

import sys

from backend.src.config.execution import get_execution_config
from backend.src.core.logging_config import get_logger
from backend.src.core.time_profiling import profiler

from .commands import run_workflow
from .parser import parse_args
from .wizard import run_interactive_wizard

logger = get_logger(__name__)


def main(argv: list[str] | None = None) -> None:
    """Run the backend CLI, using the wizard when no args are provided in a TTY."""
    args_list = list(sys.argv[1:] if argv is None else argv)

    if not args_list and sys.stdin.isatty():
        wizard_args = run_interactive_wizard()
        if not wizard_args:
            return
        args_list = wizard_args

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
        logger.exception("An unexpected error occurred: %s", exc)
        sys.exit(1)
    finally:
        profiler.report("Run timing breakdown")


if __name__ == "__main__":
    main()
