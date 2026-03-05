import json
import os
import sys

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from config.general_config import TSTR_TARGET_COLUMN, TSTR_TASK_TYPE

from src.core.loader import FileDataLoader
from src.core.preprocessing.preprocessor import DataPreprocessor
from src.evaluation.abstract_evaluation_engine import AbstractEvaluationEngine
from src.evaluation.mlflow_evaluation_engine import MLflowEvaluationEngine
from src.evaluation.utils import (
    align_datasets_structure_and_types,
    select_original_files,
    select_synthetic_files,
    setup_synthcity_environment,
)


def main_eval(
    real_data_files_path: list[str],
    synthetic_files_path: list[str],
    eval_dir: str,
    evaluator: AbstractEvaluationEngine,
    model_id: str | None = None,
    simulation_id: str | None = None,
) -> pd.DataFrame:
    """Ejecuta la evaluación completa de datos sintéticos contra datos reales.

    Carga los datos reales y sintéticos, los preprocesa, alinea sus estructuras y tipos,
    ejecuta la evaluación mediante el motor proporcionado y guarda los resultados.

    Args:
        real_data_files_path (list[str]): Lista de rutas de archivo de datos reales.
        synthetic_files_path (list[str]): Lista de rutas de archivo de datos sintéticos.
        eval_dir (str): Directorio donde se guardarán los resultados de evaluación.
        evaluator (AbstractEvaluationEngine): Motor de evaluación a utilizar para ejecutar
            las métricas.

    Returns:
        pd.DataFrame: DataFrame con los resultados de la evaluación.

    Raises:
        AssertionError: Si el reporte de evaluación está vacío.
    """
    data_loader = FileDataLoader()
    raw_real = data_loader.load(real_data_files_path)
    raw_synthetic = data_loader.load(synthetic_files_path)

    processed_real, _, _, _ = DataPreprocessor(raw_real, interactive_mode=False).run(
        run_data_profiling=False
    )
    processed_synthetic, _, _, _ = DataPreprocessor(raw_synthetic, interactive_mode=False).run(
        run_data_profiling=False
    )

    cured_real, cured_synthetic = align_datasets_structure_and_types(
        processed_real, processed_synthetic
    )

    eval_report = evaluator.run(
        real_data_dict=cured_real,
        synthetic_data_dict=cured_synthetic,
        target_column=TSTR_TARGET_COLUMN,
        task_type=TSTR_TASK_TYPE,
        model_id=model_id,
        simulation_id=simulation_id,
    )

    assert not eval_report.empty, "El reporte de evaluación está vacío."

    print("\nReporte de evaluación:")
    print(eval_report)

    save_path = os.path.join(eval_dir, "eval_report.csv")
    eval_report.reset_index().rename(columns={"index": "metric"}).to_csv(save_path, index=False)

    print(f"Resultados guardados en: {save_path}")
    return


if __name__ == "__main__":
    # 1. User Inputs
    real_data_files_path = select_original_files()
    if not real_data_files_path:
        sys.exit("No se seleccionaron archivos originales.")

    synthetic_files_path, run_dir = select_synthetic_files(real_data_files_path)
    if not synthetic_files_path:
        sys.exit("No se seleccionaron archivos sintéticos.")

    setup_synthcity_environment(run_dir)

    eval_dir = os.path.join(run_dir, "evaluation")
    os.makedirs(eval_dir, exist_ok=True)

    # Extract model and simulation IDs from paths
    model_id = None
    simulation_id = None
    if run_dir:
        if "simulation_" in run_dir:
            simulation_id = os.path.basename(run_dir)
            # Try to find model_id from sim_card.json
            sim_card_path = os.path.join(run_dir, "sim_card.json")
            if os.path.exists(sim_card_path):
                with open(sim_card_path) as f:
                    sim_card = json.load(f)
                    model_id = sim_card.get("model_id")
        elif "model_" in run_dir:
            model_id = os.path.basename(run_dir)

    # 3. Dependency Injection
    engine_instance = MLflowEvaluationEngine(eval_results_dir=eval_dir)

    main_eval(
        real_data_files_path=real_data_files_path,
        synthetic_files_path=synthetic_files_path,
        eval_dir=eval_dir,
        evaluator=engine_instance,
        model_id=model_id,
        simulation_id=simulation_id,
    )
