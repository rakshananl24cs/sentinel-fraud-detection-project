"""Tests for SHAP explainability and end-to-end inference pipeline."""

import numpy as np
import pytest

from ml.src.models.inference import (
    EXPECTED_FEATURE_NAMES,
    InferenceError,
    predict_fraud,
)


@pytest.fixture
def synthetic_valid_transaction() -> dict:
    """Creates a clearly labeled synthetic transaction fixture conforming to the 30-feature schema."""
    tx = {"Time": 50000.0, "Amount": 149.50}
    for i in range(1, 29):
        tx[f"V{i}"] = 0.05 * (-1 if i % 2 == 0 else 1)
    return tx


def test_inference_valid_output_schema(synthetic_valid_transaction):
    """Verifies that predict_fraud produces complete, valid output schema."""
    result = predict_fraud(synthetic_valid_transaction)

    # Core required fields
    assert "transaction_id" in result
    assert result["model_version"] == "xgb-cost-v1"
    assert "timestamp_utc" in result
    assert "fraud_probability" in result
    assert "raw_probability" in result
    assert "risk_level" in result
    assert "decision" in result
    assert "expected_cost" in result
    assert "policy_parameters" in result
    assert "explanation" in result

    # Value ranges
    assert 0.0 <= result["fraud_probability"] <= 1.0
    assert 0.0 <= result["raw_probability"] <= 1.0
    assert result["decision"] in ["APPROVE", "REVIEW", "BLOCK"]
    assert result["risk_level"] in ["LOW", "MEDIUM", "HIGH"]
    assert result["expected_cost"] >= 0.0


def test_inference_shap_explanation_structure(synthetic_valid_transaction):
    """Verifies SHAP explanation formatting, output space, and ranking."""
    result = predict_fraud(synthetic_valid_transaction)
    exp = result["explanation"]

    assert exp["output_space"] == "raw_margin_log_odds"
    assert "base_value" in exp
    assert "analyst_summary" in exp
    assert "limitations" in exp
    assert "empirical real-world causation" in exp["limitations"]

    top_contribs = exp["top_contributions"]
    assert len(top_contribs) == 5

    # Contributions must be sorted in descending order of absolute magnitude
    abs_magnitudes = [c["absolute_contribution"] for c in top_contribs]
    assert abs_magnitudes == sorted(abs_magnitudes, reverse=True)

    for item in top_contribs:
        assert item["feature"] in EXPECTED_FEATURE_NAMES
        assert item["direction"] in ["increases_risk", "decreases_risk"]


def test_inference_rejects_missing_features(synthetic_valid_transaction):
    """Verifies that missing features trigger an actionable InferenceError."""
    bad_tx = synthetic_valid_transaction.copy()
    del bad_tx["V14"]

    with pytest.raises(InferenceError, match="Missing required features"):
        predict_fraud(bad_tx)


def test_inference_rejects_non_finite_values(synthetic_valid_transaction):
    """Verifies that NaN and Inf are rejected."""
    bad_nan = synthetic_valid_transaction.copy()
    bad_nan["Amount"] = float("nan")
    with pytest.raises(InferenceError, match="non-finite value"):
        predict_fraud(bad_nan)

    bad_inf = synthetic_valid_transaction.copy()
    bad_inf["V1"] = float("inf")
    with pytest.raises(InferenceError, match="non-finite value"):
        predict_fraud(bad_inf)


def test_inference_rejects_target_class(synthetic_valid_transaction):
    """Verifies that including 'Class' in the transaction payload is rejected."""
    bad_tx = synthetic_valid_transaction.copy()
    bad_tx["Class"] = 1

    with pytest.raises(InferenceError, match="Target column 'Class' must not be included"):
        predict_fraud(bad_tx)


def test_inference_deterministic_reproducibility(synthetic_valid_transaction):
    """Verifies identical predictions for identical transaction input."""
    res1 = predict_fraud(synthetic_valid_transaction)
    res2 = predict_fraud(synthetic_valid_transaction)

    assert res1["fraud_probability"] == res2["fraud_probability"]
    assert res1["raw_probability"] == res2["raw_probability"]
    assert res1["decision"] == res2["decision"]
    assert res1["expected_cost"] == res2["expected_cost"]

    # SHAP contributions identical
    c1 = res1["explanation"]["top_contributions"]
    c2 = res2["explanation"]["top_contributions"]
    assert [x["contribution"] for x in c1] == [x["contribution"] for x in c2]
