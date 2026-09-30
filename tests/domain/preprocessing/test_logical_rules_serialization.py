import pytest
import pandas as pd
from backend.src.domain.preprocessing.logical_rules_serialization import (
    serialize_logical_rule_manager_to_dict,
    reconstruct_logical_rule_manager_from_dict,
    _encode_relationships,
    _decode_relationships,
    RuleManagerSerializationError,
    VERSION,
)
from backend.src.domain.preprocessing.logical_rules import (
    LogicalRuleManager,
    DateToAgeRule,
)

def test_encode_decode_relationships_none():
    """``_encode_relationships`` should return ``None`` for ``None`` input
    and ``_decode_relationships`` should round‑trip back to ``None``.
    """
    assert _encode_relationships(None) is None
    assert _decode_relationships(None) is None
def test_encode_decode_relationships_basic():
    """Encode a simple relationship mapping and decode it back.
    The format is ``{(child, parent): [(fk, pk), ...]}``.
    """
    rel = {("orders", "customers"): [("customer_id", "id")], ("items", "orders"): [("order_id", "id")]}  # type: ignore
    encoded = _encode_relationships(rel)
    # The encoded representation is a list of lists.
    assert isinstance(encoded, list)
    decoded = _decode_relationships(encoded)
    assert decoded == rel
def test_round_trip_serialization_simple_manager():
    """Serialize a ``LogicalRuleManager`` with a simple rule and reconstruct it.
    The reconstructed manager should be equivalent to the original one.
    """
    # Create a trivial rule instance.
    rule = DateToAgeRule(
        table_origin="source",
        table_target="target",
        origin_col="birth_date",
        reference_date_col="sometime",
        aux_col="age",
        drop_origin=False,
    )
    manager = LogicalRuleManager(
        rules=[rule],
        relationships=None,
        rejection_sampling_config={},
        date_formats={},
    )
    payload = serialize_logical_rule_manager_to_dict(manager)
    assert payload["version"] == VERSION
    # Reconstruct should produce an equivalent manager.
    reconstructed = reconstruct_logical_rule_manager_from_dict(payload)
    # Compare simple attributes.
    assert reconstructed.rejection_sampling_config == manager.rejection_sampling_config
    assert reconstructed.date_formats == manager.date_formats
    assert reconstructed.relationships == manager.relationships
    # Rules list should contain a rule of the same type with matching fields.
    assert len(reconstructed.rules) == 1
    recon_rule = reconstructed.rules[0]
    assert isinstance(recon_rule, DateToAgeRule)
    assert recon_rule.table_origin == rule.table_origin
    assert recon_rule.table_target == rule.table_target
    assert recon_rule.origin_col == rule.origin_col
    assert recon_rule.aux_col == rule.aux_col
    assert recon_rule.reference_date_col == rule.reference_date_col
    assert reconstructed.relationships is None
    assert reconstructed.rejection_sampling_config == {}
    assert reconstructed.date_formats == {}
def test_reconstruct_invalid_payload_type():
    """Passing a non‑dict payload should raise ``RuleManagerSerializationError``.
    """
    with pytest.raises(RuleManagerSerializationError) as exc:
        reconstruct_logical_rule_manager_from_dict([1, 2, 3])
    assert "Top-level payload must be an object" in str(exc.value)
def test_reconstruct_unsupported_version():
    """If the version in the payload does not match ``VERSION`` a error is raised.
    """
    payload = {
        "version": VERSION + 1,
        "rules": [],
        "relationships": None,
        "rejection_sampling_config": {},
        "date_formats": {},
    }
    with pytest.raises(RuleManagerSerializationError) as exc:
        reconstruct_logical_rule_manager_from_dict(payload)
    assert "Unsupported rule manager version" in str(exc.value)
