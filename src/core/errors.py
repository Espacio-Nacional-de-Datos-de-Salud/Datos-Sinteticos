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
