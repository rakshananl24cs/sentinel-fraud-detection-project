"""SQLAlchemy model for model inference predictions and explanations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, JSON, String, Uuid
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

if TYPE_CHECKING:
    from backend.app.models.transaction import Transaction


class Prediction(Base):
    """Represents an immutable, append-only risk prediction record.

    Stores model outputs, calibrated probabilities, three-way decisions,
    expected cost values, policy parameters, and SHAP explanation details.
    Multiple predictions may be linked to a single transaction over time
    to support model comparison and retraining evaluations.

    IMMUTABILITY & RETENTION POLICY:
    Prediction records are strictly immutable and protected by PostgreSQL trigger
    'trg_predictions_immutable' prohibiting UPDATE and DELETE operations.
    Historical predictions and their referenced transactions must be retained
    in perpetuity for model governance and financial compliance. The foreign key
    is enforced as ON DELETE RESTRICT. Any future privacy-retention or GDPR
    purging requirements must use a separately designed, cryptographically
    audited ledger archiving process rather than row deletion.
    """

    __tablename__ = "predictions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("transactions.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    model_version: Mapped[str] = mapped_column(
        String(50),
        index=True,
        nullable=False,
    )
    raw_probability: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    calibrated_probability: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    risk_level: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(
        String(20),
        index=True,
        nullable=False,
    )
    expected_cost: Mapped[float] = mapped_column(
        Float,
        nullable=False,
    )
    policy_parameters_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
    )
    explanation_json: Mapped[Dict[str, Any]] = mapped_column(
        JSON().with_variant(JSONB(), "postgresql"),
        nullable=False,
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
        back_populates="predictions",
    )

    __table_args__ = (
        CheckConstraint(
            "raw_probability >= 0.0 AND raw_probability <= 1.0",
            name="ck_predictions_raw_probability_range",
        ),
        CheckConstraint(
            "calibrated_probability >= 0.0 AND calibrated_probability <= 1.0",
            name="ck_predictions_calibrated_probability_range",
        ),
        CheckConstraint(
            "risk_level IN ('LOW', 'MEDIUM', 'HIGH')",
            name="ck_predictions_risk_level",
        ),
        CheckConstraint(
            "decision IN ('APPROVE', 'REVIEW', 'BLOCK')",
            name="ck_predictions_decision",
        ),
        Index("ix_predictions_transaction_created", "transaction_id", "created_at"),
    )

    def __repr__(self) -> str:
        return (
            f"<Prediction id={self.id} model={self.model_version!r} "
            f"decision={self.decision!r} calibrated_p={self.calibrated_probability:.4f}>"
        )
