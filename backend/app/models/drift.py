"""SQLAlchemy model for data and concept drift monitoring reports."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict

from sqlalchemy import CheckConstraint, DateTime, Float, JSON, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base


class DriftReport(Base):
    """Represents a computed statistical drift evaluation report.

    Monitors distribution shifts over designated time windows using metrics
    such as Population Stability Index (PSI), Kolmogorov-Smirnov test (KS),
    and empirical fraud prevalence tracking.
    """

    __tablename__ = "drift_reports"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    model_version: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False,
    )
    metric_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )
    metric_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
    )
    time_window_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    time_window_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    summary_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
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
            "status IN ('NORMAL', 'WARNING', 'CRITICAL')",
            name="ck_drift_reports_status",
        ),
        CheckConstraint(
            "time_window_end >= time_window_start",
            name="ck_drift_reports_time_window",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<DriftReport id={self.id} model={self.model_version!r} "
            f"metric={self.metric_name!r}={self.metric_value:.4f} status={self.status!r}>"
        )
