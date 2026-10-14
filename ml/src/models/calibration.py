"""Probability calibration module for fraud probability estimation.

Provides Platt scaling (sigmoid) and Isotonic regression calibrators
fitted on validation predictions to improve probability reliability
without compromising rank ordering.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
from sklearn.calibration import calibration_curve
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

logger = logging.getLogger(__name__)


class CalibrationError(Exception):
    """Raised when probability calibration fails or inputs are invalid."""
    pass


class ProbabilityCalibrator:
    """Calibrates classifier risk scores using validation observations.

    Supported methods:
        - 'isotonic': Non-parametric isotonic regression.
        - 'platt': Parametric sigmoid scaling via 1D Logistic Regression.
    """

    def __init__(self, method: str = "isotonic") -> None:
        if method not in ("isotonic", "platt"):
            raise ValueError(f"Method must be 'isotonic' or 'platt', got '{method}'")
        self.method: str = method
        self.is_fitted: bool = False
        self._isotonic: Optional[IsotonicRegression] = None
        self._platt: Optional[LogisticRegression] = None

    def fit(self, y_prob: np.ndarray, y_true: np.ndarray) -> ProbabilityCalibrator:
        """Fits calibration curve on validation probabilities and labels.

        Args:
            y_prob: 1D array of uncalibrated probabilities in [0, 1].
            y_true: 1D array of binary true labels in {0, 1}.

        Returns:
            Self (fitted calibrator).
        """
        y_prob = np.asarray(y_prob, dtype=np.float64).ravel()
        y_true = np.asarray(y_true, dtype=np.int32).ravel()

        if len(y_prob) != len(y_true):
            raise CalibrationError("Length mismatch between probabilities and ground truth labels.")

        if len(np.unique(y_true)) < 2:
            raise CalibrationError("Ground truth must contain both classes (0 and 1) for calibration.")

        # Clip inputs to strictly valid probability bounds [1e-7, 1 - 1e-7]
        y_prob_clipped = np.clip(y_prob, 1e-7, 1.0 - 1e-7)

        if self.method == "isotonic":
            self._isotonic = IsotonicRegression(y_min=0.0, y_max=1.0, out_of_bounds="clip")
            self._isotonic.fit(y_prob_clipped, y_true)
        elif self.method == "platt":
            # Platt scaling: fit logistic regression on logits: log(p / (1 - p))
            logits = np.log(y_prob_clipped / (1.0 - y_prob_clipped)).reshape(-1, 1)
            self._platt = LogisticRegression(solver="lbfgs", max_iter=1000)
            self._platt.fit(logits, y_true)

        self.is_fitted = True
        logger.info(f"Fitted {self.method} probability calibrator on {len(y_prob)} samples.")
        return self

    def calibrate(self, y_prob: np.ndarray) -> np.ndarray:
        """Transforms uncalibrated probabilities into calibrated probabilities.

        Args:
            y_prob: 1D array of probabilities in [0, 1].

        Returns:
            Calibrated 1D array bounded strictly in [0.0, 1.0].
        """
        if not self.is_fitted:
            raise CalibrationError("Calibrator must be fitted on validation data before transform.")

        y_prob = np.asarray(y_prob, dtype=np.float64).ravel()
        y_prob_clipped = np.clip(y_prob, 1e-7, 1.0 - 1e-7)

        if self.method == "isotonic":
            assert self._isotonic is not None
            calibrated = self._isotonic.transform(y_prob_clipped)
        elif self.method == "platt":
            assert self._platt is not None
            logits = np.log(y_prob_clipped / (1.0 - y_prob_clipped)).reshape(-1, 1)
            calibrated = self._platt.predict_proba(logits)[:, 1]
        else:
            raise CalibrationError(f"Unknown calibration method: {self.method}")

        # Ensure bounds and finite values
        calibrated = np.clip(calibrated, 0.0, 1.0)
        return calibrated

    def save(self, filepath: str | Path) -> Path:
        """Serializes calibrator to disk if destination path does not exist."""
        if not self.is_fitted:
            raise CalibrationError("Cannot save unfitted calibrator.")
        path = Path(filepath)
        if path.exists():
            raise FileExistsError(f"Target path {path} already exists. Overwrite prevented.")
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info(f"Saved calibrator artifact to {path}")
        return path

    @classmethod
    def load(cls, filepath: str | Path) -> ProbabilityCalibrator:
        """Loads serialized calibrator from disk."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Calibrator artifact not found at {path}")
        loaded = joblib.load(path)
        if not isinstance(loaded, cls):
            raise TypeError(f"Loaded object is not a {cls.__name__}")
        return loaded


def evaluate_calibration(
    y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10
) -> Dict[str, Any]:
    """Computes calibration reliability metrics including Brier score and bin statistics.

    Args:
        y_true: Ground truth binary labels.
        y_prob: Estimated probabilities.
        n_bins: Number of probability bins for reliability diagram.

    Returns:
        Dictionary containing Brier score, bin statistics, and error bounds.
    """
    y_true = np.asarray(y_true, dtype=np.int32).ravel()
    y_prob = np.asarray(y_prob, dtype=np.float64).ravel()

    brier = float(brier_score_loss(y_true, y_prob))

    # Reliability curve binning
    prob_true, prob_pred = calibration_curve(y_true, y_prob, n_bins=n_bins, strategy="uniform")

    # Mean calibration error (MCE) and Expected Calibration Error (ECE)
    bin_edges = np.linspace(0.0, 1.0, n_bins + 1)
    bin_assignments = np.digitize(y_prob, bin_edges) - 1

    ece = 0.0
    mce = 0.0
    bin_summaries: List[Dict[str, Any]] = []

    for b in range(n_bins):
        mask = bin_assignments == b
        count = int(np.sum(mask))
        if count > 0:
            avg_pred = float(np.mean(y_prob[mask]))
            avg_true = float(np.mean(y_true[mask]))
            abs_diff = abs(avg_pred - avg_true)
            ece += (count / len(y_prob)) * abs_diff
            mce = max(mce, abs_diff)
            bin_summaries.append({
                "bin_index": b,
                "bin_range": [round(float(bin_edges[b]), 3), round(float(bin_edges[b + 1]), 3)],
                "count": count,
                "avg_pred": avg_pred,
                "avg_true": avg_true,
                "gap": abs_diff,
            })

    return {
        "brier_score": brier,
        "expected_calibration_error": float(ece),
        "maximum_calibration_error": float(mce),
        "num_bins": n_bins,
        "calibration_curve": {
            "fraction_of_positives": [float(x) for x in prob_true],
            "mean_predicted_value": [float(x) for x in prob_pred],
        },
        "bin_summaries": bin_summaries,
    }
