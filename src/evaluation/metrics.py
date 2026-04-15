"""Custom evaluation metrics used by the project evaluation engines.

This module contains project-specific metric implementations that complement
the built-in SynthCity metrics. Evaluators in ``src.evaluation`` import these
classes to compute privacy, statistical, and report-detail metrics that are
not provided directly by external libraries.
"""

import numpy as np
import pandas as pd
import yaml
from config.evaluation.evaluation_config import (
    AVERAGE_COMPLEMENTARY_TVD_N_BINS,
    CONFIDENCE_INTERVAL_LEVEL,
    CUSTOM_STATISTICS_MODULE,
    QUASI_IDENTIFIER_SUBSETS,
    SENSITIVE_COLUMNS,
    STATISTICS_CONFIG_PATH,
)
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import LabelEncoder, StandardScaler

from src.core.logging_config import get_logger
from src.evaluation.utils import get_id_columns

from .statistics import Statistic, create_statistic

logger = get_logger(__name__)


class MetricEvaluator:
    def _encode_categorical_columns(
        self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Encode categorical columns using LabelEncoder.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            tuple[pd.DataFrame, pd.DataFrame]: Encoded real and synthetic data.
        """
        real_processed = real_data.copy()
        synthetic_processed = synthetic_data.copy()

        for col in real_data.columns:
            if real_data[col].dtype == "object":
                le = LabelEncoder()
                combined_values = pd.concat([real_data[col], synthetic_data[col]]).astype(str)
                le.fit(combined_values)
                real_processed[col] = le.transform(real_data[col].astype(str))
                synthetic_processed[col] = le.transform(synthetic_data[col].astype(str))

        return real_processed, synthetic_processed


class DCR(MetricEvaluator):
    """Distance to Closest Record (DCR) — real and synthetic.

    ``dcr.syn``: mean distance from each synthetic record to its nearest real
    record.  Low values indicate synthetic records may be memorising real ones.

    ``dcr.real``: mean distance from each real record to its nearest *other*
    real record (baseline).  Comparing dcr.syn against dcr.real tells you
    whether synthetic records sit at natural data density or are suspiciously
    close to real ones.

    Both directions: higher is safer (more distance = less leakage risk).
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        return "dcr"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        if len(real_data) < 2 or len(synthetic_data) == 0:
            logger.warning("Cannot calculate DCR, not enough data.")
            return {"score": float("inf")}

        real_processed, syn_processed = self._encode_categorical_columns(real_data, synthetic_data)
        real_processed = real_processed.dropna()
        syn_processed = syn_processed.dropna()

        if len(real_processed) < 2 or len(syn_processed) == 0:
            logger.warning("Cannot calculate DCR, not enough non-NaN data.")
            return {"score": float("inf")}

        scaler = StandardScaler()
        real_scaled = scaler.fit_transform(real_processed)
        syn_scaled = scaler.transform(syn_processed)

        # dcr.syn: each synthetic → nearest real
        nn = NearestNeighbors(n_neighbors=1, metric="euclidean")
        nn.fit(real_scaled)
        syn_distances, _ = nn.kneighbors(syn_scaled)
        syn_dcr = syn_distances[:, 0]

        # dcr.real: each real → nearest other real (k=2, skip self at index 0)
        nn2 = NearestNeighbors(n_neighbors=2, metric="euclidean")
        nn2.fit(real_scaled)
        real_distances, _ = nn2.kneighbors(real_scaled)
        real_dcr = real_distances[:, 1]

        return {
            "scores": {
                "dcr.real": {
                    "mean": float(np.mean(real_dcr)),
                    "min": float(np.min(real_dcr)),
                    "max": float(np.max(real_dcr)),
                },
                "dcr.syn": {
                    "mean": float(np.mean(syn_dcr)),
                    "min": float(np.min(syn_dcr)),
                    "max": float(np.max(syn_dcr)),
                },
            },
        }


class NNDR(MetricEvaluator):
    """Nearest Neighbour Distance Ratio (NNDR) — real and synthetic.

    ``nndr.syn``: for each synthetic record, ratio of its distance to the
    nearest real record vs the second nearest real record (d1/d2).  A ratio
    close to 1 means the record sits in a dense region (good generalisation);
    a ratio close to 0 means it is anchored to a single real record (privacy
    risk).

    ``nndr.real``: same ratio computed on real records against other real
    records (baseline).

    Both directions: higher is safer because the nearest and second-nearest
    neighbours are similarly distant, which suggests less anchoring to a
    single real record.
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        return "nndr"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        if len(real_data) < 3 or len(synthetic_data) == 0:
            logger.warning("Cannot calculate NNDR, not enough data.")
            return {"score": float("inf")}

        real_processed, syn_processed = self._encode_categorical_columns(real_data, synthetic_data)
        real_processed = real_processed.dropna()
        syn_processed = syn_processed.dropna()

        if len(real_processed) < 3 or len(syn_processed) == 0:
            logger.warning("Cannot calculate NNDR, not enough non-NaN data.")
            return {"score": float("inf")}

        scaler = StandardScaler()
        real_scaled = scaler.fit_transform(real_processed)
        syn_scaled = scaler.transform(syn_processed)

        # nndr.syn: fit on real, query synthetic (k=2)
        nn = NearestNeighbors(n_neighbors=2, metric="euclidean")
        nn.fit(real_scaled)
        d_syn, _ = nn.kneighbors(syn_scaled)
        syn_ratios = d_syn[:, 0] / np.where(d_syn[:, 1] > 0, d_syn[:, 1], np.finfo(float).eps)

        # nndr.real: fit on real, query real (k=3 to skip self at index 0)
        nn3 = NearestNeighbors(n_neighbors=3, metric="euclidean")
        nn3.fit(real_scaled)
        d_real, _ = nn3.kneighbors(real_scaled)
        real_ratios = d_real[:, 1] / np.where(d_real[:, 2] > 0, d_real[:, 2], np.finfo(float).eps)

        return {
            "scores": {
                "nndr.real": {
                    "mean": float(np.mean(real_ratios)),
                    "min": float(np.min(real_ratios)),
                    "max": float(np.max(real_ratios)),
                },
                "nndr.syn": {
                    "mean": float(np.mean(syn_ratios)),
                    "min": float(np.min(syn_ratios)),
                    "max": float(np.max(syn_ratios)),
                },
            },
        }


class CorrelationMatrixDistance(MetricEvaluator):
    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "correlation_matrix_distance"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute SRMSE between correlation matrices of real and synthetic data.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with a "score" key and numeric value.
        """
        if len(real_data) == 0 or len(synthetic_data) == 0:
            logger.debug("Cannot calculate correlation matrix distance, not enough data.")
            return {"score": float("inf")}

        real_processed, synthetic_processed = self._encode_categorical_columns(
            real_data, synthetic_data
        )

        real_processed = real_processed.dropna()
        synthetic_processed = synthetic_processed.dropna()

        if len(real_processed) == 0 or len(synthetic_processed) == 0:
            logger.debug("Cannot calculate correlation matrix distance, not enough non-NaN data.")
            return {"score": float("inf")}

        real_corr = real_processed.corr()
        synthetic_corr = synthetic_processed.corr()

        # Remove diagonal (always 1.0) and check if matrix is not empty
        mask = ~np.eye(real_corr.shape[0], dtype=bool)
        real_corr_no_diag = real_corr.values[mask]
        synthetic_corr_no_diag = synthetic_corr.values[mask]

        if len(real_corr_no_diag) == 0:
            logger.debug("Cannot calculate correlation matrix distance, 1x1 matrix")
            return {"score": 0.0}

        # Generate correlation matrix figures
        import matplotlib.pyplot as plt
        import seaborn as sns

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 5))

        sns.heatmap(real_corr, annot=True, cmap="coolwarm", center=0, ax=ax1, fmt=".2f")
        ax1.set_title("Real Data Correlation Matrix")

        sns.heatmap(synthetic_corr, annot=True, cmap="coolwarm", center=0, ax=ax2, fmt=".2f")
        ax2.set_title("Synthetic Data Correlation Matrix")

        fig.tight_layout()

        # Calculate SRMSE using off-diagonal values
        diff = real_corr_no_diag - synthetic_corr_no_diag
        mse = np.mean(diff**2)
        rmse = np.sqrt(mse)

        # Scale by standard deviation of real correlation matrix
        real_corr_std = np.std(real_corr_no_diag)
        srmse = rmse / real_corr_std if real_corr_std > 0 else rmse

        # Calculate L1 and Frobenius (L2) distances as well
        l1_distance = np.sum(np.abs(diff))
        frobenius_distance = np.sqrt(np.sum(diff**2))

        return {
            "score": float(srmse),
            "figure": fig,
            "additional": {
                "l1_distance": float(l1_distance),
                "frobenius_distance": float(frobenius_distance),
            },
        }


class ConfidenceIntervalOverlap(MetricEvaluator):
    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            statistics_config_path (str): Path to statistics configuration file (optional).
            custom_statistics_module (str): Path to custom statistics module (optional).
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)
        self.custom_statistics_module = kwargs.get("custom_statistics_module")
        self.statistics = self._load_statistics()

    def _load_custom_statistics(self) -> dict | None:
        """Load custom statistics from configured module.

        Returns:
            dict | None: Mapping of operation names to Statistic classes, or None if not configured.
        """
        module_path = self.custom_statistics_module or CUSTOM_STATISTICS_MODULE

        if not module_path:
            return None

        try:
            # Dynamically import the custom statistics module
            import importlib

            module = importlib.import_module(module_path)

            # Extract CUSTOM_STATISTIC_MAP from module
            if hasattr(module, "CUSTOM_STATISTIC_MAP"):
                custom_map = module.CUSTOM_STATISTIC_MAP
                logger.debug(f"Loaded {len(custom_map)} custom statistics from {module_path}")
                return custom_map
            else:
                logger.warning(f"Module {module_path} does not contain CUSTOM_STATISTIC_MAP")
                return None
        except ImportError as e:
            logger.error(f"Could not import custom statistics module {module_path}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error loading custom statistics from {module_path}: {e}")
            return None

    def _load_statistics(self) -> list[Statistic]:
        """Load statistics from configuration file and optionally custom statistics.

        Returns:
            List[Statistic]: List of configured statistics.
        """
        custom_stats = self._load_custom_statistics()

        try:
            with open(STATISTICS_CONFIG_PATH) as f:
                config = yaml.safe_load(f)

            statistics = []
            for stat_config in config.get("statistics", []):
                try:
                    stat = create_statistic(
                        CONFIDENCE_INTERVAL_LEVEL, stat_config, custom_statistic_map=custom_stats
                    )
                    statistics.append(stat)
                except ValueError as e:
                    logger.error(f"Failed to create statistic from config {stat_config}: {e}")
                    continue

            return statistics
        except FileNotFoundError:
            logger.error(f"Could not find statistics config at path {STATISTICS_CONFIG_PATH}")
            return []
        except Exception as e:
            logger.error(f"Error loading statistics configuration: {e}")
            return []

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "confidence_interval_overlap"

    def _calculate_overlap(self, ci1: tuple, ci2: tuple) -> float:
        """Calculate overlap between two confidence intervals.

        Args:
            ci1 (tuple): First confidence interval (lower, upper).
            ci2 (tuple): Second confidence interval (lower, upper).

        Returns:
            float: Overlap ratio (0 to 1).
        """
        if any(np.isnan([ci1[0], ci1[1], ci2[0], ci2[1]])):
            logger.debug("Could not calculate confidence level: NaN")
            return 0.0

        overlap_start = max(ci1[0], ci2[0])
        overlap_end = min(ci1[1], ci2[1])

        if overlap_start >= overlap_end:
            return 0.0

        overlap_length = overlap_end - overlap_start
        total_length = max(ci1[1], ci2[1]) - min(ci1[0], ci2[0])

        return overlap_length / total_length if total_length > 0 else 0.0

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute confidence interval overlap for configured statistics.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with overall score and detailed results per statistic.
        """

        if len(self.statistics) == 0:
            logger.debug("No statistics configured.")
            return {"score": 0.0}

        overlaps = []
        details = {}

        real_processed, synthetic_processed = self._encode_categorical_columns(
            real_data, synthetic_data
        )

        for statistic in self.statistics:
            try:
                # Calculate statistic for real data
                logger.debug(f"Running statistic {statistic.name()}")
                real_result = {}
                synthetic_result = {}
                if statistic.valueConvertCategorical():
                    real_result = statistic.calculate(real_processed)
                    synthetic_result = statistic.calculate(synthetic_processed)
                else:
                    real_result = statistic.calculate(real_data)
                    synthetic_result = statistic.calculate(synthetic_data)

                # Calculate overlap
                overlap = self._calculate_overlap(real_result["ci"], synthetic_result["ci"])
                overlaps.append(overlap)

                details[f"{statistic.table}_{statistic.column}_{type(statistic).__name__}"] = {
                    "overlap": overlap,
                    "real_ci_lower": real_result["ci"][0],  # have to split them for mlflow
                    "real_ci_upper": real_result["ci"][1],
                    "synthetic_ci_lower": synthetic_result["ci"][0],
                    "synthetic_ci_upper": synthetic_result["ci"][1],
                    "real_value": real_result["value"],
                    "synthetic_value": synthetic_result["value"],
                }
            except Exception as e:
                logger.error(f"Failed to run statistic metric {statistic.name()}, error: {e}")

        overall_score = np.mean(overlaps) if overlaps else 0.0

        return {"score": float(overall_score), "additional": details, "direction": "maximize"}


class AverageComplementaryTVD(MetricEvaluator):
    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)
        self.n_bins = AVERAGE_COMPLEMENTARY_TVD_N_BINS

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "average_complementary_tvd"

    def _calculate_tvd(self, real_dist: dict, synthetic_dist: dict) -> float:
        """Calculate Total Variation Distance between two distributions.

        TVD = 0.5 * Σ |P(x) - Q(x)|

        Args:
            real_dist (dict): Distribution of real data (category -> frequency).
            synthetic_dist (dict): Distribution of synthetic data (category -> frequency).

        Returns:
            float: Total Variation Distance value between 0 and 1.
        """
        all_categories = set(real_dist.keys()) | set(synthetic_dist.keys())

        tvd = 0.0
        for category in all_categories:
            real_prob = real_dist.get(category, 0)
            synthetic_prob = synthetic_dist.get(category, 0)
            tvd += abs(real_prob - synthetic_prob)

        return tvd / 2.0

    def _bin_numeric_feature(self, feature_values: pd.Series) -> pd.Series:
        """Bin a numeric feature into categorical bins.

        Args:
            feature_values (pd.Series): Numeric values to bin.

        Returns:
            pd.Series: Binned categorical values.
        """
        return pd.cut(feature_values, bins=self.n_bins, labels=False, duplicates="drop")

    def _get_distribution(self, feature_values: pd.Series) -> dict:
        """Get the distribution (frequency) of values in a feature.

        Args:
            feature_values (pd.Series): Feature values (already categorical or binned).

        Returns:
            dict: Distribution with normalized frequencies (sum to 1).
        """
        value_counts = feature_values.value_counts()
        total = len(feature_values)
        return {category: count / total for category, count in value_counts.items()}

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute the average complementary TVD across all features.

        For each feature:
        1. Bin numeric features to treat them as categorical
        2. Calculate the Total Variation Distance
        3. Compute 1 - TVD (complementary TVD)
        4. Average across all features

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.

        Returns:
            dict: A dict with "score" (average complementary TVD), per-feature scores, and direction.
        """
        if len(real_data) == 0 or len(synthetic_data) == 0:
            logger.debug("Complementary TVD: Empty dataset(s)")
            return {"score": 0.0, "per_feature_scores": {}, "errors": 1}

        complementary_tvd_scores = {}

        for column in real_data.columns:
            try:
                real_feature = real_data[column].dropna()
                synthetic_feature = synthetic_data[column].dropna()

                if len(real_feature) == 0 or len(synthetic_feature) == 0:
                    continue

                # Bin numeric features
                if pd.api.types.is_numeric_dtype(real_feature):
                    # For numeric data, use quantile-based binning to handle outliers better
                    combined_data = pd.concat([real_feature, synthetic_feature])
                    bins = np.linspace(combined_data.min(), combined_data.max(), self.n_bins + 1)
                    real_binned = pd.cut(real_feature, bins=bins, labels=False, duplicates="drop")
                    synthetic_binned = pd.cut(
                        synthetic_feature, bins=bins, labels=False, duplicates="drop"
                    )
                else:
                    real_binned = real_feature
                    synthetic_binned = synthetic_feature

                # Get distributions
                real_dist = self._get_distribution(real_binned)
                synthetic_dist = self._get_distribution(synthetic_binned)

                # Calculate TVD and inverse TVD
                tvd = self._calculate_tvd(real_dist, synthetic_dist)
                complementary_tvd = 1.0 - tvd

                complementary_tvd_scores[column] = complementary_tvd

            except Exception as e:
                logger.warning(
                    f"Error processing feature '{column}' for AverageComplementaryTVD: {e}"
                )
                continue

        if not complementary_tvd_scores:
            logger.debug("Inverse TVD: No valid features to compare")
            return {"score": 0.0, "per_feature_scores": {}, "errors": 1}

        # Calculate average inverse TVD
        average_complementary_tvd = np.mean(list(complementary_tvd_scores.values()))

        return {
            "score": float(average_complementary_tvd),
            "additional": {k: float(v) for k, v in complementary_tvd_scores.items()},
        }


class KAnonymity(MetricEvaluator):
    """Compute k-anonymity for specific column subsets with granularity analysis.

    k-anonymity measures whether each record is indistinguishable from at least k-1
    others on quasi-identifying attributes.

    In addition to the k value per subset, this metric produces:
    - **Column granularity**: single-column k and number of unique values, showing
      which columns are inherently most identifying.
    - **Equivalence class distribution**: statistics on group sizes per subset,
      showing whether groups are uniformly large (safe) or skewed with tiny groups.
    - **Marginal contribution**: for each column in a subset, the synthetic-data
      k that would result from removing it. The delta shows how much that column
      drives the synthetic k down.

    Higher k-values indicate better privacy. Returns 999 on fail.
    """

    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "k_anonymity"

    @staticmethod
    def _eq_class_stats(data: pd.DataFrame, columns: list[str]) -> dict:
        """Compute equivalence class size statistics for a set of quasi-identifiers.

        Args:
            data: Dataset to analyse.
            columns: Quasi-identifier columns that define the equivalence classes.

        Returns:
            dict with n_eq_classes and size distribution percentiles.
        """
        group_sizes = data.groupby(columns, observed=True).size()
        return {
            "n_eq_classes": int(len(group_sizes)),
            "size_min": int(group_sizes.min()),
            "size_p25": float(group_sizes.quantile(0.25)),
            "size_median": float(group_sizes.median()),
            "size_mean": float(group_sizes.mean()),
            "size_p75": float(group_sizes.quantile(0.75)),
            "size_max": int(group_sizes.max()),
        }

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute k-anonymity for multiple column subsets with granularity analysis.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.
        Returns:
            dict: A dict with per-subset scores, granularity analysis, and comparison.
        """
        from pycanon import anonymity

        if len(real_data) == 0 or len(synthetic_data) == 0:
            logger.warning("Cannot compute k-anonymity: empty dataset(s)")
            return {"score": 999, "additional": {}}

        quasi_identifier_subsets = QUASI_IDENTIFIER_SUBSETS
        subset_source = "config.evaluation.evaluation_config.QUASI_IDENTIFIER_SUBSETS"
        if quasi_identifier_subsets is None:
            logger.debug("No Quasi Identifiers found in config. Performing pairwise combinations")
            from itertools import combinations

            columns = list(real_data.columns)
            quasi_identifier_subsets = {}
            subset_source = "pairwise_combinations_of_all_columns"
            for col1, col2 in combinations(columns, 2):
                subset_name = f"{col1}/{col2}"
                quasi_identifier_subsets[subset_name] = [col1, col2]

        # --- Per-subset k-anonymity + equivalence class stats + marginal ---
        subset_results = {}

        for subset_name, columns in quasi_identifier_subsets.items():
            if not columns:
                logger.warning(f"Skipping subset '{subset_name}': no valid columns found")
                continue

            try:
                k_real = anonymity.k_anonymity(real_data, columns)
                k_syn = anonymity.k_anonymity(synthetic_data, columns)

                result_entry = {
                    "real_k": int(k_real),
                    "syn_k": int(k_syn),
                    "columns": columns,
                    "real_eq_class_stats": self._eq_class_stats(real_data, columns),
                    "syn_eq_class_stats": self._eq_class_stats(synthetic_data, columns),
                }

                # Marginal contribution on synthetic data: k when each column is removed
                if len(columns) > 1:
                    marginal = {}
                    for col in columns:
                        remaining = [c for c in columns if c != col]
                        try:
                            k_without = int(anonymity.k_anonymity(synthetic_data, remaining))
                            marginal[col] = {
                                "k_without": k_without,
                                "k_delta": k_without - int(k_syn),
                            }
                        except Exception as e:
                            logger.warning(
                                f"Could not compute marginal for '{col}' in '{subset_name}': {e}"
                            )
                    result_entry["marginal_contributions_syn"] = marginal

                subset_results[subset_name] = result_entry
                logger.debug(f"Subset '{subset_name}': real_k={k_real}, syn_k={k_syn}")

            except Exception as e:
                logger.error(f"Failed to compute k-anonymity for subset '{subset_name}': {e}")

        # --- Single-column granularity for every QI column ---
        all_qi_columns = sorted({col for cols in quasi_identifier_subsets.values() for col in cols})
        column_granularity = {}

        for col in all_qi_columns:
            try:
                column_granularity[col] = {
                    "real_k": int(anonymity.k_anonymity(real_data, [col])),
                    "syn_k": int(anonymity.k_anonymity(synthetic_data, [col])),
                    "real_n_unique": int(real_data[col].nunique()),
                    "syn_n_unique": int(synthetic_data[col].nunique()),
                }
            except Exception as e:
                logger.warning(f"Could not compute single-column granularity for '{col}': {e}")

        # --- Scores (real vs synthetic, as separate rows) ---
        report_metadata = {
            "metric_name": "k_anonymity",
            "activation_key": "k-anonymization",
            "subset_source": subset_source,
            "summary_rows": {
                "k_anonymity.real": "Minimum k observed across all configured subsets in the real dataset.",
                "k_anonymity.syn": "Minimum k observed across all configured subsets in the synthetic dataset.",
            },
            "comparison_guidance": (
                "Compare real_k and syn_k subset by subset. "
                "If syn_k is below real_k, the synthetic data is more unique on that subset. "
                "If syn_k is far above real_k, privacy is stronger but utility may be lower."
            ),
        }
        field_descriptions = {
            "real_k": (
                "k-anonymity computed on the real dataset for the subset. "
                "It is the size of the smallest equivalence class in the real data."
            ),
            "syn_k": (
                "k-anonymity computed on the synthetic dataset for the subset. "
                "It is the size of the smallest equivalence class in the synthetic data."
            ),
            "equivalence_class": (
                "A group of rows that share exactly the same values for the subset columns."
            ),
            "real_eq_class_stats": (
                "Distribution of equivalence-class sizes in the real dataset for the subset."
            ),
            "syn_eq_class_stats": (
                "Distribution of equivalence-class sizes in the synthetic dataset for the subset."
            ),
            "n_eq_classes": (
                "Number of distinct equivalence classes, i.e. unique value combinations in the subset."
            ),
            "size_min": (
                "Smallest equivalence-class size. In practice this matches the subset k value."
            ),
            "size_p25": "25th percentile of equivalence-class sizes.",
            "size_median": "Median equivalence-class size.",
            "size_mean": "Mean equivalence-class size.",
            "size_p75": "75th percentile of equivalence-class sizes.",
            "size_max": "Largest equivalence-class size.",
            "column_granularity": (
                "Single-column view showing how identifying each quasi-identifier is on its own."
            ),
            "real_n_unique": "Number of distinct values in the real dataset for that column.",
            "syn_n_unique": "Number of distinct values in the synthetic dataset for that column.",
            "marginal_reference_dataset": (
                "Dataset used to compute marginal contributions. Currently always synthetic."
            ),
            "marginal_contributions": (
                "Impact of removing one column at a time from the subset when recomputing k on synthetic data."
            ),
            "marginal_contributions_syn": (
                "Same as marginal_contributions, kept with an explicit name to indicate the reference dataset."
            ),
            "k_without": "k obtained after removing the indicated column from the subset.",
            "k_delta": (
                "Difference between k_without and syn_k. Larger positive values mean the removed column was strongly identifying."
            ),
        }
        additional = {
            "report_metadata": report_metadata,
            "field_descriptions": field_descriptions,
            "subsets": subset_results,
            "column_granularity": column_granularity,
        }

        if subset_results:
            syn_ks = [v["syn_k"] for v in subset_results.values()]
            real_ks = [v["real_k"] for v in subset_results.values()]
            return {
                "scores": {
                    "k_anonymity.real": {
                        "mean": float(np.min(real_ks)),
                        "min": float(np.min(real_ks)),
                        "max": float(np.max(real_ks)),
                    },
                    "k_anonymity.syn": {
                        "mean": float(np.min(syn_ks)),
                        "min": float(np.min(syn_ks)),
                        "max": float(np.max(syn_ks)),
                    },
                },
                "additional": additional,
            }
        else:
            return {"score": 999, "additional": additional}


class LDiversityPyCanon(MetricEvaluator):
    """Compute l-diversity for specific column subsets.

    l-diversity measures whether each group of records sharing quasi-identifiers has at least l "well-represented" sensitive values.

    Higher l-values indicate better privacy. Returns 999 on fail
    """

    def __init__(self, **kwargs) -> None:
        """Initialize the metric evaluator.

        Args:
            **kwargs: Optional keyword arguments for future extensions.
        """
        super().__init__(**kwargs)

    @staticmethod
    def name() -> str:
        """Return the canonical metric name.

        Returns:
            str: Metric identifier used in reports.
        """
        return "l_diversity_pycanon"

    def evaluate(self, real_data: pd.DataFrame, synthetic_data: pd.DataFrame) -> dict:
        """Compute l-diversity for multiple column subsets.

        Args:
            real_data (pd.DataFrame): Reference dataset.
            synthetic_data (pd.DataFrame): Generated dataset.
        Returns:
            dict: A dict with per-subset scores, additional metadata, and comparison.
        """
        from pycanon import anonymity

        if len(real_data) == 0 or len(synthetic_data) == 0:
            logger.warning("Cannot compute l-diversity: empty dataset(s)")
            return {"score": 999, "additional": {}}

        quasi_identifier_subsets = QUASI_IDENTIFIER_SUBSETS
        if quasi_identifier_subsets is None:
            logger.debug("No Quasi Identifiers found in config. Performing pairwise combinations")
            from itertools import combinations

            columns = list(real_data.columns)
            quasi_identifier_subsets = {}
            for col1, col2 in combinations(columns, 2):
                subset_name = f"{col1}/{col2}"
                quasi_identifier_subsets[subset_name] = [col1, col2]

        sensitive_columns = SENSITIVE_COLUMNS
        if sensitive_columns is None:
            logger.debug(
                "No sensitive columns defined. Performing automatic detection of id columns"
            )
            sensitive_columns = get_id_columns(real_data)

        subset_results = {}

        for subset_name, columns in quasi_identifier_subsets.items():
            if not columns:
                logger.warning(f"Skipping subset '{subset_name}': no valid columns found")
                continue

            try:
                l_real = anonymity.l_diversity(real_data, columns, sensitive_columns)
                l_syn = anonymity.l_diversity(synthetic_data, columns, sensitive_columns)

                subset_results[subset_name] = {"real_l": l_real, "syn_l": l_syn, "columns": columns}
                logger.debug(f"Subset '{subset_name}': real_l={l_real}, syn_l={l_syn}")

            except Exception as e:
                logger.error(f"Failed to compute l-diversity for subset '{subset_name}': {e}")

        # Use synthetic l-diversity for all subsets as the main score
        # (lower value indicates which subset is most vulnerable)
        if subset_results:
            main_score = np.min([v["syn_l"] for v in subset_results.values()])
        else:
            main_score = 999

        return {
            "score": float(main_score),
            "min": float(main_score),
            "max": float(np.max([v["syn_l"] for v in subset_results.values()]))
            if subset_results
            else 999,
            "additional": subset_results,
        }
