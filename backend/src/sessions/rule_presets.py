"""Rule library (presets) flow.

A *rule preset* is a user-saved snapshot of ``rules.yaml`` kept for reuse,
independent of any BRC run. The user crafts a rule set in the live editor and
saves it to the library with an optional functional name; later they can load it
back into the live editor (on any upload) and iterate from there.

Each preset lives in its own folder under ``RULES_LIBRARY_DIR``:

    outputs/rules_library/preset_<ts>/
        preset_card.json    Descriptor: id, name, timestamp(s), rules_count.
        rules.yaml          Frozen copy of the rules YAML at save time.

Storage mirrors the run catalogues (folder + card.json) but presets are not
runs — they carry no status/progress. Read/write helpers here are consumed by
``api.routers.rule_presets``.
"""

import os
import shutil

import pandas as pd
import yaml

from backend.src.config.general import (
    RULES_LIBRARY_DIR,
    RULES_PRESET_CARD_FILENAME,
    RULES_PRESET_FOLDER_PREFIX,
    RULES_PRESET_RULES_FILENAME,
    refresh_run_timestamp,
)
from backend.src.infrastructure.logging_config import get_logger
from backend.src.runs.card_io import read_json, write_json
from backend.src.sessions.configs import validate_config_content_syntax

logger = get_logger(__name__)


def _count_rules(content: str) -> int:
    """Return the number of entries under ``rules:`` in a rules YAML string."""
    try:
        parsed = yaml.safe_load(content) or {}
    except yaml.YAMLError:
        return 0
    rules = parsed.get("rules") if isinstance(parsed, dict) else None
    return len(rules) if isinstance(rules, list) else 0


def _default_preset_name() -> str:
    """Human-friendly auto name used when the user leaves the name blank."""
    return f"Reglas {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}"


def _new_preset_id() -> str:
    """Allocate a unique, timestamped preset id (folder name)."""
    base = f"{RULES_PRESET_FOLDER_PREFIX}_{refresh_run_timestamp()}"
    preset_id = base
    suffix = 1
    while os.path.isdir(os.path.join(RULES_LIBRARY_DIR, preset_id)):
        preset_id = f"{base}_{suffix}"
        suffix += 1
    return preset_id


def _preset_dir(preset_id: str) -> str:
    target = os.path.join(RULES_LIBRARY_DIR, preset_id)
    if not os.path.isdir(target):
        raise FileNotFoundError(f"Rule preset not found: {preset_id}")
    return target


def _card_path(preset_id: str) -> str:
    return os.path.join(RULES_LIBRARY_DIR, preset_id, RULES_PRESET_CARD_FILENAME)


def save_rule_preset(
    content: str,
    name: str | None = None,
    excluded_columns: dict[str, list[str]] | None = None,
) -> dict:
    """Persist a rules YAML string as a new library preset.

    Args:
        content: The rules YAML text to snapshot (typically the live
            ``rules.yaml``).
        name: Optional functional name. Auto-generated when blank.
        excluded_columns: Reglas-de-negocio column deletions to bundle with the
            rule set so loading the preset also restores the removed columns.

    Returns:
        The preset card dict.

    Raises:
        ConfigParseError: If ``content`` is not valid YAML.
    """
    validate_config_content_syntax(content, ".yaml")

    preset_id = _new_preset_id()
    preset_dir = os.path.join(RULES_LIBRARY_DIR, preset_id)
    os.makedirs(preset_dir, exist_ok=True)

    with open(
        os.path.join(preset_dir, RULES_PRESET_RULES_FILENAME), "w", encoding="utf-8"
    ) as handle:
        handle.write(content)

    preset_name = name.strip() if name and name.strip() else _default_preset_name()
    timestamp = refresh_run_timestamp()
    card = {
        "preset_id": preset_id,
        "preset_name": preset_name,
        "timestamp": timestamp,
        "timestamp_ms": int(pd.Timestamp.utcnow().timestamp() * 1000),
        "rules_count": _count_rules(content),
        "excluded_columns": {
            t: list(cs) for t, cs in (excluded_columns or {}).items() if cs
        },
    }
    write_json(_card_path(preset_id), card)
    logger.info("Saved rule preset %s (%r, %d rules).", preset_id, preset_name, card["rules_count"])
    return card


def list_rule_presets() -> list[dict]:
    """Return every preset card on disk, newest first."""
    if not os.path.isdir(RULES_LIBRARY_DIR):
        return []
    out: list[dict] = []
    for entry in sorted(os.listdir(RULES_LIBRARY_DIR), reverse=True):
        card_path = os.path.join(RULES_LIBRARY_DIR, entry, RULES_PRESET_CARD_FILENAME)
        if not os.path.exists(card_path):
            continue
        try:
            out.append(read_json(card_path))
        except Exception as exc:
            logger.warning("Skipping unreadable rule-preset card '%s': %s", card_path, exc)
    return out


def load_rule_preset_card(preset_id: str) -> dict:
    card_path = _card_path(preset_id)
    if not os.path.exists(card_path):
        raise FileNotFoundError(f"Rule preset not found: {preset_id}")
    return read_json(card_path)


def rule_preset_rules_path(preset_id: str) -> str:
    """Return the path to a preset's rules YAML file."""
    path = os.path.join(_preset_dir(preset_id), RULES_PRESET_RULES_FILENAME)
    if not os.path.exists(path):
        raise FileNotFoundError(f"Rules file not found for preset: {preset_id}")
    return path


def rename_rule_preset(preset_id: str, new_name: str) -> dict:
    card = load_rule_preset_card(preset_id)
    card["preset_name"] = new_name.strip() or card.get("preset_name") or preset_id
    write_json(_card_path(preset_id), card)
    return card


def delete_rule_preset(preset_id: str) -> None:
    shutil.rmtree(_preset_dir(preset_id))
