"""Three-way decision policy (APPROVE, REVIEW, BLOCK) for fraud management.

Separates probability inference from business policy execution using strictly ordered
review and block decision boundaries.
"""

from __future__ import annotations

from enum import Enum
from typing import List, Union
import numpy as np


class DecisionAction(str, Enum):
    """Permitted decision outcomes under the frozen project contract."""
    APPROVE = "APPROVE"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


class PolicyValidationError(Exception):
    """Raised when threshold bounds or input probability ranges are invalid."""
    pass


class ThreeWayDecisionPolicy:
    """Evaluates fraud probabilities into APPROVE, REVIEW, or BLOCK actions.

    Attributes:
        threshold_review: Boundary below which transactions are APPROVED.
        threshold_block: Boundary at or above which transactions are BLOCKED.
        model_version: Associated model identifier for audit logging.
        calibration_variant: Associated calibration method ('uncalibrated', 'platt', 'isotonic').
    """

    def __init__(
        self,
        threshold_review: float,
        threshold_block: float,
        model_version: str = "xgb-cost-v1",
        calibration_variant: str = "uncalibrated",
    ) -> None:
        self.threshold_review = float(threshold_review)
        self.threshold_block = float(threshold_block)
        self.model_version = model_version
        self.calibration_variant = calibration_variant

        self._validate_thresholds()

    def _validate_thresholds(self) -> None:
        """Validates that thresholds are strictly ordered and bounded in [0, 1]."""
        if not (0.0 <= self.threshold_review < self.threshold_block <= 1.0):
            raise PolicyValidationError(
                f"Invalid threshold ordering: required 0.0 <= threshold_review < threshold_block <= 1.0, "
                f"got threshold_review={self.threshold_review}, threshold_block={self.threshold_block}"
            )

    def decide_single(self, probability: float) -> str:
        """Determines action for a single transaction probability."""
        p = float(probability)
        if not np.isfinite(p) or not (0.0 <= p <= 1.0):
            raise PolicyValidationError(f"Invalid probability: must be finite in [0, 1], got {p}")

        if p < self.threshold_review:
            return DecisionAction.APPROVE.value
        elif p < self.threshold_block:
            return DecisionAction.REVIEW.value
        else:
            return DecisionAction.BLOCK.value

    def decide(self, probabilities: Union[np.ndarray, List[float]]) -> np.ndarray:
        """Vectorized evaluation of an array of transaction probabilities.

        Args:
            probabilities: 1D array of fraud risk scores in [0.0, 1.0].

        Returns:
            1D numpy array of string decision tokens ('APPROVE', 'REVIEW', 'BLOCK').
        """
        probs = np.asarray(probabilities, dtype=np.float64)

        if not np.all(np.isfinite(probs)):
            raise PolicyValidationError("Input probabilities contain non-finite values (NaN or Inf).")

        if np.any((probs < 0.0) | (probs > 1.0)):
            raise PolicyValidationError("Input probabilities contain values outside valid range [0.0, 1.0].")

        decisions = np.empty(len(probs), dtype=object)

        is_approve = probs < self.threshold_review
        is_block = probs >= self.threshold_block
        is_review = ~(is_approve | is_block)

        decisions[is_approve] = DecisionAction.APPROVE.value
        decisions[is_review] = DecisionAction.REVIEW.value
        decisions[is_block] = DecisionAction.BLOCK.value

        return decisions
