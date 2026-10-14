"""SQLAlchemy model for machine learning model versioning and lifecycle governance."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import CheckConstraint, DateTime, JSON, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class ModelRegistry(Base):
    """Represents a registered machine learning model artifact and governance metadata.

    Tracks model version identifier, architecture, hyperparameters, validation
    evaluation metrics, and lifecycle stage ('ACTIVE', 'CANDIDATE', 'ARCHIVED').
    """

    __tablename__ = "model_registry"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    version: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )
    architecture: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    artifact_path: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    hyperparameters_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
    metrics_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
    lifecycle_status: Mapped[str] = mapped_column(
        String(30),
        index=True,
        nullable=False,
        default="CANDIDATE",
    )
    trained_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    __table_args__ = (
        CheckConstraint(
            "lifecycle_status IN ('ACTIVE', 'CANDIDATE', 'ARCHIVED')",
            name="ck_model_registry_lifecycle_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<ModelRegistry version={self.version!r} arch={self.architecture!r} status={self.lifecycle_status!r}>"
