"""SQLAlchemy model for ingested financial transactions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List

from sqlalchemy import DateTime, JSON, Numeric, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

if TYPE_CHECKING:
    from backend.app.models.alert import FraudAlert
    from backend.app.models.feedback import OperatorFeedback
    from backend.app.models.prediction import Prediction


class Transaction(Base):
    """Represents an ingested financial transaction record."""

    __tablename__ = "transactions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    external_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        index=True,
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
    )
    payload_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        index=True,
        nullable=False,
    )

    # Relationships (append-only history supported; predictions are immutable)
    predictions: Mapped[List[Prediction]] = relationship(
        "Prediction",
        back_populates="transaction",
        order_by="desc(Prediction.created_at)",
    )
    feedback: Mapped[List[OperatorFeedback]] = relationship(
        "OperatorFeedback",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="desc(OperatorFeedback.created_at)",
    )
    alerts: Mapped[List[FraudAlert]] = relationship(
        "FraudAlert",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="desc(FraudAlert.created_at)",
    )

    def __repr__(self) -> str:
        return f"<Transaction id={self.id} external_id={self.external_id!r} amount={self.amount}>"
