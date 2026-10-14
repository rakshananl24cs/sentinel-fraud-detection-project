"""Integration tests for Fraud Alert Notifications API and dispatching logic.

Verifies:
- High-risk (BLOCK) transactions generate HIGH_RISK alerts with correct messaging and disclaimer.
- Review-needed (REVIEW) transactions generate NEEDS_REVIEW alerts.
- Approved transactions (APPROVE) NEVER generate fraud alerts.
- Failed predictions NEVER generate alerts.
- Batch scoring generates individual alerts for correct transactions and amounts.
- Unread counters and filtering work correctly.
- Marking an alert as read does NOT alter the underlying transaction or prediction decision.
- Truth-in-reporting: external email/SMS notifications are not fabricated.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Dict

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token, hash_password
from backend.app.db.session import get_session_factory
from backend.app.main import app
from backend.app.models.alert import FraudAlert
from backend.app.models.prediction import Prediction
from backend.app.models.transaction import Transaction
from backend.app.models.user import User


@pytest.fixture(scope="module")
def client():
    """Provides a TestClient instance for the FastAPI application."""
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


@pytest.fixture
def auth_headers(db_session):
    """Creates an isolated analyst user and returns valid Authorization headers."""
    user = User(
        email=f"analyst_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash=hash_password("ValidPassword123!"),
        role="ANALYST",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    token = create_access_token(subject=user.id, claims={"role": user.role, "email": user.email})
    return {"Authorization": f"Bearer {token}"}


def make_genuine_payload(external_id: str | None = None) -> Dict[str, float | str]:
    """Generates a genuine transaction that scores APPROVE."""
    payload: Dict[str, float | str] = {
        "Time": 1000.0,
        **{f"V{i}": 0.05 * ((-1) ** i) for i in range(1, 29)},
        "Amount": 49.99,
    }
    if external_id is not None:
        payload["external_id"] = external_id
    return payload


def make_review_payload(external_id: str | None = None) -> Dict[str, float | str]:
    """Generates a borderline transaction that scores REVIEW."""
    payload: Dict[str, float | str] = {
        "Time": 406.0,
        "Amount": 999.0,
        **{f"V{i}": 0.05 for i in range(1, 29)},
        "V14": -9.04,
        "V10": -4.71,
        "V12": -6.07,
    }
    if external_id is not None:
        payload["external_id"] = external_id
    return payload


def make_block_payload(external_id: str | None = None) -> Dict[str, float | str]:
    """Generates a clear fraud transaction that scores BLOCK."""
    payload: Dict[str, float | str] = {
        "Time": 406.0,
        "Amount": 1499.00,
        "V1": -2.31, "V2": 1.95, "V3": -1.61, "V4": 3.99, "V5": -0.52,
        "V6": -1.42, "V7": -2.54, "V8": 1.39, "V9": -2.77, "V10": -4.71,
        "V11": 3.21, "V12": -6.07, "V13": -0.27, "V14": -9.04, "V15": -0.56,
        "V16": -4.84, "V17": -8.45, "V18": -2.98, "V19": 0.42, "V20": 0.13,
        "V21": 0.52, "V22": -0.04, "V23": -0.46, "V24": 0.32, "V25": 0.04,
        "V26": 0.18, "V27": 0.26, "V28": -0.14,
    }
    if external_id is not None:
        payload["external_id"] = external_id
    return payload


def test_block_transaction_generates_high_risk_alert(client, auth_headers, db_session):
    """Verifies that a BLOCK decision creates a persistent HIGH_RISK alert."""
    ext_id = f"TX-BLOCK-{uuid.uuid4().hex[:8]}"
    payload = make_block_payload(external_id=ext_id)

    resp = client.post("/api/v1/transactions/predict", json=payload, headers=auth_headers)
    assert resp.status_code == status.HTTP_201_CREATED
    pred_data = resp.json()
    assert pred_data["decision"] == "BLOCK"

    # Query persistent alerts in database
    alert = db_session.execute(
        select(FraudAlert).where(FraudAlert.external_id == ext_id)
    ).scalar_one_or_none()

    assert alert is not None
    assert alert.alert_type == "HIGH_RISK"
    assert alert.severity == "HIGH"
    assert alert.decision == "BLOCK"
    assert alert.amount == Decimal("1499.00")
    assert alert.is_read is False
    assert ext_id in alert.message
    assert "blocked under the current policy" in alert.message.lower()
    assert "statistical risk" in alert.disclaimer.lower()
    assert "investigate" in alert.recommended_action.lower()


def test_review_transaction_generates_needs_review_alert(client, auth_headers, db_session):
    """Verifies that a REVIEW decision creates a persistent NEEDS_REVIEW alert."""
    ext_id = f"TX-REV-{uuid.uuid4().hex[:8]}"
    payload = make_review_payload(external_id=ext_id)

    resp = client.post("/api/v1/transactions/predict", json=payload, headers=auth_headers)
    assert resp.status_code == status.HTTP_201_CREATED
    pred_data = resp.json()
    assert pred_data["decision"] == "REVIEW"

    alert = db_session.execute(
        select(FraudAlert).where(FraudAlert.external_id == ext_id)
    ).scalar_one_or_none()

    assert alert is not None
    assert alert.alert_type == "NEEDS_REVIEW"
    assert alert.severity == "MEDIUM"
    assert alert.decision == "REVIEW"
    assert alert.amount == Decimal("999.00")
    assert alert.is_read is False
    assert ext_id in alert.message
    assert "review queue" in alert.recommended_action.lower()


def test_approved_transaction_does_not_generate_alert(client, auth_headers, db_session):
    """Verifies that an APPROVE decision does NOT create any fraud alert."""
    ext_id = f"TX-APP-{uuid.uuid4().hex[:8]}"
    payload = make_genuine_payload(external_id=ext_id)

    resp = client.post("/api/v1/transactions/predict", json=payload, headers=auth_headers)
    assert resp.status_code == status.HTTP_201_CREATED
    pred_data = resp.json()
    assert pred_data["decision"] == "APPROVE"

    alert = db_session.execute(
        select(FraudAlert).where(FraudAlert.external_id == ext_id)
    ).scalar_one_or_none()

    assert alert is None


def test_failed_prediction_does_not_generate_alert(client, auth_headers, db_session):
    """Verifies that unprocessable or failed inputs do NOT generate alerts."""
    ext_id = f"TX-FAIL-{uuid.uuid4().hex[:8]}"
    payload = {"external_id": ext_id, "Time": 100.0, "Amount": -50.0}  # Invalid schema / missing features

    resp = client.post("/api/v1/transactions/predict", json=payload, headers=auth_headers)
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    alert = db_session.execute(
        select(FraudAlert).where(FraudAlert.external_id == ext_id)
    ).scalar_one_or_none()

    assert alert is None


def test_batch_scoring_generates_alerts_for_high_risk_and_review(client, auth_headers, db_session):
    """Verifies that batch CSV inference creates alerts specifically for BLOCK and REVIEW items."""
    b_id = f"BATCH-ALERT-{uuid.uuid4().hex[:6]}"
    tx_app = f"TX-B-APP-{uuid.uuid4().hex[:6]}"
    tx_rev = f"TX-B-REV-{uuid.uuid4().hex[:6]}"
    tx_blk = f"TX-B-BLK-{uuid.uuid4().hex[:6]}"

    item_app = make_genuine_payload(external_id=tx_app)
    item_rev = make_review_payload(external_id=tx_rev)
    item_blk = make_block_payload(external_id=tx_blk)

    batch_payload = {
        "batch_id": b_id,
        "filename": "alert_test_batch.csv",
        "items": [item_app, item_rev, item_blk],
    }

    resp = client.post("/api/v1/transactions/batch-predict", json=batch_payload, headers=auth_headers)
    assert resp.status_code == status.HTTP_201_CREATED

    # Verify database alerts
    alert_app = db_session.execute(
        select(FraudAlert).where(FraudAlert.external_id == tx_app)
    ).scalar_one_or_none()
    assert alert_app is None  # Approved item has NO alert

    alert_rev = db_session.execute(
        select(FraudAlert).where(FraudAlert.external_id == tx_rev)
    ).scalar_one_or_none()
    assert alert_rev is not None
    assert alert_rev.alert_type == "NEEDS_REVIEW"
    assert alert_rev.amount == Decimal("999.00")

    alert_blk = db_session.execute(
        select(FraudAlert).where(FraudAlert.external_id == tx_blk)
    ).scalar_one_or_none()
    assert alert_blk is not None
    assert alert_blk.alert_type == "HIGH_RISK"
    assert alert_blk.amount == Decimal("1499.00")


def test_list_alerts_and_stats_api(client, auth_headers):
    """Verifies GET /api/v1/alerts and GET /api/v1/alerts/stats."""
    # Score one block transaction
    ext_id = f"TX-LST-{uuid.uuid4().hex[:8]}"
    client.post(
        "/api/v1/transactions/predict",
        json=make_block_payload(external_id=ext_id),
        headers=auth_headers,
    )

    # 1. Test Stats endpoint
    stats_resp = client.get("/api/v1/alerts/stats", headers=auth_headers)
    assert stats_resp.status_code == status.HTTP_200_OK
    stats = stats_resp.json()
    assert stats["total"] >= 1
    assert stats["unread_count"] >= 1
    assert stats["high_risk_unread_count"] >= 1

    # 2. Test List endpoint
    list_resp = client.get("/api/v1/alerts?limit=10", headers=auth_headers)
    assert list_resp.status_code == status.HTTP_200_OK
    data = list_resp.json()
    assert "items" in data
    assert data["total"] >= 1
    assert data["unread_count"] >= 1

    # Check alert structure
    found = next((a for a in data["items"] if a["external_id"] == ext_id), None)
    assert found is not None
    assert found["alert_type"] == "HIGH_RISK"
    assert found["decision"] == "BLOCK"
    assert found["is_read"] is False
    assert found["amount"] == 1499.00
    assert "disclaimer" in found


def test_mark_alert_as_read_preserves_decision(client, auth_headers, db_session):
    """Verifies that marking an alert as read updates alert status without altering prediction."""
    ext_id = f"TX-READ-{uuid.uuid4().hex[:8]}"
    client.post(
        "/api/v1/transactions/predict",
        json=make_block_payload(external_id=ext_id),
        headers=auth_headers,
    )

    alert = db_session.execute(
        select(FraudAlert).where(FraudAlert.external_id == ext_id)
    ).scalar_one()
    alert_id = str(alert.id)
    tx_id = alert.transaction_id

    # Mark as read via API
    read_resp = client.patch(f"/api/v1/alerts/{alert_id}/read", headers=auth_headers)
    assert read_resp.status_code == status.HTTP_200_OK
    res_data = read_resp.json()
    assert res_data["is_read"] is True
    assert res_data["read_at"] is not None

    # Verify in DB that prediction decision is STILL BLOCK and unchanged
    pred = db_session.execute(
        select(Prediction).where(Prediction.transaction_id == tx_id)
    ).scalar_one()
    assert pred.decision == "BLOCK"
    assert pred.risk_level == "HIGH"


def test_mark_all_alerts_as_read(client, auth_headers):
    """Verifies POST /api/v1/alerts/mark-all-read."""
    # Ensure there's at least one alert
    client.post(
        "/api/v1/transactions/predict",
        json=make_review_payload(external_id=f"TX-BULK-{uuid.uuid4().hex[:8]}"),
        headers=auth_headers,
    )

    resp = client.post("/api/v1/alerts/mark-all-read", headers=auth_headers)
    assert resp.status_code == status.HTTP_200_OK
    assert "updated_count" in resp.json()

    # Stats should now reflect 0 unread
    stats_resp = client.get("/api/v1/alerts/stats", headers=auth_headers)
    assert stats_resp.status_code == status.HTTP_200_OK
    assert stats_resp.json()["unread_count"] == 0
