"""Punto de entrada para la generación de datos sintéticos con modo train/simulation.

Orquesta el flujo completo: carga de datos, preprocesamiento, entrenamiento de modelo
y generación de datos sintéticos. Soporta dos modos de ejecución:

- 'train': Procesa datos crudos, extrae metadatos, entrena el modelo con Mostly AI
  y guarda artefactos (generador, metadatos, reglas).
- 'simulation': Carga un generador entrenado, genera nuevos datos sintéticos y aplica
  post-procesamiento mediante reglas lógicas.

El módulo proporciona interfaz CLI con argumentos para seleccionar archivos,
tamaño de muestra y modo de ejecución, con soporte para modo interactivo.
"""

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from config.general_config import (
    DEFAULT_DATA_PATH,
    ENABLE_DATA_PROFILING,
    MOSTLYAI_CONFIG_PATH,
    RULES_CONFIG_PATH,
)

from src.core.errors import (
    DataLoadError,
    MetadataNotFoundError,
    RelationshipNotDefinedError,
    RuleManagerNotFoundError,
    TableMetadataMissingError,
)
from src.core.general_sanity_checks import sanity_check_referential_integrity
from src.core.loader import FileDataLoader
from src.core.logging_config import get_logger
from src.core.preprocessing.preprocessor import DataPreprocessor
from src.core.synthesis import MostlyAIEngine
from src.core.tracking import ModelTracker, SimulationTracker
from src.core.utils import (
    create_simulation_config,
    delete_empty_folders,
    extract_rules_from_config,
    get_files_from_directory,
    interactive_file_selection,
    load_metadata,
    load_rule_manager,
    should_continue_after_training,
)

logger = get_logger(__name__)


def main(
    mode: str,
    file_paths: list[str] | None,
    sample_size: int | None = None,
    interactive_mode: bool = True,
    rule_sanity_only: bool = False,
) -> None:
    """Ejecuta el pipeline completo de entrenamiento y/o generación de datos sintéticos.

    Orquesta todo el proceso: carga datos, ejecuta preprocesamiento, entrena modelo
    (en modo train), genera datos sintéticos y aplica validaciones.

    Args:
        mode (str): Modo de ejecución: 't' para train o 's' para simulation.
        file_paths (list[str] | None): Rutas a archivos CSV/Excel/Parquet a procesar.
            Si None, se solicita interactivamente. Solo aplica en modo train.
        sample_size (int | None): Número de registros sintéticos a generar.
            Si None, se solicita interactivamente. Solo aplica en modo simulation.
        interactive_mode (bool): Si True, permite validación manual de metadatos
            durante preprocesamiento. Si False, acepta metadatos automáticos.
            Defaults to True.
        rule_sanity_only (bool): Si True, solo se aplican reglas de sanity checks en
        post-procesamiento.

    Raises:
        FileNotFoundError: Si los archivos especificados no existen.
        ValueError: Si mode no es 't' o 's'.
        Exception: Si el entrenamiento o simulación falla en el motor Mostly AI.

    Example:
        >>> main(mode='t', file_paths=['data/users.csv', 'data/orders.csv'],
        ...      sample_size=1000, interactive_mode=False)
        >>> # Entrena modelo y genera 1000 registros sintéticos.
    """
    metadata = None
    rule_manager = None
    generator = None
    model_id = None

    # --- MODO ENTRENAMIENTO ---
    if mode == "t":
        try:
            with ModelTracker(
                data_file_paths=file_paths,
                mostly_config_path=MOSTLYAI_CONFIG_PATH,
                rules_config_path=RULES_CONFIG_PATH,
            ) as model_tracker:
                os.environ["MOSTLYAI_LOCAL_DIR"] = model_tracker.get_tempdir()
                engine = MostlyAIEngine(config_path=MOSTLYAI_CONFIG_PATH, run_dir=model_tracker.output_directory)

                raw_data = FileDataLoader().load(file_paths)
                preprocessor = DataPreprocessor(raw_data, interactive_mode=interactive_mode)

                for rule in extract_rules_from_config(RULES_CONFIG_PATH):
                    rule.sanity_only = rule_sanity_only
                    preprocessor.rule_manager.add_rule(rule)

                processed_data, metadata, rule_manager, data_profiles = preprocessor.run(
                    run_data_profiling=ENABLE_DATA_PROFILING
                )

                model_tracker.save_rule_manager(rule_manager)
                model_tracker.save_metadata(metadata)
                if data_profiles:
                    model_tracker.save_data_profiles(data_profiles)

                generator = engine.train(processed_data, metadata)
                model_tracker.save_generator(generator)
                model_id = model_tracker.model_id
        except (DataLoadError, TableMetadataMissingError, RelationshipNotDefinedError) as e:
            logger.error("%s", e)
            return

        if not should_continue_after_training(sample_size):
            return

    # --- MODO SIMULACIÓN ---
    if mode == "s":
        try:
            engine = MostlyAIEngine(config_path=MOSTLYAI_CONFIG_PATH)
            result = engine.select_generator()
            if result is None:
                logger.error("No se pudo seleccionar un generador. Abortando.")
                return
            generator, path_results_folder = result
            metadata = load_metadata(path_results_folder)
            rule_manager = load_rule_manager(path_results_folder)
            model_id = Path(path_results_folder).name
        except (MetadataNotFoundError, RuleManagerNotFoundError) as e:
            logger.error("%s", e)
            return

    with SimulationTracker(model_id=model_id) as sim_tracker:
        if mode == "s":
            engine_for_sim = engine
            engine_for_sim.setup_mostlyai_logging(sim_tracker.output_directory)
        else:
            engine_for_sim = MostlyAIEngine(config_path=MOSTLYAI_CONFIG_PATH, run_dir=sim_tracker.output_directory)
        
        simulation_config = create_simulation_config(metadata, sample_size)
        sim_tracker.save_sim_config(simulation_config)
        sim_tracker.save_sim_card(sample_size=sample_size)

        raw_synthetic_results = engine_for_sim.simulate(generator, simulation_config)
        synthetic_results = rule_manager.apply_all_post(raw_synthetic_results)

        sim_tracker.save_synthetic_results(synthetic_results)

        sanity_checks: list[pd.DataFrame] = []

        rules_sanity_checks_report = rule_manager.run_all_sanity_checks(synthetic_results)
        if not rules_sanity_checks_report.empty:
            sanity_checks.append(rules_sanity_checks_report)

        referential_integrity_report = sanity_check_referential_integrity(
            synthetic_results, metadata
        )
        if not referential_integrity_report.empty:
            sanity_checks.append(referential_integrity_report)

        if sanity_checks:
            combined_report = pd.concat(sanity_checks, ignore_index=True)
            sim_tracker.save_sanity_report(combined_report)

    print("Simulación finalizada exitosamente.")
    delete_empty_folders(Path(sim_tracker.output_directory).parent.parent)


if __name__ == "__main__":
    # 1. Parse CLI arguments
    parser = argparse.ArgumentParser(description="Herramienta de Datos Sintéticos")
    parser.add_argument("--mode", choices=["t", "s"])
    parser.add_argument("--files", nargs="+", help="Ruta a la carpeta o lista de archivos")
    parser.add_argument("--sample-size", type=int, help="Tamaño de la muestra a generar")
    parser.add_argument(
        "--sanity-only",
        action="store_true",
        help="Solo aplicar reglas de sanity checks en post-procesamiento",
    )
    args = parser.parse_args()

    interactive_mode = (args.files is None) and (args.sample_size is None)

    if args.sanity_only:
        print(
            "Modo SANITY CHECKS ONLY activado: Solo se aplicarán reglas de sanity checks en post-procesamiento."
        )

    mode = args.mode
    if mode is None:
        mode = (
            input("Seleccione modo [train ('t') / simulation ('s')] (default: train): ")
            .strip()
            .lower()
            or "t"
        )

    selected_files = args.files
    if mode == "t" and not selected_files:
        print("\n--- Selección de Archivos ---")
        user_path = input(f"Directorio base (Enter para '{DEFAULT_DATA_PATH}'): ").strip()
        base_dir = user_path if user_path else DEFAULT_DATA_PATH
        selected_files = interactive_file_selection(base_dir)
    elif selected_files and len(selected_files) == 1 and os.path.isdir(selected_files[0]):
        selected_files = get_files_from_directory(selected_files[0])

    try:
        main(
            mode=mode,
            file_paths=selected_files,
            sample_size=args.sample_size,
            interactive_mode=interactive_mode,
            rule_sanity_only=args.sanity_only,
        )
    except KeyboardInterrupt:
        logger.info("Herramienta interrumpida por el usuario.")
