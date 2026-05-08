"""Argument parser for the backend command-line interface."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for non-interactive CLI execution."""
    parser = argparse.ArgumentParser(
        description="ENDS Synthetic Data Tool - Core CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Inspect raw data
  python -m backend.src.cli --mode i --files data/table1.csv data/table2.csv

  # Train from an existing inspection
  python -m backend.src.cli --mode t --inspection-id inspection_20240501_120000

  # Generate synthetic data from a trained model
  python -m backend.src.cli --mode s --model-id model_20240501_130000 --sample-size 5000
        """,
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["i", "t", "s"],
        help="Execution mode: 'i' (inspect), 't' (train), 's' (simulate).",
    )
    parser.add_argument(
        "-f",
        "--files",
        nargs="+",
        help="Paths to CSV/Parquet/Excel files (for 'i' or 't' modes).",
    )
    parser.add_argument(
        "-n",
        "--sample-size",
        type=int,
        help="Number of records to generate (for 's' or 't' followed by 's').",
    )
    parser.add_argument(
        "--model-id",
        help="Model ID for simulation mode.",
    )
    parser.add_argument(
        "--inspection-id",
        help="Inspection ID to resume training from.",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    return build_parser().parse_args(argv)
