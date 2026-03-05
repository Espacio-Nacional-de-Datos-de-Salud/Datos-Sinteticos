"""Utilidades de preprocesamiento para transformación de datos y metadatos."""


def format_relationships(relationships: dict) -> dict:
    """Convierte relaciones a formato aceptado por LogicalRuleManager.

    Transforma estructura de relaciones de formato {fks: [...]} a diccionario
    optimizado para búsquedas rápidas (child, parent) -> (fk_column, pk_column).

    Args:
        relationships (dict): Estructura con FKs detectadas
            {fks: [{child, parent, fk_column, pk_column}, ...]}.

    Returns:
        dict: Relaciones formateadas {(tabla_hija, tabla_padre): (col_fk, col_pk)}.

    Example:
        >>> rels_raw = {"fks": [{"child": "orders", "parent": "users", ...}]}
        >>> rels_fmt = format_relationships(rels_raw)
        >>> print(rels_fmt[('orders', 'users')])  # ('user_id', 'id')
    """
    formatted_relationships = {}
    for rel in relationships["fks"]:
        # LogicalRuleManager relationships format: (child, parent) -> (fk, pk)
        key = (rel["child"], rel["parent"])
        val = (rel["fk_column"], rel["pk_column"])
        formatted_relationships[key] = val
    return formatted_relationships
