"""Validation threshold optimization and sensitivity analysis for fraud decisions.

Searches optimal (threshold_review, threshold_block) pairs on validation predictions
to minimize total expected operational cost under review capacity constraints.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from ml.src.decision.cost_matrix import CostMatrix
from ml.src.decision.policy import DecisionAction, ThreeWayDecisionPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PolicyOptimizationResult:
    """Stores optimal policy thresholds and evaluated performance."""
    variant_name: str
    threshold_review: float
    threshold_block: float
    total_cost: float
    cost_per_transaction: float
    review_rate_pct: float
    capacity_satisfied: bool
    itemized_costs: Dict[str, float]
    outcome_counts: Dict[str, int]
    cost_matrix_params: Dict[str, float]


class PolicyOptimizer:
    """Optimizes review and block thresholds on validation observations."""

    def __init__(self, cost_matrix: Optional[CostMatrix] = None) -> None:
        self.cost_matrix = cost_matrix or CostMatrix()

    def search_optimal_thresholds(
        self,
        y_val: np.ndarray,
        probs_val: np.ndarray,
        variant_name: str,
        candidate_review_thresholds: Optional[np.ndarray] = None,
        candidate_block_thresholds: Optional[np.ndarray] = None,
    ) -> PolicyOptimizationResult:
        """Searches the optimal pair (tau_review, tau_block) minimizing validation cost.

        Deterministic tie-breaking:
        1. Minimum total cost.
        2. If tied, lower review rate (less operational workload).
        3. If still tied, higher tau_review (more automated approvals).
        """
        y_val = np.asarray(y_val, dtype=np.int32).ravel()
        probs = np.asarray(probs_val, dtype=np.float64).ravel()

        if candidate_review_thresholds is None:
            # Dense grid for review threshold: 0.001 to 0.50 (review band entry)
            candidate_review_thresholds = np.concatenate([
                np.linspace(0.001, 0.05, 50),
                np.linspace(0.06, 0.50, 45)
            ])

        if candidate_block_thresholds is None:
            # Grid for block threshold: 0.10 to 0.99 (hard block threshold)
            candidate_block_thresholds = np.linspace(0.10, 0.99, 50)

        best_cost = float("inf")
        best_candidate: Optional[PolicyOptimizationResult] = None

        # Fallback unconstrained best candidate in case 5% capacity cannot be met
        best_unconstrained_cost = float("inf")
        best_unconstrained_candidate: Optional[PolicyOptimizationResult] = None

        for t_rev in candidate_review_thresholds:
            for t_blk in candidate_block_thresholds:
                if t_rev >= t_blk:
                    continue

                policy = ThreeWayDecisionPolicy(
                    threshold_review=t_rev,
                    threshold_block=t_blk,
                    calibration_variant=variant_name,
                )
                decisions = policy.decide(probs)
                cost_eval = self.cost_matrix.evaluate_cost(y_val, decisions)

                cand = PolicyOptimizationResult(
                    variant_name=variant_name,
                    threshold_review=round(float(t_rev), 5),
                    threshold_block=round(float(t_blk), 5),
                    total_cost=cost_eval["total_cost"],
                    cost_per_transaction=cost_eval["cost_per_transaction"],
                    review_rate_pct=cost_eval["review_rate_pct"],
                    capacity_satisfied=cost_eval["capacity_satisfied"],
                    itemized_costs=cost_eval["itemized_costs"],
                    outcome_counts=cost_eval["outcome_counts"],
                    cost_matrix_params=asdict(self.cost_matrix),
                )

                # Track unconstrained best
                if cost_eval["total_cost"] < best_unconstrained_cost:
                    best_unconstrained_cost = cost_eval["total_cost"]
                    best_unconstrained_candidate = cand

                # Track capacity-constrained best (review rate <= 5.0%)
                if cost_eval["capacity_satisfied"]:
                    # Deterministic tie-breaking
                    is_strictly_better = cost_eval["total_cost"] < best_cost
                    is_tied_but_lower_workload = (
                        np.isclose(cost_eval["total_cost"], best_cost)
                        and best_candidate is not None
                        and cost_eval["review_rate_pct"] < best_candidate.review_rate_pct
                    )

                    if is_strictly_better or is_tied_but_lower_workload:
                        best_cost = cost_eval["total_cost"]
                        best_candidate = cand

        # Return constrained optimal if available, else best unconstrained
        selected = best_candidate or best_unconstrained_candidate
        if selected is None:
            raise RuntimeError("Threshold optimization failed to evaluate any valid candidates.")

        return selected

    def evaluate_fixed_baseline_05(
        self, y_val: np.ndarray, probs_val: np.ndarray, variant_name: str
    ) -> PolicyOptimizationResult:
        """Evaluates fixed binary threshold 0.50 (Approve < 0.50, Block >= 0.50, 0% Review).

        Clearly labeled as a reference benchmark rather than the operational policy.
        """
        # Approximated in 3-way engine by setting tau_review = tau_block = 0.50
        # or tau_review = 0.50 - 1e-9, tau_block = 0.50
        policy = ThreeWayDecisionPolicy(
            threshold_review=0.499999,
            threshold_block=0.500000,
            calibration_variant=variant_name,
        )
        decisions = policy.decide(probs_val)
        cost_eval = self.cost_matrix.evaluate_cost(y_val, decisions)

        return PolicyOptimizationResult(
            variant_name=f"{variant_name}_Fixed_0.50_Baseline",
            threshold_review=0.50,
            threshold_block=0.50,
            total_cost=cost_eval["total_cost"],
            cost_per_transaction=cost_eval["cost_per_transaction"],
            review_rate_pct=cost_eval["review_rate_pct"],
            capacity_satisfied=True,
            itemized_costs=cost_eval["itemized_costs"],
            outcome_counts=cost_eval["outcome_counts"],
            cost_matrix_params=asdict(self.cost_matrix),
        )

    def run_sensitivity_analysis(
        self,
        y_val: np.ndarray,
        probs_val: np.ndarray,
        base_policy: ThreeWayDecisionPolicy,
    ) -> Dict[str, Any]:
        """Performs multi-dimensional cost sensitivity analysis on validation data.

        Varies:
        1. False-negative cost (missed fraud loss): $50, $100, $200, $500
        2. Block friction cost (customer churn): $10, $25, $50, $100
        3. Review efficiency gamma (operator detection rate): 1.0, 0.9, 0.8, 0.6, 0.0
        """
        decisions = base_policy.decide(probs_val)
        sensitivity_results: Dict[str, Any] = {}

        # 1. Missed Fraud Cost Sensitivity (C_FN)
        fn_costs = [50.0, 100.0, 200.0, 500.0]
        fn_sweep = []
        for c_fn in fn_costs:
            cm = CostMatrix(
                cost_fn=c_fn,
                cost_fp=self.cost_matrix.cost_fp,
                cost_review=self.cost_matrix.cost_review,
                cost_friction=self.cost_matrix.cost_friction,
                review_efficiency=self.cost_matrix.review_efficiency,
            )
            res = cm.evaluate_cost(y_val, decisions)
            fn_sweep.append({
                "cost_fn": c_fn,
                "total_cost": res["total_cost"],
                "cost_per_transaction": res["cost_per_transaction"],
            })
        sensitivity_results["missed_fraud_cost_sensitivity"] = fn_sweep

        # 2. Block Friction Cost Sensitivity (C_friction)
        friction_costs = [10.0, 25.0, 50.0, 100.0]
        friction_sweep = []
        for c_fric in friction_costs:
            cm = CostMatrix(
                cost_fn=self.cost_matrix.cost_fn,
                cost_fp=self.cost_matrix.cost_fp,
                cost_review=self.cost_matrix.cost_review,
                cost_friction=c_fric,
                review_efficiency=self.cost_matrix.review_efficiency,
            )
            res = cm.evaluate_cost(y_val, decisions)
            friction_sweep.append({
                "cost_friction": c_fric,
                "total_cost": res["total_cost"],
                "cost_per_transaction": res["cost_per_transaction"],
            })
        sensitivity_results["block_friction_cost_sensitivity"] = friction_sweep

        # 3. Operator Review Efficiency Sensitivity (gamma)
        gamma_values = [1.0, 0.90, 0.80, 0.60, 0.0]
        gamma_sweep = []
        for g in gamma_values:
            cm = CostMatrix(
                cost_fn=self.cost_matrix.cost_fn,
                cost_fp=self.cost_matrix.cost_fp,
                cost_review=self.cost_matrix.cost_review,
                cost_friction=self.cost_matrix.cost_friction,
                review_efficiency=g,
            )
            res = cm.evaluate_cost(y_val, decisions)
            gamma_sweep.append({
                "review_efficiency_gamma": g,
                "residual_fraud_cost": res["itemized_costs"]["residual_fraud_cost"],
                "total_cost": res["total_cost"],
                "cost_per_transaction": res["cost_per_transaction"],
            })
        sensitivity_results["operator_efficiency_sensitivity"] = gamma_sweep

        return sensitivity_results
