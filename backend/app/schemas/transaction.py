"""Pydantic schemas for transaction ingestion and fraud scoring."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class TransactionPredictRequest(BaseModel):
    """Transaction scoring request requiring exactly the 30 canonical numeric features."""

    model_config = ConfigDict(extra="forbid")

    external_id: Optional[str] = Field(
        default=None,
        min_length=1,
        max_length=64,
        description="Optional client-specified transaction identifier. Generated automatically if omitted.",
    )
    Time: float = Field(allow_inf_nan=False, description="Elapsed seconds since initial dataset reference")
    V1: float = Field(allow_inf_nan=False)
    V2: float = Field(allow_inf_nan=False)
    V3: float = Field(allow_inf_nan=False)
    V4: float = Field(allow_inf_nan=False)
    V5: float = Field(allow_inf_nan=False)
    V6: float = Field(allow_inf_nan=False)
    V7: float = Field(allow_inf_nan=False)
    V8: float = Field(allow_inf_nan=False)
    V9: float = Field(allow_inf_nan=False)
    V10: float = Field(allow_inf_nan=False)
    V11: float = Field(allow_inf_nan=False)
    V12: float = Field(allow_inf_nan=False)
    V13: float = Field(allow_inf_nan=False)
    V14: float = Field(allow_inf_nan=False)
    V15: float = Field(allow_inf_nan=False)
    V16: float = Field(allow_inf_nan=False)
    V17: float = Field(allow_inf_nan=False)
    V18: float = Field(allow_inf_nan=False)
    V19: float = Field(allow_inf_nan=False)
    V20: float = Field(allow_inf_nan=False)
    V21: float = Field(allow_inf_nan=False)
    V22: float = Field(allow_inf_nan=False)
    V23: float = Field(allow_inf_nan=False)
    V24: float = Field(allow_inf_nan=False)
    V25: float = Field(allow_inf_nan=False)
    V26: float = Field(allow_inf_nan=False)
    V27: float = Field(allow_inf_nan=False)
    V28: float = Field(allow_inf_nan=False)
    Amount: float = Field(allow_inf_nan=False, ge=0.0, description="Transaction monetary amount")

    @model_validator(mode="before")
    @classmethod
    def check_forbidden_fields_and_normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        # Explicit rejection of Class target label
        if "Class" in data or "class" in data:
            raise ValueError("Target label 'Class' is strictly forbidden in transaction features.")

        # Normalize nested 'features' structure if client passes {"features": {...}, "external_id": ...}
        if "features" in data and isinstance(data["features"], dict):
            features = data["features"]
            if "Class" in features or "class" in features:
                raise ValueError("Target label 'Class' is strictly forbidden in transaction features.")
            flattened = {**features}
            if "external_id" in data:
                flattened["external_id"] = data["external_id"]
            elif "transaction_id" in data:
                flattened["external_id"] = data["transaction_id"]
            return flattened

        # Map transaction_id alias to external_id if present
        if "transaction_id" in data and "external_id" not in data:
            data_copy = dict(data)
            data_copy["external_id"] = data_copy.pop("transaction_id")
            return data_copy

        return data

    def get_features_dict(self) -> Dict[str, float]:
        """Extracts exactly the 30 canonical numeric features."""
        feature_names = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount"]
        return {feat: float(getattr(self, feat)) for feat in feature_names}


class SHAPContribution(BaseModel):
    feature: str = Field(description="Feature name")
    contribution: float = Field(description="SHAP attribution value in log-odds margin space")
    absolute_contribution: float = Field(description="Absolute magnitude of feature contribution")
    direction: str = Field(description="Directional impact: increases_risk or decreases_risk")


class SHAPExplanation(BaseModel):
    output_space: str = Field(description="Model margin output space explained (raw_margin_log_odds)")
    base_value: float = Field(description="Expected value base margin of the XGBoost ensemble")
    total_shap_sum: float = Field(description="Sum of all feature SHAP attribution values")
    top_contributions: List[SHAPContribution] = Field(description="Top influential features ranked by magnitude")
    analyst_summary: str = Field(description="Human-readable synthesis for compliance and operational review")
    limitations: str = Field(description="Disclaimers regarding non-causal attribution interpretation")


class PolicyParameters(BaseModel):
    threshold_review: float = Field(description="Operational review boundary tau_review")
    threshold_block: float = Field(description="Automated block boundary tau_block")
    calibration_variant: str = Field(description="Probability calibration method applied")
    status: str = Field(description="Optimization lifecycle status")


class TransactionPredictResponse(BaseModel):
    """Documented response contract for synchronous fraud scoring."""
    prediction_id: uuid.UUID = Field(description="Unique persistent identifier of the prediction record")
    transaction_id: str = Field(description="Unique external transaction identifier")
    external_id: str = Field(description="Unique external transaction identifier")
    model_version: str = Field(description="Machine learning model version used for scoring")
    decision: str = Field(description="Cost-sensitive three-way decision: APPROVE, REVIEW, or BLOCK")
    risk_level: str = Field(description="Assigned risk tier: LOW, MEDIUM, or HIGH")
    fraud_probability: float = Field(description="Calibrated posterior fraud probability in [0, 1]")
    raw_probability: float = Field(description="Raw uncalibrated XGBoost fraud probability in [0, 1]")
    expected_cost: float = Field(description="Expected monetary loss under cost-sensitive policy")
    policy_parameters: PolicyParameters = Field(description="Thresholds and policy configuration applied")
    explanation: SHAPExplanation = Field(description="Local SHAP feature contribution attributions")
    created_at: datetime = Field(description="UTC timestamp of the persisted prediction")


class BatchTransactionItem(BaseModel):
    """Single transaction item within a batch CSV scoring submission."""

    model_config = ConfigDict(extra="ignore")

    external_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Optional transaction identifier",
    )
    Time: float = Field(allow_inf_nan=False, description="Elapsed seconds since initial dataset reference")
    V1: float = Field(allow_inf_nan=False)
    V2: float = Field(allow_inf_nan=False)
    V3: float = Field(allow_inf_nan=False)
    V4: float = Field(allow_inf_nan=False)
    V5: float = Field(allow_inf_nan=False)
    V6: float = Field(allow_inf_nan=False)
    V7: float = Field(allow_inf_nan=False)
    V8: float = Field(allow_inf_nan=False)
    V9: float = Field(allow_inf_nan=False)
    V10: float = Field(allow_inf_nan=False)
    V11: float = Field(allow_inf_nan=False)
    V12: float = Field(allow_inf_nan=False)
    V13: float = Field(allow_inf_nan=False)
    V14: float = Field(allow_inf_nan=False)
    V15: float = Field(allow_inf_nan=False)
    V16: float = Field(allow_inf_nan=False)
    V17: float = Field(allow_inf_nan=False)
    V18: float = Field(allow_inf_nan=False)
    V19: float = Field(allow_inf_nan=False)
    V20: float = Field(allow_inf_nan=False)
    V21: float = Field(allow_inf_nan=False)
    V22: float = Field(allow_inf_nan=False)
    V23: float = Field(allow_inf_nan=False)
    V24: float = Field(allow_inf_nan=False)
    V25: float = Field(allow_inf_nan=False)
    V26: float = Field(allow_inf_nan=False)
    V27: float = Field(allow_inf_nan=False)
    V28: float = Field(allow_inf_nan=False)
    Amount: float = Field(allow_inf_nan=False, ge=0.0, description="Transaction monetary amount")

    @model_validator(mode="before")
    @classmethod
    def normalize_case_and_aliases(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        normalized: Dict[str, Any] = {}
        for k, v in data.items():
            key_clean = str(k).strip()
            key_lower = key_clean.lower()
            if key_lower == "time":
                normalized["Time"] = v
            elif key_lower == "amount":
                normalized["Amount"] = v
            elif key_clean.upper().startswith("V") and key_clean[1:].isdigit():
                normalized[key_clean.upper()] = v
            elif key_lower in ("external_id", "id", "transaction_id"):
                normalized["external_id"] = str(v)
            elif key_lower == "class":
                # Ground truth target label from test CSV; silently stripped
                pass
            else:
                pass
        return normalized

    def get_features_dict(self) -> Dict[str, float]:
        """Extracts exactly the 30 canonical numeric features."""
        feature_names = ["Time"] + [f"V{i}" for i in range(1, 29)] + ["Amount"]
        return {feat: float(getattr(self, feat)) for feat in feature_names}


class BatchPredictRequest(BaseModel):
    """Batch scoring request payload."""

    batch_id: Optional[str] = Field(
        default=None,
        max_length=64,
        description="Optional client-defined batch identifier. Auto-generated if omitted.",
    )
    filename: Optional[str] = Field(
        default="uploaded_transactions.csv",
        max_length=255,
        description="Original uploaded CSV filename for audit trail",
    )
    items: List[BatchTransactionItem] = Field(
        ...,
        min_length=1,
        description="Array of transaction records to be scored and ingested",
    )


class BatchItemResult(BaseModel):
    """Individual transaction prediction result within a batch response."""

    transaction_id: str = Field(description="Unique external transaction identifier")
    external_id: str = Field(description="Unique external transaction identifier")
    amount: Optional[float] = Field(default=None, description="Monetary transaction amount")
    decision: str = Field(description="Decision policy: APPROVE, REVIEW, BLOCK, or FAILED")
    risk_level: str = Field(description="Assigned risk tier: LOW, MEDIUM, HIGH, or UNKNOWN")
    fraud_probability: Optional[float] = Field(default=None, description="Calibrated posterior fraud probability")
    raw_probability: Optional[float] = Field(default=None, description="Raw uncalibrated XGBoost fraud probability")
    expected_cost: Optional[float] = Field(default=None, description="Expected monetary loss under cost-sensitive policy")
    model_version: Optional[str] = Field(default=None, description="Model version used for scoring")
    created_at: Optional[datetime] = Field(default=None, description="UTC timestamp of the prediction")
    status: str = Field(default="SUCCESS", description="Row-level status: SUCCESS or ERROR")
    error: Optional[str] = Field(default=None, description="Error reason if inference or validation failed for this row")


class BatchSummary(BaseModel):
    """Aggregated operational metrics for an uploaded transaction batch."""

    batch_id: str = Field(description="Unique batch identifier")
    filename: str = Field(description="Source CSV filename")
    total_submitted: int = Field(description="Total transactions submitted in batch")
    total_processed: int = Field(description="Successfully processed transactions")
    failed_count: int = Field(default=0, description="Transactions that failed inference or validation")
    approved_count: int = Field(description="Number of transactions auto-approved")
    review_count: int = Field(description="Number of transactions routed to review queue")
    block_count: int = Field(description="Number of transactions auto-blocked")
    low_risk_count: int = Field(description="Transactions in LOW risk tier")
    medium_risk_count: int = Field(description="Transactions in MEDIUM risk tier")
    high_risk_count: int = Field(description="Transactions in HIGH risk tier")
    total_amount: float = Field(description="Cumulative monetary value across successfully processed transactions")
    average_fraud_probability: float = Field(description="Mean calibrated fraud probability across processed transactions")
    created_at: datetime = Field(description="UTC timestamp of batch execution")


class BatchPredictResponse(BaseModel):
    """Complete response payload for batch fraud analysis."""

    summary: BatchSummary = Field(description="Batch-level summary metrics")
    items: List[BatchItemResult] = Field(description="Individual scored transaction records")


class OperationalStatsResponse(BaseModel):
    """Cumulative operational metrics across all persisted transaction records."""

    total_transactions: int = Field(description="Total number of ingested and scored transactions")
    approved_count: int = Field(description="Total approved transactions")
    review_count: int = Field(description="Total review-routed transactions")
    block_count: int = Field(description="Total blocked transactions")
    low_risk_count: int = Field(description="Total low risk transactions")
    medium_risk_count: int = Field(description="Total medium risk transactions")
    high_risk_count: int = Field(description="Total high risk transactions")
    total_amount: float = Field(description="Total monetary value processed")
    average_fraud_probability: float = Field(description="Global mean fraud probability")
    latest_transaction_at: Optional[datetime] = Field(default=None, description="Timestamp of most recent transaction")


class RecentTransactionItem(BaseModel):
    """Summary of a recent transaction and its latest prediction."""

    id: uuid.UUID = Field(description="Internal transaction UUID")
    external_id: str = Field(description="External transaction identifier")
    amount: float = Field(description="Monetary amount")
    decision: str = Field(description="Policy decision (APPROVE, REVIEW, BLOCK)")
    risk_level: str = Field(description="Risk level (LOW, MEDIUM, HIGH)")
    fraud_probability: float = Field(description="Calibrated fraud probability")
    created_at: datetime = Field(description="UTC creation timestamp")
    batch_id: Optional[str] = Field(default=None, description="Batch identifier if uploaded in batch")


class RecentTransactionsResponse(BaseModel):
    """List of recently processed transactions."""

    items: List[RecentTransactionItem] = Field(description="Recent transaction records")
    total: Optional[int] = Field(default=None, description="Total matching transaction records")
    limit: Optional[int] = Field(default=None, description="Page limit")
    offset: Optional[int] = Field(default=None, description="Page offset")


