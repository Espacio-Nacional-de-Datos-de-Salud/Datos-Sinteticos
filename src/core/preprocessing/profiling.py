import warnings

from src.core.logging_config import get_logger

logger = get_logger(__name__)


def generate_profile_report(processed_data: dict[str, object]) -> dict[str, object] | None:
    """Generates HTML profiling reports for each processed table.

    Creates detailed analyses of distributions, missing values, correlations,
    and statistics for each DataFrame using ydata-profiling.

    Args:
        processed_data (dict[str, object]): Dictionary of DataFrames
            {table_name: dataframe}.

    Returns:
        dict[str, object] | None: Dictionary {table_name: profile_object}
            with profiling reports, or None if there is an error.

    Example:
        >>> profiles = generate_profile_report(processed_data)
        >>> profiles['users'].to_file('report_users.html')
    """
    warnings.filterwarnings("ignore", category=DeprecationWarning, module="matplotlib")

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", category=DeprecationWarning)
        from ydata_profiling import ProfileReport

    profiles = {}

    for name, df in processed_data.items():
        try:
            logger.info("----- Profiling Data -----")
            profile = ProfileReport(df, title=f"Profiling Report: {name}")

            profiles[name] = profile

            # profile.to_file(output_file)
        except Exception as e:
            logger.error(f"Could not generate profile for {name}: {e}")

    return profiles
