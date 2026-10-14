"""Operator review queue and human-in-the-loop feedback adjudication endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import require_role
from backend.app.db.session import get_db
from backend.app.models.audit import AuditLog
from backend.app.models.feedback import OperatorFeedback
from backend.app.models.prediction import Prediction
from backend.app.models.transaction import Transaction
from backend.app.models.user import User
from backend.app.schemas.feedback import (
    FeedbackCreateRequest,
    FeedbackResponse,
    ReviewQueueItemResponse,
    ReviewQueueResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/transactions", tags=["Review Queue & Feedback"])


def resolve_transaction(identifier: str, db: Session) -> Optional[Transaction]:
    """Resolves a transaction by internal UUID or unique external_id."""
    try:
        tx_uuid = uuid.UUID(identifier)
        tx = db.execute(select(Transaction).where(Transaction.id == tx_uuid)).scalar_one_or_none()
        if tx is not None:
            return tx
    except (ValueError, TypeError):
        pass

    return db.execute(
        select(Transaction).where(Transaction.external_id == identifier)
    ).scalar_one_or_none()


@router.get(
    "/review-queue",
    response_model=ReviewQueueResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"model": ReviewQueueResponse, "description": "Review queue transactions"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid authentication"},
        status.HTTP_403_FORBIDDEN: {"description": "Insufficient permissions"},
    },
    summary="Operator Review Queue",
    description=(
        "Retrieves a paginated list of transactions whose latest applicable risk prediction "
        "decision is 'REVIEW'. Employs window-partitioned deduplication to guarantee transactions "
        "are never duplicated due to prediction history or prior feedback records. Strictly "
        "read-only and deterministic."
    ),
)
def get_review_queue(
    limit: int = Query(default=20, ge=1, le=100, description="Page size limit (1 to 100)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    status_filter: Optional[str] = Query(
        default=None,
        regex="^(PENDING|REVIEWED)$",
        description="Filter by adjudication status: 'PENDING' (unreviewed) or 'REVIEWED' (has feedback)",
    ),
    model_version: Optional[str] = Query(
        default=None,
        description="Filter by ML model version (e.g. 'xgb-cost-v1')",
    ),
    min_probability: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Filter for calibrated fraud probability >= min_probability",
    ),
    max_probability: Optional[float] = Query(
        default=None,
        ge=0.0,
        le=1.0,
        description="Filter for calibrated fraud probability <= max_probability",
    ),
    batch_id: Optional[str] = Query(
        default=None,
        description="Filter by batch identifier",
    ),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> ReviewQueueResponse:
    """Lists transactions awaiting operational review without mutating records."""
    # 1. Window function ranking predictions per transaction to identify the latest prediction
    pred_subq = (
        select(
            Prediction.id.label("pred_id"),
            Prediction.transaction_id.label("pred_transaction_id"),
            Prediction.model_version.label("pred_model_version"),
            Prediction.raw_probability.label("pred_raw_probability"),
            Prediction.calibrated_probability.label("pred_calibrated_probability"),
            Prediction.risk_level.label("pred_risk_level"),
            Prediction.decision.label("pred_decision"),
            Prediction.explanation_json.label("pred_explanation_json"),
            Prediction.created_at.label("pred_created_at"),
            func.row_number()
            .over(
                partition_by=Prediction.transaction_id,
                order_by=(desc(Prediction.created_at), desc(Prediction.id)),
            )
            .label("rn"),
        )
        .subquery()
    )

    # 2. Correlated scalar subqueries for feedback metadata to prevent cartesian product / row duplication
    feedback_count_subq = (
        select(func.count(OperatorFeedback.id))
        .where(OperatorFeedback.transaction_id == Transaction.id)
        .scalar_subquery()
    )

    latest_feedback_decision_subq = (
        select(OperatorFeedback.decision)
        .where(OperatorFeedback.transaction_id == Transaction.id)
        .order_by(desc(OperatorFeedback.created_at), desc(OperatorFeedback.id))
        .limit(1)
        .scalar_subquery()
    )

    latest_feedback_verified_subq = (
        select(OperatorFeedback.is_verified)
        .where(OperatorFeedback.transaction_id == Transaction.id)
        .order_by(desc(OperatorFeedback.created_at), desc(OperatorFeedback.id))
        .limit(1)
        .scalar_subquery()
    )

    # 3. Join with Transaction where the latest prediction is 'REVIEW' (rn == 1)
    base_query = (
        select(
            Transaction.id.label("tx_id"),
            Transaction.external_id.label("tx_external_id"),
            Transaction.amount.label("tx_amount"),
            Transaction.payload_json.label("tx_payload_json"),
            Transaction.created_at.label("tx_created_at"),
            pred_subq.c.pred_id,
            pred_subq.c.pred_model_version,
            pred_subq.c.pred_raw_probability,
            pred_subq.c.pred_calibrated_probability,
            pred_subq.c.pred_risk_level,
            pred_subq.c.pred_decision,
            pred_subq.c.pred_explanation_json,
            pred_subq.c.pred_created_at,
            feedback_count_subq.label("feedback_count"),
            latest_feedback_decision_subq.label("latest_feedback_decision"),
            latest_feedback_verified_subq.label("latest_feedback_verified"),
        )
        .join(Transaction, Transaction.id == pred_subq.c.pred_transaction_id)
        .where(pred_subq.c.rn == 1, pred_subq.c.pred_decision == "REVIEW")
    )

    # 4. Apply validated filters
    if status_filter == "PENDING":
        base_query = base_query.where(feedback_count_subq == 0)
    elif status_filter == "REVIEWED":
        base_query = base_query.where(feedback_count_subq > 0)

    if model_version:
        base_query = base_query.where(pred_subq.c.pred_model_version == model_version)

    if min_probability is not None:
        base_query = base_query.where(pred_subq.c.pred_calibrated_probability >= min_probability)

    if max_probability is not None:
        base_query = base_query.where(pred_subq.c.pred_calibrated_probability <= max_probability)

    if batch_id:
        base_query = base_query.where(Transaction.payload_json["batch_id"].as_string() == batch_id)

    # 5. Compute total matching count
    count_subq = base_query.order_by(None).subquery()
    total = db.execute(select(func.count()).select_from(count_subq)).scalar_one()

    # 6. Fetch paginated records with deterministic ordering
    items_query = base_query.order_by(
        desc(pred_subq.c.pred_created_at),
        desc(Transaction.id),
    ).limit(limit).offset(offset)

    rows = db.execute(items_query).all()

    items: List[ReviewQueueItemResponse] = []
    for row in rows:
        expl_summary = None
        if isinstance(row.pred_explanation_json, dict):
            expl_summary = row.pred_explanation_json.get("analyst_summary")

        tx_batch_id = None
        if isinstance(row.tx_payload_json, dict):
            tx_batch_id = row.tx_payload_json.get("batch_id")

        items.append(
            ReviewQueueItemResponse(
                transaction_id=row.tx_id,
                external_id=row.tx_external_id,
                amount=float(row.tx_amount),
                transaction_created_at=row.tx_created_at,
                prediction_id=row.pred_id,
                decision=row.pred_decision,
                fraud_probability=row.pred_calibrated_probability,
                raw_probability=row.pred_raw_probability,
                risk_level=row.pred_risk_level,
                model_version=row.pred_model_version,
                prediction_created_at=row.pred_created_at,
                explanation_summary=expl_summary,
                feedback_count=row.feedback_count or 0,
                latest_feedback_decision=row.latest_feedback_decision,
                latest_feedback_verified=row.latest_feedback_verified,
                batch_id=tx_batch_id,
            )
        )

    return ReviewQueueResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{transaction_id}/feedback",
    response_model=FeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"model": FeedbackResponse, "description": "Feedback recorded and persisted"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid authentication"},
        status.HTTP_403_FORBIDDEN: {"description": "Insufficient permissions or unauthorized verification"},
        status.HTTP_404_NOT_FOUND: {"description": "Transaction or prediction not found"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Invalid feedback payload"},
    },
    summary="Adjudicate Transaction Feedback",
    description=(
        "Submits human operator adjudication for a transaction. Resolves transaction by internal "
        "UUID or unique external_id. Preserves full append-only feedback history without overwriting "
        "previous entries. Retraining eligibility is strictly computed based on explicit admin "
        "verification and ground-truth decisions. Inserts atomic audit logs."
    ),
)
def submit_transaction_feedback(
    transaction_id: str,
    payload: FeedbackCreateRequest,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    """Submits operator feedback with append-only history and atomic audit logging."""
    # 1. Resolve transaction
    tx = resolve_transaction(transaction_id, db)
    if tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{transaction_id}' not found.",
        )

    # 2. Validate relevant prediction exists
    latest_pred = db.execute(
        select(Prediction)
        .where(Prediction.transaction_id == tx.id)
        .order_by(desc(Prediction.created_at), desc(Prediction.id))
    ).scalars().first()
    if latest_pred is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No risk prediction found for transaction '{transaction_id}'.",
        )

    # 3. Role authorization check for verification flag
    if payload.is_verified and current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators are authorized to submit verified feedback.",
        )

    # 4. Strictly compute retraining eligibility (cannot be client-controlled)
    is_verified = bool(payload.is_verified and current_user.role == "ADMIN")
    is_eligible_for_retraining = OperatorFeedback.compute_retraining_eligibility(
        decision=payload.decision,
        is_verified=is_verified,
    )

    # 5. History preservation & Conflict detection
    existing_feedbacks = db.execute(
        select(OperatorFeedback)
        .where(OperatorFeedback.transaction_id == tx.id)
        .order_by(desc(OperatorFeedback.created_at), desc(OperatorFeedback.id))
    ).scalars().all()

    feedback_sequence = len(existing_feedbacks) + 1
    is_conflicting = False
    if existing_feedbacks:
        if any(fb.decision != payload.decision for fb in existing_feedbacks):
            is_conflicting = True

    # 6. Atomic persistence of Feedback and AuditLog
    now_utc = datetime.now(timezone.utc)
    try:
        feedback = OperatorFeedback(
            transaction_id=tx.id,
            user_id=current_user.id,
            decision=payload.decision,
            reason_code=payload.reason_code,
            comment=payload.comment,
            is_verified=is_verified,
            is_eligible_for_retraining=is_eligible_for_retraining,
            created_at=now_utc,
        )
        db.add(feedback)
        db.flush()  # Assigns feedback.id

        audit_entry = AuditLog(
            user_id=current_user.id,
            action="FEEDBACK_SUBMISSION",
            entity_type="FEEDBACK",
            entity_id=str(feedback.id),
            metadata_json={
                "transaction_id": str(tx.id),
                "external_id": tx.external_id,
                "prediction_id": str(latest_pred.id),
                "decision": feedback.decision,
                "reason_code": feedback.reason_code,
                "is_verified": feedback.is_verified,
                "is_eligible_for_retraining": feedback.is_eligible_for_retraining,
                "operator_email": current_user.email,
                "operator_username": current_user.email,
                "operator_role": current_user.role,
                "feedback_sequence": feedback_sequence,
                "is_conflicting": is_conflicting,
            },
            created_at=now_utc,
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(feedback)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to persist operator feedback and audit log: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to persist operator feedback record.",
        )

    return FeedbackResponse(
        id=feedback.id,
        transaction_id=tx.id,
        external_id=tx.external_id,
        user_id=current_user.id,
        operator_email=current_user.email,
        operator_username=current_user.email,
        decision=feedback.decision,
        reason_code=feedback.reason_code,
        comment=feedback.comment,
        is_verified=feedback.is_verified,
        is_eligible_for_retraining=feedback.is_eligible_for_retraining,
        created_at=feedback.created_at,
        feedback_sequence=feedback_sequence,
        is_conflicting=is_conflicting,
    )


@router.post(
    "/{transaction_id}/feedback/{feedback_id}/verify",
    response_model=FeedbackResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"model": FeedbackResponse, "description": "Feedback verified and updated"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid authentication"},
        status.HTTP_403_FORBIDDEN: {"description": "Administrator role required"},
        status.HTTP_404_NOT_FOUND: {"description": "Transaction or feedback record not found"},
    },
    summary="Verify Operator Feedback",
    description=(
        "Explicitly verifies an existing operator feedback record. Restricted strictly to "
        "administrators. Updates retraining eligibility according to database constraints "
        "and generates an immutable audit log entry."
    ),
)
def verify_transaction_feedback(
    transaction_id: str,
    feedback_id: str,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
) -> FeedbackResponse:
    """Explicitly verifies an existing operator feedback record (Admin only)."""
    # 1. Resolve transaction
    tx = resolve_transaction(transaction_id, db)
    if tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{transaction_id}' not found.",
        )

    # 2. Resolve feedback record
    try:
        fb_uuid = uuid.UUID(feedback_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invalid feedback identifier format.",
        )

    feedback = db.execute(
        select(OperatorFeedback).where(
            OperatorFeedback.id == fb_uuid,
            OperatorFeedback.transaction_id == tx.id,
        )
    ).scalar_one_or_none()
    if feedback is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Feedback record '{feedback_id}' not found for transaction '{transaction_id}'.",
        )

    # 3. Calculate new verification and eligibility state
    new_verified = True
    new_eligible = OperatorFeedback.compute_retraining_eligibility(
        decision=feedback.decision,
        is_verified=new_verified,
    )

    # 4. Atomic update and audit log
    now_utc = datetime.now(timezone.utc)
    try:
        feedback.is_verified = new_verified
        feedback.is_eligible_for_retraining = new_eligible

        audit_entry = AuditLog(
            user_id=current_user.id,
            action="FEEDBACK_VERIFICATION",
            entity_type="FEEDBACK",
            entity_id=str(feedback.id),
            metadata_json={
                "transaction_id": str(tx.id),
                "external_id": tx.external_id,
                "feedback_id": str(feedback.id),
                "decision": feedback.decision,
                "is_verified": True,
                "is_eligible_for_retraining": new_eligible,
                "verified_by_user_id": str(current_user.id),
                "verified_by_email": current_user.email,
                "verified_by_username": current_user.email,
            },
            created_at=now_utc,
        )
        db.add(audit_entry)
        db.commit()
        db.refresh(feedback)
    except Exception as exc:
        db.rollback()
        logger.error("Failed to verify feedback record: %s", type(exc).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update feedback verification state.",
        )

    # Find submitting user email
    submitting_user_email = db.execute(
        select(User.email).where(User.id == feedback.user_id)
    ).scalar_one_or_none() or "unknown"

    return FeedbackResponse(
        id=feedback.id,
        transaction_id=tx.id,
        external_id=tx.external_id,
        user_id=feedback.user_id,
        operator_email=submitting_user_email,
        operator_username=submitting_user_email,
        decision=feedback.decision,
        reason_code=feedback.reason_code,
        comment=feedback.comment,
        is_verified=feedback.is_verified,
        is_eligible_for_retraining=feedback.is_eligible_for_retraining,
        created_at=feedback.created_at,
        feedback_sequence=1,
        is_conflicting=False,
    )


@router.get(
    "/{transaction_id}/feedback",
    response_model=List[FeedbackResponse],
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"description": "Historical feedback list for transaction"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid authentication"},
        status.HTTP_403_FORBIDDEN: {"description": "Insufficient permissions"},
        status.HTTP_404_NOT_FOUND: {"description": "Transaction not found"},
    },
    summary="List Transaction Feedback History",
    description=(
        "Lists the complete chronological adjudication history for a given transaction, "
        "demonstrating that prior submissions are preserved rather than overwritten."
    ),
)
def get_transaction_feedback_history(
    transaction_id: str,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> List[FeedbackResponse]:
    """Retrieves all feedback records for a transaction in chronological order."""
    tx = resolve_transaction(transaction_id, db)
    if tx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Transaction '{transaction_id}' not found.",
        )

    feedbacks_with_user = db.execute(
        select(OperatorFeedback, User.email)
        .join(User, User.id == OperatorFeedback.user_id)
        .where(OperatorFeedback.transaction_id == tx.id)
        .order_by(asc(OperatorFeedback.created_at), asc(OperatorFeedback.id))
    ).all()

    first_decision = feedbacks_with_user[0][0].decision if feedbacks_with_user else None
    result: List[FeedbackResponse] = []

    for idx, (fb, email) in enumerate(feedbacks_with_user, start=1):
        is_conflict = (first_decision is not None and fb.decision != first_decision)
        result.append(
            FeedbackResponse(
                id=fb.id,
                transaction_id=tx.id,
                external_id=tx.external_id,
                user_id=fb.user_id,
                operator_email=email,
                operator_username=email,
                decision=fb.decision,
                reason_code=fb.reason_code,
                comment=fb.comment,
                is_verified=fb.is_verified,
                is_eligible_for_retraining=fb.is_eligible_for_retraining,
                created_at=fb.created_at,
                feedback_sequence=idx,
                is_conflicting=is_conflict,
            )
        )

    return result
