"""Excepciones específicas del pipeline de datos sintéticos.

Cada excepción lleva un mensaje descriptivo que main.py logea al capturarla.
"""


class DataLoadError(Exception):
    """No se pudo cargar ninguna tabla válida."""


class MetadataNotFoundError(Exception):
    """No se encontró el archivo de metadatos."""


class RuleManagerNotFoundError(Exception):
    """No se encontró el archivo del RuleManager."""


class TableMetadataMissingError(Exception):
    """No hay metadatos para una tabla requerida."""


class RelationshipNotDefinedError(Exception):
    """No existe relación definida entre dos tablas."""
