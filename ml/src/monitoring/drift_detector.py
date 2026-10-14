"""Reproducible data drift detection module implementing KS tests and PSI.

Calculates statistical distribution divergence between reference populations
(derived strictly from the training partition) and observed transaction windows.
Distinguishes statistical input drift from supervised model degradation.
"""

from __future__ import annotations

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from scipy import stats

from ml.src.data.loader import ChronologicalDataLoader

logger = logging.getLogger(__name__)

EXPECTED_FEATURE_NAMES: List[str] = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount"]

# Standard production alert thresholds
PSI_WARNING_THRESHOLD: float = 0.10
PSI_CRITICAL_THRESHOLD: float = 0.25
KS_WARNING_THRESHOLD: float = 0.10
KS_CRITICAL_THRESHOLD: float = 0.25
KS_ALPHA_SIGNIFICANCE: float = 0.05
MIN_RELIABLE_SAMPLE_SIZE: int = 30
SMOOTHING_EPSILON: float = 1e-4


@dataclass
class FeatureDriftResult:
    """Statistical drift evaluation results for a single numeric feature."""

    feature: str
    ks_statistic: Optional[float]
    ks_pvalue: Optional[float]
    psi: Optional[float]
    status: str  # NORMAL, WARNING, CRITICAL, or INSUFFICIENT_DATA
    observed_mean: Optional[float]
    reference_mean: float
    observed_std: Optional[float]
    reference_std: float
    is_constant: bool
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature": self.feature,
            "ks_statistic": round(self.ks_statistic, 5) if self.ks_statistic is not None else None,
            "ks_pvalue": round(self.ks_pvalue, 5) if self.ks_pvalue is not None else None,
            "psi": round(self.psi, 5) if self.psi is not None else None,
            "status": self.status,
            "observed_mean": round(self.observed_mean, 5) if self.observed_mean is not None else None,
            "reference_mean": round(self.reference_mean, 5),
            "observed_std": round(self.observed_std, 5) if self.observed_std is not None else None,
            "reference_std": round(self.reference_std, 5),
            "is_constant": self.is_constant,
            "warnings": self.warnings,
        }


def derive_reference_bin_edges(ref_values: np.ndarray, n_bins: int = 10) -> np.ndarray:
    """Derives strictly monotonic, deterministic bin edges from reference data.

    Args:
        ref_values: 1D array of reference feature values.
        n_bins: Target number of quantile bins (default: 10 deciles).

    Returns:
        1D array of bin edges bounded by [-inf, q1, ..., qk, +inf].
    """
    finite_ref = ref_values[np.isfinite(ref_values)]
    if len(finite_ref) == 0:
        return np.array([-np.inf, np.inf])

    percentiles = np.linspace(100.0 / n_bins, 100.0 - (100.0 / n_bins), n_bins - 1)
    q_edges = np.percentile(finite_ref, percentiles)
    # Deduplicate edges (e.g. For zero-heavy or constant features) while preserving bounds
    unique_edges = np.unique(np.concatenate([[-np.inf], q_edges, [np.inf]]))
    return unique_edges


def compute_psi(
    ref_values: np.ndarray,
    obs_values: np.ndarray,
    bin_edges: np.ndarray,
    epsilon: float = SMOOTHING_EPSILON,
) -> Optional[float]:
    """Calculates Population Stability Index (PSI) with zero-frequency smoothing.

    Uses deterministic bin edges derived from the reference distribution:
        PSI = sum((Q_i - P_i) * ln(Q_i / P_i))
    where P_i is the reference proportion and Q_i is the observed proportion.

    Args:
        ref_values: 1D array of reference feature values.
        obs_values: 1D array of observed feature values.
        bin_edges: Pre-derived reference quantile edges.
        epsilon: Smoothing constant applied to zero-count bins.

    Returns:
        PSI float value, or None if sample size is zero.
    """
    ref_finite = ref_values[np.isfinite(ref_values)]
    obs_finite = obs_values[np.isfinite(obs_values)]

    if len(ref_finite) == 0 or len(obs_finite) == 0:
        return None

    ref_counts, _ = np.histogram(ref_finite, bins=bin_edges)
    obs_counts, _ = np.histogram(obs_finite, bins=bin_edges)

    p_prop = ref_counts / len(ref_finite)
    q_prop = obs_counts / len(obs_finite)

    # Documented smoothing rule: Clamp zero or tiny counts to epsilon and renormalize
    p_smooth = np.maximum(p_prop, epsilon)
    p_smooth = p_smooth / p_smooth.sum()

    q_smooth = np.maximum(q_prop, epsilon)
    q_smooth = q_smooth / q_smooth.sum()

    psi_val = float(np.sum((q_smooth - p_smooth) * np.log(q_smooth / p_smooth)))
    return max(0.0, psi_val)


def compute_ks(
    ref_values: np.ndarray,
    obs_values: np.ndarray,
) -> Tuple[Optional[float], Optional[float]]:
    """Calculates two-sample Kolmogorov-Smirnov statistic and asymptotic p-value.

    Args:
        ref_values: 1D array of reference observations.
        obs_values: 1D array of observed observations.

    Returns:
        Tuple of (ks_statistic, p_value), or (None, None) if samples are empty.
    """
    ref_finite = ref_values[np.isfinite(ref_values)]
    obs_finite = obs_values[np.isfinite(obs_values)]

    if len(ref_finite) == 0 or len(obs_finite) == 0:
        return None, None

    # Handle constant arrays
    ref_min, ref_max = np.min(ref_finite), np.max(ref_finite)
    obs_min, obs_max = np.min(obs_finite), np.max(obs_finite)

    if ref_min == ref_max and obs_min == obs_max:
        if ref_min == obs_min:
            return 0.0, 1.0
        return 1.0, 0.0

    res = stats.ks_2samp(ref_finite, obs_finite)
    return float(res.statistic), float(res.pvalue)


class ReferenceProfile:
    """Encapsulates reference distribution baselines derived from training data."""

    def __init__(
        self,
        feature_names: List[str],
        reference_data: Dict[str, np.ndarray],
        version: str = "training_v1",
        time_range: Tuple[float, float] = (0.0, 0.0),
    ) -> None:
        self.feature_names = feature_names
        self.reference_data = reference_data
        self.version = version
        self.time_range = time_range
        self.sample_count = len(next(iter(reference_data.values()))) if reference_data else 0

        # Precompute per-feature reference properties and deterministic quantile bin edges
        self.stats: Dict[str, Dict[str, Any]] = {}
        for feat in self.feature_names:
            vals = reference_data[feat]
            finite_vals = vals[np.isfinite(vals)]
            edges = derive_reference_bin_edges(finite_vals, n_bins=10)
            self.stats[feat] = {
                "mean": float(np.mean(finite_vals)) if len(finite_vals) > 0 else 0.0,
                "std": float(np.std(finite_vals)) if len(finite_vals) > 0 else 0.0,
                "min": float(np.min(finite_vals)) if len(finite_vals) > 0 else 0.0,
                "max": float(np.max(finite_vals)) if len(finite_vals) > 0 else 0.0,
                "bin_edges": edges,
                "is_constant": bool(np.min(finite_vals) == np.max(finite_vals)) if len(finite_vals) > 0 else False,
            }

    @classmethod
    def from_dataframe(
        cls,
        df: pd.DataFrame,
        version: str = "training_v1_chronological_70",
    ) -> ReferenceProfile:
        """Constructs reference profile strictly from an approved training DataFrame.

        Never reads or accepts held-out test data.
        """
        if "Class" in df.columns:
            df = df.drop(columns=["Class"])

        cols = [c for c in EXPECTED_FEATURE_NAMES if c in df.columns]
        ref_dict = {col: df[col].to_numpy(dtype=float) for col in cols}

        time_min = float(df["Time"].min()) if "Time" in df.columns else 0.0
        time_max = float(df["Time"].max()) if "Time" in df.columns else 0.0

        return cls(
            feature_names=cols,
            reference_data=ref_dict,
            version=version,
            time_range=(time_min, time_max),
        )

    def evaluate_feature(
        self,
        feature_name: str,
        obs_values: np.ndarray,
    ) -> FeatureDriftResult:
        """Evaluates KS and PSI drift for a single feature against reference profile."""
        if feature_name not in self.stats:
            raise ValueError(f"Unknown feature '{feature_name}' not in reference profile.")

        ref_feat_stats = self.stats[feature_name]
        ref_values = self.reference_data[feature_name]
        bin_edges = ref_feat_stats["bin_edges"]
        warnings: List[str] = []

        obs_finite = obs_values[np.isfinite(obs_values)]
        n_obs = len(obs_finite)

        if n_obs == 0:
            return FeatureDriftResult(
                feature=feature_name,
                ks_statistic=None,
                ks_pvalue=None,
                psi=None,
                status="INSUFFICIENT_DATA",
                observed_mean=None,
                reference_mean=ref_feat_stats["mean"],
                observed_std=None,
                reference_std=ref_feat_stats["std"],
                is_constant=ref_feat_stats["is_constant"],
                warnings=["Empty observation sample; statistical metrics are undefined."],
            )

        if n_obs < MIN_RELIABLE_SAMPLE_SIZE:
            warnings.append(
                f"Sample size N={n_obs} < {MIN_RELIABLE_SAMPLE_SIZE}: statistical power is limited."
            )

        # Check if observed feature is constant
        obs_min, obs_max = float(np.min(obs_finite)), float(np.max(obs_finite))
        obs_constant = bool(obs_min == obs_max)
        if obs_constant and not ref_feat_stats["is_constant"]:
            warnings.append(f"Observed feature is invariant/constant (val={obs_min}).")

        # Compute metrics
        ks_stat, ks_pval = compute_ks(ref_values, obs_finite)
        psi_val = compute_psi(ref_values, obs_finite, bin_edges=bin_edges)

        obs_mean = float(np.mean(obs_finite))
        obs_std = float(np.std(obs_finite))

        # Determine feature status
        status_val = "NORMAL"
        if psi_val is not None and psi_val >= PSI_CRITICAL_THRESHOLD:
            status_val = "CRITICAL"
        elif ks_stat is not None and ks_pval is not None and ks_stat >= KS_CRITICAL_THRESHOLD and ks_pval < KS_ALPHA_SIGNIFICANCE:
            status_val = "CRITICAL"
        elif psi_val is not None and psi_val >= PSI_WARNING_THRESHOLD:
            status_val = "WARNING"
        elif ks_stat is not None and ks_pval is not None and ks_stat >= KS_WARNING_THRESHOLD and ks_pval < KS_ALPHA_SIGNIFICANCE:
            status_val = "WARNING"

        return FeatureDriftResult(
            feature=feature_name,
            ks_statistic=ks_stat,
            ks_pvalue=ks_pval,
            psi=psi_val,
            status=status_val,
            observed_mean=obs_mean,
            reference_mean=ref_feat_stats["mean"],
            observed_std=obs_std,
            reference_std=ref_feat_stats["std"],
            is_constant=obs_constant,
            warnings=warnings,
        )

    def evaluate_dataset(
        self,
        observed_df: pd.DataFrame,
        time_window_start: datetime,
        time_window_end: datetime,
        model_version: str = "xgb-cost-v1",
        invalid_rows_count: int = 0,
        quality_issues: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Runs full 30-feature drift evaluation and compiles a persistent summary report."""
        n_obs = len(observed_df)
        report_warnings: List[str] = []

        if invalid_rows_count > 0:
            report_warnings.append(
                f"Excluded {invalid_rows_count} invalid/non-finite transactions from statistical calculations."
            )

        if n_obs == 0:
            report_warnings.append(
                "Empty observation window: 0 transactions available. Statistical drift metrics are undefined."
            )
            overall_status = "WARNING"
            primary_metric_val = 0.0
            primary_metric_name = "MAX_FEATURE_PSI"
            per_feature_results: Dict[str, Dict[str, Any]] = {}
            for feat in self.feature_names:
                per_feature_results[feat] = self.evaluate_feature(feat, np.array([])).to_dict()

            summary = {
                "report_id": str(uuid.uuid4()),
                "model_version": model_version,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "overall_status": overall_status,
                "primary_metric": {
                    "name": primary_metric_name,
                    "value": primary_metric_val,
                    "feature": None,
                    "status": "INSUFFICIENT_DATA",
                },
                "reference_population": {
                    "dataset_source": "creditcard.csv training split (chronological 70%)",
                    "version": self.version,
                    "sample_count": self.sample_count,
                    "time_range": list(self.time_range),
                },
                "observed_population": {
                    "time_window_start": time_window_start.isoformat(),
                    "time_window_end": time_window_end.isoformat(),
                    "total_transactions_in_window": invalid_rows_count,
                    "valid_sample_count": 0,
                    "invalid_sample_count": invalid_rows_count,
                    "invalid_rows_handling": "Excluded non-finite/missing rows from distribution calculation; logged in quality audit",
                    "insufficient_sample_size": True,
                },
                "methodology": {
                    "ks_test": {
                        "method": "Two-sample Kolmogorov-Smirnov test (scipy.stats.ks_2samp)",
                        "warning_threshold": KS_WARNING_THRESHOLD,
                        "critical_threshold": KS_CRITICAL_THRESHOLD,
                        "significance_level": KS_ALPHA_SIGNIFICANCE,
                    },
                    "psi": {
                        "method": "Population Stability Index using reference-derived decile bins",
                        "bins_count": 10,
                        "smoothing_epsilon": SMOOTHING_EPSILON,
                        "warning_threshold": PSI_WARNING_THRESHOLD,
                        "critical_threshold": PSI_CRITICAL_THRESHOLD,
                    },
                    "disclaimer": (
                        "Statistical data drift measures input feature distribution shifts against the reference "
                        "training population. It is an operational alerting signal and does NOT demonstrate model "
                        "performance degradation, nor does it automatically trigger retraining or model promotion."
                    ),
                },
                "metrics_summary": {
                    "features_analyzed": len(self.feature_names),
                    "features_normal": 0,
                    "features_warning": 0,
                    "features_critical": 0,
                    "max_psi": 0.0,
                    "mean_psi": 0.0,
                    "max_ks": 0.0,
                    "mean_ks": 0.0,
                },
                "per_feature_drift": per_feature_results,
                "warnings": report_warnings,
                "quality_issues": quality_issues or [],
            }
            return summary

        # Non-empty sample evaluation
        per_feature_results = {}
        psi_values: List[float] = []
        ks_values: List[float] = []
        status_counts = {"NORMAL": 0, "WARNING": 0, "CRITICAL": 0, "INSUFFICIENT_DATA": 0}
        max_psi_feature = None
        max_psi_val = -1.0

        for feat in self.feature_names:
            vals = observed_df[feat].to_numpy(dtype=float) if feat in observed_df.columns else np.array([])
            res = self.evaluate_feature(feat, vals)
            res_dict = res.to_dict()
            per_feature_results[feat] = res_dict

            status_counts[res.status] = status_counts.get(res.status, 0) + 1

            if res.psi is not None:
                psi_values.append(res.psi)
                if res.psi > max_psi_val:
                    max_psi_val = res.psi
                    max_psi_feature = feat

            if res.ks_statistic is not None:
                ks_values.append(res.ks_statistic)

        # Overall status derivation
        if status_counts["CRITICAL"] > 0:
            overall_status = "CRITICAL"
        elif status_counts["WARNING"] > 0 or (n_obs < MIN_RELIABLE_SAMPLE_SIZE):
            overall_status = "WARNING"
        else:
            overall_status = "NORMAL"

        if n_obs < MIN_RELIABLE_SAMPLE_SIZE:
            report_warnings.append(
                f"Small sample size (N={n_obs} < {MIN_RELIABLE_SAMPLE_SIZE}): Statistical significance tests have reduced statistical power."
            )

        primary_metric_val = max(0.0, max_psi_val if max_psi_val >= 0 else 0.0)

        return {
            "report_id": str(uuid.uuid4()),
            "model_version": model_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "overall_status": overall_status,
            "primary_metric": {
                "name": "MAX_FEATURE_PSI",
                "value": round(primary_metric_val, 5),
                "feature": max_psi_feature,
                "status": overall_status,
            },
            "reference_population": {
                "dataset_source": "creditcard.csv training split (chronological 70%)",
                "version": self.version,
                "sample_count": self.sample_count,
                "time_range": list(self.time_range),
            },
            "observed_population": {
                "time_window_start": time_window_start.isoformat(),
                "time_window_end": time_window_end.isoformat(),
                "total_transactions_in_window": n_obs + invalid_rows_count,
                "valid_sample_count": n_obs,
                "invalid_sample_count": invalid_rows_count,
                "invalid_rows_handling": "Excluded non-finite/missing rows from distribution calculation; logged in quality audit",
                "insufficient_sample_size": bool(n_obs < MIN_RELIABLE_SAMPLE_SIZE),
            },
            "methodology": {
                "ks_test": {
                    "method": "Two-sample Kolmogorov-Smirnov test (scipy.stats.ks_2samp)",
                    "warning_threshold": KS_WARNING_THRESHOLD,
                    "critical_threshold": KS_CRITICAL_THRESHOLD,
                    "significance_level": KS_ALPHA_SIGNIFICANCE,
                },
                "psi": {
                    "method": "Population Stability Index using reference-derived decile bins",
                    "bins_count": 10,
                    "smoothing_epsilon": SMOOTHING_EPSILON,
                    "warning_threshold": PSI_WARNING_THRESHOLD,
                    "critical_threshold": PSI_CRITICAL_THRESHOLD,
                },
                "disclaimer": (
                    "Statistical data drift measures input feature distribution shifts against the reference "
                    "training population. It is an operational alerting signal and does NOT demonstrate model "
                    "performance degradation, nor does it automatically trigger retraining or model promotion."
                ),
            },
            "metrics_summary": {
                "features_analyzed": len(self.feature_names),
                "features_normal": status_counts["NORMAL"],
                "features_warning": status_counts["WARNING"],
                "features_critical": status_counts["CRITICAL"],
                "max_psi": round(float(np.max(psi_values)), 5) if psi_values else 0.0,
                "mean_psi": round(float(np.mean(psi_values)), 5) if psi_values else 0.0,
                "max_ks": round(float(np.max(ks_values)), 5) if ks_values else 0.0,
                "mean_ks": round(float(np.mean(ks_values)), 5) if ks_values else 0.0,
            },
            "per_feature_drift": per_feature_results,
            "warnings": report_warnings,
            "quality_issues": quality_issues or [],
        }


# Module-level singleton cache
_profile_cache: Optional[ReferenceProfile] = None


def get_reference_profile() -> ReferenceProfile:
    """Returns singleton ReferenceProfile initialized strictly on training split."""
    global _profile_cache
    if _profile_cache is None:
        # Check for precomputed serialized reference profile
        candidate_paths = [
            Path(os.getenv("MODEL_DIR", "")) / "reference_profile.joblib" if os.getenv("MODEL_DIR") else None,
            Path(__file__).resolve().parents[3] / "ml" / "models" / "reference_profile.joblib",
            Path("ml/models/reference_profile.joblib"),
            Path(r"C:\FraudDetection\ml\models\reference_profile.joblib"),
        ]
        ref_file = next((p for p in candidate_paths if p and p.exists()), None)
        if ref_file is not None:
            logger.info("Loading precomputed reference profile from %s", ref_file)
            _profile_cache = joblib.load(ref_file)
        else:
            logger.info("Initializing reference profile strictly from training partition...")
            loader = ChronologicalDataLoader()
            split = loader.split()
            _profile_cache = ReferenceProfile.from_dataframe(
                split.X_train,
                version="training_v1_chronological_70",
            )
    return _profile_cache
