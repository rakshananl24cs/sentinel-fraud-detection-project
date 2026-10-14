"""Automated integration tests for review queue and operator feedback adjudication APIs."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Dict, Tuple

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token, hash_password
from backend.app.db.session import get_session_factory
from backend.app.main import app
from backend.app.models.audit import AuditLog
from backend.app.models.feedback import OperatorFeedback
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


def create_test_user(
    db_session: Session,
    role: str = "OPERATOR",
    is_active: bool = True,
) -> Tuple[User, Dict[str, str]]:
    """Helper creating an isolated test user and corresponding Bearer authorization headers."""
    user = User(
        email=f"user_{role.lower()}_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash=hash_password("SecurePassword123!"),
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


def create_test_tx_and_prediction(
    db_session: Session,
    decision: str = "REVIEW",
    fraud_prob: float = 0.55,
    model_version: str = "xgb-cost-v1",
    minutes_ago: int = 0,
) -> Tuple[Transaction, Prediction]:
    """Helper creating an isolated test transaction and linked immutable prediction."""
    created_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    tx = Transaction(
        external_id=f"TX-TEST-{uuid.uuid4().hex[:10]}",
        amount=Decimal("199.95"),
        payload_json={"Amount": 199.95, "Time": 100.0},
        created_at=created_at,
    )
    db_session.add(tx)
    db_session.flush()

    pred = Prediction(
        transaction_id=tx.id,
        model_version=model_version,
        raw_probability=0.48,
        calibrated_probability=fraud_prob,
        risk_level="MEDIUM" if decision == "REVIEW" else ("HIGH" if decision == "BLOCK" else "LOW"),
        decision=decision,
        expected_cost=15.50,
        policy_parameters_json={"threshold_review": 0.40, "threshold_block": 0.85},
        explanation_json={"analyst_summary": "Top risk factor: anomalous transaction pattern detected"},
        created_at=created_at,
    )
    db_session.add(pred)
    db_session.commit()
    db_session.refresh(tx)
    db_session.refresh(pred)
    return tx, pred


# ==============================================================================
# 1. Review Queue Tests
# ==============================================================================

def test_review_queue_authorization(client: TestClient, db_session: Session):
    """Verifies authentication and role enforcement on GET /transactions/review-queue."""
    # 1. Unauthenticated request -> 401
    resp_unauth = client.get("/api/v1/transactions/review-queue")
    assert resp_unauth.status_code == status.HTTP_401_UNAUTHORIZED

    # 2. Inactive user -> 403
    _, headers_inactive = create_test_user(db_session, role="OPERATOR", is_active=False)
    resp_inactive = client.get("/api/v1/transactions/review-queue", headers=headers_inactive)
    assert resp_inactive.status_code == status.HTTP_403_FORBIDDEN

    # 3. Authorized roles (ANALYST, OPERATOR, ADMIN) -> 200
    for role in ("ANALYST", "OPERATOR", "ADMIN"):
        _, headers_valid = create_test_user(db_session, role=role, is_active=True)
        resp_valid = client.get("/api/v1/transactions/review-queue", headers=headers_valid)
        assert resp_valid.status_code == status.HTTP_200_OK
        data = resp_valid.json()
        assert "items" in data
        assert "total" in data
        assert "limit" in data
        assert "offset" in data


def test_review_queue_filtering_and_latest_prediction_rule(client: TestClient, db_session: Session):
    """Verifies review queue includes only transactions whose LATEST prediction is 'REVIEW'."""
    _, auth_headers = create_test_user(db_session, role="ANALYST")

    # Tx1: Only prediction is REVIEW -> must appear
    tx1, pred1 = create_test_tx_and_prediction(db_session, decision="REVIEW", fraud_prob=0.60, minutes_ago=10)

    # Tx2: Only prediction is APPROVE -> must NOT appear
    tx2, _ = create_test_tx_and_prediction(db_session, decision="APPROVE", fraud_prob=0.10, minutes_ago=10)

    # Tx3: Older prediction is REVIEW, but newer prediction is BLOCK -> must NOT appear
    tx3, _ = create_test_tx_and_prediction(db_session, decision="REVIEW", fraud_prob=0.55, minutes_ago=20)
    pred3_newer = Prediction(
        transaction_id=tx3.id,
        model_version="xgb-cost-v1",
        raw_probability=0.90,
        calibrated_probability=0.92,
        risk_level="HIGH",
        decision="BLOCK",
        expected_cost=80.0,
        policy_parameters_json={},
        explanation_json={"analyst_summary": "Re-scored as high-risk BLOCK"},
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.add(pred3_newer)
    db_session.commit()

    # Tx4: Older prediction is BLOCK, but newer prediction is REVIEW -> must appear
    tx4, _ = create_test_tx_and_prediction(db_session, decision="BLOCK", fraud_prob=0.88, minutes_ago=20)
    pred4_newer = Prediction(
        transaction_id=tx4.id,
        model_version="xgb-cost-v1",
        raw_probability=0.52,
        calibrated_probability=0.58,
        risk_level="MEDIUM",
        decision="REVIEW",
        expected_cost=22.0,
        policy_parameters_json={},
        explanation_json={"analyst_summary": "Re-scored as borderline REVIEW"},
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.add(pred4_newer)
    db_session.commit()

    resp = client.get("/api/v1/transactions/review-queue?limit=100", headers=auth_headers)
    assert resp.status_code == status.HTTP_200_OK
    queue_tx_ids = [item["external_id"] for item in resp.json()["items"]]

    assert tx1.external_id in queue_tx_ids
    assert tx2.external_id not in queue_tx_ids
    assert tx3.external_id not in queue_tx_ids  # Superseded by BLOCK
    assert tx4.external_id in queue_tx_ids      # Superseded by REVIEW


def test_review_queue_duplicate_prevention_on_multiple_predictions_and_feedback(
    client: TestClient,
    db_session: Session,
):
    """Verifies transactions with multiple REVIEW predictions and multiple feedback records appear exactly once."""
    user, auth_headers = create_test_user(db_session, role="OPERATOR")

    # Create Tx with two consecutive REVIEW predictions (e.g. scored by two models)
    tx, pred1 = create_test_tx_and_prediction(db_session, decision="REVIEW", fraud_prob=0.50, minutes_ago=30)
    pred2 = Prediction(
        transaction_id=tx.id,
        model_version="xgb-cost-v2",
        raw_probability=0.54,
        calibrated_probability=0.56,
        risk_level="MEDIUM",
        decision="REVIEW",
        expected_cost=18.0,
        policy_parameters_json={},
        explanation_json={"analyst_summary": "Secondary model also evaluated REVIEW"},
        created_at=datetime.now(timezone.utc) - timedelta(minutes=15),
    )
    db_session.add(pred2)

    # Add 2 feedback records to this transaction
    fb1 = OperatorFeedback(
        transaction_id=tx.id,
        user_id=user.id,
        decision="INCONCLUSIVE",
        is_verified=False,
        is_eligible_for_retraining=False,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    fb2 = OperatorFeedback(
        transaction_id=tx.id,
        user_id=user.id,
        decision="CONFIRMED_FRAUD",
        is_verified=False,
        is_eligible_for_retraining=False,
        created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
    )
    db_session.add_all([fb1, fb2])
    db_session.commit()

    resp = client.get("/api/v1/transactions/review-queue?limit=100", headers=auth_headers)
    assert resp.status_code == status.HTTP_200_OK
    items = resp.json()["items"]

    # Filter to our specific test transaction
    matching = [it for it in items if it["external_id"] == tx.external_id]
    assert len(matching) == 1, "Transaction must appear exactly once, preventing duplicate rows"
    item = matching[0]
    assert item["prediction_id"] == str(pred2.id), "Must reference the latest prediction"
    assert item["feedback_count"] == 2
    assert item["latest_feedback_decision"] == "CONFIRMED_FRAUD"


def test_review_queue_pagination_and_deterministic_ordering(client: TestClient, db_session: Session):
    """Verifies deterministic descending ordering and bounded pagination."""
    _, auth_headers = create_test_user(db_session, role="ANALYST")

    # Create 3 distinct review transactions spaced by time
    tx_a, _ = create_test_tx_and_prediction(db_session, decision="REVIEW", minutes_ago=30)
    tx_b, _ = create_test_tx_and_prediction(db_session, decision="REVIEW", minutes_ago=20)
    tx_c, _ = create_test_tx_and_prediction(db_session, decision="REVIEW", minutes_ago=10)

    # Page 1 (limit 2)
    resp_p1 = client.get("/api/v1/transactions/review-queue?limit=2&offset=0", headers=auth_headers)
    assert resp_p1.status_code == status.HTTP_200_OK
    data_p1 = resp_p1.json()
    assert len(data_p1["items"]) == 2
    assert data_p1["limit"] == 2
    assert data_p1["offset"] == 0

    # Newer transactions must precede older ones
    first_created = data_p1["items"][0]["prediction_created_at"]
    second_created = data_p1["items"][1]["prediction_created_at"]
    assert first_created >= second_created


def test_review_queue_status_filter_and_empty_results(client: TestClient, db_session: Session):
    """Verifies status_filter (PENDING vs REVIEWED) and safe empty queue response."""
    user, auth_headers = create_test_user(db_session, role="OPERATOR")

    tx_pending, _ = create_test_tx_and_prediction(db_session, decision="REVIEW", minutes_ago=5)
    tx_reviewed, _ = create_test_tx_and_prediction(db_session, decision="REVIEW", minutes_ago=5)

    # Add feedback to tx_reviewed only
    fb = OperatorFeedback(
        transaction_id=tx_reviewed.id,
        user_id=user.id,
        decision="CONFIRMED_GENUINE",
        is_verified=False,
        is_eligible_for_retraining=False,
    )
    db_session.add(fb)
    db_session.commit()

    # Filter PENDING
    resp_pending = client.get("/api/v1/transactions/review-queue?status_filter=PENDING", headers=auth_headers)
    assert resp_pending.status_code == status.HTTP_200_OK
    pending_ids = [it["external_id"] for it in resp_pending.json()["items"]]
    assert tx_pending.external_id in pending_ids
    assert tx_reviewed.external_id not in pending_ids

    # Filter REVIEWED
    resp_reviewed = client.get("/api/v1/transactions/review-queue?status_filter=REVIEWED", headers=auth_headers)
    assert resp_reviewed.status_code == status.HTTP_200_OK
    reviewed_ids = [it["external_id"] for it in resp_reviewed.json()["items"]]
    assert tx_reviewed.external_id in reviewed_ids
    assert tx_pending.external_id not in reviewed_ids

    # Impossible filter -> empty queue without error
    resp_empty = client.get("/api/v1/transactions/review-queue?min_probability=0.99999", headers=auth_headers)
    assert resp_empty.status_code == status.HTTP_200_OK
    assert resp_empty.json()["items"] == []
    assert resp_empty.json()["total"] == 0


# ==============================================================================
# 2. Feedback Adjudication Tests
# ==============================================================================

def test_feedback_submission_by_operator_unverified(client: TestClient, db_session: Session):
    """Verifies standard operator feedback submission defaults to unverified and retraining ineligible."""
    operator, auth_headers = create_test_user(db_session, role="OPERATOR")
    tx, _ = create_test_tx_and_prediction(db_session, decision="REVIEW")

    payload = {
        "decision": "CONFIRMED_FRAUD",
        "reason_code": "STOLEN_CARD",
        "comment": "Customer confirmed card was stolen via phone call.",
    }

    # Submit using internal UUID
    resp = client.post(f"/api/v1/transactions/{tx.id}/feedback", json=payload, headers=auth_headers)
    assert resp.status_code == status.HTTP_201_CREATED
    data = resp.json()

    assert data["transaction_id"] == str(tx.id)
    assert data["external_id"] == tx.external_id
    assert data["user_id"] == str(operator.id)
    assert data["decision"] == "CONFIRMED_FRAUD"
    assert data["reason_code"] == "STOLEN_CARD"
    assert data["comment"] == "Customer confirmed card was stolen via phone call."
    assert data["is_verified"] is False
    assert data["is_eligible_for_retraining"] is False
    assert data["feedback_sequence"] == 1
    assert data["is_conflicting"] is False


def test_feedback_submission_resolves_external_id(client: TestClient, db_session: Session):
    """Verifies feedback endpoint resolves target transaction using external_id string."""
    operator, auth_headers = create_test_user(db_session, role="OPERATOR")
    tx, _ = create_test_tx_and_prediction(db_session, decision="REVIEW")

    payload = {
        "decision": "CONFIRMED_GENUINE",
        "reason_code": "CUSTOMER_VERIFIED",
    }

    # Submit using external_id
    resp = client.post(f"/api/v1/transactions/{tx.external_id}/feedback", json=payload, headers=auth_headers)
    assert resp.status_code == status.HTTP_201_CREATED
    assert resp.json()["transaction_id"] == str(tx.id)
    assert resp.json()["decision"] == "CONFIRMED_GENUINE"


def test_feedback_rejects_client_controlled_retraining_eligibility(client: TestClient, db_session: Session):
    """Verifies client cannot pass is_eligible_for_retraining in the request payload."""
    _, auth_headers = create_test_user(db_session, role="OPERATOR")
    tx, _ = create_test_tx_and_prediction(db_session, decision="REVIEW")

    payload = {
        "decision": "CONFIRMED_FRAUD",
        "is_eligible_for_retraining": True,
    }
    resp = client.post(f"/api/v1/transactions/{tx.id}/feedback", json=payload, headers=auth_headers)
    assert resp.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_feedback_operator_forbidden_from_self_verifying(client: TestClient, db_session: Session):
    """Verifies non-admin operator cannot submit pre-verified feedback (403 Forbidden)."""
    _, auth_headers = create_test_user(db_session, role="OPERATOR")
    tx, _ = create_test_tx_and_prediction(db_session, decision="REVIEW")

    payload = {
        "decision": "CONFIRMED_FRAUD",
        "is_verified": True,
    }
    resp = client.post(f"/api/v1/transactions/{tx.id}/feedback", json=payload, headers=auth_headers)
    assert resp.status_code == status.HTTP_403_FORBIDDEN


def test_feedback_admin_verified_adjudication_eligibility_matrix(client: TestClient, db_session: Session):
    """Verifies Admin verified submissions enforce database retraining eligibility rules."""
    _, admin_headers = create_test_user(db_session, role="ADMIN")

    test_cases = [
        ("CONFIRMED_FRAUD", True, True),     # Verified Fraud -> Eligible
        ("CONFIRMED_GENUINE", True, True),   # Verified Genuine -> Eligible
        ("DISPUTED", True, False),           # Verified Disputed -> Ineligible (DB constraint)
        ("INCONCLUSIVE", True, False),       # Verified Inconclusive -> Ineligible (DB constraint)
        ("CONFIRMED_FRAUD", False, False),   # Unverified Fraud -> Ineligible
    ]

    for decision_label, submit_verified, expected_eligible in test_cases:
        tx, _ = create_test_tx_and_prediction(db_session, decision="REVIEW")
        payload = {
            "decision": decision_label,
            "is_verified": submit_verified,
            "reason_code": "TEST_CASE",
        }
        resp = client.post(f"/api/v1/transactions/{tx.id}/feedback", json=payload, headers=admin_headers)
        assert resp.status_code == status.HTTP_201_CREATED
        data = resp.json()
        assert data["decision"] == decision_label
        assert data["is_verified"] is submit_verified
        assert data["is_eligible_for_retraining"] is expected_eligible


def test_feedback_validation_rejections(client: TestClient, db_session: Session):
    """Verifies rejections for invalid decisions, unknown transactions, and un-predicted transactions."""
    _, auth_headers = create_test_user(db_session, role="OPERATOR")
    tx, _ = create_test_tx_and_prediction(db_session, decision="REVIEW")

    # 1. Invalid decision label -> 422
    resp_invalid_dec = client.post(
        f"/api/v1/transactions/{tx.id}/feedback",
        json={"decision": "APPROVE"},  # APPROVE is an engine output, not an operator label
        headers=auth_headers,
    )
    assert resp_invalid_dec.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 2. Non-existent transaction -> 404
    non_existent_uuid = str(uuid.uuid4())
    resp_not_found = client.post(
        f"/api/v1/transactions/{non_existent_uuid}/feedback",
        json={"decision": "CONFIRMED_FRAUD"},
        headers=auth_headers,
    )
    assert resp_not_found.status_code == status.HTTP_404_NOT_FOUND

    # 3. Transaction with no predictions -> 404
    orphan_tx = Transaction(
        external_id=f"TX-ORPHAN-{uuid.uuid4().hex[:6]}",
        amount=Decimal("50.00"),
        payload_json={"Amount": 50.00},
    )
    db_session.add(orphan_tx)
    db_session.commit()

    resp_orphan = client.post(
        f"/api/v1/transactions/{orphan_tx.id}/feedback",
        json={"decision": "CONFIRMED_FRAUD"},
        headers=auth_headers,
    )
    assert resp_orphan.status_code == status.HTTP_404_NOT_FOUND


def test_conflicting_feedback_appends_history(client: TestClient, db_session: Session):
    """Verifies repeated feedback creates append-only records and flags conflicts."""
    _, op1_headers = create_test_user(db_session, role="OPERATOR")
    _, op2_headers = create_test_user(db_session, role="ANALYST")
    tx, _ = create_test_tx_and_prediction(db_session, decision="REVIEW")

    # First submission: Genuine
    resp1 = client.post(
        f"/api/v1/transactions/{tx.id}/feedback",
        json={"decision": "CONFIRMED_GENUINE", "comment": "Operator 1 approved."},
        headers=op1_headers,
    )
    assert resp1.status_code == status.HTTP_201_CREATED
    assert resp1.json()["feedback_sequence"] == 1
    assert resp1.json()["is_conflicting"] is False

    # Second submission on same transaction: Fraud (Conflicting)
    resp2 = client.post(
        f"/api/v1/transactions/{tx.id}/feedback",
        json={"decision": "CONFIRMED_FRAUD", "comment": "Operator 2 found fraud evidence."},
        headers=op2_headers,
    )
    assert resp2.status_code == status.HTTP_201_CREATED
    assert resp2.json()["feedback_sequence"] == 2
    assert resp2.json()["is_conflicting"] is True

    # Check history endpoint GET /transactions/{tx_id}/feedback
    resp_hist = client.get(f"/api/v1/transactions/{tx.id}/feedback", headers=op1_headers)
    assert resp_hist.status_code == status.HTTP_200_OK
    history = resp_hist.json()
    assert len(history) == 2
    assert history[0]["decision"] == "CONFIRMED_GENUINE"
    assert history[1]["decision"] == "CONFIRMED_FRAUD"
    assert history[1]["is_conflicting"] is True


def test_explicit_admin_verification_workflow(client: TestClient, db_session: Session):
    """Verifies separate admin verification updates retraining eligibility and writes audit log."""
    _, operator_headers = create_test_user(db_session, role="OPERATOR")
    _, admin_headers = create_test_user(db_session, role="ADMIN")
    tx, _ = create_test_tx_and_prediction(db_session, decision="REVIEW")

    # Operator creates unverified CONFIRMED_FRAUD
    resp_create = client.post(
        f"/api/v1/transactions/{tx.id}/feedback",
        json={"decision": "CONFIRMED_FRAUD", "reason_code": "PHISHING"},
        headers=operator_headers,
    )
    assert resp_create.status_code == status.HTTP_201_CREATED
    fb_id = resp_create.json()["id"]
    assert resp_create.json()["is_verified"] is False
    assert resp_create.json()["is_eligible_for_retraining"] is False

    # Operator attempts to verify -> 403 Forbidden
    resp_op_verify = client.post(
        f"/api/v1/transactions/{tx.id}/feedback/{fb_id}/verify",
        headers=operator_headers,
    )
    assert resp_op_verify.status_code == status.HTTP_403_FORBIDDEN

    # Admin verifies -> 200 OK, becomes eligible
    resp_admin_verify = client.post(
        f"/api/v1/transactions/{tx.id}/feedback/{fb_id}/verify",
        headers=admin_headers,
    )
    assert resp_admin_verify.status_code == status.HTTP_200_OK
    data = resp_admin_verify.json()
    assert data["is_verified"] is True
    assert data["is_eligible_for_retraining"] is True


def test_feedback_audit_log_atomicity_and_redaction(client: TestClient, db_session: Session):
    """Verifies audit log entries are atomically created without exposing sensitive payloads."""
    operator, auth_headers = create_test_user(db_session, role="OPERATOR")
    tx, pred = create_test_tx_and_prediction(db_session, decision="REVIEW")

    resp = client.post(
        f"/api/v1/transactions/{tx.id}/feedback",
        json={"decision": "CONFIRMED_FRAUD", "reason_code": "ACCOUNT_TAKEOVER"},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED
    fb_id = resp.json()["id"]

    # Verify audit log in database
    audit = db_session.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "FEEDBACK",
            AuditLog.entity_id == fb_id,
        )
    ).scalar_one_or_none()

    assert audit is not None
    assert audit.action == "FEEDBACK_SUBMISSION"
    assert audit.user_id == operator.id
    meta = audit.metadata_json
    assert meta["transaction_id"] == str(tx.id)
    assert meta["prediction_id"] == str(pred.id)
    assert meta["decision"] == "CONFIRMED_FRAUD"
    # Ensure no secrets or transaction payload features were leaked in audit log
    assert "password" not in meta
    assert "token" not in meta
    assert "V1" not in meta
    assert "V28" not in meta


def test_prediction_ledger_immutability_maintained_during_feedback(
    client: TestClient,
    db_session: Session,
):
    """Verifies prediction trigger trg_predictions_immutable remains active and prevents updates."""
    _, auth_headers = create_test_user(db_session, role="OPERATOR")
    tx, pred = create_test_tx_and_prediction(db_session, decision="REVIEW")

    # Submit feedback
    resp = client.post(
        f"/api/v1/transactions/{tx.id}/feedback",
        json={"decision": "CONFIRMED_GENUINE"},
        headers=auth_headers,
    )
    assert resp.status_code == status.HTTP_201_CREATED

    # Attempting to update the prediction record in PostgreSQL must fail with immutability trigger
    with pytest.raises(DBAPIError) as exc_info:
        db_session.execute(
            text("UPDATE predictions SET decision = 'APPROVE' WHERE id = :pred_id"),
            {"pred_id": pred.id},
        )
        db_session.commit()
    db_session.rollback()

    assert "immutable" in str(exc_info.value).lower()
