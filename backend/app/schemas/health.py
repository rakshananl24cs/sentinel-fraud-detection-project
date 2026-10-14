"""Pydantic schemas for service health checks."""

from __future__ import annotations

from datetime import datetime, timezone
from pydantic import BaseModel, Field


class HealthLiveResponse(BaseModel):
    """Response payload for liveness probe."""
    status: str = Field("ok", description="Service process liveness indicator")
    service: str = Field("fraud-detection-api", description="Service identifier")
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Current UTC timestamp",
    )


class HealthReadyResponse(BaseModel):
    """Response payload for readiness probe with database verification."""
    status: str = Field("ok", description="Overall readiness status")
    database: str = Field("connected", description="Database connectivity status")
    service: str = Field("fraud-detection-api", description="Service identifier")
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Current UTC timestamp",
    )


class HealthUnhealthyResponse(BaseModel):
    """Response payload when a dependency fails readiness checks."""
    status: str = Field("unhealthy", description="Overall readiness failure status")
    database: str = Field("disconnected", description="Database connectivity status")
    service: str = Field("fraud-detection-api", description="Service identifier")
    timestamp_utc: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Current UTC timestamp",
    )
