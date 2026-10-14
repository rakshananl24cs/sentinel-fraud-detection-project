"""Pydantic request and response schemas for Fraud Alert Notifications."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AlertItemResponse(BaseModel):
    """Schema for a single persistent fraud alert."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    transaction_id: uuid.UUID
    external_id: str
    prediction_id: Optional[uuid.UUID] = None
    alert_type: str = Field(..., description="'HIGH_RISK' for BLOCK or 'NEEDS_REVIEW' for REVIEW")
    severity: str = Field(..., description="'HIGH' or 'MEDIUM'")
    decision: str = Field(..., description="'BLOCK' or 'REVIEW'")
    fraud_probability: float
    amount: float
    title: str
    message: str
    recommended_action: str
    disclaimer: str
    is_read: bool
    read_at: Optional[datetime] = None
    created_at: datetime


class AlertListResponse(BaseModel):
    """Schema for paginated list of fraud alerts."""

    items: List[AlertItemResponse]
    total: int
    unread_count: int
    high_risk_unread_count: int
    review_needed_unread_count: int
    limit: int
    offset: int


class AlertStatsResponse(BaseModel):
    """Schema for quick alert badge counters."""

    total: int
    unread_count: int
    high_risk_unread_count: int
    review_needed_unread_count: int


class MarkAlertsReadResponse(BaseModel):
    """Schema for bulk mark-as-read operation."""

    message: str
    updated_count: int
