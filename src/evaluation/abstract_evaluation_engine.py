from abc import ABC, abstractmethod

import pandas as pd


class AbstractEvaluationEngine(ABC):
    def __init__(self, eval_results_dir: str | None):
        """Initializes the abstract evaluation engine.

        Args:
            eval_results_dir (str | None): Directory where evaluation results will be saved.
        """
        self.eval_results_dir = eval_results_dir

    @abstractmethod
    def run(
        self,
        real_data_dict: dict[str, pd.DataFrame],
        synthetic_data_dict: dict[str, pd.DataFrame],
        target_column: str | None = None,
        task_type: str = "classification",
        model_id: str | None = None,
        simulation_id: str | None = None,
        metadata_path: str | None = None,
    ) -> pd.DataFrame:
        """Standard interface for all evaluation engines.

        Runs evaluation metrics on the provided real and synthetic data.

        Args:
            real_data_dict (dict[str, pd.DataFrame]): Dictionary with real data where keys
                are table names and values are DataFrames.
            synthetic_data_dict (dict[str, pd.DataFrame]): Dictionary with synthetic data where
                keys are table names and values are DataFrames.
            target_column (str | None): Name of the target column for performance metrics.
                Default is None.
            task_type (str): Type of machine learning task. Default is 'classification'.
            model_id (str | None): Optional model ID for lineage tracking.
            simulation_id (str | None): Optional simulation ID for result association.
            metadata_path (str | None): Path to the metadata.json file to identify ID columns.
                Default is None.

        Returns:
            pd.DataFrame: DataFrame with metrics as index or rows.

        Example:
            >>> eval_engine = EvaluationEngine(eval_results_dir='eval_results/')
            >>> report = eval_engine.run(
            ...     real_data_dict=real_data,
            ...     synthetic_data_dict=synthetic_data,
            ...     target_column='target',
            ...     task_type='classification',
            ...     metadata_path='path/to/metadata.json'
            ... )
        """
        pass
