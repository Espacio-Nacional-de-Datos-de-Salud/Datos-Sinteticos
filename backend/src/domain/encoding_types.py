"""Canonical column encoding vocabulary and per-engine mappers.

``ModelEncodingType`` is the tool's *internal* representation of how each column
should be modelled. Its string values currently **coincide with the Mostly AI
SDK's encoding-type labels** (``TABULAR_CATEGORICAL``, ``LANGUAGE_TEXT``, …) —
i.e. today this is Mostly's vocabulary, not a vendor-neutral taxonomy.
Autodetection (``auto_detect_encoding_type``) produces these values, and for
Mostly they flow through to the SDK unchanged.

To support other engines without rewriting detection or the stored
``inspection_metadata.json`` schema, ``get_encoding_type_mapper`` returns a
per-engine translation function selected by the same ``engine_name`` used by
``create_engine`` (see ``domain.synthesis.factory``). For Mostly the mapper is
the identity (1:1, since the values already are Mostly's). Other engines
register a mapper that converts each ``ModelEncodingType`` into their own type
system (e.g. SDV ``sdtypes``), defined as needed.
"""

from collections.abc import Callable
from enum import Enum


class ModelEncodingType(str, Enum):
    """Internal column encoding types used throughout preprocessing.

    NOTE: these values are currently Mostly AI's encoding-type labels, not a
    generic taxonomy. They serve as the canonical internal representation that
    per-engine mappers (see :func:`get_encoding_type_mapper`) translate *from*.
    """

    auto = "AUTO"
    tabular_categorical = "TABULAR_CATEGORICAL"
    tabular_numeric_auto = "TABULAR_NUMERIC_AUTO"
    tabular_numeric_discrete = "TABULAR_NUMERIC_DISCRETE"
    tabular_numeric_binned = "TABULAR_NUMERIC_BINNED"
    tabular_numeric_digit = "TABULAR_NUMERIC_DIGIT"
    tabular_character = "TABULAR_CHARACTER"
    tabular_datetime = "TABULAR_DATETIME"
    tabular_datetime_relative = "TABULAR_DATETIME_RELATIVE"
    tabular_lat_long = "TABULAR_LAT_LONG"
    language_text = "LANGUAGE_TEXT"
    language_categorical = "LANGUAGE_CATEGORICAL"
    language_numeric = "LANGUAGE_NUMERIC"
    language_datetime = "LANGUAGE_DATETIME"


# A mapper translates one canonical ``ModelEncodingType`` into the representation
# a given engine expects. The return type is engine-specific (Mostly keeps the
# enum member; another engine might return a plain ``sdtype`` string), so it is
# intentionally ``object``.
EncodingTypeMapper = Callable[[ModelEncodingType], object]


def _mostly_encoding_type_mapper(encoding_type: ModelEncodingType) -> ModelEncodingType:
    """Identity mapping: this enum's values already are Mostly AI's labels."""
    return encoding_type


# Keyed by the same engine names used by ``create_engine`` (``domain.synthesis``).
# Add a new entry when wiring up another engine; until then unknown engines fail
# loudly via ``get_encoding_type_mapper``.
_ENCODING_TYPE_MAPPERS: dict[str, EncodingTypeMapper] = {
    "mostly": _mostly_encoding_type_mapper,
}


def get_encoding_type_mapper(engine_name: str) -> EncodingTypeMapper:
    """Return the encoding-type mapper for ``engine_name``.

    The returned function translates a canonical :class:`ModelEncodingType` into
    the representation that engine expects. New engines register their mapper in
    ``_ENCODING_TYPE_MAPPERS``.

    Args:
        engine_name: Engine identifier, matching the names accepted by
            ``create_engine`` (e.g. ``"mostly"``).

    Returns:
        EncodingTypeMapper: Per-engine translation function.

    Raises:
        ValueError: If no mapper is registered for ``engine_name``.
    """
    try:
        return _ENCODING_TYPE_MAPPERS[engine_name]
    except KeyError:
        raise ValueError(
            f"No encoding-type mapper registered for engine: {engine_name!r}. "
            f"Supported: {sorted(_ENCODING_TYPE_MAPPERS)}."
        ) from None
