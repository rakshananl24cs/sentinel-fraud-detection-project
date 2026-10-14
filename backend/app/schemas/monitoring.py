"""Pydantic schemas for data drift reporting and model monitoring."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_OBSERVATION_WINDOW_SECONDS: float = 30 * 86400.0  # 30 days


class DriftReportCreateRequest(BaseModel):
    """Payload to trigger statistical drift evaluation for an observation window."""

    model_config = ConfigDict(extra="forbid")

    time_window_start: datetime = Field(
        description="Observation window start timestamp (UTC)",
    )
    time_window_end: datetime = Field(
        description="Observation window end timestamp (UTC)",
    )
    model_version: str = Field(
        default="xgb-cost-v1",
        min_length=1,
        max_length=50,
        description="ML model version to evaluate",
    )

    @model_validator(mode="after")
    def validate_time_window(self) -> DriftReportCreateRequest:
        # Normalize timezone to UTC
        start = self.time_window_start
        end = self.time_window_end

        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
            self.time_window_start = start
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
            self.time_window_end = end

        if end < start:
            raise ValueError("Observation window end time must be greater than or equal to start time.")

        duration = (end - start).total_seconds()
        if duration > MAX_OBSERVATION_WINDOW_SECONDS:
            raise ValueError(
                f"Observation window ({duration / 86400:.1f} days) exceeds synchronous processing limit of 30 days."
            )

        return self


class DriftReportResponse(BaseModel):
    """Schema representing a persisted statistical drift monitoring report."""

    id: uuid.UUID = Field(description="Unique persistent identifier of the drift report")
    model_version: str = Field(description="Model version evaluated")
    metric_name: str = Field(description="Primary aggregate metric name (e.g. MAX_FEATURE_PSI)")
    metric_value: float = Field(description="Primary metric scalar value")
    status: str = Field(description="Overall drift status: NORMAL, WARNING, or CRITICAL")
    time_window_start: datetime = Field(description="Observation window start UTC")
    time_window_end: datetime = Field(description="Observation window end UTC")
    created_at: datetime = Field(description="UTC timestamp when report was generated and persisted")
    summary: Dict[str, Any] = Field(description="Full statistical breakdown, methodology, and per-feature drift results")

    model_config = ConfigDict(from_attributes=True)


class DriftReportListResponse(BaseModel):
    """Paginated list of historical drift evaluation reports."""

    items: List[DriftReportResponse] = Field(description="List of drift reports")
    total: int = Field(description="Total count of reports matching filter criteria")
    limit: int = Field(description="Requested page size limit")
    offset: int = Field(description="Requested pagination offset")
