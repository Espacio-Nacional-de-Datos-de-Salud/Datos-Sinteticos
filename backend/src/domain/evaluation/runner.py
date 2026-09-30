"""End-to-end evaluation runner.

``EvaluationRunner.run`` is the single entry point for evaluating a real /
synthetic data pair. It executes synthcity's built-in metrics and the
project's custom metrics, returning a unified report DataFrame. Persisting
results locally is the responsibility of ``EvaluationTracker`` — this
class is purely about computing the report.
"""

import os

import pandas as pd
import synthcity.logger as synthcity_log

import backend.src.config.general as general_config
from backend.src.config.evaluation import (
    DROP_ID_COLUMNS_FROM_METRICS,
    EVAL_DEFAULT_METRICS,
    EXACT_MATCH_SHOW_FILTERED_ROWS,
    TVD_N_BINS,
    UTILITY_TESTS_CONFIG,
)
from backend.src.domain.evaluation._custom_metrics import run_custom_metrics
from backend.src.domain.evaluation._synthcity_metrics import (
    build_data_loaders,
    evaluate_synthcity_metrics,
)
from backend.src.domain.evaluation.dtype_alignment import align_dtypes
from backend.src.domain.evaluation.table_settings import TableEvalSettings
from backend.src.domain.evaluation.utility_filter import drop_ood_performance_rows
from backend.src.domain.evaluation.utils import filter_id_columns, normalize_for_exact_match
from backend.src.infrastructure.logging_config import get_logger
from backend.src.infrastructure.progress import ProfilerPhase
from backend.src.infrastructure.time_profiling import profiler

logger = get_logger(__name__)


class EvaluationRunner:
    """Compute fidelity/privacy/detection metrics for a real/synthetic data pair.

    Args:
        eval_results_dir (str): Directory used to host the synthcity log file
            and the synthcity workspace cache. Output reports are written by
            ``EvaluationTracker``, not by this class.
        metrics (dict[str, list[str]] | None): Metric groups to run. Defaults
            to ``EVAL_DEFAULT_METRICS``.
    """

    def __init__(self, eval_results_dir: str, metrics: dict[str, list[str]] | None = None) -> None:
        self.eval_results_dir = eval_results_dir
        self.metrics = metrics or EVAL_DEFAULT_METRICS

        synthcity_log_path = os.path.join(
            eval_results_dir, f"synthcity_{general_config.get_run_timestamp()}.log"
        )
        synthcity_log.add(sink=synthcity_log_path, level="INFO")
        self.synthcity_workspace = os.path.join(eval_results_dir, "workspace")

    def run(
        self,
        real_data_dict: dict[str, pd.DataFrame],
        synthetic_data_dict: dict[str, pd.DataFrame],
        metadata_path: str | None = None,
        settings: TableEvalSettings | None = None,
    ) -> pd.DataFrame:
        """Run all configured metrics against a single table.

        Args:
            real_data_dict (dict[str, pd.DataFrame]): Mapping of table name to real data.
            synthetic_data_dict (dict[str, pd.DataFrame]): Mapping of table name to synthetic data.
            metadata_path (str | None): Path to ``metadata.json`` used to drop
                ID columns when enabled.
            settings (TableEvalSettings | None): Resolved per-table settings
                (which table, target, sensitive columns, knobs…). When ``None``
                the first table is evaluated with the global config defaults.

        Returns:
            pd.DataFrame: Report with one row per metric.
        """
        target_column = settings.target_column if settings else None
        task_type = settings.task_type if settings else "classification"
        evaluated_table = settings.table if settings else None
        drop_id_columns = settings.drop_id_columns if settings else DROP_ID_COLUMNS_FROM_METRICS
        utility_tests = settings.utility_tests if settings else (UTILITY_TESTS_CONFIG or {})

        table_name = self._select_table_name(real_data_dict, evaluated_table)
        real_data, synthetic_data = self._prepare_table(
            real_data_dict[table_name], synthetic_data_dict[table_name], metadata_path,
            drop_id_columns=drop_id_columns,
        )
        logger.info("Evaluating single table '%s'.", table_name)

        synthcity_metrics, custom_metric_names = self._partition_requested_metrics(
            target_column, utility_tests
        )

        loader_real, loader_syn = build_data_loaders(real_data, synthetic_data, target_column)

        logger.info("Running metrics: %s", list(synthcity_metrics.keys()))
        try:
            with profiler.phase(ProfilerPhase.SYNTHCITY_METRICS):
                report = evaluate_synthcity_metrics(
                    loader_real,
                    loader_syn,
                    metrics=synthcity_metrics,
                    task_type=task_type,
                    workspace_path=self.synthcity_workspace,
                )
        except Exception:
            logger.error("Error during synthcity metrics evaluation.", exc_info=True)
            raise

        if custom_metric_names:
            report = run_custom_metrics(
                real_data,
                synthetic_data,
                report,
                custom_metric_names,
                real_data_dict=real_data_dict,
                synthetic_data_dict=synthetic_data_dict,
                evaluated_table=table_name,
                sensitive_columns=settings.sensitive_columns if settings else None,
                quasi_identifier_subsets=(
                    settings.quasi_identifier_subsets if settings else None
                ),
                tvd_n_bins=settings.tvd_n_bins if settings else TVD_N_BINS,
                exact_match_show_filtered_rows=(
                    settings.exact_match_show_filtered_rows
                    if settings
                    else EXACT_MATCH_SHOW_FILTERED_ROWS
                ),
                utility_tests=utility_tests,
            )

        return drop_ood_performance_rows(report)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _prepare_table(
        self,
        real_data: pd.DataFrame,
        synthetic_data: pd.DataFrame,
        metadata_path: str | None,
        drop_id_columns: bool = DROP_ID_COLUMNS_FROM_METRICS,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Strip ID columns and align dtypes for the evaluated table."""
        if drop_id_columns:
            real_data = filter_id_columns(real_data, metadata_path)
            synthetic_data = filter_id_columns(synthetic_data, metadata_path)

        real_data, synthetic_data = align_dtypes(real_data, synthetic_data)
        real_data, synthetic_data = normalize_for_exact_match(real_data, synthetic_data)
        return real_data, synthetic_data

    @staticmethod
    def _select_table_name(
        real_data_dict: dict[str, pd.DataFrame],
        evaluated_table: str | None,
    ) -> str:
        """Return the table to evaluate.

        Uses the explicitly requested ``evaluated_table`` when present; otherwise
        falls back to the first table (legacy behaviour).
        """
        first_table = next(iter(real_data_dict))
        if not evaluated_table:
            return first_table
        if evaluated_table in real_data_dict:
            return evaluated_table

        logger.warning(
            "Requested table '%s' not found among %s; evaluating first table '%s'.",
            evaluated_table,
            list(real_data_dict.keys()),
            first_table,
        )
        return first_table

    def _partition_requested_metrics(
        self, target_column: str | None, utility_tests: dict | None = None
    ) -> tuple[dict[str, list[str]], list[str]]:
        """Split configured metrics into a synthcity dict and a custom-name list.

        Also handles two project-specific overrides:

        - ``performance`` is dropped when no target column is provided.
        - ``k-anonymization`` and ``distinct l-diversity`` are replaced by
          project custom metrics that use configured quasi-identifier subsets.
        """
        synthcity_metrics = {k: list(v) for k, v in self.metrics.items()}
        custom_metric_names = list(synthcity_metrics.pop("custom", []))

        if not target_column and "performance" in synthcity_metrics:
            if synthcity_metrics["performance"]:
                logger.info("No 'target_column' provided. Skipping 'performance' metrics.")
            del synthcity_metrics["performance"]

        privacy_metrics = synthcity_metrics.get("privacy", [])
        if "k-anonymization" in privacy_metrics:
            logger.info(
                "Replacing synthcity 'k-anonymization' with custom subset-aware k_anonymity."
            )
            privacy_metrics.remove("k-anonymization")
            if "k_anonymity" not in custom_metric_names:
                custom_metric_names.append("k_anonymity")

        if "distinct l-diversity" in privacy_metrics:
            logger.info("Running 'distinct l-diversity' with custom PyCanon l_diversity.")
            privacy_metrics.remove("distinct l-diversity")
            if "l_diversity_pycanon" not in custom_metric_names:
                custom_metric_names.append("l_diversity_pycanon")

        sanity_metrics = synthcity_metrics.get("sanity", [])
        if "exact_match_rows" in sanity_metrics:
            logger.info("Replacing synthcity 'exact_match_rows' with custom ExactMatchRows.")
            sanity_metrics.remove("exact_match_rows")
            if "exact_match_rows" not in custom_metric_names:
                custom_metric_names.append("exact_match_rows")

        # Statistical-utility tests are opt-in via their own config block rather
        # than a name in metrics.default; request them only when enabled.
        utility_tests = utility_tests if utility_tests is not None else (UTILITY_TESTS_CONFIG or {})
        utility_tests_enabled = utility_tests.get("enabled")
        if utility_tests_enabled and "utility_tests" not in custom_metric_names:
            logger.info("Statistical-utility tests enabled; requesting custom utility_tests.")
            custom_metric_names.append("utility_tests")

        return synthcity_metrics, custom_metric_names
