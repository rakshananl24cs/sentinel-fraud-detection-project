"""FastAPI endpoints for data drift monitoring and batch reporting."""

from __future__ import annotations

import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.api.deps import require_role
from backend.app.db.session import get_db
from backend.app.models.drift import DriftReport
from backend.app.models.user import User
from backend.app.schemas.monitoring import (
    DriftReportCreateRequest,
    DriftReportListResponse,
    DriftReportResponse,
)
from backend.app.services.monitoring import generate_drift_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/monitoring", tags=["Monitoring & Drift Detection"])


def to_drift_response(entity: DriftReport) -> DriftReportResponse:
    """Helper converting DriftReport ORM model to Pydantic response."""
    return DriftReportResponse(
        id=entity.id,
        model_version=entity.model_version,
        metric_name=entity.metric_name,
        metric_value=entity.metric_value,
        status=entity.status,
        time_window_start=entity.time_window_start,
        time_window_end=entity.time_window_end,
        created_at=entity.created_at,
        summary=entity.summary_json,
    )


@router.post(
    "/drift-reports",
    response_model=DriftReportResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_201_CREATED: {"model": DriftReportResponse, "description": "Drift report successfully computed and stored"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid authentication"},
        status.HTTP_403_FORBIDDEN: {"description": "Administrator role required to generate drift reports"},
        status.HTTP_409_CONFLICT: {"description": "Window exceeds synchronous processing limit"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Invalid time window parameters"},
    },
    summary="Generate Data Drift Report",
    description=(
        "Executes two-sample Kolmogorov-Smirnov (KS) tests and Population Stability Index (PSI) "
        "evaluations on transactions within the validated time window against reference training "
        "distributions. Atomically records results in the drift_reports table. Restricted to ADMIN."
    ),
)
def create_drift_report(
    payload: DriftReportCreateRequest,
    current_user: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
) -> DriftReportResponse:
    """Generates and persists a reproducible drift monitoring report for an observation window."""
    report_entity = generate_drift_report(
        db=db,
        time_window_start=payload.time_window_start,
        time_window_end=payload.time_window_end,
        model_version=payload.model_version,
    )
    return to_drift_response(report_entity)


@router.get(
    "/drift-reports",
    response_model=DriftReportListResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"model": DriftReportListResponse, "description": "List of drift reports"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid authentication"},
        status.HTTP_403_FORBIDDEN: {"description": "Insufficient permissions"},
    },
    summary="List Historical Drift Reports",
    description=(
        "Retrieves a paginated list of historical drift evaluation reports with deterministic "
        "chronological ordering. Accessible by ADMIN, OPERATOR, and ANALYST."
    ),
)
def list_drift_reports(
    limit: int = Query(default=20, ge=1, le=100, description="Page size limit (1 to 100)"),
    offset: int = Query(default=0, ge=0, description="Pagination offset"),
    status_filter: Optional[str] = Query(
        default=None,
        regex="^(NORMAL|WARNING|CRITICAL)$",
        description="Filter by drift status tier (NORMAL, WARNING, or CRITICAL)",
    ),
    model_version: Optional[str] = Query(
        default=None,
        description="Filter by ML model version (e.g. 'xgb-cost-v1')",
    ),
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> DriftReportListResponse:
    """Lists drift monitoring reports with bounded pagination and deterministic ordering."""
    base_query = select(DriftReport)

    if status_filter:
        base_query = base_query.where(DriftReport.status == status_filter)
    if model_version:
        base_query = base_query.where(DriftReport.model_version == model_version)

    # Compute total matching count
    count_query = select(func.count()).select_from(base_query.order_by(None).subquery())
    total = db.execute(count_query).scalar_one()

    # Deterministic descending ordering
    items_query = base_query.order_by(
        desc(DriftReport.created_at),
        desc(DriftReport.id),
    ).limit(limit).offset(offset)

    rows = db.execute(items_query).scalars().all()
    items = [to_drift_response(row) for row in rows]

    return DriftReportListResponse(
        items=items,
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/drift-reports/{report_id}",
    response_model=DriftReportResponse,
    status_code=status.HTTP_200_OK,
    responses={
        status.HTTP_200_OK: {"model": DriftReportResponse, "description": "Drift report details"},
        status.HTTP_401_UNAUTHORIZED: {"description": "Missing or invalid authentication"},
        status.HTTP_403_FORBIDDEN: {"description": "Insufficient permissions"},
        status.HTTP_404_NOT_FOUND: {"description": "Drift report not found"},
    },
    summary="Get Drift Report by ID",
    description="Retrieves a specific drift report by its unique UUID identifier.",
)
def get_drift_report(
    report_id: str,
    current_user: User = Depends(require_role(["ADMIN", "OPERATOR", "ANALYST"])),
    db: Session = Depends(get_db),
) -> DriftReportResponse:
    """Retrieves a single drift monitoring report by UUID."""
    try:
        report_uuid = uuid.UUID(report_id)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drift report '{report_id}' not found.",
        )

    entity = db.execute(
        select(DriftReport).where(DriftReport.id == report_uuid)
    ).scalar_one_or_none()

    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Drift report '{report_id}' not found.",
        )

    return to_drift_response(entity)
