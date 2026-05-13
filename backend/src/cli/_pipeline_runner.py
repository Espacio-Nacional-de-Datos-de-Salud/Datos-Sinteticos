"""Entry-point for running a pipeline in a background subprocess.

Invoked by pipeline_wizard._run_pipeline_path as:
    python -m backend.src.cli._pipeline_runner <config_path> [--pipeline-id <id>]

Running in a separate process (with start_new_session=True) means:
- Ctrl+C in the terminal does NOT reach this process.
- All stdout/stderr (including rich progress bars from mostlyai) are
  redirected to a log file, keeping the CLI terminal clean.

When --pipeline-id is supplied, the session card has already been written by
the calling wizard — we reconstruct the PipelineSession without touching
the card, so the pipeline_id is stable and can be shown to the user
before training starts.
"""

from __future__ import annotations


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(prog="_pipeline_runner")
    parser.add_argument("config_path", help="Path to pipeline YAML")
    parser.add_argument("--pipeline-id", default=None, help="Pre-created pipeline ID")
    args = parser.parse_args()

    config_path: str = args.config_path

    from backend.src.sessions.pipeline import (
        PipelineSession,
        initialize_pipeline_session,
        run_pipeline_from_config,
    )

    if args.pipeline_id:
        import os

        from backend.src.config.general import PIPELINE_CARD_FILENAME, PIPELINES_DIR

        pid = args.pipeline_id
        output_dir = os.path.join(PIPELINES_DIR, pid)
        card_path = os.path.join(output_dir, PIPELINE_CARD_FILENAME)
        # Timestamp lives after the first underscore prefix "pipeline_"
        timestamp = "_".join(pid.split("_")[1:]) if "_" in pid else ""
        session = PipelineSession(
            pipeline_id=pid,
            output_directory=output_dir,
            card_path=card_path,
            timestamp=timestamp,
        )
    else:
        session = initialize_pipeline_session(config_path)

    run_pipeline_from_config(config_path, session=session)


if __name__ == "__main__":
    main()
