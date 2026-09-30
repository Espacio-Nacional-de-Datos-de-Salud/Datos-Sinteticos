"""Endpoints for the rule library (presets).

A rule preset is a user-saved snapshot of ``rules.yaml`` kept for reuse,
independent of any BRC run. The Reglas de negocio page saves the current rule
set here and lets the user load any preset back into the live editor. Filesystem
work lives in ``sessions.rule_presets``; this router just maps HTTP status codes.
"""

from pathlib import Path

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import PlainTextResponse

from backend.src.api.schemas.rule_presets import (
    RulePresetCreate,
    RulePresetDeletedResponse,
    RulePresetRename,
    RulePresetSummary,
)
from backend.src.sessions.configs import ConfigParseError
from backend.src.sessions.rule_presets import (
    delete_rule_preset,
    list_rule_presets,
    rename_rule_preset,
    rule_preset_rules_path,
    save_rule_preset,
)

router = APIRouter(prefix="/rule-presets", tags=["RulePresets"])


@router.get("/", response_model=list[RulePresetSummary])
def list_presets() -> list[dict]:
    return list_rule_presets()


@router.post("/", response_model=RulePresetSummary, status_code=status.HTTP_201_CREATED)
def create_preset(request: RulePresetCreate) -> dict:
    try:
        return save_rule_preset(request.content, request.name, request.excluded_columns)
    except ConfigParseError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid rules YAML: {exc}") from exc


@router.get("/{preset_id}/rules", response_class=PlainTextResponse)
def get_preset_rules(preset_id: str) -> str:
    try:
        path = rule_preset_rules_path(preset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Path(path).read_text(encoding="utf-8")


@router.patch("/{preset_id}/name", response_model=RulePresetSummary)
def patch_preset_name(preset_id: str, body: RulePresetRename) -> dict:
    try:
        return rename_rule_preset(preset_id, body.name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{preset_id}", response_model=RulePresetDeletedResponse)
def delete_preset(preset_id: str) -> RulePresetDeletedResponse:
    try:
        delete_rule_preset(preset_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RulePresetDeletedResponse(preset_id=preset_id)
