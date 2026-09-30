"""Shared CLI command alias sets and sentinel constants."""

from __future__ import annotations

INTERACTIVE_EXIT = "__interactive_exit__"

_EXECUTE_ALIASES = {"1", "ejecutar", "execute", "run"}
_RESULTS_ALIASES = {"2", "resultados", "results", "ver", "historial", "runs"}
_BACK_ALIASES = {"b", "back", "volver", "atras"}
_MODE_ALIASES = {
    "1": "i",
    "i": "i",
    "cargar": "i",
    "carga": "i",
    "load": "i",
    # Legacy aliases (UI now calls this "Carga de Datos"); kept for muscle memory.
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
    "generar": "s",
    "generacion": "s",
    "generación": "s",
    "generate": "s",
    "generation": "s",
    # Legacy aliases (UI now calls this "Generación"); kept for muscle memory.
    "simulate": "s",
    "simulation": "s",
    "simular": "s",
    "simulacion": "s",
}
_EVALUATE_ALIASES = {
    "4",
    "a",
    "auditar",
    "auditoria",
    "auditoría",
    "audit",
    # Legacy aliases (UI now calls this step "Auditoría"); kept for muscle memory.
    "e",
    "eval",
    "evaluate",
    "evaluation",
    "evaluar",
    "evaluacion",
}
_HELP_ALIASES = {"?", "h", "help", "ayuda"}
_QUIT_ALIASES = {"q", "quit", "exit", "salir"}
