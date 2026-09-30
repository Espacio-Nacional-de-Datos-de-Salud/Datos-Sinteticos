"""Pydantic schemas for the rule library (presets) API."""

from pydantic import BaseModel, Field


class RulePresetSummary(BaseModel):
    """Catalogue entry for a saved rule preset."""

    preset_id: str
    preset_name: str = ""
    timestamp: str = ""
    timestamp_ms: int | None = None
    rules_count: int = 0
    # Reglas-de-negocio column deletions captured with the rule set, so loading a
    # preset also restores the columns marked for removal. Schema-specific, like
    # the rules themselves.
    excluded_columns: dict[str, list[str]] = {}


class RulePresetCreate(BaseModel):
    """Body of ``POST /rule-presets``."""

    content: str = Field(
        ...,
        description="Rules YAML text to snapshot (typically the current rules.yaml).",
    )
    name: str | None = Field(
        default=None,
        max_length=100,
        description="Optional functional name. Auto-generated when blank.",
    )
    excluded_columns: dict[str, list[str]] = Field(
        default_factory=dict,
        description="Column deletions (rules_excluded_columns) to bundle with the rule set.",
    )


class RulePresetRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)


class RulePresetDeletedResponse(BaseModel):
    preset_id: str
    deleted: bool = True
