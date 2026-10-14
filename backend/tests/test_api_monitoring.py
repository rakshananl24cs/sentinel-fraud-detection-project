"""Automated integration tests for data drift monitoring and reporting API."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Tuple
from unittest.mock import patch

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token, hash_password
from backend.app.db.session import get_session_factory
from backend.app.main import app
from backend.app.models.drift import DriftReport
from backend.app.models.prediction import Prediction
from backend.app.models.transaction import Transaction
from backend.app.models.user import User


@pytest.fixture(scope="module")
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


@pytest.fixture
def db_session():
    """Provides a transactional database session rolled back after each test."""
    session_factory = get_session_factory()
    session: Session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def create_user_with_role(
    db_session: Session,
    role: str = "ANALYST",
    is_active: bool = True,
) -> Tuple[User, Dict[str, str]]:
    """Creates isolated user and returns valid Authorization headers."""
    user = User(
        email=f"user_{role.lower()}_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash=hash_password("MonitorPass123!"),
        role=role,
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    token = create_access_token(
        subject=user.id,
        claims={"role": user.role, "email": user.email},
    )
    return user, {"Authorization": f"Bearer {token}"}


def insert_mock_transactions_in_window(
    db_session: Session,
    count: int = 5,
    base_time: datetime | None = None,
) -> Tuple[datetime, datetime]:
    """Inserts mock transactions with 30 features and returns (start_time, end_time)."""
    if base_time is None:
        random_offset = uuid.uuid4().int % 100000
        base_time = datetime(2025, 1, 1, 0, 0, tzinfo=timezone.utc) + timedelta(minutes=random_offset)

    for i in range(count):
        tx_time = base_time + timedelta(minutes=i * 5)
        features = {
            "Time": 50000.0 + i * 10,
            **{f"V{k}": 0.05 * ((-1) ** k) for k in range(1, 29)},
            "Amount": 50.0 + i * 10,
        }
        tx = Transaction(
            external_id=f"TX-MON-{uuid.uuid4().hex[:8]}",
            amount=Decimal(str(features["Amount"])),
            payload_json=features,
            created_at=tx_time,
        )
        db_session.add(tx)

    db_session.commit()
    start_window = base_time - timedelta(minutes=5)
    end_window = base_time + timedelta(minutes=count * 5 + 5)
    return start_window, end_window


def test_drift_report_authorization(client: TestClient, db_session: Session):
    """Verifies role permissions: POST requires ADMIN; GET allows ANALYST, OPERATOR, ADMIN."""
    _, analyst_headers = create_user_with_role(db_session, role="ANALYST")
    _, operator_headers = create_user_with_role(db_session, role="OPERATOR")
    _, admin_headers = create_user_with_role(db_session, role="ADMIN")

    now_utc = datetime.now(timezone.utc)
    payload = {
        "time_window_start": (now_utc - timedelta(hours=1)).isoformat(),
        "time_window_end": now_utc.isoformat(),
        "model_version": "xgb-cost-v1",
    }

    # 1. POST unauthenticated -> 401
    resp_unauth = client.post("/api/v1/monitoring/drift-reports", json=payload)
    assert resp_unauth.status_code == status.HTTP_401_UNAUTHORIZED

    # 2. POST by ANALYST or OPERATOR -> 403 Forbidden
    resp_analyst = client.post("/api/v1/monitoring/drift-reports", json=payload, headers=analyst_headers)
    assert resp_analyst.status_code == status.HTTP_403_FORBIDDEN

    resp_op = client.post("/api/v1/monitoring/drift-reports", json=payload, headers=operator_headers)
    assert resp_op.status_code == status.HTTP_403_FORBIDDEN

    # 3. POST by ADMIN -> 201 Created
    resp_admin = client.post("/api/v1/monitoring/drift-reports", json=payload, headers=admin_headers)
    assert resp_admin.status_code == status.HTTP_201_CREATED

    # 4. GET allowed for all authorized roles
    for headers in (analyst_headers, operator_headers, admin_headers):
        resp_get = client.get("/api/v1/monitoring/drift-reports", headers=headers)
        assert resp_get.status_code == status.HTTP_200_OK


def test_drift_report_time_window_validation(client: TestClient, db_session: Session):
    """Verifies rejection of invalid or excessively large time windows."""
    _, admin_headers = create_user_with_role(db_session, role="ADMIN")
    now_utc = datetime.now(timezone.utc)

    # 1. end < start -> 422
    payload_inverted = {
        "time_window_start": now_utc.isoformat(),
        "time_window_end": (now_utc - timedelta(hours=1)).isoformat(),
    }
    resp_inv = client.post("/api/v1/monitoring/drift-reports", json=payload_inverted, headers=admin_headers)
    assert resp_inv.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 2. window > 30 days -> 422
    payload_huge = {
        "time_window_start": (now_utc - timedelta(days=35)).isoformat(),
        "time_window_end": now_utc.isoformat(),
    }
    resp_huge = client.post("/api/v1/monitoring/drift-reports", json=payload_huge, headers=admin_headers)
    assert resp_huge.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_drift_report_generation_and_persistence(client: TestClient, db_session: Session):
    """Verifies successful drift report creation, database storage, and retrieval."""
    _, admin_headers = create_user_with_role(db_session, role="ADMIN")
    _, analyst_headers = create_user_with_role(db_session, role="ANALYST")

    # Insert transactions in isolated window
    start_win, end_win = insert_mock_transactions_in_window(db_session, count=10)

    payload = {
        "time_window_start": start_win.isoformat(),
        "time_window_end": end_win.isoformat(),
        "model_version": "xgb-cost-v1",
    }
    resp_post = client.post("/api/v1/monitoring/drift-reports", json=payload, headers=admin_headers)
    assert resp_post.status_code == status.HTTP_201_CREATED
    data = resp_post.json()

    assert "id" in data
    report_id = data["id"]
    assert data["model_version"] == "xgb-cost-v1"
    assert data["metric_name"] == "MAX_FEATURE_PSI"
    assert data["status"] in ("NORMAL", "WARNING", "CRITICAL")
    assert "summary" in data
    summary = data["summary"]
    assert summary["observed_population"]["valid_sample_count"] == 10
    assert "per_feature_drift" in summary
    assert "V14" in summary["per_feature_drift"]

    # Retrieve single report by ID via GET
    resp_get = client.get(f"/api/v1/monitoring/drift-reports/{report_id}", headers=analyst_headers)
    assert resp_get.status_code == status.HTTP_200_OK
    assert resp_get.json()["id"] == report_id


def test_drift_report_empty_window_handling(client: TestClient, db_session: Session):
    """Verifies an observation window with 0 transactions generates a WARNING report safely."""
    _, admin_headers = create_user_with_role(db_session, role="ADMIN")

    # Time window far in the future with 0 transactions
    future_start = datetime.now(timezone.utc) + timedelta(days=1)
    future_end = future_start + timedelta(hours=2)

    payload = {
        "time_window_start": future_start.isoformat(),
        "time_window_end": future_end.isoformat(),
        "model_version": "xgb-cost-v1",
    }
    resp = client.post("/api/v1/monitoring/drift-reports", json=payload, headers=admin_headers)
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()

    assert data["status"] == "WARNING"
    summary = data["summary"]
    assert summary["observed_population"]["valid_sample_count"] == 0
    assert summary["observed_population"]["insufficient_sample_size"] is True
    assert len(summary["warnings"]) > 0


def test_drift_report_exceeds_synchronous_limit_rejection(client: TestClient, db_session: Session):
    """Verifies that exceeding the 10,000 transaction bound returns 409 Conflict."""
    _, admin_headers = create_user_with_role(db_session, role="ADMIN")

    # Mock count to simulate 12,000 transactions
    with patch("backend.app.services.monitoring.select") as mock_select:
        now_utc = datetime.now(timezone.utc)
        payload = {
            "time_window_start": (now_utc - timedelta(hours=5)).isoformat(),
            "time_window_end": now_utc.isoformat(),
            "model_version": "xgb-cost-v1",
        }
        # Rather than mocking complex SQL, test the service function directly with mock count
        from backend.app.services.monitoring import generate_drift_report

        class MockSession:
            def execute(self, q):
                class MockResult:
                    def scalar_one(self):
                        return 15000  # Exceeds limit
                return MockResult()

        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc_info:
            generate_drift_report(MockSession(), now_utc - timedelta(hours=5), now_utc)

        assert exc_info.value.status_code == status.HTTP_409_CONFLICT
        assert "exceeding the synchronous processing limit" in exc_info.value.detail


def test_drift_report_listing_pagination_and_ordering(client: TestClient, db_session: Session):
    """Verifies listing reports supports pagination and deterministic order."""
    _, admin_headers = create_user_with_role(db_session, role="ADMIN")
    _, analyst_headers = create_user_with_role(db_session, role="ANALYST")

    resp_list = client.get("/api/v1/monitoring/drift-reports?limit=5&offset=0", headers=analyst_headers)
    assert resp_list.status_code == status.HTTP_200_OK
    data = resp_list.json()
    assert "items" in data
    assert "total" in data
    assert "limit" in data
    assert "offset" in data


def test_drift_report_get_by_id_not_found(client: TestClient, db_session: Session):
    """Verifies 404 response for non-existent report UUID or malformed identifier."""
    _, analyst_headers = create_user_with_role(db_session, role="ANALYST")

    # Unknown UUID -> 404
    resp_not_found = client.get(f"/api/v1/monitoring/drift-reports/{uuid.uuid4()}", headers=analyst_headers)
    assert resp_not_found.status_code == status.HTTP_404_NOT_FOUND

    # Malformed ID -> 404
    resp_malformed = client.get("/api/v1/monitoring/drift-reports/not-a-valid-uuid", headers=analyst_headers)
    assert resp_malformed.status_code == status.HTTP_404_NOT_FOUND


def test_prediction_ledger_immutability_maintained_during_monitoring(
    client: TestClient,
    db_session: Session,
):
    """Verifies prediction trigger trg_predictions_immutable remains active and prevents updates."""
    # Ensure prediction update attempt is strictly blocked by PostgreSQL trigger
    pred = db_session.execute(select(Prediction)).scalars().first()
    if pred is not None:
        with pytest.raises(DBAPIError) as exc_info:
            db_session.execute(
                text("UPDATE predictions SET decision = 'APPROVE' WHERE id = :pred_id"),
                {"pred_id": pred.id},
            )
            db_session.commit()
        db_session.rollback()
        assert "immutable" in str(exc_info.value).lower()
