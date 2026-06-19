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


class TrainingJobFailedError(Exception):
    """The Mostly AI training job finished in a non-successful state.

    Raised when the underlying job reports ``failed``/``canceled`` so callers
    surface the real failing step instead of a misleading downstream error
    (e.g. ``HTTP 400: Cannot export generator that is not trained``)."""


class InsufficientTrainingDataError(TrainingJobFailedError):
    """A table has too little data to train a usable model.

    Raised by the pre-flight check *before* a job starts, so the user gets a
    concise, actionable reason instead of an opaque engine crash deep inside
    training (e.g. ``batch_size should be a positive integer value, but got
    batch_size=0`` when a sequential table has too few subject rows). Subclasses
    :class:`TrainingJobFailedError` so existing failure handling still applies."""


class InvalidBatchSizeError(TrainingJobFailedError):
    """The configured batch size is too small to train.

    Raised by the pre-flight check when ``model_settings.batch_size`` is below
    the minimum the engine can use. MostlyAI halves the batch size for the
    validation split, so a value of 1 underflows to 0 and training crashes with
    ``batch_size should be a positive integer value, but got batch_size=0`` — no
    matter how much data is present. This is a property of the *setting*, not the
    data. Subclasses :class:`TrainingJobFailedError` so existing failure handling
    still applies."""


class UnsupportedTrainingConfigurationError(TrainingJobFailedError):
    """The requested training configuration hits a known engine limitation.

    Raised by the pre-flight check when the table layout plus model settings
    match a combination the engine cannot train (e.g. differential privacy on
    three or more related tables linked through context keys, which crashes
    inside Opacus/PyTorch). Subclasses :class:`TrainingJobFailedError` so
    existing failure handling still applies."""


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
