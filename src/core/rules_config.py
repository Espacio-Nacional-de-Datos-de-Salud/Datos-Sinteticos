"""Rule configuration: registry and YAML loader for logical rules.

Centralizes the rule type map and config parsing that were previously
split between config/general_config.py and src/core/utils.py, removing
the circular dependency (config -> src).
"""

import yaml

from src.core.logging_config import get_logger
from src.core.preprocessing.logical_rules import (
    DateInequalityRule,
    ForeignKeysConsistencyRule,
    LogicalRule,
    NumericInequalityRule,
    SemanticProportionalConsistencyRule,
    SemanticRankingConsistencyRule,
)

logger = get_logger(__name__)

RULE_MAP: dict[str, type[LogicalRule]] = {
    "foreign_keys_consistency_rule": ForeignKeysConsistencyRule,
    "date_inequality": DateInequalityRule,
    "numeric_inequality": NumericInequalityRule,
    "semantic_ranking_consistency": SemanticRankingConsistencyRule,
    "semantic_proportional_consistency": SemanticProportionalConsistencyRule,
}


def extract_rules_from_config(config_path: str) -> list[LogicalRule]:
    """Load logical rules from a YAML configuration file.

    Parses the YAML and instantiates LogicalRule subclasses according to
    the ``type`` field in each entry matched against ``RULE_MAP``.

    Args:
        config_path: Path to the YAML file with rule definitions.

    Returns:
        List of instantiated LogicalRule objects.
    """
    with open(config_path) as f:
        config_data = yaml.safe_load(f)

    extracted_rules: list[LogicalRule] = []

    for entry in config_data.get("rules", []):
        rule_type = entry.pop("type")

        if rule_type in RULE_MAP:
            try:
                rule_instance = RULE_MAP[rule_type](**entry)
                extracted_rules.append(rule_instance)
            except (ValueError, TypeError) as e:
                logger.error(
                    "Invalid configuration for rule type '%s': %s. Skipping.", rule_type, e
                )
        else:
            logger.warning("Rule type '%s' not recognized. Skipping.", rule_type)

    return extracted_rules
