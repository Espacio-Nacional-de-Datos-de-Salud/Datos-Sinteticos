from abc import ABC, abstractmethod

import pandas as pd


class AbstractEvaluationEngine(ABC):
    def __init__(self, eval_results_dir: str | None):
        """Inicializa el motor de evaluación abstracto.

        Args:
            eval_results_dir (str | None): Directorio donde se guardarán los resultados de evaluación.
        """
        self.eval_results_dir = eval_results_dir

    @abstractmethod
    def run(
        self,
        real_data_dict: dict[str, pd.DataFrame],
        synthetic_data_dict: dict[str, pd.DataFrame],
        target_column: str | None = None,
        task_type: str = "classification",
    ) -> pd.DataFrame:
        """Interfaz estándar para todos los motores de evaluación.

        Ejecuta métricas de evaluación en los datos reales y sintéticos proporcionados.

        Args:
            real_data_dict (dict[str, pd.DataFrame]): Diccionario con datos reales donde las claves
                son nombres de tablas y los valores son DataFrames.
            synthetic_data_dict (dict[str, pd.DataFrame]): Diccionario con datos sintéticos donde las
                claves son nombres de tablas y los valores son DataFrames.
            target_column (str | None): Nombre de la columna objetivo para métricas de desempeño.
                Por defecto es None.
            task_type (str): Tipo de tarea de aprendizaje automático. Por defecto es 'classification'.

        Returns:
            pd.DataFrame: DataFrame con métricas como índice o filas.

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
        pass
