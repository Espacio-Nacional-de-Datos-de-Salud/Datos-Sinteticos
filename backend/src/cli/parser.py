"""Argument parser for the backend command-line interface."""

from __future__ import annotations

import argparse


def build_parser() -> argparse.ArgumentParser:
    """Build the parser for non-interactive CLI execution."""
    parser = argparse.ArgumentParser(
        description="Herramienta de Datos Sinteticos ENDS - CLI principal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  # Inspeccionar datos de entrada
  python -m backend.src.cli --mode i --files data/table1.csv data/table2.csv

    # Definir reglas logicas para una inspeccion
    python -m backend.src.cli --mode r --inspection-id inspection_20240501_120000

  # Entrenar desde una inspeccion existente
  python -m backend.src.cli --mode t --inspection-id inspection_20240501_120000

  # Generar datos sinteticos desde un modelo entrenado
  python -m backend.src.cli --mode s --model-id model_20240501_130000 --sample-size 5000
        """,
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["i", "r", "t", "s"],
        help=(
            "Modo de ejecucion: 'i' (inspeccionar), 'r' (reglas), 't' (entrenar), 's' (simular)."
        ),
    )
    parser.add_argument(
        "-f",
        "--files",
        nargs="+",
        help="Rutas a archivos CSV/Parquet/Excel (para modos 'i' o 't').",
    )
    parser.add_argument(
        "-n",
        "--sample-size",
        type=int,
        help="Numero de registros a generar (para 's' o 't' seguido de 's').",
    )
    parser.add_argument(
        "--model-id",
        help="ID del modelo para modo simulacion.",
    )
    parser.add_argument(
        "--inspection-id",
        help="ID de inspeccion desde la que entrenar.",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments."""
    return build_parser().parse_args(argv)
