"""Helpers for recording modeling-mode intent without leaking local fields to MostlyAI."""

from __future__ import annotations

from typing import Any

_LOCAL_MODEL_SETTINGS = {
    "requested_modeling_mode",
    "modeling_mode",
    "entity_key",
    "time_column",
    # Per-table overrides are resolved locally (one merged config per table)
    # before handing settings to MostlyAI, which has no such concept.
    "per_table",
}


def backend_model_settings(model_settings: dict[str, Any]) -> dict[str, Any]:
    """Return model settings accepted by the MostlyAI backend."""
    return {key: value for key, value in model_settings.items() if key not in _LOCAL_MODEL_SETTINGS}


def build_modeling_configuration(
    model_settings: dict[str, Any],
    metadata: dict,
) -> dict[str, Any]:
    """Build a reportable modeling configuration from local model settings.

    The local SDK currently decides flat/sequential modeling from table metadata
    and relationships. We therefore keep the requested intent for lineage while
    leaving backend configuration untouched.
    """
    requested_mode = model_settings.get("requested_modeling_mode") or model_settings.get(
        "modeling_mode"
    )
    entity_key = model_settings.get("entity_key")
    time_column = model_settings.get("time_column")
    warnings: list[str] = []

    if requested_mode not in {None, "", "auto", "flat", "sequential"}:
        warnings.append(f"Unsupported requested_modeling_mode '{requested_mode}' ignored.")
        requested_mode = None

    column_names = {
        column.get("name")
        for table in metadata.get("tables", [])
        for column in table.get("columns", [])
        if isinstance(column, dict)
    }
    if entity_key and entity_key not in column_names:
        warnings.append(f"Configured entity_key '{entity_key}' was not found in metadata.")
    if time_column and time_column not in column_names:
        warnings.append(f"Configured time_column '{time_column}' was not found in metadata.")

    return {
        "requested_modeling_mode": requested_mode,
        "applied_modeling_mode": "backend_default",
        "detected_modeling_mode": metadata.get("detected_modeling_mode"),
        "entity_key": entity_key,
        "time_column": time_column,
        "backend_supports_manual_modeling_mode": False,
        "backend_manual_config_method": "not_supported",
        "backend_sequence_config_applied": False,
        "warnings": warnings,
    }
