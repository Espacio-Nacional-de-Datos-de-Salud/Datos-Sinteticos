"""Rule configuration: registry and YAML loader for logical rules.

Centralizes the rule type map and config parsing that were previously
split between the general config module and src/core/utils.py, removing
the circular dependency (config -> src).
"""

from dataclasses import dataclass
from typing import Any

import yaml
from backend.src.core.logging_config import get_logger
from backend.src.core.preprocessing.logical_rules import (
    DateInequalityRule,
    DateToAgeRule,
    ForeignKeysConsistencyRule,
    LogicalRule,
    NumericBucketRule,
    NumericInequalityRule,
    NumericThresholdRule,
    SemanticProportionalConsistencyRule,
    SemanticRankingConsistencyRule,
)

logger = get_logger(__name__)

RULE_MAP: dict[str, type[LogicalRule]] = {
    "foreign_keys_consistency_rule": ForeignKeysConsistencyRule,
    "date_inequality": DateInequalityRule,
    "date_to_age": DateToAgeRule,
    "numeric_inequality": NumericInequalityRule,
    "numeric_threshold": NumericThresholdRule,
    "numeric_bucket": NumericBucketRule,
    "semantic_ranking_consistency": SemanticRankingConsistencyRule,
    "semantic_proportional_consistency": SemanticProportionalConsistencyRule,
}


@dataclass(frozen=True)
class RejectionSamplingConfig:
    """Configuration for rejection sampling during simulation."""

    max_attempts: int = 5
    overgenerate_factor: float = 2.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "max_attempts": self.max_attempts,
            "overgenerate_factor": self.overgenerate_factor,
        }


def _extract_rejection_sampling_config(config_data: dict) -> RejectionSamplingConfig:
    config = config_data.get("rejection_sampling", {}) or {}
    max_attempts = int(config.get("max_attempts", RejectionSamplingConfig.max_attempts))
    overgenerate_factor = float(
        config.get("overgenerate_factor", RejectionSamplingConfig.overgenerate_factor)
    )
    if max_attempts < 1:
        logger.warning("rejection_sampling.max_attempts < 1. Defaulting to 1.")
        max_attempts = 1
    if overgenerate_factor < 1.0:
        logger.warning("rejection_sampling.overgenerate_factor < 1. Defaulting to 1.0.")
        overgenerate_factor = 1.0
    return RejectionSamplingConfig(
        max_attempts=max_attempts, overgenerate_factor=overgenerate_factor
    )


def extract_rules_and_rejection_config(
    config_path: str,
) -> tuple[list[LogicalRule], RejectionSamplingConfig]:
    """Load logical rules and rejection sampling config from YAML."""
    with open(config_path) as f:
        config_data = yaml.safe_load(f) or {}

    extracted_rules: list[LogicalRule] = []

    for entry in config_data.get("rules", []):
        rule_entry = dict(entry)
        rule_type = rule_entry.pop("type")

        if rule_type in RULE_MAP:
            try:
                rule_instance = RULE_MAP[rule_type](**rule_entry)
                extracted_rules.append(rule_instance)
            except (ValueError, TypeError) as e:
                logger.error(
                    "Invalid configuration for rule type '%s': %s. Skipping.", rule_type, e
                )
        else:
            logger.warning("Rule type '%s' not recognized. Skipping.", rule_type)

    rejection_config = _extract_rejection_sampling_config(config_data)
    return extracted_rules, rejection_config


def extract_rules_from_config(config_path: str) -> list[LogicalRule]:
    """Load logical rules from a YAML configuration file.

    Parses the YAML and instantiates LogicalRule subclasses according to
    the ``type`` field in each entry matched against ``RULE_MAP``.
    """
    rules, _ = extract_rules_and_rejection_config(config_path)
    return rules
