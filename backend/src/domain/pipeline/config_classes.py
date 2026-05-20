"""Data models for the synthetic data pipeline."""

from dataclasses import dataclass, field

from backend.src.config.general import DEFAULT_SAMPLE_SIZE


@dataclass
class TrainStepConfig:
    """Configuration for a training step.

    A train step has two possible input sources:
      - ``files``: train from raw inputs (preprocessing runs implicitly).
      - ``inspection_id``: resume from a previously produced inspection session
        — handy when the user has manually edited relationships / encoding
        types on that inspection. When ``inspection_id`` is set, ``files`` is
        ignored.

    Attributes:
        files (list[str]): Paths to input data files or directories.
        inspection_id (str | None): When set, train resumes from this inspection
            instead of preprocessing raw files.
    """

    files: list[str] = field(default_factory=list)
    inspection_id: str | None = None


@dataclass
class SimulateStepConfig:
    """Configuration for a simulation step.

    Attributes:
        sample_size (int): Number of synthetic records to generate.
        model_id (str | None): Explicit model ID to use. If None and a train step
            precedes this in the same job, the trained model is used automatically.
        synthetic_data_file_format (str | None): Output format for generated data.
    """

    sample_size: int = DEFAULT_SAMPLE_SIZE
    model_id: str | None = None
    synthetic_data_file_format: str | None = None


@dataclass
class EvaluateStepConfig:
    """Configuration for an evaluation step.

    Attributes:
        real_data (list[str] | None): Advanced override — explicit paths to use
            as the real-data reference. Normally left as ``None``: the eval
            session auto-binds it to the model's preprocessed training data via
            :func:`backend.src.runs.catalog.models.resolve_model_real_data_paths`,
            which keeps the real and synthetic sides on the same post-rule
            schema (derived columns present, dropped columns absent).
        simulation_id (str | None): Explicit simulation ID to evaluate. If None and
            a simulate step precedes this in the same job, that simulation is used.
        model_id (str | None): Explicit model ID. If None, inferred from job context.
    """

    real_data: list[str] | None = None
    simulation_id: str | None = None
    model_id: str | None = None


@dataclass
class JobConfigOverrides:
    """Per-job configuration overrides.

    Allows each pipeline job to customise rules, Mostly AI hyperparameters,
    and general settings independently, instead of relying only on the
    global defaults.

    Attributes:
        rules_config (str | None): Path to a job-specific rules YAML file.
            When None the resolved ``rules`` config is used
            (``backend/config/rules.yaml``, bootstrapped from its ``.example`` template).
        mostly_ai (dict | None): Deep-merge overrides applied on top of the
            base ``mostly_ai.yaml``.  Only the keys you specify are changed;
            everything else keeps its default value.
        general (dict | None): Overrides for selected values from
            ``general.yaml`` (e.g. ``enable_data_profiling``, ``csv_delimiter``).
    """

    rules_config: str | None = None
    mostly_ai: dict | None = None
    general: dict | None = None


@dataclass
class PipelineJobConfig:
    """Configuration for a single pipeline job.

    A job can contain any combination of train, simulate, and evaluate steps.
    Steps execute in order: train → simulate → evaluate. Artifacts produced
    by earlier steps are passed automatically to later ones in the same job.

    Attributes:
        name (str): Human-readable job name used in log messages.
        config (JobConfigOverrides | None): Per-job configuration overrides.
        train (TrainStepConfig | None): Training step config, or None to skip.
        simulate (SimulateStepConfig | None): Simulation step config, or None to skip.
        evaluate (EvaluateStepConfig | None): Evaluation step config, or None to skip.
    """

    name: str
    config: JobConfigOverrides | None = None
    train: TrainStepConfig | None = None
    simulate: SimulateStepConfig | None = None
    evaluate: EvaluateStepConfig | None = None


@dataclass
class PipelineConfig:
    """Top-level pipeline configuration.

    Attributes:
        jobs (list[PipelineJobConfig]): Ordered list of jobs to execute.
    """

    jobs: list[PipelineJobConfig] = field(default_factory=list)
