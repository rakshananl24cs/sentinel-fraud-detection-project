"""Primary XGBoost fraud detection model (xgb-cost-v1).

Trains a gradient-boosted decision tree on the training partition with scale_pos_weight
to address severe class imbalance, recording all hyperparameters, random seeds,
and training metadata.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from xgboost import XGBClassifier

logger = logging.getLogger(__name__)

MODEL_VERSION: str = "xgb-cost-v1"


class XGBoostFraudModel:
    """Primary XGBoost classifier wrapper for fraud probability estimation.

    Attributes:
        version: Model identifier string ('xgb-cost-v1').
        model: Underlying XGBClassifier instance.
        params: Hyperparameter dictionary.
        feature_names: Ordered list of feature names used during training.
        scale_pos_weight: Imbalance ratio calculated from training labels.
    """

    def __init__(
        self,
        random_state: int = 42,
        n_estimators: int = 300,
        max_depth: int = 6,
        learning_rate: float = 0.05,
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        n_jobs: int = -1,
    ) -> None:
        self.version = MODEL_VERSION
        self.random_state = random_state
        self.feature_names: Optional[List[str]] = None
        self.scale_pos_weight: Optional[float] = None
        self.is_fitted: bool = False

        self.params: Dict[str, Any] = {
            "n_estimators": n_estimators,
            "max_depth": max_depth,
            "learning_rate": learning_rate,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "objective": "binary:logistic",
            "eval_metric": "logloss",
            "random_state": random_state,
            "n_jobs": n_jobs,
        }
        self.model: Optional[XGBClassifier] = None

    def fit(
        self,
        X_train: pd.DataFrame,
        y_train: pd.Series,
        eval_set: Optional[List[Tuple[pd.DataFrame, pd.Series]]] = None,
        verbose: bool = False,
    ) -> XGBoostFraudModel:
        """Fits XGBoost strictly on training data with class-weighting.

        Args:
            X_train: Scaled training feature matrix.
            y_train: Training binary labels.
            eval_set: Optional evaluation set (e.g. validation) for metric monitoring.
            verbose: Verbosity flag for training iterations.

        Returns:
            Self (fitted model).
        """
        self.feature_names = list(X_train.columns)

        # Calculate scale_pos_weight dynamically: negative_count / positive_count
        pos_count = int(np.sum(y_train == 1))
        neg_count = int(np.sum(y_train == 0))
        if pos_count == 0:
            raise ValueError("Training labels contain zero positive fraud cases.")

        self.scale_pos_weight = float(neg_count / pos_count)
        self.params["scale_pos_weight"] = self.scale_pos_weight

        logger.info(
            f"Initializing {self.version} with scale_pos_weight={self.scale_pos_weight:.4f} "
            f"(Negatives={neg_count}, Positives={pos_count})"
        )

        self.model = XGBClassifier(**self.params)

        fit_kwargs: Dict[str, Any] = {"verbose": verbose}
        if eval_set:
            fit_kwargs["eval_set"] = eval_set

        self.model.fit(X_train, y_train, **fit_kwargs)
        self.is_fitted = True
        logger.info(f"Model {self.version} successfully fitted on {len(X_train)} samples.")
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        """Returns raw fraud probabilities (Class=1) in [0.0, 1.0]."""
        if not self.is_fitted or self.model is None:
            raise RuntimeError("Model must be fitted before predict_proba().")
        return self.model.predict_proba(X)[:, 1]

    def predict(self, X: pd.DataFrame, threshold: float = 0.50) -> np.ndarray:
        """Returns binary predictions based on decision threshold."""
        probs = self.predict_proba(X)
        return (probs >= threshold).astype(int)

    def save(self, filepath: str | Path = r"C:\FraudDetection\ml\models\xgboost_baseline.joblib") -> Path:
        """Saves model artifact to disk if destination path does not exist."""
        if not self.is_fitted or self.model is None:
            raise RuntimeError("Cannot save unfitted model.")
        path = Path(filepath)
        if path.exists():
            raise FileExistsError(f"Target artifact path already exists: {path}. Overwrite prevented.")
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self.model, path)
        logger.info(f"Saved model artifact to {path}")
        return path

    @classmethod
    def load(
        cls,
        filepath: str | Path,
        feature_names: Optional[List[str]] = None,
        scale_pos_weight: Optional[float] = None,
    ) -> XGBoostFraudModel:
        """Loads trained XGBoost model artifact."""
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Model artifact not found at {path}")
        loaded_model = joblib.load(path)
        instance = cls()
        instance.model = loaded_model
        instance.is_fitted = True
        instance.feature_names = feature_names
        instance.scale_pos_weight = scale_pos_weight
        return instance

    def build_metadata(
        self,
        training_samples: int,
        training_frauds: int,
        validation_metrics: Dict[str, Any],
        package_versions: Dict[str, str],
    ) -> Dict[str, Any]:
        """Builds standardized model_metadata.json payload."""
        return {
            "model_version": self.version,
            "architecture": "XGBClassifier (Gradient Boosted Trees)",
            "hyperparameters": {
                k: v for k, v in self.params.items() if k != "n_jobs"
            },
            "scale_pos_weight": self.scale_pos_weight,
            "feature_count": len(self.feature_names) if self.feature_names else 0,
            "feature_order": self.feature_names,
            "training_split": {
                "samples": training_samples,
                "fraud_samples": training_frauds,
                "strategy": "chronological_70_percent",
            },
            "validation_metrics": validation_metrics,
            "package_versions": package_versions,
        }
