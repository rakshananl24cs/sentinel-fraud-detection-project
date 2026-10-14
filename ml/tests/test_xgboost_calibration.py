"""Tests for XGBoost fraud model and probability calibration."""

from pathlib import Path
import numpy as np
import pandas as pd
import pytest

from ml.src.models.calibration import (
    CalibrationError,
    ProbabilityCalibrator,
    evaluate_calibration,
)
from ml.src.models.xgboost_model import XGBoostFraudModel


@pytest.fixture
def synthetic_training_data():
    """Generates synthetic classification dataset for unit testing."""
    np.random.seed(42)
    n_samples = 500
    cols = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount"]
    X = pd.DataFrame(np.random.randn(n_samples, 30), columns=cols)
    # Severe imbalance: 5% positive
    y = pd.Series(np.random.choice([0, 1], size=n_samples, p=[0.95, 0.05]))
    return X, y


def test_xgboost_training_and_probability_bounds(synthetic_training_data):
    """Verifies that XGBoost trains and outputs finite probabilities in [0, 1]."""
    X, y = synthetic_training_data
    model = XGBoostFraudModel(n_estimators=10, max_depth=3, random_state=42)
    model.fit(X, y)

    probs = model.predict_proba(X)
    assert len(probs) == len(X)
    assert np.all(np.isfinite(probs))
    assert np.all(probs >= 0.0)
    assert np.all(probs <= 1.0)


def test_xgboost_scale_pos_weight_calculation(synthetic_training_data):
    """Verifies that scale_pos_weight is mathematically computed from training labels."""
    X, y = synthetic_training_data
    pos_count = int(np.sum(y == 1))
    neg_count = int(np.sum(y == 0))
    expected_weight = neg_count / pos_count

    model = XGBoostFraudModel(n_estimators=5, max_depth=2)
    model.fit(X, y)

    assert model.scale_pos_weight is not None
    assert np.isclose(model.scale_pos_weight, expected_weight, rtol=1e-5)


def test_xgboost_non_overwrite_safeguard(tmp_path: Path, synthetic_training_data):
    """Verifies that saving the model prevents overwriting existing artifacts."""
    X, y = synthetic_training_data
    model = XGBoostFraudModel(n_estimators=5, max_depth=2)
    model.fit(X, y)

    artifact_path = tmp_path / "model.joblib"
    model.save(artifact_path)
    assert artifact_path.exists()

    with pytest.raises(FileExistsError, match="already exists"):
        model.save(artifact_path)


def test_calibrator_isotonic_and_platt():
    """Verifies that both Isotonic and Platt calibration map scores into valid [0, 1] range."""
    np.random.seed(42)
    n = 200
    raw_probs = np.random.uniform(0.01, 0.99, size=n)
    y_val = (raw_probs > 0.5).astype(int)

    # 1. Isotonic
    iso = ProbabilityCalibrator(method="isotonic")
    iso.fit(raw_probs, y_val)
    iso_cal = iso.calibrate(raw_probs)
    assert np.all(np.isfinite(iso_cal))
    assert np.all((iso_cal >= 0.0) & (iso_cal <= 1.0))

    # 2. Platt
    platt = ProbabilityCalibrator(method="platt")
    platt.fit(raw_probs, y_val)
    platt_cal = platt.calibrate(raw_probs)
    assert np.all(np.isfinite(platt_cal))
    assert np.all((platt_cal >= 0.0) & (platt_cal <= 1.0))


def test_calibrator_unfitted_rejection():
    """Verifies that calibrator rejects transformation prior to validation fitting."""
    cal = ProbabilityCalibrator(method="isotonic")
    with pytest.raises(CalibrationError, match="must be fitted"):
        cal.calibrate(np.array([0.5, 0.8]))


def test_calibrator_non_overwrite_safeguard(tmp_path: Path):
    """Verifies calibrator save raises FileExistsError on collision."""
    np.random.seed(42)
    probs = np.array([0.1, 0.4, 0.7, 0.9])
    y = np.array([0, 0, 1, 1])

    cal = ProbabilityCalibrator(method="isotonic")
    cal.fit(probs, y)

    save_path = tmp_path / "calibrator.joblib"
    cal.save(save_path)
    assert save_path.exists()

    with pytest.raises(FileExistsError, match="already exists"):
        cal.save(save_path)


def test_calibration_evaluation_metrics():
    """Verifies that evaluate_calibration outputs expected structure and finite Brier score."""
    y_true = np.array([0, 0, 0, 1, 1])
    y_prob = np.array([0.05, 0.1, 0.2, 0.8, 0.95])

    eval_result = evaluate_calibration(y_true, y_prob, n_bins=5)
    assert "brier_score" in eval_result
    assert 0.0 <= eval_result["brier_score"] <= 1.0
    assert "expected_calibration_error" in eval_result
    assert "calibration_curve" in eval_result
