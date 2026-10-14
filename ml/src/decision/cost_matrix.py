"""Explicit cost matrix and financial accounting conventions for fraud decisions.

Defines operational costs for candidate actions (APPROVE, REVIEW, BLOCK) across
actual classes (GENUINE, FRAUD) without double-counting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any
import numpy as np


@dataclass(frozen=True)
class CostMatrix:
    """Configurable cost matrix parameters representing operational and financial impacts.

    All monetary figures represent provisional research assumptions for simulation
    and policy optimization rather than verified institutional losses.

    Attributes:
        cost_fn: Financial loss per missed fraud transaction (chargeback, stolen funds). Default $100.
        cost_fp: Operational inquiry / investigation cost for flagging genuine user. Default $5.
        cost_review: Salary / operational cost per transaction reviewed by human operator. Default $5.
        cost_friction: Customer friction, embarrassment, and churn cost for an outright false block. Default $50.
        review_efficiency: Probability gamma in [0, 1] that operator correctly detects fraud in review. Default 1.0 (perfect).
        max_review_capacity_pct: Maximum percentage of transactions permitted in review queue. Default 5.0%.
    """
    cost_fn: float = 100.0
    cost_fp: float = 5.0
    cost_review: float = 5.0
    cost_friction: float = 50.0
    review_efficiency: float = 1.0
    max_review_capacity_pct: float = 5.0

    def evaluate_cost(
        self, y_true: np.ndarray, decisions: np.ndarray
    ) -> Dict[str, Any]:
        """Calculates total operational cost and breakdown across outcomes.

        Accounting conventions:
        1. GENUINE (y=0) + APPROVE: $0.0 (ideal frictionless outcome).
        2. GENUINE (y=0) + REVIEW: cost_review ($5.0) for investigator time.
        3. GENUINE (y=0) + BLOCK: cost_friction ($50.0) customer churn and friction.
        4. FRAUD (y=1) + APPROVE: cost_fn ($100.0) complete loss of stolen funds.
        5. FRAUD (y=1) + REVIEW: cost_review + (1 - gamma) * cost_fn (investigator cost + residual missed fraud).
        6. FRAUD (y=1) + BLOCK: $0.0 (fraud stopped cleanly by automated block).

        Args:
            y_true: 1D array of ground truth labels (0=genuine, 1=fraud).
            decisions: 1D array of string decisions ('APPROVE', 'REVIEW', 'BLOCK').

        Returns:
            Dictionary containing itemized costs, total cost, and per-transaction cost.
        """
        y_true = np.asarray(y_true, dtype=np.int32).ravel()
        decisions = np.asarray(decisions, dtype=str).ravel()

        if len(y_true) != len(decisions):
            raise ValueError("Length mismatch between labels and decisions.")

        n_total = len(y_true)
        if n_total == 0:
            return {"total_cost": 0.0, "cost_per_tx": 0.0}

        # Boolean masks
        is_genuine = (y_true == 0)
        is_fraud = (y_true == 1)

        is_approve = (decisions == "APPROVE")
        is_review = (decisions == "REVIEW")
        is_block = (decisions == "BLOCK")

        # 1. Missed Fraud Cost (Approved Fraud)
        approved_fraud_count = int(np.sum(is_fraud & is_approve))
        missed_fraud_cost = approved_fraud_count * self.cost_fn

        # 2. Review Operating Cost (Charged to every reviewed transaction)
        reviewed_total_count = int(np.sum(is_review))
        review_operating_cost = reviewed_total_count * self.cost_review

        # 3. Residual Fraud Loss in Review Queue (Imperfect review leakage)
        reviewed_fraud_count = int(np.sum(is_fraud & is_review))
        residual_leakage_rate = max(0.0, 1.0 - self.review_efficiency)
        residual_fraud_cost = reviewed_fraud_count * residual_leakage_rate * self.cost_fn

        # 4. Block Friction Cost (Genuine users blocked)
        blocked_genuine_count = int(np.sum(is_genuine & is_block))
        block_friction_cost = blocked_genuine_count * self.cost_friction

        # 5. Clean Automated Blocks (Fraud stopped with zero financial loss)
        blocked_fraud_count = int(np.sum(is_fraud & is_block))

        # Total cost
        total_cost = (
            missed_fraud_cost
            + review_operating_cost
            + residual_fraud_cost
            + block_friction_cost
        )
        cost_per_tx = total_cost / n_total
        review_rate_pct = (reviewed_total_count / n_total) * 100.0

        return {
            "total_cost": float(total_cost),
            "cost_per_transaction": float(cost_per_tx),
            "review_rate_pct": float(review_rate_pct),
            "capacity_satisfied": bool(review_rate_pct <= self.max_review_capacity_pct),
            "itemized_costs": {
                "missed_fraud_cost": float(missed_fraud_cost),
                "review_operating_cost": float(review_operating_cost),
                "residual_fraud_cost": float(residual_fraud_cost),
                "block_friction_cost": float(block_friction_cost),
            },
            "outcome_counts": {
                "genuine_approved": int(np.sum(is_genuine & is_approve)),
                "genuine_reviewed": int(np.sum(is_genuine & is_review)),
                "genuine_blocked": blocked_genuine_count,
                "fraud_approved": approved_fraud_count,
                "fraud_reviewed": reviewed_fraud_count,
                "fraud_blocked": blocked_fraud_count,
                "total_reviewed": reviewed_total_count,
                "total_blocked": int(np.sum(is_block)),
                "total_approved": int(np.sum(is_approve)),
            },
        }
