"""Shared CLI command alias sets and sentinel constants."""

from __future__ import annotations

INTERACTIVE_EXIT = "__interactive_exit__"

_EXECUTE_ALIASES = {"1", "ejecutar", "execute", "run"}
_RESULTS_ALIASES = {"2", "resultados", "results", "ver", "historial", "runs"}
_BACK_ALIASES = {"b", "back", "volver", "atras"}
_MODE_ALIASES = {
    "1": "i",
    "i": "i",
    "inspect": "i",
    "inspection": "i",
    "inspeccionar": "i",
    "inspeccion": "i",
    "2": "t",
    "t": "t",
    "train": "t",
    "training": "t",
    "entrenar": "t",
    "entrenamiento": "t",
    "3": "s",
    "s": "s",
    "simulate": "s",
    "simulation": "s",
    "generate": "s",
    "generation": "s",
    "simular": "s",
    "simulacion": "s",
    "generar": "s",
}
_EVALUATE_ALIASES = {"4", "e", "eval", "evaluate", "evaluation", "evaluar", "evaluacion"}
_HELP_ALIASES = {"?", "h", "help", "ayuda"}
_QUIT_ALIASES = {"q", "quit", "exit", "salir"}
