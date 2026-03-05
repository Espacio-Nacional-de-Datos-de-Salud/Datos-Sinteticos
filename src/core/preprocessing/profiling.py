import warnings

# 1. BLOQUE DE SILENCIO
# Filtrr los avisos de deprecación que vienen de librerías externas para limpiar la consola
with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=DeprecationWarning)
    from ydata_profiling import ProfileReport


def generate_profile_report(processed_data: dict[str, object]) -> dict[str, object] | None:
    """Genera reportes de profiling HTML para cada tabla procesada.

    Crea análisis detallados de distribuciones, valores faltantes, correlaciones
    y estadísticas de cada DataFrames usando ydata-profiling.

    Args:
        processed_data (dict[str, object]): Diccionario de DataFrames
            {nombre_tabla: dataframe}.

    Returns:
        dict[str, object] | None: Diccionario {nombre_tabla: profile_object}
            con reportes de profiling, o None si hay error.

    Example:
        >>> profiles = generate_profile_report(processed_data)
        >>> profiles['users'].to_file('report_users.html')
    """
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="matplotlib")

    profiles = {}

    for name, df in processed_data.items():
        try:
            profile = ProfileReport(df, title=f"Profiling Report: {name}")

            profiles[name] = profile

            # profile.to_file(output_file)
        except Exception as e:
            print(f"Could not generate profile for {name}: {e}")

    print("----- Data Profiling Completed -----")
    return profiles
