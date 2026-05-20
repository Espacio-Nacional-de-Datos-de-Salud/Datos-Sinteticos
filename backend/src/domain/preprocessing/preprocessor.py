"""Orchestration of the data preprocessing pipeline for synthesis.

Coordinates data cleaning, metadata validation, application of preprocessing
logical rules, and profile generation. Integrates multiple
components (DataCleaner, MetadataExtractor, MetadataValidator, MetadataFormatter,
LogicalRuleManager) into a coherent flow that prepares raw data to train
the synthesis model.
"""

from dataclasses import dataclass
from typing import Any

import pandas as pd
from backend.src.infrastructure.logging_config import get_logger
from backend.src.domain.preprocessing.data_cleaner import DataCleaner
from backend.src.domain.preprocessing.logical_rules import LogicalRuleManager
from backend.src.domain.preprocessing.metadata_extractor import MetadataExtractor
from backend.src.domain.preprocessing.metadata_formatter import MetadataFormatter
from backend.src.domain.preprocessing.profiling import generate_profile_report
from backend.src.domain.preprocessing.utils import (
    assign_default_context_keys,
    format_relationships,
    infer_foreign_keys_consistency_rules,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class PreprocessResult:
    """Outputs of :meth:`DataPreprocessor.run`.

    Every value the caller might need is exposed here as a named field so data
    flow is explicit at every call site — no reaching into preprocessor
    attributes after ``run()``. ``rule_manager`` is the same instance the
    caller configured before ``run()``; it is included for convenience.
    """

    processed_data: dict[str, pd.DataFrame]
    metadata: dict
    relationships: dict
    encoding_types: dict
    rule_manager: LogicalRuleManager
    data_profiles: Any | None


class DataPreprocessor:
    """Prepares raw data for training through cleaning and metadata extraction.

    Encapsulates the whole transformation flow: initial data cleaning, detection of
    relationships and column types, optional interactive metadata validation,
    application of logical rules, and data profile generation. Coordinates multiple
    components to ensure data is ready for the synthesis engine.

    Args:
        data_dict (dict[str, pd.DataFrame]): Dictionary of raw tables
            {table_name: dataframe}. It may contain multiple relational tables.

    Attributes:
        raw_data_dict (dict[str, pd.DataFrame]): Original unmodified data.
        rule_manager (LogicalRuleManager): Pre- and post-synthesis logical rule
            manager. Callers may add rules to it before invoking :meth:`run`.
    """

    def __init__(self, data_dict: dict[str, pd.DataFrame]) -> None:
        """Initializes the preprocessor with a set of raw tables.

        Args:
            data_dict (dict[str, pd.DataFrame]): Dictionary of raw tables
                {table_name: dataframe}.
        """
        self.raw_data_dict = data_dict
        self.rule_manager = LogicalRuleManager()

    def run(
        self,
        run_data_profiling: bool = False,
        user_defined_relationships: dict | None = None,
        user_defined_types: dict | None = None,
    ) -> PreprocessResult:
        """Runs the complete preprocessing pipeline.

        1. Data cleaning (DataCleaner).
        2. Metadata management:
            - Relationship and data-type extraction (MetadataExtractor).
            - Metadata formatting for the synthesis engine (MetadataFormatter).
        3. PRE logical-rule application (data transformation).
        4. Profiling (optional).

        Args:
            run_data_profiling (bool): If True, generates an HTML data report.
            user_defined_relationships (dict | None): Pre-defined relationships to bypass detection.
            user_defined_types (dict | None): Pre-defined encoding types to bypass detection.

        Returns:
            PreprocessResult with named fields ``processed_data``, ``metadata``,
            ``relationships``, ``encoding_types``, ``rule_manager`` and
            ``data_profiles``.

        Example:
            >>> preprocessor = DataPreprocessor(raw_data_dict)
            >>> result = preprocessor.run(run_data_profiling=True)
            >>> result.processed_data, result.metadata
        """
        cleaned_data = DataCleaner(self.raw_data_dict).run()

        if user_defined_relationships is not None:
            relationships = user_defined_relationships
        else:
            metadata_extractor = MetadataExtractor(cleaned_data)
            relationships = {"pks": metadata_extractor.extract_primary_keys(), "fks": []}
            relationships["fks"] = metadata_extractor.extract_foreign_keys(relationships["pks"])
            relationships = assign_default_context_keys(relationships)

        self.add_automatic_contextual_fk_propagation_rules(relationships)

        engineered_data = self.rule_manager.apply_all_pre(
            data_dict=cleaned_data, relationships=format_relationships(relationships)
        )

        if user_defined_types is not None:
            encoding_types = user_defined_types
        else:
            encoding_types = MetadataExtractor(engineered_data).extract_encoding_types()

        metadata = MetadataFormatter(engine_name="mostly").format(
            data_dfs=engineered_data,
            relationships_data=relationships,
            types_data=encoding_types,
        )

        data_profiles = generate_profile_report(engineered_data) if run_data_profiling else None

        return PreprocessResult(
            processed_data=engineered_data,
            metadata=metadata,
            relationships=relationships,
            encoding_types=encoding_types,
            rule_manager=self.rule_manager,
            data_profiles=data_profiles,
        )

    def add_automatic_contextual_fk_propagation_rules(self, relationships: dict) -> None:
        """Automatically adds logical rules to keep contextual foreign keys consistent.

        Analyzes relationships between tables and generates rules that ensure values
        of foreign keys marked as contextual are propagated correctly across
        related tables during synthesis.

        Args:
            relationships (dict): Detected relationships structure with ``fks``.
        """
        existing_rule_keys = {
            (
                type(rule).__name__,
                getattr(rule, "table_target", None),
                getattr(rule, "table_origin", None),
                getattr(rule, "target_col", None),
                getattr(rule, "source_col", None),
            )
            for rule in self.rule_manager.rules
        }
        for inferred_rule in infer_foreign_keys_consistency_rules(relationships):
            inferred_key = (
                type(inferred_rule).__name__,
                inferred_rule.table_target,
                inferred_rule.table_origin,
                inferred_rule.target_col,
                inferred_rule.source_col,
            )
            if inferred_key in existing_rule_keys:
                continue
            if self.rule_manager.add_rule(inferred_rule):
                existing_rule_keys.add(inferred_key)
