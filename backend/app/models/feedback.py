"""SQLAlchemy model for operator feedback and human-in-the-loop annotations."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.base import Base

if TYPE_CHECKING:
    from backend.app.models.transaction import Transaction
    from backend.app.models.user import User


class OperatorFeedback(Base):
    """Represents a human operator adjudication on a flagged transaction.

    Captures final operator decisions, verification status, and eligibility
    for downstream model retraining candidate sets.
    """

    __tablename__ = "operator_feedback"

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
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(
        String(30),
        index=True,
        nullable=False,
    )
    reason_code: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )
    comment: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )
    is_eligible_for_retraining: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        index=True,
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
        back_populates="feedback",
    )
    user: Mapped[User] = relationship(
        "User",
        back_populates="feedback",
    )

    __table_args__ = (
        CheckConstraint(
            "decision IN ('CONFIRMED_FRAUD', 'CONFIRMED_GENUINE', 'DISPUTED', 'INCONCLUSIVE')",
            name="ck_feedback_decision",
        ),
        CheckConstraint(
            "(is_eligible_for_retraining = FALSE) OR "
            "(is_verified = TRUE AND decision IN ('CONFIRMED_FRAUD', 'CONFIRMED_GENUINE'))",
            name="ck_feedback_retraining_eligibility",
        ),
        Index("ix_feedback_transaction_user", "transaction_id", "user_id"),
    )

    @staticmethod
    def compute_retraining_eligibility(decision: str, is_verified: bool) -> bool:
        """Determines whether feedback qualifies for downstream retraining datasets.

        Only verified adjudications with definitive ground truth
        ('CONFIRMED_FRAUD' or 'CONFIRMED_GENUINE') are eligible.
        Disputed, inconclusive, or unverified records are disqualified.
        """
        return bool(is_verified and decision in ("CONFIRMED_FRAUD", "CONFIRMED_GENUINE"))

    def __repr__(self) -> str:
        return (
            f"<OperatorFeedback id={self.id} decision={self.decision!r} "
            f"verified={self.is_verified} eligible_for_retrain={self.is_eligible_for_retraining}>"
        )
