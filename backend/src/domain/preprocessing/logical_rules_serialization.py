"""JSON serialization for ``LogicalRuleManager``.

Replaces the legacy ``pickle.dump``/``pickle.load`` of ``rule_manager.pkl``.
Pickle deserialization of an attacker-controlled file is RCE; restricting
on-disk artifacts to a typed JSON schema removes that risk.

The wire format is:

    {
        "version": 1,
        "rules": [{"__type__": "<RuleClass>", ...fields}, ...],
        "relationships": [
            [[child, parent], [[fk_col, pk_col], ...]],
            ...
        ] | null,
    }

Tuple keys, sets, and ``pd.Timestamp`` values are encoded explicitly so the
output is round-trippable.
"""

from __future__ import annotations

import dataclasses
from enum import Enum
from typing import Any

import numpy as np
import pandas as pd
from backend.src.domain.preprocessing import logical_rules as _rules_module
from backend.src.domain.preprocessing.logical_rules import LogicalRule, LogicalRuleManager

VERSION = 1

# Concrete rule classes that may appear on disk. Abstract bases are excluded.
_RULE_CLASSES: dict[str, type[LogicalRule]] = {
    cls.__name__: cls
    for cls in (
        _rules_module.DateToAgeRule,
        _rules_module.DateCompositionRule,
        _rules_module.NumericThresholdRule,
        _rules_module.NumericBucketRule,
        _rules_module.ForeignKeysConsistencyRule,
        _rules_module.DateInequalityRule,
        _rules_module.NumericInequalityRule,
        _rules_module.SemanticProportionalConsistencyRule,
        _rules_module.SemanticRankingConsistencyRule,
    )
}


class RuleManagerSerializationError(ValueError):
    """Raised when an on-disk rule manager file cannot be parsed."""


def _encode_value(value: Any) -> Any:
    if isinstance(value, pd.Timestamp):
        return {"__ts__": value.isoformat()}
    if isinstance(value, Enum):
        return {"__enum__": [type(value).__name__, value.name]}
    if isinstance(value, set):
        return {"__set__": [_encode_value(v) for v in sorted(value, key=repr)]}
    if isinstance(value, tuple):
        return {"__tuple__": [_encode_value(v) for v in value]}
    if isinstance(value, list):
        return [_encode_value(v) for v in value]
    if isinstance(value, dict):
        # Use a list of pairs so non-string keys round-trip cleanly.
        return {"__dict__": [[_encode_value(k), _encode_value(v)] for k, v in value.items()]}
    if isinstance(value, np.generic):
        return value.item()
    return value


def _decode_value(value: Any) -> Any:
    if isinstance(value, dict) and len(value) == 1:
        (tag,) = value.keys()
        payload = value[tag]
        if tag == "__ts__":
            return pd.Timestamp(payload)
        if tag == "__enum__":
            enum_class_name, enum_member_name = payload
            enum_class = getattr(_rules_module, enum_class_name, None)
            if enum_class is None:
                raise RuleManagerSerializationError(f"Unknown enum class: {enum_class_name!r}")
            return enum_class[enum_member_name]
        if tag == "__set__":
            return {_decode_value(v) for v in payload}
        if tag == "__tuple__":
            return tuple(_decode_value(v) for v in payload)
        if tag == "__dict__":
            return {_decode_value(k): _decode_value(v) for k, v in payload}
    if isinstance(value, list):
        return [_decode_value(v) for v in value]
    if isinstance(value, dict):
        return {k: _decode_value(v) for k, v in value.items()}
    return value


def _encode_rule(rule: LogicalRule) -> dict[str, Any]:
    payload: dict[str, Any] = {"__type__": type(rule).__name__}
    for f in dataclasses.fields(rule):
        payload[f.name] = _encode_value(getattr(rule, f.name))
    return payload


def _decode_rule(payload: dict[str, Any]) -> LogicalRule:
    type_name = payload.get("__type__")
    cls = _RULE_CLASSES.get(type_name)
    if cls is None:
        raise RuleManagerSerializationError(f"Unknown rule type: {type_name!r}")

    init_kwargs: dict[str, Any] = {}
    post_init_attrs: dict[str, Any] = {}
    for f in dataclasses.fields(cls):
        if f.name not in payload:
            continue
        decoded = _decode_value(payload[f.name])
        if f.init:
            init_kwargs[f.name] = decoded
        else:
            post_init_attrs[f.name] = decoded

    rule = cls(**init_kwargs)
    for name, val in post_init_attrs.items():
        setattr(rule, name, val)
    return rule


def _encode_relationships(
    relationships: dict[tuple[str, str], list[tuple[str, str]]] | None,
) -> Any:
    if relationships is None:
        return None
    return [[list(key), [list(pair) for pair in value]] for key, value in relationships.items()]


def _decode_relationships(payload: Any) -> dict[tuple[str, str], list[tuple[str, str]]] | None:
    if payload is None:
        return None
    return {tuple(key): [tuple(pair) for pair in value] for key, value in payload}


def serialize_logical_rule_manager_to_dict(manager: LogicalRuleManager) -> dict[str, Any]:
    """Serialize a ``LogicalRuleManager`` to a JSON-compatible dict."""
    return {
        "version": VERSION,
        "rules": [_encode_rule(rule) for rule in manager.rules],
        "relationships": _encode_relationships(manager.relationships),
        "rejection_sampling_config": _encode_value(manager.rejection_sampling_config),
        "date_formats": _encode_value(manager.date_formats),
    }


def reconstruct_logical_rule_manager_from_dict(payload: dict[str, Any]) -> LogicalRuleManager:
    """Reconstruct a ``LogicalRuleManager`` from a previously-serialized dict."""
    if not isinstance(payload, dict):
        raise RuleManagerSerializationError("Top-level payload must be an object.")
    version = payload.get("version")
    if version != VERSION:
        raise RuleManagerSerializationError(
            f"Unsupported rule manager version: {version!r} (expected {VERSION})."
        )
    rules = [_decode_rule(item) for item in payload.get("rules", [])]
    relationships = _decode_relationships(payload.get("relationships"))
    rejection_sampling_config = _decode_value(payload.get("rejection_sampling_config", {}))
    date_formats = _decode_value(payload.get("date_formats", {})) or {}
    return LogicalRuleManager(
        rules=rules,
        relationships=relationships,
        rejection_sampling_config=rejection_sampling_config,
        date_formats=date_formats,
    )
