import textwrap
import yaml
import pytest
from unittest.mock import patch, mock_open

from backend.src.domain.rules_config import (
    RejectionSamplingConfig,
    _extract_rejection_sampling_config,
    extract_rules_and_rejection_config,
    extract_rules_from_config,
)
from backend.src.domain.preprocessing.logical_rules import (
    NumericThresholdRule,
    DateInequalityRule,
)

# -----------------------------------------------------------------------------
# Unit Tests
# -----------------------------------------------------------------------------

def test_rejection_sampling_config_as_dict():
    """Test serialization of RejectionSamplingConfig."""
    config = RejectionSamplingConfig(max_attempts=10, overgenerate_factor=3.5)
    assert config.as_dict() == {"max_attempts": 10, "overgenerate_factor": 3.5}

def test_extract_rejection_sampling_config_defaults():
    """Test extraction uses correct default values."""
    config_data = {}
    config = _extract_rejection_sampling_config(config_data)
    assert config.max_attempts == 5
    assert config.overgenerate_factor == 2.0

def test_extract_rejection_sampling_config_custom():
    """Test extraction uses provided valid values."""
    config_data = {"rejection_sampling": {"max_attempts": 10, "overgenerate_factor": 3.0}}
    config = _extract_rejection_sampling_config(config_data)
    assert config.max_attempts == 10
    assert config.overgenerate_factor == 3.0

@patch("backend.src.domain.rules_config.logger")
def test_extract_rejection_sampling_config_invalid_clamps(mock_logger):
    """Test extraction clamps invalid low values to their minimum allowed limits."""
    config_data = {"rejection_sampling": {"max_attempts": 0, "overgenerate_factor": 0.5}}
    config = _extract_rejection_sampling_config(config_data)
    
    assert config.max_attempts == 1
    assert config.overgenerate_factor == 1.0
    
    # Verify the logger warned twice about the clamping
    warnings = [call.args[0] for call in mock_logger.warning.call_args_list]
    assert any("max_attempts < 1" in w for w in warnings)
    assert any("overgenerate_factor < 1" in w for w in warnings)

@patch("backend.src.domain.rules_config.yaml.safe_load")
@patch("builtins.open", new_callable=mock_open)
def test_extract_rules_and_rejection_config_success(mock_file, mock_yaml):
    """Test extraction logic builds rule objects and rejection configs."""
    mock_yaml.return_value = {
        "rules": [
            {
                "type": "numeric_threshold",
                "table_origin": "patients",
                "origin_col": "age",
                "table_target": "patients",
                "aux_col": "is_adult",
                "threshold": 18,
            }
        ],
        "rejection_sampling": {"max_attempts": 2}
    }
    
    rules, rejection_config = extract_rules_and_rejection_config("dummy_path.yml")
    assert len(rules) == 1
    assert isinstance(rules[0], NumericThresholdRule)
    assert rules[0].threshold == 18
    assert rules[0].origin_col == "age"
    
    assert rejection_config.max_attempts == 2

@patch("backend.src.domain.rules_config.logger")
@patch("backend.src.domain.rules_config.yaml.safe_load")
@patch("builtins.open", new_callable=mock_open)
def test_extract_rules_and_rejection_config_invalid_rule(mock_file, mock_yaml, mock_logger):
    """Test extraction logic skips rules with invalid configuration or unknown types."""
    mock_yaml.return_value = {
        "rules": [
            {
                "type": "numeric_threshold",
                # missing required params like origin_col and threshold
            },
            {
                "type": "unknown_rule_type"
            }
        ]
    }
    
    rules, _ = extract_rules_and_rejection_config("dummy_path.yml")
    assert len(rules) == 0
    
    # Check that error is logged for bad config of known type
    error_calls = [call.args[0] for call in mock_logger.error.call_args_list]
    assert any("Invalid configuration" in e for e in error_calls)
    
    # Check that warning is logged for unknown type
    warn_calls = [call.args[0] for call in mock_logger.warning.call_args_list]
    assert any("not recognized" in w for w in warn_calls)


# -----------------------------------------------------------------------------
# Integration Tests
# -----------------------------------------------------------------------------

def test_extract_rules_integration(tmp_path):
    """Integration test to load multiple valid configurations from a real file."""
    config_yaml = textwrap.dedent("""
    rules:
      - type: numeric_threshold
        origin_col: score
        aux_col: passed
        threshold: 50.0
        operator: '>='
      - type: date_inequality
        target_col: end_date
        origin_col: start_date
        constraint_operator: '>='

    rejection_sampling:
      max_attempts: 10
      overgenerate_factor: 2.5
    """)
    config_file = tmp_path / "rules_config.yml"
    config_file.write_text(config_yaml)
    
    rules, rejection = extract_rules_and_rejection_config(str(config_file))
    
    assert len(rules) == 2
    assert isinstance(rules[0], NumericThresholdRule)
    assert rules[0].origin_col == "score"
    assert rules[0].threshold == 50.0
    
    assert isinstance(rules[1], DateInequalityRule)
    assert rules[1].target_col == "end_date"
    assert rules[1].origin_col == "start_date"
    
    assert rejection.max_attempts == 10
    assert rejection.overgenerate_factor == 2.5

@patch("backend.src.domain.rules_config.logger")
def test_extract_rules_integration_with_unknown_rule(mock_logger, tmp_path):
    """Integration test to load multiple valid configurations from a real file."""
    config_yaml = textwrap.dedent("""
    rules:
      - type: numeric_threshold
        origin_col: score
        aux_col: passed
        threshold: 50.0
        operator: '>='
      - type: unknown_rule_type
        target_col: end_date
        origin_col: start_date
        constraint_operator: '>='

    rejection_sampling:
      max_attempts: 10
      overgenerate_factor: 2.5
    """)
    config_file = tmp_path / "rules_config.yml"
    config_file.write_text(config_yaml)
    
    rules, rejection = extract_rules_and_rejection_config(str(config_file))
    
    assert len(rules) == 1
    assert isinstance(rules[0], NumericThresholdRule)
    assert rules[0].origin_col == "score"
    assert rules[0].threshold == 50.0
    
    assert rejection.max_attempts == 10
    assert rejection.overgenerate_factor == 2.5

    # Check the warning was logged for the unknown rule type
    warn_calls = [call.args[0] for call in mock_logger.warning.call_args_list]
    assert any("not recognized" in w for w in warn_calls)

def test_extract_rules_from_config_integration(tmp_path):
    """Integration test testing the wrapper that only returns rules."""
    config_yaml = textwrap.dedent("""
    rules:
      - type: numeric_threshold
        origin_col: age
        aux_col: is_adult
        threshold: 18
    """)
    config_file = tmp_path / "rules_config.yml"
    config_file.write_text(config_yaml)
    
    rules = extract_rules_from_config(str(config_file))
    assert len(rules) == 1
    assert isinstance(rules[0], NumericThresholdRule)
    assert rules[0].origin_col == "age"

def test_extract_rules_malformed_yaml(tmp_path):
    """Test that malformed YAML propagates a parse error."""
    malformed = "rules:\n  - type: numeric_threshold\n    origin_col: age\n    aux_col: is_adult\n  bad_indent\n: broken"
    config_file = tmp_path / "bad.yml"
    config_file.write_text(malformed)

    with pytest.raises(yaml.YAMLError):
        extract_rules_and_rejection_config(str(config_file))
