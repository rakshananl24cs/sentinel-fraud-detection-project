"""Pydantic schemas for machine learning model metadata and governance."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ModelMetadataResponse(BaseModel):
    """Documented response contract for active model metadata."""

    id: Optional[uuid.UUID] = Field(default=None, description="Model record UUID")
    version: str = Field(description="Active model version identifier")
    architecture: str = Field(description="Classifier pipeline architecture")
    artifact_path: Optional[str] = Field(default=None, description="Path to binary model artifact")
    lifecycle_status: str = Field(default="ACTIVE", description="Lifecycle stage: ACTIVE, CANDIDATE, ARCHIVED")
    hyperparameters: Dict[str, Any] = Field(default_factory=dict, description="Model training hyperparameters")
    metrics: Dict[str, Any] = Field(default_factory=dict, description="Offline evaluation benchmark metrics")
    trained_at: Optional[datetime] = Field(default=None, description="Timestamp when model was trained")
    created_at: Optional[datetime] = Field(default=None, description="Timestamp of registration")
    is_deployed: bool = Field(default=False, description="True if this version is actively deployed in runtime inference")
    provenance: str = Field(default="DATABASE_REGISTRY", description="Model provenance: RUNTIME_DEPLOYMENT or TEST_FIXTURE")


class ModelListResponse(BaseModel):
    """List of registered models."""

    items: List[ModelMetadataResponse] = Field(description="Registered models")
    total: int = Field(description="Total registered models")
