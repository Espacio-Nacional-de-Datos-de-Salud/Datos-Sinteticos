import pandas as pd


class MetricEvaluator:
    pass


class NearestNeighborDistance(MetricEvaluator):
    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "nearest_neighbor_distance_ratio"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute the metric value for real vs synthetic data.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with a "score" key and numeric value.
        """
        # Implement metric calculation here
        # may want to change typing to use Dataset
        return {"score": 0.0}


class CorrelationMatrixDistance(MetricEvaluator):
    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "correlation_matrix_distance"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute the metric value for real vs synthetic data.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with a "score" key and numeric value.
        """
        # Implement metric calculation here
        return {"score": 0.0}


class ConfidenceIntervalOverlap(MetricEvaluator):
    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "confidence_interval_overlap"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute the metric value for real vs synthetic data.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with a "score" key and numeric value.
        """
        # Implement metric calculation here
        return {"score": 0.0}
