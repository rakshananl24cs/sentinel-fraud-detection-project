"""Pydantic schemas for operator review queue and feedback adjudication."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

FeedbackDecisionType = Literal["CONFIRMED_FRAUD", "CONFIRMED_GENUINE", "DISPUTED", "INCONCLUSIVE"]


class FeedbackCreateRequest(BaseModel):
    """Schema for submitting human operator adjudication on a transaction."""

    model_config = ConfigDict(extra="forbid")

    decision: FeedbackDecisionType = Field(
        description="Operator adjudication label: CONFIRMED_FRAUD, CONFIRMED_GENUINE, DISPUTED, or INCONCLUSIVE",
    )
    reason_code: Optional[str] = Field(
        default=None,
        max_length=100,
        description="Optional categorical rationale code (e.g. CARD_NOT_PRESENT_FRAUD, AUTHORIZED_USER)",
    )
    comment: Optional[str] = Field(
        default=None,
        max_length=1000,
        description="Optional detailed qualitative commentary for compliance and auditing",
    )
    is_verified: bool = Field(
        default=False,
        description="Verification flag. Can only be submitted as True by ADMIN role.",
    )

    @model_validator(mode="before")
    @classmethod
    def reject_client_eligibility(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "is_eligible_for_retraining" in data or "eligible_for_retraining" in data:
                raise ValueError("Client is strictly forbidden from directly setting retraining eligibility.")
        return data


class FeedbackResponse(BaseModel):
    """Schema representing a persisted operator adjudication record."""

    id: uuid.UUID = Field(description="Unique persistent identifier of the feedback record")
    transaction_id: uuid.UUID = Field(description="Internal UUID of the target transaction")
    external_id: str = Field(description="Unique external transaction identifier")
    user_id: uuid.UUID = Field(description="UUID of the operator who submitted this feedback")
    operator_email: str = Field(description="Email address of the operator who submitted this feedback")
    operator_username: Optional[str] = Field(default=None, description="Alias for operator email")
    decision: str = Field(description="Adjudication decision label")
    reason_code: Optional[str] = Field(default=None, description="Optional reason code")
    comment: Optional[str] = Field(default=None, description="Optional qualitative comment")
    is_verified: bool = Field(description="Whether feedback has been verified by an administrator")
    is_eligible_for_retraining: bool = Field(description="Whether feedback qualifies for retraining candidate datasets")
    created_at: datetime = Field(description="UTC timestamp of feedback record creation")
    feedback_sequence: int = Field(default=1, description="Sequential submission number for this transaction (1=initial, >1=repeated)")
    is_conflicting: bool = Field(default=False, description="True if feedback conflicts with a prior adjudication on this transaction")


class ReviewQueueItemResponse(BaseModel):
    """Analyst-facing summary item for transactions queued for manual review."""

    transaction_id: uuid.UUID = Field(description="Internal transaction UUID")
    external_id: str = Field(description="External transaction identifier")
    amount: float = Field(description="Transaction monetary amount")
    transaction_created_at: datetime = Field(description="Timestamp when transaction was ingested")
    prediction_id: uuid.UUID = Field(description="Identifier of the latest applicable risk prediction")
    decision: str = Field(description="Decision policy output: always 'REVIEW' in this queue")
    fraud_probability: float = Field(description="Calibrated posterior fraud probability in [0, 1]")
    raw_probability: float = Field(description="Raw XGBoost ensemble probability in [0, 1]")
    risk_level: str = Field(description="Risk level tier: LOW, MEDIUM, or HIGH")
    model_version: str = Field(description="Model version used for scoring")
    prediction_created_at: datetime = Field(description="Timestamp of the latest prediction")
    explanation_summary: Optional[str] = Field(default=None, description="Human-readable synthesis of top risk drivers")
    feedback_count: int = Field(default=0, description="Total operator feedback records logged for this transaction")
    latest_feedback_decision: Optional[str] = Field(default=None, description="Most recent operator adjudication, if any")
    latest_feedback_verified: Optional[bool] = Field(default=None, description="Verification status of the most recent feedback")
    batch_id: Optional[str] = Field(default=None, description="Batch identifier if uploaded in batch")



class ReviewQueueResponse(BaseModel):
    """Paginated list of transactions in the manual operator review queue."""

    items: List[ReviewQueueItemResponse] = Field(description="List of review queue items")
    total: int = Field(description="Total count of transactions matching filter criteria")
    limit: int = Field(description="Requested page size limit")
    offset: int = Field(description="Requested pagination offset")
