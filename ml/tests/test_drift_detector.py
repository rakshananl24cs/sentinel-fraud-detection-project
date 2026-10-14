"""Unit tests for Kolmogorov-Smirnov and Population Stability Index (PSI) drift detection."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

from ml.src.data.loader import ChronologicalDataLoader
from ml.src.monitoring.drift_detector import (
    FeatureDriftResult,
    ReferenceProfile,
    compute_ks,
    compute_psi,
    derive_reference_bin_edges,
)


def test_derive_reference_bin_edges_deterministic():
    """Verifies bin edges are deterministic, strictly monotonic, and bounded by inf."""
    np.random.seed(42)
    ref = np.random.normal(10.0, 2.5, 1000)

    edges1 = derive_reference_bin_edges(ref, n_bins=10)
    edges2 = derive_reference_bin_edges(ref, n_bins=10)

    assert np.array_equal(edges1, edges2), "Bin edges must be completely deterministic"
    assert edges1[0] == -np.inf
    assert edges1[-1] == np.inf
    assert len(edges1) == 11, "10 bins should produce 11 edges when unique"
    assert np.all(np.diff(edges1[1:-1]) > 0), "Inner edges must be strictly increasing"


def test_psi_identical_distributions():
    """Verifies PSI is near zero for samples drawn from the identical distribution."""
    np.random.seed(42)
    ref = np.random.normal(0.0, 1.0, 50000)
    obs = np.random.normal(0.0, 1.0, 10000)

    edges = derive_reference_bin_edges(ref, n_bins=10)
    psi = compute_psi(ref, obs, edges)

    assert psi is not None
    assert psi < 0.05, f"PSI for identical distribution should be near 0, got {psi}"


def test_psi_deliberately_shifted_distribution():
    """Verifies PSI flags significant drift for shifted distribution (> 0.25)."""
    np.random.seed(42)
    ref = np.random.normal(0.0, 1.0, 50000)
    # Substantial distribution shift
    obs = np.random.normal(1.2, 1.0, 10000)

    edges = derive_reference_bin_edges(ref, n_bins=10)
    psi = compute_psi(ref, obs, edges)

    assert psi is not None
    assert psi > 0.25, f"PSI for substantial distribution shift should be > 0.25, got {psi}"


def test_psi_zero_frequency_smoothing():
    """Verifies zero-frequency bins are smoothed without division by zero or NaN."""
    ref = np.array([-5.0, -4.0, -3.0, -2.0, -1.0, 1.0, 2.0, 3.0, 4.0, 5.0])
    # Obs contains only positive numbers, meaning negative bins will have 0 counts
    obs = np.array([2.0, 2.5, 3.0, 3.5, 4.0])

    edges = derive_reference_bin_edges(ref, n_bins=5)
    psi = compute_psi(ref, obs, edges, epsilon=1e-4)

    assert psi is not None
    assert np.isfinite(psi)
    assert psi > 0.0


def test_ks_identical_and_shifted_distributions():
    """Verifies KS statistic and p-value on identical and shifted samples."""
    np.random.seed(42)
    ref = np.random.normal(0.0, 1.0, 10000)
    obs_identical = np.random.normal(0.0, 1.0, 5000)
    obs_shifted = np.random.normal(0.8, 1.0, 5000)

    # Identical
    ks_stat_ident, ks_p_ident = compute_ks(ref, obs_identical)
    assert ks_stat_ident is not None and ks_p_ident is not None
    assert ks_stat_ident < 0.05
    assert ks_p_ident > 0.05

    # Shifted
    ks_stat_shift, ks_p_shift = compute_ks(ref, obs_shifted)
    assert ks_stat_shift is not None and ks_p_shift is not None
    assert ks_stat_shift > 0.20
    assert ks_p_shift < 1e-10


def test_constant_features_handling():
    """Verifies constant feature handling in KS and PSI without exceptions."""
    ref_const = np.array([5.0] * 100)
    obs_same_const = np.array([5.0] * 50)
    obs_diff_const = np.array([10.0] * 50)

    # Identical constant -> zero divergence
    ks_stat_same, ks_p_same = compute_ks(ref_const, obs_same_const)
    assert ks_stat_same == 0.0
    assert ks_p_same == 1.0

    # Different constant -> divergence = 1.0
    ks_stat_diff, ks_p_diff = compute_ks(ref_const, obs_diff_const)
    assert ks_stat_diff == 1.0
    assert ks_p_diff == 0.0


def test_missing_and_non_finite_values_handling():
    """Verifies non-finite values (NaN, inf) are handled safely."""
    ref = np.array([1.0, 2.0, 3.0, 4.0, 5.0, np.nan, np.inf])
    obs = np.array([1.0, 2.0, np.nan, -np.inf, 3.0])

    edges = derive_reference_bin_edges(ref, n_bins=3)
    psi = compute_psi(ref, obs, edges)
    ks_stat, ks_p = compute_ks(ref, obs)

    assert psi is not None and np.isfinite(psi)
    assert ks_stat is not None and np.isfinite(ks_stat)


def test_empty_observation_sample():
    """Verifies empty observation sample returns None metrics."""
    ref = np.array([1.0, 2.0, 3.0])
    obs_empty = np.array([])

    edges = derive_reference_bin_edges(ref, n_bins=3)
    assert compute_psi(ref, obs_empty, edges) is None
    ks_stat, ks_p = compute_ks(ref, obs_empty)
    assert ks_stat is None and ks_p is None


def test_reference_profile_evaluation_and_test_split_isolation():
    """Verifies ReferenceProfile constructs correctly from training data and never uses test split."""
    # 1. Load data split
    loader = ChronologicalDataLoader()
    split = loader.split()

    # Ensure reference profile can be built strictly on X_train
    profile = ReferenceProfile.from_dataframe(split.X_train, version="test_profile")
    assert profile.sample_count == 199368
    assert len(profile.feature_names) == 30

    # 2. Evaluate simulated observed DataFrame
    synthetic_obs = split.X_val.iloc[:100].copy()
    start_utc = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)
    end_utc = datetime(2026, 10, 10, 0, 0, tzinfo=timezone.utc)

    report = profile.evaluate_dataset(
        observed_df=synthetic_obs,
        time_window_start=start_utc,
        time_window_end=end_utc,
        model_version="xgb-cost-v1",
    )

    assert "report_id" in report
    assert report["overall_status"] in ("NORMAL", "WARNING", "CRITICAL")
    assert report["metrics_summary"]["features_analyzed"] == 30
    assert "Time" in report["per_feature_drift"]
    assert "Amount" in report["per_feature_drift"]
    assert "disclaimer" in report["methodology"]

    # Verify that X_test was never passed to profile
    assert profile.sample_count != len(split.X_test)
