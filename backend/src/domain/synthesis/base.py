"""Engine-agnostic synthesis contract.

``SynthesisEngine`` is the structural interface every synthesis backend must
satisfy. Call sites (training, simulation, artifact loading) type-hint against
this Protocol and obtain instances through ``create_engine`` so the tool never
hard-depends on a concrete engine such as Mostly AI.

The contract is deliberately vendor-neutral: ``train`` and
``load_generator_by_id`` return an opaque ``object`` (the engine's native
generator handle), and tables flow in and out as ``{table_name: DataFrame}``.
Nothing here imports a specific SDK.
"""

import threading
from typing import Protocol, runtime_checkable

import pandas as pd


@runtime_checkable
class SynthesisEngine(Protocol):
    """Structural contract for a synthetic-data generation backend.

    Implementations wrap a concrete engine (e.g. ``MostlyAIEngine`` for the
    Mostly AI SDK). A type checker verifies conformance structurally, so
    implementations need not inherit from this class.
    """

    def train(
        self,
        data_dict: dict[str, pd.DataFrame],
        metadata: dict,
        cancel_event: threading.Event | None = None,
    ) -> object:
        """Train a generator on preprocessed tables.

        Args:
            data_dict: Preprocessed tables ``{table_name: dataframe}``.
            metadata: Engine-formatted schema (tables, PKs, FKs, encoding types).
            cancel_event: Optional cooperative cancellation signal.

        Returns:
            The engine's native trained-generator handle (opaque to callers).
        """
        ...

    def load_generator_by_id(self, model_id: str) -> tuple[object, str]:
        """Load a previously trained generator by its model ID.

        Args:
            model_id: Folder name under the models directory.

        Returns:
            Tuple of ``(generator_handle, model_run_folder_path)``.
        """
        ...

    def simulate(
        self,
        generator: object,
        simulation_configuration: dict,
        cancel_event: threading.Event | None = None,
        progress_copy_dest: str | None = None,
        progress_copy_interval: float = 120.0,
    ) -> tuple[dict[str, pd.DataFrame], str]:
        """Generate synthetic data from a trained generator.

        Args:
            generator: A handle returned by ``train`` or ``load_generator_by_id``.
            simulation_configuration: Engine generation config
                (``{tables: [{name, configuration}, ...]}``).
            cancel_event: Optional cooperative cancellation signal.
            progress_copy_dest: Optional path to receive periodic progress copies.
            progress_copy_interval: Seconds between progress copies.

        Returns:
            Tuple of ``({table_name: dataframe}, run_identifier)``.
        """
        ...
