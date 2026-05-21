"""Synthetic data pipeline-specific exceptions.

Each exception carries a descriptive message that main.py logs when caught.
"""


class DataLoadError(Exception):
    """No valid table could be loaded."""


class MetadataNotFoundError(Exception):
    """Metadata file was not found."""


class RuleManagerNotFoundError(Exception):
    """RuleManager file was not found."""


class TableMetadataMissingError(Exception):
    """There is no metadata for a required table."""


class RelationshipNotDefinedError(Exception):
    """There is no defined relationship between two tables."""


class SimulationNotFoundError(Exception):
    """Simulation folder was not found."""


class SimCardNotFoundError(Exception):
    """sim_card.json file was not found in a simulation folder."""


class ModelCardNotFoundError(Exception):
    """model_card.json file was not found in a model folder."""


class DataSourceNotFoundError(Exception):
    """Original data sources referenced by a model card are missing or unreadable."""


class ModelNotFoundError(Exception):
    """Model folder was not found."""


class InspectionNotFoundError(Exception):
    """Inspection folder was not found."""


class InspectionProfilingNotFoundError(Exception):
    """Profiling reports subfolder was not found (or empty) inside an inspection."""


class InspectionProcessedDataNotFoundError(Exception):
    """Processed-data subfolder was not found (or empty) inside an inspection."""


class PipelineNotFoundError(Exception):
    """Pipeline folder was not found."""


class EvaluationNotFoundError(Exception):
    """Evaluation subfolder was not found inside a simulation."""


class SyntheticDataNotFoundError(Exception):
    """Synthetic data subfolder was not found inside a simulation."""


class GeneratorEssentialsIncompleteError(Exception):
    """A model folder is missing one or more files required to simulate."""


class RuleSuperimpositionError(Exception):
    """A new logical rule overlaps with an existing one in the same manager."""


class RuleConcatenationError(Exception):
    """A new logical rule creates a circular dependency with existing rules."""


class ColumnNotFoundError(Exception):
    """A logical rule references a column that does not exist in the target table."""
