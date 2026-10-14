"""Baseline models for credit card fraud detection.

Implements Logistic Regression and Decision Tree classifiers trained strictly
on the training partition with class weighting to handle extreme imbalance.
Evaluates models on the validation set using fraud-relevant metrics.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.tree import DecisionTreeClassifier

from ml.src.data.loader import DatasetSplit
from ml.src.preprocessing.preprocessor import FraudPreprocessor

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelEvaluationMetrics:
    """Container for fraud evaluation metrics evaluated on a validation set."""
    model_name: str
    evaluation_split: str  # e.g., 'validation'
    threshold: float
    precision: float
    recall: float
    f1: float
    pr_auc: float
    roc_auc: float
    true_negatives: int
    false_positives: int
    false_negatives: int
    true_positives: int
    hyperparameters: Dict[str, Any]
    random_seed: Optional[int]


class BaselineTrainer:
    """Trains, evaluates, and serializes baseline fraud classification models."""

    def __init__(self, random_seed: int = 42) -> None:
        self.random_seed = random_seed
        self.logreg_model: Optional[LogisticRegression] = None
        self.dtree_model: Optional[DecisionTreeClassifier] = None
        self.preprocessor: Optional[FraudPreprocessor] = None

    def evaluate_predictions(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
        model_name: str,
        hyperparameters: Dict[str, Any],
        threshold: float = 0.50,
        split_name: str = "validation",
    ) -> ModelEvaluationMetrics:
        """Calculates minority-class classification and ranking metrics.

        Args:
            y_true: Ground truth binary labels.
            y_prob: Predicted fraud probabilities (Class=1).
            model_name: Name of the model evaluated.
            hyperparameters: Hyperparameters dictionary.
            threshold: Decision boundary (default 0.50 baseline).
            split_name: Name of the evaluation split (e.g., 'validation').

        Returns:
            ModelEvaluationMetrics object.
        """
        y_pred = (y_prob >= threshold).astype(int)

        tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()

        prec = float(precision_score(y_true, y_pred, zero_division=0))
        rec = float(recall_score(y_true, y_pred, zero_division=0))
        f1 = float(f1_score(y_true, y_pred, zero_division=0))
        pr_auc = float(average_precision_score(y_true, y_prob))
        roc_auc = float(roc_auc_score(y_true, y_prob))

        return ModelEvaluationMetrics(
            model_name=model_name,
            evaluation_split=split_name,
            threshold=threshold,
            precision=prec,
            recall=rec,
            f1=f1,
            pr_auc=pr_auc,
            roc_auc=roc_auc,
            true_negatives=int(tn),
            false_positives=int(fp),
            false_negatives=int(fn),
            true_positives=int(tp),
            hyperparameters=hyperparameters,
            random_seed=self.random_seed,
        )

    def train_logistic_regression(
        self, X_train: pd.DataFrame, y_train: pd.Series
    ) -> LogisticRegression:
        """Trains Logistic Regression baseline with balanced class weights."""
        logger.info("Training Logistic Regression baseline...")
        params = {
            "class_weight": "balanced",
            "max_iter": 1000,
            "random_state": self.random_seed,
            "solver": "lbfgs",
        }
        model = LogisticRegression(**params)
        model.fit(X_train, y_train)
        self.logreg_model = model
        return model

    def train_decision_tree(
        self, X_train: pd.DataFrame, y_train: pd.Series
    ) -> DecisionTreeClassifier:
        """Trains Decision Tree baseline with balanced class weights and depth control."""
        logger.info("Training Decision Tree baseline...")
        params = {
            "class_weight": "balanced",
            "max_depth": 6,
            "min_samples_split": 20,
            "min_samples_leaf": 10,
            "random_state": self.random_seed,
        }
        model = DecisionTreeClassifier(**params)
        model.fit(X_train, y_train)
        self.dtree_model = model
        return model

    def train_and_evaluate_baselines(
        self, split: DatasetSplit, preprocessor: FraudPreprocessor
    ) -> Tuple[ModelEvaluationMetrics, ModelEvaluationMetrics]:
        """Runs the complete baseline training workflow on training data and evaluates on validation data.

        WARNING: The held-out test split (X_test, y_test) is deliberately omitted
        from this method to guarantee test isolation.
        """
        self.preprocessor = preprocessor

        # Scale features using preprocessor fitted ONLY on training data
        logger.info("Scaling training and validation features...")
        X_train_scaled = preprocessor.transform(split.X_train)
        X_val_scaled = preprocessor.transform(split.X_val)

        # 1. Logistic Regression
        logreg = self.train_logistic_regression(X_train_scaled, split.y_train)
        logreg_val_probs = logreg.predict_proba(X_val_scaled)[:, 1]
        logreg_metrics = self.evaluate_predictions(
            y_true=split.y_val.values,
            y_prob=logreg_val_probs,
            model_name="LogisticRegression_Baseline",
            hyperparameters={
                "class_weight": "balanced",
                "max_iter": 1000,
                "solver": "lbfgs",
            },
            split_name="validation",
        )

        # 2. Decision Tree
        dtree = self.train_decision_tree(X_train_scaled, split.y_train)
        dtree_val_probs = dtree.predict_proba(X_val_scaled)[:, 1]
        dtree_metrics = self.evaluate_predictions(
            y_true=split.y_val.values,
            y_prob=dtree_val_probs,
            model_name="DecisionTree_Baseline",
            hyperparameters={
                "class_weight": "balanced",
                "max_depth": 6,
                "min_samples_split": 20,
                "min_samples_leaf": 10,
            },
            split_name="validation",
        )

        return logreg_metrics, dtree_metrics

    def save_artifacts(
        self,
        models_dir: str | Path = r"C:\FraudDetection\ml\models",
        reports_dir: str | Path = r"C:\FraudDetection\ml\reports",
        logreg_metrics: Optional[ModelEvaluationMetrics] = None,
        dtree_metrics: Optional[ModelEvaluationMetrics] = None,
    ) -> Dict[str, Path]:
        """Saves baseline models and validation reports to disk without overwriting existing files."""
        models_path = Path(models_dir)
        reports_path = Path(reports_dir)
        models_path.mkdir(parents=True, exist_ok=True)
        reports_path.mkdir(parents=True, exist_ok=True)

        saved_files: Dict[str, Path] = {}

        # Save Logistic Regression model
        logreg_path = models_path / "logistic_regression_baseline.joblib"
        if logreg_path.exists():
            raise FileExistsError(f"Artifact {logreg_path} already exists. Overwrite prevented.")
        if self.logreg_model is not None:
            joblib.dump(self.logreg_model, logreg_path)
            saved_files["logistic_regression"] = logreg_path

        # Save Decision Tree model
        dtree_path = models_path / "decision_tree_baseline.joblib"
        if dtree_path.exists():
            raise FileExistsError(f"Artifact {dtree_path} already exists. Overwrite prevented.")
        if self.dtree_model is not None:
            joblib.dump(self.dtree_model, dtree_path)
            saved_files["decision_tree"] = dtree_path

        # Save validation report
        if logreg_metrics and dtree_metrics:
            report_path = reports_path / "baseline_validation_report.json"
            if report_path.exists():
                raise FileExistsError(f"Report {report_path} already exists. Overwrite prevented.")

            report_data = {
                "evaluation_environment": "validation_set_only",
                "notice": "These are validation set benchmarks for research comparison. Final test set remains isolated.",
                "validation_samples": 42718,
                "validation_fraud_samples": 56,
                "baselines": {
                    "logistic_regression": asdict(logreg_metrics),
                    "decision_tree": asdict(dtree_metrics),
                },
            }
            with open(report_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=2)
            saved_files["validation_report"] = report_path

        return saved_files
