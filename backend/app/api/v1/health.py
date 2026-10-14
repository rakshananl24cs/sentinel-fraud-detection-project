"""Health check and dependency verification endpoints."""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.session import get_db
from backend.app.schemas.health import (
    HealthLiveResponse,
    HealthReadyResponse,
    HealthUnhealthyResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])


@router.get(
    "/live",
    response_model=HealthLiveResponse,
    status_code=status.HTTP_200_OK,
    summary="Liveness Probe",
    description="Reports whether the application process is running without querying dependencies.",
)
def check_liveness() -> HealthLiveResponse:
    """Returns basic process liveness status."""
    return HealthLiveResponse()


@router.get(
    "/ready",
    response_model=HealthReadyResponse,
    responses={
        status.HTTP_200_OK: {"model": HealthReadyResponse},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"model": HealthUnhealthyResponse},
    },
    summary="Readiness Probe",
    description="Validates PostgreSQL database connectivity via a minimal query.",
)
def check_readiness(
    response: Response,
    db: Session = Depends(get_db),
) -> HealthReadyResponse | HealthUnhealthyResponse:
    """Verifies database connectivity without leaking infrastructure details."""
    try:
        result = db.execute(text("SELECT 1")).scalar()
        if result == 1:
            return HealthReadyResponse()
        
        logger.error("Readiness check received unexpected result from database probe.")
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthUnhealthyResponse()
    except Exception as exc:
        logger.error("Database connectivity check failed during readiness probe: %s", type(exc).__name__)
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return HealthUnhealthyResponse()
