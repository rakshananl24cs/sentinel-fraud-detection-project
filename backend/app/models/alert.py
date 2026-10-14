"""SQLAlchemy model for persistent fraud alert notifications."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

if TYPE_CHECKING:
    from backend.app.models.prediction import Prediction
    from backend.app.models.transaction import Transaction


class FraudAlert(Base):
    """Represents a persistent alert notification generated when a transaction
    receives a HIGH_RISK (BLOCK) or NEEDS_REVIEW (REVIEW) decision from ML inference.
    """

    __tablename__ = "fraud_alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    external_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    prediction_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("predictions.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    alert_type: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False,
    )
    severity: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    fraud_probability: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )
    message: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    recommended_action: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    disclaimer: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="Model predictions indicate statistical risk and do not independently confirm fraud.",
    )
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
        nullable=False,
    )
    read_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    # Relationships
    transaction: Mapped[Transaction] = relationship(
        "Transaction",
        back_populates="alerts",
    )
    prediction: Mapped[Optional[Prediction]] = relationship("Prediction")

    __table_args__ = (
        CheckConstraint(
            "alert_type IN ('HIGH_RISK', 'NEEDS_REVIEW')",
            name="ck_fraud_alert_type",
        ),
        CheckConstraint(
            "decision IN ('BLOCK', 'REVIEW')",
            name="ck_fraud_alert_decision",
        ),
    )

    def __repr__(self) -> str:
        return (
            f"<FraudAlert id={self.id} type={self.alert_type} "
            f"tx={self.external_id} decision={self.decision} is_read={self.is_read}>"
        )
