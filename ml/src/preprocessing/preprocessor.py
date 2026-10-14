"""Leakage-safe preprocessing module for credit card fraud detection.

Standardizes input features (Time, V1-V28, Amount) using StandardScaler fitted
strictly on the training partition. Ensures target Class is isolated and transforms
validation/inference data using pre-fitted parameters without refitting.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


class PreprocessingError(Exception):
    """Raised when preprocessing fitting or transformation validation fails."""
    pass


class FraudPreprocessor:
    """Manages feature standardization with strict leakage prevention safeguards.

    Attributes:
        scaler: The underlying scikit-learn StandardScaler instance.
        feature_names: List of expected input feature names in exact order.
        is_fitted: Boolean flag indicating whether the preprocessor has been fitted.
    """

    def __init__(self) -> None:
        self.scaler: StandardScaler = StandardScaler(copy=True, with_mean=True, with_std=True)
        self.feature_names: Optional[List[str]] = None
        self.is_fitted: bool = False

    def fit(self, X: pd.DataFrame) -> FraudPreprocessor:
        """Fits StandardScaler strictly on training feature matrix.

        Args:
            X: Training features DataFrame (must NOT contain 'Class').

        Returns:
            Self (fitted preprocessor).

        Raises:
            PreprocessingError: If target 'Class' is present or input is invalid.
        """
        if "Class" in X.columns:
            raise PreprocessingError(
                "Target column 'Class' detected in feature matrix. Target must remain unscaled."
            )

        self.feature_names = list(X.columns)
        self.scaler.fit(X.values)
        self.is_fitted = True
        logger.info(
            f"Fitted StandardScaler on {len(X)} rows across {len(self.feature_names)} features: {self.feature_names[:3]}..."
        )
        return self

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Transforms feature matrix using previously fitted scaling parameters.

        Args:
            X: Feature matrix DataFrame to standardize (validation, test, or inference).

        Returns:
            Standardized pandas DataFrame preserving column names and index.

        Raises:
            PreprocessingError: If preprocessor is not fitted or feature columns mismatch.
        """
        if not self.is_fitted or self.feature_names is None:
            raise PreprocessingError(
                "Preprocessor must be fitted on training data before calling transform()."
            )

        if "Class" in X.columns:
            raise PreprocessingError(
                "Target column 'Class' detected in feature matrix during transformation."
            )

        actual_cols = list(X.columns)
        if actual_cols != self.feature_names:
            raise PreprocessingError(
                f"Feature column mismatch. Expected: {self.feature_names}, Received: {actual_cols}"
            )

        scaled_values = self.scaler.transform(X.values)
        return pd.DataFrame(scaled_values, columns=self.feature_names, index=X.index)

    def fit_transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Fits on training data and returns transformed DataFrame.

        WARNING: Use only on the training partition to prevent data leakage.
        """
        return self.fit(X).transform(X)

    def save(self, filepath: str | Path = r"C:\FraudDetection\ml\models\preprocessor.joblib") -> Path:
        """Serializes fitted preprocessor to disk if target path does not exist.

        Args:
            filepath: Destination joblib file path.

        Returns:
            Resolved Path of saved artifact.

        Raises:
            FileExistsError: If destination file already exists (preventing overwrite).
            PreprocessingError: If preprocessor is not fitted.
        """
        if not self.is_fitted:
            raise PreprocessingError("Cannot save unfitted preprocessor.")

        path = Path(filepath)
        if path.exists():
            raise FileExistsError(f"Target artifact path already exists: {path}. Overwrite prevented.")

        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        logger.info(f"Saved fitted preprocessor artifact to {path}")
        return path

    @classmethod
    def load(cls, filepath: str | Path = r"C:\FraudDetection\ml\models\preprocessor.joblib") -> FraudPreprocessor:
        """Loads a serialized preprocessor artifact from disk.

        Args:
            filepath: Path to the joblib artifact.

        Returns:
            Fitted FraudPreprocessor instance.
        """
        path = Path(filepath)
        if not path.exists():
            raise FileNotFoundError(f"Preprocessor artifact not found at {path}")

        loaded = joblib.load(path)
        if not isinstance(loaded, cls):
            raise TypeError(f"Loaded object is not an instance of {cls.__name__}")

        return loaded
