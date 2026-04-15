"""Orchestration of the data preprocessing pipeline for synthesis.

Coordinates data cleaning, metadata validation, application of preprocessing
logical rules, and profile generation. Integrates multiple
components (DataCleaner, MetadataExtractor, MetadataValidator, MetadataFormatter,
LogicalRuleManager) into a coherent flow that prepares raw data to train
the synthesis model.
"""

from typing import Any

import pandas as pd

from src.core.preprocessing.data_cleaner import DataCleaner
from src.core.preprocessing.logical_rules import LogicalRuleManager
from src.core.preprocessing.metadata_extractor import MetadataExtractor
from src.core.preprocessing.metadata_formatter import MetadataFormatter
from src.core.preprocessing.profiling import generate_profile_report
from src.core.preprocessing.utils import (
    assign_default_context_keys,
    format_relationships,
    infer_foreign_keys_consistency_rules,
)


class DataPreprocessor:
    """Prepares raw data for training through cleaning and metadata extraction.

    Encapsulates the whole transformation flow: initial data cleaning, detection of
    relationships and column types, optional interactive metadata validation,
    application of logical rules, and data profile generation. Coordinates multiple
    components to ensure data is ready for the synthesis engine.

    Args:
        data_dict (dict[str, pd.DataFrame]): Dictionary of raw tables
            {table_name: dataframe}. It may contain multiple relational tables.
            detected metadata (relationships and column types). If False, it
            automatically accepts extracted metadata. Defaults to True.

    Attributes:
        raw_data_dict (dict[str, pd.DataFrame]): Original unmodified data.
        processed_data_dict (dict[str, pd.DataFrame]): Data after processing.
        metadata (dict): Metadata extracted and formatted for the synthesis engine.
        rule_manager (LogicalRuleManager): Pre- and post-synthesis logical rule manager.
    """

    def __init__(self, data_dict: dict[str, pd.DataFrame]) -> None:
        """Initializes the preprocessor with a set of raw tables.

        Args:
            data_dict (dict[str, pd.DataFrame]): Dictionary of raw tables
                {table_name: dataframe}.
        """
        self.raw_data_dict = data_dict
        self.processed_data_dict = {name: df.copy() for name, df in data_dict.items()}
        self.metadata = {}
        self.rule_manager = LogicalRuleManager()
        self.relationships: dict = {"pks": {}, "fks": []}
        self.encoding_types: dict = {}

    def run(
        self, run_data_profiling: bool = False
    ) -> tuple[dict[str, pd.DataFrame], dict, LogicalRuleManager, Any | None]:
        """
        Runs the complete preprocessing pipeline.

        1. Data cleaning (DataCleaner).
        2. Metadata management:
            - Relationship and data-type extraction (MetadataExtractor).
            - Metadata formatting for the synthesis engine (MetadataFormatter).
        3. PRE logical-rule application (data transformation).
        4. Profiling (opcional).

        Args:
            run_data_profiling (bool): If True, generates an HTML data report.

        Returns:
            tuple:
                - Processed data.
                - Metadata (JSON dict).
                - RuleManager.
                - Profiling object (or None).

        Example:
            >>> preprocessor = DataPreprocessor(raw_data_dict)
            >>> processed_data, metadata, rule_manager, data_profiles = preprocessor.run(
            ...     run_data_profiling=True
            ... )
        """
        cleaned_data = DataCleaner(self.raw_data_dict).run()

        metadata_extractor = MetadataExtractor(cleaned_data)
        relationships = {"pks": metadata_extractor.extract_primary_keys(), "fks": []}

        relationships["fks"] = metadata_extractor.extract_foreign_keys(relationships["pks"])
        relationships = assign_default_context_keys(relationships)
        self.add_automatic_contextual_fk_propagation_rules(relationships)

        engineered_data = self.rule_manager.apply_all_pre(
            data_dict=cleaned_data, relationships=format_relationships(relationships)
        )

        encoding_types = MetadataExtractor(engineered_data).extract_encoding_types()
        metadata = MetadataFormatter(engine_name="mostly").format(
            data_dfs=engineered_data,
            relationships_data=relationships,
            types_data=encoding_types,
        )

        data_profiles = generate_profile_report(engineered_data) if run_data_profiling else None

        self.processed_data_dict = engineered_data
        self.metadata = metadata
        self.relationships = relationships
        self.encoding_types = encoding_types

        return engineered_data, metadata, self.rule_manager, data_profiles

    def add_automatic_contextual_fk_propagation_rules(self, relationships: dict) -> None:
        """Automatically adds logical rules to keep contextual foreign keys consistent.

        Analyzes relationships between tables and generates rules that ensure values
        of foreign keys marked as contextual are propagated correctly across
        related tables during synthesis. This helps maintain referential
        consistency in generated synthetic data.
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
            self.rule_manager.add_rule(inferred_rule)
            existing_rule_keys.add(inferred_key)
