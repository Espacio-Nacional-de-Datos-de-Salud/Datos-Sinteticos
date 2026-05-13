"""Entry point for the synthetic data pipeline."""

import argparse
import os
import sys

# Ensure the root directory is accessible.
sys.path.append(os.path.join(os.path.dirname(__file__), "..", ".."))

from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.time_profiling import profiler
from backend.src.domain.pipeline.executor import run_pipeline
from backend.src.domain.pipeline.loader import load_pipeline_config

logger = get_logger(__name__)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run an automated synthetic data pipeline.")
    parser.add_argument(
        "--config",
        required=True,
        help="Path to the pipeline YAML configuration file.",
    )
    args = parser.parse_args()

    try:
        pipeline_config = load_pipeline_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        sys.exit(f"Failed to load pipeline config: {exc}")

    try:
        run_pipeline(pipeline_config, config_path=args.config)
    except KeyboardInterrupt:
        logger.info("Pipeline interrupted by user.")
    finally:
        profiler.report("Pipeline timing breakdown")
