"""Fraud Alert notification endpoints."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select, update
from sqlalchemy.orm import Session

from backend.app.api.deps import require_role
from backend.app.db.session import get_db
from backend.app.models.alert import FraudAlert
from backend.app.models.user import User
from backend.app.schemas.alert import (
    AlertItemResponse,
    AlertListResponse,
    AlertStatsResponse,
    MarkAlertsReadResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/alerts", tags=["Fraud Alerts & Notifications"])


@router.get(
    "",
    response_model=AlertListResponse,
    status_code=status.HTTP_200_OK,
    summary="List Fraud Alerts",
    description="Returns a paginated list of persistent fraud alerts with unread counters.",
)
def list_alerts(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    unread_only: bool = Query(default=False),
    alert_type: Optional[str] = Query(default=None, pattern="^(HIGH_RISK|NEEDS_REVIEW)$"),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> AlertListResponse:
    """Retrieves fraud alert notifications with pagination and filtering."""
    base_query = select(FraudAlert)

    if unread_only:
        base_query = base_query.where(FraudAlert.is_read.is_(False))

    if alert_type:
        base_query = base_query.where(FraudAlert.alert_type == alert_type)

    total = db.execute(select(func.count()).select_from(base_query.subquery())).scalar_one() or 0

    alerts = db.execute(
        base_query.order_by(desc(FraudAlert.created_at), desc(FraudAlert.id))
        .limit(limit)
        .offset(offset)
    ).scalars().all()

    # Aggregate counters
    unread_total = db.execute(
        select(func.count(FraudAlert.id)).where(FraudAlert.is_read.is_(False))
    ).scalar_one() or 0

    high_risk_unread = db.execute(
        select(func.count(FraudAlert.id)).where(
            FraudAlert.is_read.is_(False),
            FraudAlert.alert_type == "HIGH_RISK",
        )
    ).scalar_one() or 0

    review_needed_unread = db.execute(
        select(func.count(FraudAlert.id)).where(
            FraudAlert.is_read.is_(False),
            FraudAlert.alert_type == "NEEDS_REVIEW",
        )
    ).scalar_one() or 0

    items = [
        AlertItemResponse(
            id=a.id,
            transaction_id=a.transaction_id,
            external_id=a.external_id,
            prediction_id=a.prediction_id,
            alert_type=a.alert_type,
            severity=a.severity,
            decision=a.decision,
            fraud_probability=float(a.fraud_probability),
            amount=float(a.amount),
            title=a.title,
            message=a.message,
            recommended_action=a.recommended_action,
            disclaimer=a.disclaimer,
            is_read=a.is_read,
            read_at=a.read_at,
            created_at=a.created_at,
        )
        for a in alerts
    ]

    return AlertListResponse(
        items=items,
        total=total,
        unread_count=int(unread_total),
        high_risk_unread_count=int(high_risk_unread),
        review_needed_unread_count=int(review_needed_unread),
        limit=limit,
        offset=offset,
    )


@router.get(
    "/stats",
    response_model=AlertStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Fraud Alert Counters",
    description="Returns aggregate total and unread alert counts for notification badge display.",
)
def get_alert_stats(
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> AlertStatsResponse:
    """Computes summary alert statistics for header badge indicators."""
    total = db.execute(select(func.count(FraudAlert.id))).scalar_one() or 0

    unread = db.execute(
        select(func.count(FraudAlert.id)).where(FraudAlert.is_read.is_(False))
    ).scalar_one() or 0

    high_risk_unread = db.execute(
        select(func.count(FraudAlert.id)).where(
            FraudAlert.is_read.is_(False),
            FraudAlert.alert_type == "HIGH_RISK",
        )
    ).scalar_one() or 0

    review_needed_unread = db.execute(
        select(func.count(FraudAlert.id)).where(
            FraudAlert.is_read.is_(False),
            FraudAlert.alert_type == "NEEDS_REVIEW",
        )
    ).scalar_one() or 0

    return AlertStatsResponse(
        total=int(total),
        unread_count=int(unread),
        high_risk_unread_count=int(high_risk_unread),
        review_needed_unread_count=int(review_needed_unread),
    )


@router.get(
    "/{alert_id}",
    response_model=AlertItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Fraud Alert Details",
)
def get_alert(
    alert_id: uuid.UUID,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> AlertItemResponse:
    """Retrieves a single alert record by ID."""
    alert = db.execute(
        select(FraudAlert).where(FraudAlert.id == alert_id)
    ).scalar_one_or_none()

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' was not found.",
        )

    return AlertItemResponse(
        id=alert.id,
        transaction_id=alert.transaction_id,
        external_id=alert.external_id,
        prediction_id=alert.prediction_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        decision=alert.decision,
        fraud_probability=float(alert.fraud_probability),
        amount=float(alert.amount),
        title=alert.title,
        message=alert.message,
        recommended_action=alert.recommended_action,
        disclaimer=alert.disclaimer,
        is_read=alert.is_read,
        read_at=alert.read_at,
        created_at=alert.created_at,
    )


@router.patch(
    "/{alert_id}/read",
    response_model=AlertItemResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark Alert as Read",
)
def mark_alert_as_read(
    alert_id: uuid.UUID,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> AlertItemResponse:
    """Marks an alert notification as read.

    NOTE: Does NOT alter the underlying transaction or prediction record.
    """
    alert = db.execute(
        select(FraudAlert).where(FraudAlert.id == alert_id)
    ).scalar_one_or_none()

    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Alert '{alert_id}' was not found.",
        )

    if not alert.is_read:
        alert.is_read = True
        alert.read_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(alert)

    return AlertItemResponse(
        id=alert.id,
        transaction_id=alert.transaction_id,
        external_id=alert.external_id,
        prediction_id=alert.prediction_id,
        alert_type=alert.alert_type,
        severity=alert.severity,
        decision=alert.decision,
        fraud_probability=float(alert.fraud_probability),
        amount=float(alert.amount),
        title=alert.title,
        message=alert.message,
        recommended_action=alert.recommended_action,
        disclaimer=alert.disclaimer,
        is_read=alert.is_read,
        read_at=alert.read_at,
        created_at=alert.created_at,
    )


@router.post(
    "/mark-all-read",
    response_model=MarkAlertsReadResponse,
    status_code=status.HTTP_200_OK,
    summary="Mark All Alerts as Read",
)
def mark_all_alerts_as_read(
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> MarkAlertsReadResponse:
    """Marks all currently unread alerts as read in bulk."""
    now_utc = datetime.now(timezone.utc)
    result = db.execute(
        update(FraudAlert)
        .where(FraudAlert.is_read.is_(False))
        .values(is_read=True, read_at=now_utc)
    )
    db.commit()
    updated_count = result.rowcount or 0

    return MarkAlertsReadResponse(
        message="All alerts marked as read successfully.",
        updated_count=int(updated_count),
    )
