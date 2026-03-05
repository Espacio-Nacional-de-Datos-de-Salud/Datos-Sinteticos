import os
from pathlib import Path

import pandas as pd
import synthcity.logger as log
from config.general_config import EVAL_DEFAULT_METRICS, RUN_TIMESTAMP
from synthcity.metrics import Metrics
from synthcity.plugins.core.dataloader import GenericDataLoader

from src.core.logging_config import get_logger
from src.evaluation.metrics import (
    ConfidenceIntervalOverlap,
    CorrelationMatrixDistance,
    NearestNeighborDistance,
)

custom_metrics = [NearestNeighborDistance, CorrelationMatrixDistance, ConfidenceIntervalOverlap]

logger = get_logger(__name__)


class EvaluationEngine:
    def __init__(self, eval_results_dir: str | None, metrics: dict[str, list[str]] | None = None):
        """Inicializa el motor de evaluación con métricas configurables.

        Configura las rutas de registro y área de trabajo, además de las métricas a utilizar.

        Args:
            eval_results_dir (str | None): Directorio donde se guardarán los resultados de evaluación.
            metrics (dict[str, list[str]] | None): Diccionario de configuración de métricas a ejecutar.
                Si es None, se utilizan las métricas por defecto de EVAL_DEFAULT_METRICS.
        """

        self.evaluation_logger_path = os.path.join(
            eval_results_dir, f"synthcity_{RUN_TIMESTAMP}.log"
        )
        self.evaluation_workspace_path = os.path.join(eval_results_dir, "workspace")

        log.add(sink=self.evaluation_logger_path, level="INFO")

        # Default metrics config
        # https://github.com/vanderschaarlab/synthcity
        self.metrics = metrics or EVAL_DEFAULT_METRICS

    def run(
        self,
        real_data_dict: dict[str, pd.DataFrame],
        synthetic_data_dict: dict[str, pd.DataFrame],
        target_column: str | None = None,
        task_type: str = "classification",  # Options: 'classification', 'regression', 'survival_analysis'
    ) -> pd.DataFrame:
        """Ejecuta métricas de evaluación configuradas en los datos proporcionados.

        Convierte los datos a formato compatible con SynthCity, configura las métricas según
        los argumentos proporcionados, ejecuta la evaluación y retorna un DataFrame con los
        resultados.

        Args:
            real_data_dict (dict[str, pd.DataFrame]): Diccionario con datos reales donde las claves
                son nombres de tablas y los valores son DataFrames.
            synthetic_data_dict (dict[str, pd.DataFrame]): Diccionario con datos sintéticos generados
                donde las claves son nombres de tablas y los valores son DataFrames.
            target_column (str | None): Nombre de la columna objetivo para métricas de desempeño.
                Si es None, se omiten las métricas de desempeño. Por defecto es None.
            task_type (str): Tipo de tarea de aprendizaje automático. Opciones: 'classification',
                'regression', 'survival_analysis'. Por defecto es 'classification'.

        Returns:
            pd.DataFrame: DataFrame con métricas como índice y resultados en columnas.

        Raises:
            Exception: Si ocurre un error al crear DataLoaders o durante la evaluación de métricas.

        Example:
            >>> eval_engine = EvaluationEngine(eval_results_dir='eval_results/')
            >>> report = eval_engine.run(
            ...     real_data_dict=real_data,
            ...     synthetic_data_dict=synthetic_data,
            ...     target_column='target',
            ...     task_type='classification'
            ... )
            >>> print(report)
        """

        # 1. Convert to SynthCity compatible DataLoaders
        real_data = next(iter(real_data_dict.values()))
        synthetic_data = next(iter(synthetic_data_dict.values()))

        logger.debug("Real data head:\n%s", real_data.head())
        logger.debug("Synthetic data head:\n%s", synthetic_data.head())

        try:
            loader_real = GenericDataLoader(
                real_data, target_column=target_column, sensitive_features=[]
            )

            loader_syn = GenericDataLoader(
                synthetic_data, target_column=target_column, sensitive_features=[]
            )
        except Exception as e:
            logger.error("Failed to create DataLoaders: %s", e)
            raise

        # 2. Adjust metrics configuration based on arguments
        current_metrics = self.metrics.copy()

        # Extract custom metrics to be run separately
        requested_custom_metrics = current_metrics.pop("custom", [])

        # If no target column is provided, we cannot run performance metrics (ML utility)
        if not target_column and "performance" in current_metrics:
            if current_metrics["performance"]:
                logger.info("No 'target_column' provided. Skipping 'performance' metrics.")
            del current_metrics["performance"]

        # 3. Run Evaluation
        try:
            logger.info("Running metrics: %s", list(current_metrics.keys()))
            report = Metrics.evaluate(
                loader_real,
                loader_syn,
                metrics=current_metrics,
                task_type=task_type,
                workspace=Path(self.evaluation_workspace_path),
                X_train=loader_real,
                X_ref_syn=loader_syn,
            )

            # 4. Run Custom Metrics
            if requested_custom_metrics:
                logger.info("Running custom metrics: %s", requested_custom_metrics)
                for MetricClass in custom_metrics:
                    metric_name = MetricClass.name()
                    if metric_name in requested_custom_metrics:
                        try:
                            evaluator = MetricClass()
                            results = evaluator.evaluate(real_data, synthetic_data)

                            # Add to report
                            score = results.get("score", None)
                            if score is not None:
                                # Ensure 'mean' column exists in report
                                if "mean" not in report.columns:
                                    report["mean"] = float("nan")

                                report.loc[metric_name, "mean"] = score

                        except Exception as e:
                            logger.error("Failed to run custom metric %s: %s", metric_name, e)

            # The report is typically a pandas DataFrame
            logger.info("Evaluation completed successfully.")
            return report

        except Exception as e:
            logger.error("Error during SynthCity metrics evaluation: %s", e)
            raise
