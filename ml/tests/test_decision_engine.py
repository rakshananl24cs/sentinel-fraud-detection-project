"""Tests for CostMatrix, ThreeWayDecisionPolicy, and PolicyOptimizer."""

import numpy as np
import pytest

from ml.src.decision.cost_matrix import CostMatrix
from ml.src.decision.policy import (
    DecisionAction,
    PolicyValidationError,
    ThreeWayDecisionPolicy,
)
from ml.src.decision.optimizer import PolicyOptimizer


def test_decision_mapping_boundaries():
    """Verifies exact action mapping below, inside, and above threshold boundaries."""
    policy = ThreeWayDecisionPolicy(threshold_review=0.10, threshold_block=0.80)

    # 1. Single decisions
    assert policy.decide_single(0.00) == DecisionAction.APPROVE.value
    assert policy.decide_single(0.0999) == DecisionAction.APPROVE.value
    assert policy.decide_single(0.10) == DecisionAction.REVIEW.value
    assert policy.decide_single(0.50) == DecisionAction.REVIEW.value
    assert policy.decide_single(0.7999) == DecisionAction.REVIEW.value
    assert policy.decide_single(0.80) == DecisionAction.BLOCK.value
    assert policy.decide_single(1.00) == DecisionAction.BLOCK.value

    # 2. Vectorized decisions
    probs = np.array([0.05, 0.10, 0.50, 0.80, 0.95])
    decisions = policy.decide(probs)
    expected = [
        DecisionAction.APPROVE.value,
        DecisionAction.REVIEW.value,
        DecisionAction.REVIEW.value,
        DecisionAction.BLOCK.value,
        DecisionAction.BLOCK.value,
    ]
    assert list(decisions) == expected


def test_invalid_thresholds_rejection():
    """Verifies that invalid or unordered thresholds raise PolicyValidationError."""
    with pytest.raises(PolicyValidationError, match="Invalid threshold ordering"):
        ThreeWayDecisionPolicy(threshold_review=0.80, threshold_block=0.20)  # Inverted

    with pytest.raises(PolicyValidationError, match="Invalid threshold ordering"):
        ThreeWayDecisionPolicy(threshold_review=0.50, threshold_block=0.50)  # Equal

    with pytest.raises(PolicyValidationError, match="Invalid threshold ordering"):
        ThreeWayDecisionPolicy(threshold_review=-0.1, threshold_block=0.80)  # Negative


def test_invalid_probabilities_rejection():
    """Verifies that non-finite or out-of-range probabilities are rejected."""
    policy = ThreeWayDecisionPolicy(threshold_review=0.10, threshold_block=0.80)

    with pytest.raises(PolicyValidationError, match="non-finite"):
        policy.decide(np.array([0.2, np.nan, 0.5]))

    with pytest.raises(PolicyValidationError, match="outside valid range"):
        policy.decide(np.array([0.2, 1.2, 0.5]))

    with pytest.raises(PolicyValidationError, match="outside valid range"):
        policy.decide(np.array([-0.01, 0.5]))


def test_cost_matrix_accounting_and_no_double_counting():
    """Validates exact arithmetic of the documented cost matrix with hand-crafted outcomes."""
    cm = CostMatrix(
        cost_fn=100.0,
        cost_fp=5.0,
        cost_review=5.0,
        cost_friction=50.0,
        review_efficiency=1.0,
    )

    # 6 hand-verified cases:
    # 0: Genuine approved -> $0
    # 1: Genuine reviewed -> $5 (review op)
    # 2: Genuine blocked  -> $50 (friction)
    # 3: Fraud approved   -> $100 (missed fraud)
    # 4: Fraud reviewed   -> $5 (review op, 0 residual fraud since gamma=1)
    # 5: Fraud blocked    -> $0
    y_true = np.array([0, 0, 0, 1, 1, 1])
    decisions = np.array(["APPROVE", "REVIEW", "BLOCK", "APPROVE", "REVIEW", "BLOCK"])

    eval_result = cm.evaluate_cost(y_true, decisions)

    # Expected sum: 0 + 5 + 50 + 100 + 5 + 0 = 160.0
    assert eval_result["total_cost"] == 160.0
    assert eval_result["itemized_costs"]["missed_fraud_cost"] == 100.0
    assert eval_result["itemized_costs"]["review_operating_cost"] == 10.0  # 2 reviewed * $5
    assert eval_result["itemized_costs"]["block_friction_cost"] == 50.0
    assert eval_result["itemized_costs"]["residual_fraud_cost"] == 0.0


def test_review_capacity_constraint():
    """Verifies that review capacity threshold (5%) is correctly checked."""
    cm = CostMatrix(max_review_capacity_pct=5.0)

    y_dummy = np.zeros(100)
    # 4 reviews out of 100 = 4.0% <= 5.0%
    decisions_pass = np.array(["REVIEW"] * 4 + ["APPROVE"] * 96)
    res_pass = cm.evaluate_cost(y_dummy, decisions_pass)
    assert res_pass["review_rate_pct"] == 4.0
    assert res_pass["capacity_satisfied"] is True

    # 6 reviews out of 100 = 6.0% > 5.0%
    decisions_fail = np.array(["REVIEW"] * 6 + ["APPROVE"] * 94)
    res_fail = cm.evaluate_cost(y_dummy, decisions_fail)
    assert res_fail["review_rate_pct"] == 6.0
    assert res_fail["capacity_satisfied"] is False


def test_sensitivity_analysis_review_efficiency():
    """Verifies that decreasing operator review efficiency increases residual fraud cost."""
    optimizer = PolicyOptimizer()

    y_val = np.array([1, 1, 0, 0])
    probs = np.array([0.5, 0.5, 0.01, 0.01])
    policy = ThreeWayDecisionPolicy(threshold_review=0.10, threshold_block=0.90)

    sens = optimizer.run_sensitivity_analysis(y_val, probs, policy)
    gamma_sweep = sens["operator_efficiency_sensitivity"]

    # At gamma=1.0, residual fraud cost must be 0
    res_g1 = next(x for x in gamma_sweep if x["review_efficiency_gamma"] == 1.0)
    assert res_g1["residual_fraud_cost"] == 0.0

    # At gamma=0.80, residual fraud cost must be 2 frauds * 0.20 * $100 = $40
    res_g8 = next(x for x in gamma_sweep if x["review_efficiency_gamma"] == 0.80)
    assert res_g8["residual_fraud_cost"] == pytest.approx(40.0)
