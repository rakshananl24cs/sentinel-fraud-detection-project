"""Standardized inference pipeline for fraud risk estimation.

Provides the canonical predict_fraud(transaction: dict) entrypoint connecting
schema validation, feature standardization, XGBoost probability inference,
probability calibration, SHAP feature attributions, and cost-sensitive decisions.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import joblib
import numpy as np
import pandas as pd

from ml.src.decision.cost_matrix import CostMatrix
from ml.src.decision.policy import DecisionAction, ThreeWayDecisionPolicy
from ml.src.explainability.explainer import FraudExplainer
from ml.src.models.calibration import ProbabilityCalibrator
from ml.src.preprocessing.preprocessor import FraudPreprocessor

logger = logging.getLogger(__name__)

EXPECTED_FEATURE_NAMES: List[str] = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount"]
MODEL_VERSION: str = "xgb-cost-v1"

# Validation-optimized research settings from Step 10
DEFAULT_THRESHOLD_REVIEW: float = 0.042
DEFAULT_THRESHOLD_BLOCK: float = 0.75388
DEFAULT_CALIBRATION_VARIANT: str = "isotonic"


def resolve_default_models_dir() -> Path:
    """Dynamically resolves model artifacts directory across local and containerized runtimes."""
    env_dir = os.getenv("MODEL_DIR")
    if env_dir and Path(env_dir).exists() and (Path(env_dir) / "xgboost_baseline.joblib").exists():
        return Path(env_dir)
    repo_models = Path(__file__).resolve().parents[3] / "ml" / "models"
    if repo_models.exists() and (repo_models / "xgboost_baseline.joblib").exists():
        return repo_models
    local_models = Path("ml/models")
    if local_models.exists() and (local_models / "xgboost_baseline.joblib").exists():
        return local_models
    return Path(r"C:\FraudDetection\ml\models")


class InferenceError(Exception):
    """Raised when inference validation, execution, or artifact loading fails."""
    pass


class FraudInferencePipeline:
    """Encapsulates loaded artifacts and runs standardized fraud inference.

    Attributes:
        models_dir: Directory containing serialized model artifacts.
        preprocessor: Fitted FraudPreprocessor instance.
        model: Fitted XGBClassifier instance.
        calibrator: Fitted ProbabilityCalibrator instance.
        policy: ThreeWayDecisionPolicy instance.
        explainer: FraudExplainer instance.
    """

    def __init__(
        self,
        models_dir: Optional[str | Path] = None,
        calibration_variant: str = DEFAULT_CALIBRATION_VARIANT,
        threshold_review: float = DEFAULT_THRESHOLD_REVIEW,
        threshold_block: float = DEFAULT_THRESHOLD_BLOCK,
        cost_matrix: Optional[CostMatrix] = None,
    ) -> None:
        self.models_dir = Path(models_dir) if models_dir is not None else resolve_default_models_dir()
        self.calibration_variant = calibration_variant
        self.threshold_review = threshold_review
        self.threshold_block = threshold_block
        self.cost_matrix = cost_matrix or CostMatrix()

        self.preprocessor: Optional[FraudPreprocessor] = None
        self.model: Any = None
        self.calibrator: Optional[ProbabilityCalibrator] = None
        self.policy: Optional[ThreeWayDecisionPolicy] = None
        self.explainer: Optional[FraudExplainer] = None

        self._load_artifacts()

    def _load_artifacts(self) -> None:
        """Loads and verifies all required runtime artifacts without refitting."""
        # 1. Load Preprocessor
        prep_path = self.models_dir / "preprocessor.joblib"
        if not prep_path.exists():
            raise InferenceError(f"Missing required preprocessor artifact: {prep_path}")
        self.preprocessor = FraudPreprocessor.load(prep_path)

        # 2. Load XGBoost Model
        model_path = self.models_dir / "xgboost_baseline.joblib"
        if not model_path.exists():
            raise InferenceError(f"Missing required model artifact: {model_path}")
        self.model = joblib.load(model_path)

        # 3. Load Calibrator
        if self.calibration_variant == "isotonic":
            cal_path = self.models_dir / "calibrator_isotonic.joblib"
        elif self.calibration_variant == "platt":
            cal_path = self.models_dir / "calibrator_platt.joblib"
        elif self.calibration_variant == "uncalibrated":
            cal_path = None
        else:
            raise InferenceError(f"Unsupported calibration variant: {self.calibration_variant}")

        if cal_path:
            if not cal_path.exists():
                raise InferenceError(f"Missing required calibrator artifact: {cal_path}")
            self.calibrator = joblib.load(cal_path)
        else:
            self.calibrator = None

        # 4. Initialize Decision Policy
        self.policy = ThreeWayDecisionPolicy(
            threshold_review=self.threshold_review,
            threshold_block=self.threshold_block,
            model_version=MODEL_VERSION,
            calibration_variant=self.calibration_variant,
        )

        # 5. Initialize SHAP Explainer
        self.explainer = FraudExplainer(self.model)

    def validate_transaction_dict(self, transaction: Dict[str, Any]) -> pd.DataFrame:
        """Validates input payload against exact 30-feature schema and returns 1-row DataFrame."""
        if not isinstance(transaction, dict):
            raise InferenceError(f"Transaction payload must be a dict, got {type(transaction).__name__}")

        if "Class" in transaction:
            raise InferenceError("Target column 'Class' must not be included in transaction features.")

        # Extract features dictionary if nested under 'features' key
        feature_dict = transaction.get("features", transaction)
        if not isinstance(feature_dict, dict):
            raise InferenceError("Features dictionary is malformed or invalid.")

        missing_keys = [k for k in EXPECTED_FEATURE_NAMES if k not in feature_dict]
        if missing_keys:
            raise InferenceError(f"Missing required features ({len(missing_keys)} missing): {missing_keys[:5]}...")

        # Validate numeric types and finite values
        row_values = []
        for feat in EXPECTED_FEATURE_NAMES:
            val = feature_dict[feat]
            try:
                val_float = float(val)
            except (ValueError, TypeError):
                raise InferenceError(f"Feature '{feat}' must be numeric, got {type(val).__name__} ({val!r})")

            if not np.isfinite(val_float):
                raise InferenceError(f"Feature '{feat}' contains non-finite value ({val_float})")

            row_values.append(val_float)

        return pd.DataFrame([row_values], columns=EXPECTED_FEATURE_NAMES)

    def predict(self, transaction: Dict[str, Any]) -> Dict[str, Any]:
        """Runs complete end-to-end inference and explanation for a transaction."""
        # 1. Schema Validation
        X_df = self.validate_transaction_dict(transaction)

        # 2. Preprocessing (StandardScaler using transform only)
        assert self.preprocessor is not None
        X_scaled = self.preprocessor.transform(X_df)

        # 3. Model Inference (Raw Probability)
        assert self.model is not None
        raw_prob = float(self.model.predict_proba(X_scaled)[0, 1])

        # 4. Probability Calibration
        if self.calibrator is not None:
            calibrated_prob = float(self.calibrator.calibrate(np.array([raw_prob]))[0])
        else:
            calibrated_prob = raw_prob

        # 5. Cost-Sensitive Three-Way Decision
        assert self.policy is not None
        decision = self.policy.decide_single(calibrated_prob)

        # Assign risk tier based on decision
        if decision == DecisionAction.APPROVE.value:
            risk_level = "LOW"
            expected_cost = calibrated_prob * self.cost_matrix.cost_fn
        elif decision == DecisionAction.REVIEW.value:
            risk_level = "MEDIUM"
            residual_loss = calibrated_prob * (1.0 - self.cost_matrix.review_efficiency) * self.cost_matrix.cost_fn
            expected_cost = self.cost_matrix.cost_review + residual_loss
        else:
            risk_level = "HIGH"
            expected_cost = (1.0 - calibrated_prob) * self.cost_matrix.cost_friction

        # 6. SHAP Attribution Explanation
        assert self.explainer is not None
        explanation = self.explainer.explain_transaction(X_scaled, top_k=5)

        tx_id = transaction.get("transaction_id", f"TX-{int(datetime.now(timezone.utc).timestamp()*1000)}")

        return {
            "transaction_id": tx_id,
            "model_version": MODEL_VERSION,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "fraud_probability": round(calibrated_prob, 5),
            "raw_probability": round(raw_prob, 5),
            "risk_level": risk_level,
            "decision": decision,
            "expected_cost": round(expected_cost, 2),
            "policy_parameters": {
                "threshold_review": self.threshold_review,
                "threshold_block": self.threshold_block,
                "calibration_variant": self.calibration_variant,
                "status": "validation_optimized_research_setting",
            },
            "explanation": explanation.to_dict(),
        }


# Module-level cached pipeline instance
_pipeline_cache: Optional[FraudInferencePipeline] = None


def get_inference_pipeline() -> FraudInferencePipeline:
    """Returns initialized singleton FraudInferencePipeline."""
    global _pipeline_cache
    if _pipeline_cache is None:
        _pipeline_cache = FraudInferencePipeline()
    return _pipeline_cache


def predict_fraud(transaction: Dict[str, Any]) -> Dict[str, Any]:
    """Canonical public API function for fraud inference and explanation.

    Args:
        transaction: Dictionary containing the 30 required features.

    Returns:
        Structured prediction, decision, and explanation dictionary.
    """
    pipeline = get_inference_pipeline()
    return pipeline.predict(transaction)
