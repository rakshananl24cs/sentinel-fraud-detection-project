"""SHAP TreeExplainer service for XGBoost fraud detection model.

Computes exact additive feature contributions in the model's raw margin (log-odds)
space, ranking features by absolute impact and generating concise analyst summaries.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd
import shap
from xgboost.sklearn import XGBClassifier

logger = logging.getLogger(__name__)

EXPECTED_FEATURE_NAMES = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount"]


class ExplainabilityError(Exception):
    """Raised when SHAP explanation generation or input validation fails."""
    pass


@dataclass(frozen=True)
class FeatureContribution:
    """Represents a single feature's attribution to the prediction."""
    feature: str
    contribution: float
    absolute_contribution: float
    direction: str  # 'increases_risk' or 'decreases_risk'


@dataclass(frozen=True)
class ExplanationResult:
    """Complete explanation payload for a single transaction prediction."""
    output_space: str
    base_value: float
    total_shap_sum: float
    top_contributions: List[FeatureContribution]
    all_contributions: List[FeatureContribution]
    analyst_summary: str
    limitations: str

    def to_dict(self) -> Dict[str, Any]:
        """Serializes result to dictionary."""
        return {
            "output_space": self.output_space,
            "base_value": self.base_value,
            "total_shap_sum": self.total_shap_sum,
            "top_contributions": [asdict(c) for c in self.top_contributions],
            "analyst_summary": self.analyst_summary,
            "limitations": self.limitations,
        }


class FraudExplainer:
    """Generates reproducible SHAP explanations using TreeExplainer on XGBoost.

    Attributes:
        model: Underlying fitted XGBClassifier instance.
        explainer: Pre-initialized shap.TreeExplainer instance.
        expected_features: List of 30 expected feature column names.
    """

    def __init__(self, model: XGBClassifier) -> None:
        if not hasattr(model, "predict_proba"):
            raise ExplainabilityError("Provided model is not a fitted classifier.")
        self.model = model
        self.expected_features = (
            list(model.feature_names_in_)
            if hasattr(model, "feature_names_in_")
            else EXPECTED_FEATURE_NAMES
        )
        try:
            # TreeExplainer using tree_path_dependent perturbation (output_space: raw margin / log-odds)
            self.explainer = shap.TreeExplainer(self.model)
        except Exception as e:
            raise ExplainabilityError(f"Failed to initialize shap.TreeExplainer: {e}")

    def validate_features(self, X: pd.DataFrame) -> None:
        """Validates that input features match schema and contain finite values."""
        if list(X.columns) != self.expected_features:
            raise ExplainabilityError(
                f"Feature mismatch. Expected: {self.expected_features}, Received: {list(X.columns)}"
            )

        if not np.all(np.isfinite(X.values)):
            raise ExplainabilityError("Input feature matrix contains non-finite values (NaN or Inf).")

    def explain_transaction(
        self,
        X_scaled_single: pd.DataFrame,
        top_k: int = 5,
    ) -> ExplanationResult:
        """Computes SHAP feature attributions for a single standardized transaction.

        Args:
            X_scaled_single: 1-row DataFrame containing the 30 standardized features.
            top_k: Number of highest-impact features to include in top_contributions.

        Returns:
            ExplanationResult object.
        """
        if len(X_scaled_single) != 1:
            raise ExplainabilityError(
                f"explain_transaction expects exactly 1 row, got {len(X_scaled_single)}"
            )

        self.validate_features(X_scaled_single)

        # Compute SHAP values
        shap_explanation = self.explainer(X_scaled_single)
        shap_values = shap_explanation.values[0]  # Array of length 30

        base_val = float(
            self.explainer.expected_value[0]
            if isinstance(self.explainer.expected_value, (list, np.ndarray))
            else self.explainer.expected_value
        )
        total_sum = float(np.sum(shap_values))

        # Assemble individual contributions
        all_contribs: List[FeatureContribution] = []
        for feat_name, val in zip(self.expected_features, shap_values):
            contrib = float(val)
            direction = "increases_risk" if contrib > 0 else "decreases_risk"
            all_contribs.append(
                FeatureContribution(
                    feature=feat_name,
                    contribution=round(contrib, 5),
                    absolute_contribution=round(abs(contrib), 5),
                    direction=direction,
                )
            )

        # Rank features by absolute impact magnitude
        ranked_contribs = sorted(all_contribs, key=lambda c: c.absolute_contribution, reverse=True)
        top_contribs = ranked_contribs[:top_k]

        # Generate analyst summary
        top_risk_drivers = [c.feature for c in top_contribs if c.direction == "increases_risk"]
        top_mitigators = [c.feature for c in top_contribs if c.direction == "decreases_risk"]

        summary_parts = []
        if top_risk_drivers:
            summary_parts.append(f"Risk elevation primarily driven by {', '.join(top_risk_drivers[:3])}.")
        if top_mitigators:
            summary_parts.append(f"Risk score moderated by {', '.join(top_mitigators[:2])}.")
        if not summary_parts:
            summary_parts.append("Features contributed neutrally to baseline prediction.")

        analyst_summary = " ".join(summary_parts)
        limitations = (
            "SHAP values represent local additive feature attribution in the model's raw margin "
            "(log-odds) space. They reflect algorithmic weighting in this specific tree ensemble, "
            "not empirical real-world causation."
        )

        return ExplanationResult(
            output_space="raw_margin_log_odds",
            base_value=round(base_val, 5),
            total_shap_sum=round(total_sum, 5),
            top_contributions=top_contribs,
            all_contributions=ranked_contribs,
            analyst_summary=analyst_summary,
            limitations=limitations,
        )
