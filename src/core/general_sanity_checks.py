import pandas as pd

from src.core.logging_config import get_logger

logger = get_logger(__name__)


def sanity_check_referential_integrity(
    synthetic_data: dict[str, pd.DataFrame] | pd.DataFrame, metadata: dict
) -> pd.DataFrame:
    """Valida integridad referencial de claves foráneas en datos sintéticos.

    Genera una fila de reporte por cada relación FK encontrada en los metadatos,
    con el mismo esquema que el reporte del RuleManager para poder combinarse
    en un único CSV de sanity checks.

    Si solo hay una tabla (o es un DataFrame suelto), retorna un DataFrame vacío
    para que no aparezca en el reporte unificado.

    Args:
        synthetic_data (dict[str, pd.DataFrame] | pd.DataFrame): Diccionario
            de tablas sintéticas o DataFrame único.
        metadata (dict): Metadatos con estructura de tablas, PKs y FKs.

    Returns:
        pd.DataFrame: Reporte con columnas [check, rule, table, status,
            failed_rows, total_rows, details]. Vacío si no aplica.

    Example:
        >>> report = sanity_check_referential_integrity(synthetic_data, metadata)
        >>> report[report['status'] == 'FAIL']
    """

    # 1. Input Validation — single table: nothing to check, return empty
    if isinstance(synthetic_data, pd.DataFrame) or len(synthetic_data) < 2:
        logger.info("Single DataFrame or insufficient tables provided. No relationships to check.")
        return pd.DataFrame()

    logger.info("=" * 80)
    logger.info("%s", f"{'REFERENTIAL INTEGRITY CHECK':^80}")
    logger.info("=" * 80)

    rows: list[dict] = []

    # 2. Extract Primary Keys Mapping first {table_name: pk_column}
    table_pks = {}
    for table in metadata.get("tables", []):
        if "primary_key" in table:
            table_pks[table["name"]] = table["primary_key"]

    # 3. Iterate through tables to find Foreign Keys
    for table_info in metadata.get("tables", []):
        child_name = table_info["name"]

        fks = table_info.get("foreign_keys", [])
        if not fks:
            continue

        for fk in fks:
            child_fk_col = fk["column"]
            parent_name = fk["referenced_table"]
            check_label = f"FK {child_name}.{child_fk_col} -> {parent_name}"

            # A. Check if DataFrames exist
            if child_name not in synthetic_data:
                logger.warning("Skipping check: Table '%s' not found in data.", child_name)
                rows.append(
                    {
                        "check": "referential_integrity",
                        "rule": check_label,
                        "table": child_name,
                        "status": "SKIPPED",
                        "failed_rows": 0,
                        "total_rows": 0,
                        "details": f"Table '{child_name}' not found in data",
                    }
                )
                continue
            if parent_name not in synthetic_data:
                logger.warning("Skipping check: Parent table '%s' not found in data.", parent_name)
                rows.append(
                    {
                        "check": "referential_integrity",
                        "rule": check_label,
                        "table": child_name,
                        "status": "SKIPPED",
                        "failed_rows": 0,
                        "total_rows": 0,
                        "details": f"Parent table '{parent_name}' not found in data",
                    }
                )
                continue

            # B. Check if Parent has a known PK
            parent_pk_col = table_pks.get(parent_name)
            if not parent_pk_col:
                logger.warning(
                    "Skipping %s->%s: PK for '%s' not found in metadata.",
                    child_name,
                    parent_name,
                    parent_name,
                )
                rows.append(
                    {
                        "check": "referential_integrity",
                        "rule": check_label,
                        "table": child_name,
                        "status": "SKIPPED",
                        "failed_rows": 0,
                        "total_rows": 0,
                        "details": f"PK for '{parent_name}' not found in metadata",
                    }
                )
                continue

            # C. Perform the Math
            parent_df = synthetic_data[parent_name]
            child_df = synthetic_data[child_name]

            valid_parent_ids = set(parent_df[parent_pk_col].dropna().unique())
            child_fks = child_df[child_fk_col].dropna()

            total_children = len(child_fks)

            if total_children == 0:
                orphan_count = 0
            else:
                orphan_count = int((~child_fks.isin(valid_parent_ids)).sum())

            # D. Build row
            if orphan_count == 0:
                status = "PASS"
                details = f"100% integrity ({total_children} rows)"
            else:
                success_rate = round(((total_children - orphan_count) / total_children) * 100, 2)
                status = "FAIL"
                details = f"{orphan_count} orphans, {success_rate}% integrity"

            rows.append(
                {
                    "check": "referential_integrity",
                    "rule": check_label,
                    "table": child_name,
                    "status": status,
                    "failed_rows": orphan_count,
                    "total_rows": total_children,
                    "details": details,
                }
            )

    # 4. Output
    if not rows:
        logger.info("No foreign keys found in metadata tables.")
        return pd.DataFrame()

    report_df = pd.DataFrame(rows)

    logger.info("\n%s", report_df.to_string(index=False))
    logger.info("=" * 80)

    return report_df


def sanity_check_temporal_consistency(
    df: pd.DataFrame, table_name: str, origin_col: str, target_col: str
) -> pd.DataFrame:
    """Valida coherencia temporal entre dos columnas tipo fecha.

    Verifica que valores en columna de fin no sean anteriores a valores
    en columna de inicio. Retorna filas con incoherencias detectadas.

    Args:
        df (pd.DataFrame): DataFrame a validar.
        table_name (str): Nombre descriptivo de tabla (para reportes).
        origin_col (str): Nombre columna de fecha inicio.
        target_col (str): Nombre columna de fecha fin.

    Returns:
        pd.DataFrame: Filas con incoherencias (vacío si todas correctas).

    Example:
        >>> failing_rows = sanity_check_temporal_consistency(
        ...     df, 'procedure', 'start_date', 'end_date'
        ... )
        >>> if not failing.empty:
        ...     print(f'Encontradas {len(failing)} incoherencias')
    """
    # Validar que las columnas existen
    if origin_col not in df.columns or target_col not in df.columns:
        logger.warning(
            "Columnas %s o %s no encontradas en %s. Saltando check temporal.",
            origin_col,
            target_col,
            table_name,
        )
        return pd.DataFrame()

    # Convertir a datetime
    start_dates = pd.to_datetime(df[origin_col], errors="coerce")
    end_dates = pd.to_datetime(df[target_col], errors="coerce")

    inconsistent_mask = start_dates > end_dates

    failing_rows = df[inconsistent_mask].copy()

    if not failing_rows.empty:
        # Añadimos columnas informativas para ver el error fácilmente
        failing_rows["error_type"] = "TEMPORAL_INCONSISTENCY"
        failing_rows["table_origin"] = table_name
        failing_rows["details"] = (
            f"Start ({origin_col}): "
            + failing_rows[origin_col].astype(str)
            + " > End ({target_col}): "
            + failing_rows[target_col].astype(str)
        )

        count = len(failing_rows)
        total = len(df)
        logger.warning(
            "%s: Encontrados %d/%d registros con incoherencia temporal (%s > %s)",
            table_name,
            count,
            total,
            origin_col,
            target_col,
        )
    else:
        logger.info(
            "%s: Coherencia temporal correcta (%s <= %s)",
            table_name,
            origin_col,
            target_col,
        )

    return failing_rows
