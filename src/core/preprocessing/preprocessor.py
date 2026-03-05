"""Orquestación del pipeline de preprocesamiento de datos para síntesis.

Coordina la limpieza de datos, validación de metadatos, aplicación de reglas
lógicas de pre-procesamiento y generación de perfiles. Integra múltiples
componentes (DataCleaner, MetadataExtractor, MetadataValidator, MetadataFormatter,
LogicalRuleManager) en un flujo coherente que prepara datos crudos para entrenar
el modelo de síntesis.
"""

from typing import Any

import pandas as pd

from src.core.preprocessing.data_cleaner import DataCleaner
from src.core.preprocessing.logical_rules import LogicalRuleManager
from src.core.preprocessing.metadata_extractor import MetadataExtractor
from src.core.preprocessing.metadata_formatter import MetadataFormatter
from src.core.preprocessing.metadata_validator import MetadataValidator
from src.core.preprocessing.profiling import generate_profile_report
from src.core.preprocessing.utils import format_relationships


class DataPreprocessor:
    """Prepara datos crudos para entrenamiento mediante limpieza y extracción de metadatos.

    Encapsula todo el flujo de transformación: limpieza inicial de datos, detección de
    relaciones y tipos de columnas, validación interactiva (opcional) de metadatos,
    aplicación de reglas lógicas y generación de perfiles de datos. Coordina múltiples
    componentes para garantizar que los datos estén listos para el motor de síntesis.

    Args:
        data_dict (dict[str, pd.DataFrame]): Diccionario de tablas crudas
            {nombre_tabla: dataframe}. Puede contener múltiples tablas relacionales.
        interactive_mode (bool): Si True, permite validación manual interactiva de
            metadatos detectados (relaciones y tipos de columna). Si False, acepta
            automáticamente los metadatos extraídos. Defaults to True.

    Attributes:
        raw_data_dict (dict[str, pd.DataFrame]): Datos originales sin modificar.
        processed_data_dict (dict[str, pd.DataFrame]): Datos después del procesamiento.
        metadata (dict): Metadatos extraídos y formateados para el motor de síntesis.
        rule_manager (LogicalRuleManager): Gestor de reglas lógicas pre y post-síntesis.
        interactive_mode (bool): Modo de validación manual de metadatos.
    """

    def __init__(self, data_dict: dict[str, pd.DataFrame], interactive_mode: bool = True) -> None:
        """Inicializa el preprocesador con un conjunto de tablas crudas.

        Args:
            data_dict (dict[str, pd.DataFrame]): Diccionario de tablas crudas
                {nombre_tabla: dataframe}.
            interactive_mode (bool): Si True, permite validación manual de metadatos.
                Defaults to True.
        """
        self.raw_data_dict = data_dict
        self.processed_data_dict = {name: df.copy() for name, df in data_dict.items()}
        self.metadata = {}
        self.rule_manager = LogicalRuleManager()
        self.interactive_mode = interactive_mode

    def run(
        self, run_data_profiling: bool = False
    ) -> tuple[dict[str, pd.DataFrame], dict, LogicalRuleManager, Any | None]:
        """
        Ejecuta el pipeline completo de preprocesamiento.

        1. Limpieza de datos (DataCleaner).
        2. Gestión de Metadatos:
            - Extracción de relaciones y tipos de datos (MetadataExtractor).
            - Validación manual de metadatos (MetadataValidator) si interactive_mode=True.
            - Formateo de metadatos para el motor de síntesis (MetadataFormatter).
        3. Aplicación de reglas lógicas PRE (transformación de datos).
        4. Profiling (opcional).

        Args:
            run_data_profiling (bool): Si es True, genera reporte HTML de los datos.

        Returns:
            tuple:
                - Datos procesados.
                - Metadatos (JSON dict).
                - RuleManager.
                - Objeto Profiling (o None).

        Example:
            >>> preprocessor = DataPreprocessor(raw_data_dict, interactive_mode=True)
            >>> processed_data, metadata, rule_manager, data_profiles = preprocessor.run(run_data_profiling=True)
        """
        cleaned_data = DataCleaner(self.raw_data_dict).run()

        metadata_extractor = MetadataExtractor(cleaned_data)
        relationships = metadata_extractor.extract_relationships()
        metadata_validator = None

        if self.interactive_mode:
            metadata_validator = MetadataValidator(engine_name="mostly")
            relationships = metadata_validator.validate_relationships(
                data_dfs=cleaned_data, relationships=relationships
            )

        engineered_data = self.rule_manager.apply_all_pre(
            data_dict=cleaned_data, relationships=format_relationships(relationships)
        )

        encoding_types = MetadataExtractor(engineered_data).extract_encoding_types()
        if self.interactive_mode and metadata_validator is not None:
            encoding_types = metadata_validator.validate_encoding_types(types_data=encoding_types)

        metadata = MetadataFormatter(engine_name="mostly").format(
            data_dfs=engineered_data,
            relationships_data=relationships,
            types_data=encoding_types,
        )

        data_profiles = generate_profile_report(engineered_data) if run_data_profiling else None

        return engineered_data, metadata, self.rule_manager, data_profiles
