"""Automated verification suite for SQLAlchemy 2.0 ORM models and PostgreSQL persistence.

Tests schema structure, table creation, foreign keys, check constraints,
append-only prediction histories, operator feedback workflows, retraining eligibility,
and audit logging against the PostgreSQL database.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError, ProgrammingError
from sqlalchemy.orm import Session

from backend.app.db.session import get_engine, get_session_factory
from backend.app.models import (
    AuditLog,
    Base,
    DriftReport,
    ModelRegistry,
    OperatorFeedback,
    Prediction,
    Transaction,
    User,
)
from ml.src.models.inference import predict_fraud


@pytest.fixture(scope="session")
def engine():
    """Provides the shared SQLAlchemy engine."""
    return get_engine()


@pytest.fixture
def db_session(engine):
    """Provides a transactional database session rolled back after each test."""
    session_factory = get_session_factory()
    session: Session = session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def test_schema_tables_exist(engine):
    """Verifies that all 7 application tables plus alembic_version exist in PostgreSQL."""
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    expected_tables = {
        "alembic_version",
        "users",
        "transactions",
        "predictions",
        "operator_feedback",
        "audit_logs",
        "model_registry",
        "drift_reports",
    }
    assert expected_tables.issubset(set(table_names)), (
        f"Missing expected tables: {expected_tables - set(table_names)}"
    )


def test_user_creation_and_role_constraint(db_session):
    """Verifies User creation, UUID generation, timestamps, and role check constraint."""
    user = User(
        email=f"analyst_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash="mock_bcrypt_hash_placeholder",
        role="OPERATOR",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    assert user.id is not None
    assert isinstance(user.id, uuid.UUID)
    assert user.created_at is not None
    assert user.created_at.tzinfo is not None

    # Test invalid role fails check constraint
    invalid_user = User(
        email=f"invalid_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash="hash",
        role="SUPERUSER",  # Invalid, only ADMIN, OPERATOR, ANALYST allowed
    )
    db_session.add(invalid_user)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_transaction_creation_and_uniqueness(db_session):
    """Verifies Transaction persistence and external_id uniqueness constraint."""
    ext_id = f"TX-{uuid.uuid4().hex[:12]}"
    tx_payload = {"Time": 100.0, **{f"V{i}": 0.05 for i in range(1, 29)}, "Amount": 149.50}

    tx = Transaction(
        external_id=ext_id,
        amount=Decimal("149.50"),
        payload_json=tx_payload,
    )
    db_session.add(tx)
    db_session.commit()

    assert tx.id is not None
    assert tx.amount == Decimal("149.50")
    assert tx.payload_json["Amount"] == 149.50

    # Duplicate external_id must fail
    duplicate_tx = Transaction(
        external_id=ext_id,
        amount=Decimal("20.00"),
        payload_json=tx_payload,
    )
    db_session.add(duplicate_tx)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_prediction_append_only_history(db_session):
    """Verifies that multiple predictions can be appended to a single transaction."""
    ext_id = f"TX-{uuid.uuid4().hex[:12]}"
    raw_payload = {"Time": 500.0, **{f"V{i}": 0.0 for i in range(1, 29)}, "Amount": 85.00}

    tx = Transaction(
        external_id=ext_id,
        amount=Decimal("85.00"),
        payload_json=raw_payload,
    )
    db_session.add(tx)
    db_session.commit()

    # Generate real inference output using canonical predict_fraud()
    ml_result = predict_fraud(raw_payload)

    # 1. First prediction (production model)
    pred_1 = Prediction(
        transaction_id=tx.id,
        model_version=ml_result["model_version"],
        raw_probability=ml_result["raw_probability"],
        calibrated_probability=ml_result["fraud_probability"],
        risk_level=ml_result["risk_level"],
        decision=ml_result["decision"],
        expected_cost=ml_result["expected_cost"],
        policy_parameters_json=ml_result["policy_parameters"],
        explanation_json=ml_result["explanation"],
    )
    db_session.add(pred_1)
    db_session.commit()

    # 2. Second prediction for the same transaction (e.g. candidate model evaluation)
    pred_2 = Prediction(
        transaction_id=tx.id,
        model_version="xgb-cost-v2-candidate",
        raw_probability=0.015,
        calibrated_probability=0.012,
        risk_level="LOW",
        decision="APPROVE",
        expected_cost=1.20,
        policy_parameters_json={"threshold_review": 0.05, "status": "candidate"},
        explanation_json={"top_contributions": []},
    )
    db_session.add(pred_2)
    db_session.commit()

    # Query transaction predictions relationship
    db_session.refresh(tx)
    assert len(tx.predictions) == 2
    assert {p.model_version for p in tx.predictions} == {"xgb-cost-v1", "xgb-cost-v2-candidate"}


def test_prediction_check_constraints(db_session):
    """Verifies range and category check constraints on predictions."""
    ext_id = f"TX-{uuid.uuid4().hex[:12]}"
    tx = Transaction(
        external_id=ext_id,
        amount=Decimal("10.00"),
        payload_json={"Time": 0.0},
    )
    db_session.add(tx)
    db_session.commit()

    # Invalid calibrated_probability (> 1.0)
    invalid_pred = Prediction(
        transaction_id=tx.id,
        model_version="xgb-cost-v1",
        raw_probability=0.5,
        calibrated_probability=1.5,  # Out of range!
        risk_level="HIGH",
        decision="BLOCK",
        expected_cost=50.0,
        policy_parameters_json={},
        explanation_json={},
    )
    db_session.add(invalid_pred)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Invalid decision ('HOLD' instead of APPROVE, REVIEW, BLOCK)
    invalid_decision_pred = Prediction(
        transaction_id=tx.id,
        model_version="xgb-cost-v1",
        raw_probability=0.2,
        calibrated_probability=0.2,
        risk_level="MEDIUM",
        decision="HOLD",  # Invalid!
        expected_cost=10.0,
        policy_parameters_json={},
        explanation_json={},
    )
    db_session.add(invalid_decision_pred)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_operator_feedback_and_retraining_eligibility(db_session):
    """Verifies OperatorFeedback creation, check constraints, and retraining eligibility logic."""
    # Create operator user and transaction
    user = User(
        email=f"op_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash="secret_hash",
        role="OPERATOR",
    )
    tx = Transaction(
        external_id=f"TX-{uuid.uuid4().hex[:12]}",
        amount=Decimal("500.00"),
        payload_json={"Time": 1.0},
    )
    db_session.add_all([user, tx])
    db_session.commit()

    # Verified fraud -> eligible for retraining
    feedback = OperatorFeedback(
        transaction_id=tx.id,
        user_id=user.id,
        decision="CONFIRMED_FRAUD",
        reason_code="STOLEN_CARD",
        comment="Confirmed with cardholder via phone.",
        is_verified=True,
        is_eligible_for_retraining=OperatorFeedback.compute_retraining_eligibility("CONFIRMED_FRAUD", True),
    )
    db_session.add(feedback)
    db_session.commit()

    assert feedback.id is not None
    assert feedback.is_eligible_for_retraining is True

    # Test retraining logic helper:
    # 1. Unverified feedback cannot qualify for retraining
    assert OperatorFeedback.compute_retraining_eligibility("CONFIRMED_FRAUD", is_verified=False) is False
    # 2. Inconclusive or disputed cannot qualify for retraining
    assert OperatorFeedback.compute_retraining_eligibility("INCONCLUSIVE", is_verified=True) is False
    assert OperatorFeedback.compute_retraining_eligibility("DISPUTED", is_verified=True) is False
    # 3. Verified genuine qualifies
    assert OperatorFeedback.compute_retraining_eligibility("CONFIRMED_GENUINE", is_verified=True) is True

    # Database-enforced check constraint tests for retraining eligibility:
    # A. Unverified feedback with is_eligible_for_retraining=True must be REJECTED by PostgreSQL
    invalid_unverified = OperatorFeedback(
        transaction_id=tx.id,
        user_id=user.id,
        decision="CONFIRMED_FRAUD",
        is_verified=False,
        is_eligible_for_retraining=True,  # Disallowed by ck_feedback_retraining_eligibility
    )
    db_session.add(invalid_unverified)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # B. Disputed feedback with is_eligible_for_retraining=True must be REJECTED by PostgreSQL
    invalid_disputed = OperatorFeedback(
        transaction_id=tx.id,
        user_id=user.id,
        decision="DISPUTED",
        is_verified=True,
        is_eligible_for_retraining=True,  # Disallowed by ck_feedback_retraining_eligibility
    )
    db_session.add(invalid_disputed)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # C. Inconclusive feedback with is_eligible_for_retraining=True must be REJECTED by PostgreSQL
    invalid_inconclusive = OperatorFeedback(
        transaction_id=tx.id,
        user_id=user.id,
        decision="INCONCLUSIVE",
        is_verified=True,
        is_eligible_for_retraining=True,  # Disallowed by ck_feedback_retraining_eligibility
    )
    db_session.add(invalid_inconclusive)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # D. Valid unverified/disputed with is_eligible_for_retraining=False is ACCEPTED
    valid_disputed = OperatorFeedback(
        transaction_id=tx.id,
        user_id=user.id,
        decision="DISPUTED",
        is_verified=False,
        is_eligible_for_retraining=False,
    )
    db_session.add(valid_disputed)
    db_session.commit()
    assert valid_disputed.id is not None

    # Test invalid decision check constraint
    invalid_feedback = OperatorFeedback(
        transaction_id=tx.id,
        user_id=user.id,
        decision="MAYBE_FRAUD",  # Invalid
        is_verified=False,
        is_eligible_for_retraining=False,
    )
    db_session.add(invalid_feedback)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_audit_log_creation(db_session):
    """Verifies AuditLog records with system or user attribution and entity constraints."""
    user = User(
        email=f"auditor_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash="secret_hash",
        role="ADMIN",
    )
    db_session.add(user)
    db_session.commit()

    # User action audit log
    log1 = AuditLog(
        user_id=user.id,
        action="OPERATOR_OVERRIDE",
        entity_type="FEEDBACK",
        entity_id="FB-1001",
        metadata_json={"previous_status": "REVIEW", "new_status": "CONFIRMED_FRAUD"},
    )
    # System automated audit log (user_id is None)
    log2 = AuditLog(
        user_id=None,
        action="AUTOMATED_BATCH_INFERENCE",
        entity_type="SYSTEM",
        entity_id="BATCH-2026-10",
        metadata_json={"processed_count": 500, "flagged_count": 3},
    )
    db_session.add_all([log1, log2])
    db_session.commit()

    assert log1.id is not None
    assert log2.id is not None
    assert log2.user_id is None

    # Invalid entity_type
    invalid_log = AuditLog(
        action="TEST_ACTION",
        entity_type="UNKNOWN_ENTITY",  # Invalid
        metadata_json={},
    )
    db_session.add(invalid_log)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_model_registry_and_drift_report(db_session):
    """Verifies ModelRegistry version uniqueness and DriftReport persistence."""
    version = f"xgb-cost-v{uuid.uuid4().hex[:6]}"
    now = datetime.now(timezone.utc)

    reg = ModelRegistry(
        version=version,
        architecture="XGBClassifier + IsotonicCalibrator",
        artifact_path=r"ml\models\xgboost_baseline.joblib",
        hyperparameters_json={"n_estimators": 300, "max_depth": 6, "learning_rate": 0.05},
        metrics_json={"brier_score": 0.000288, "pr_auc": 0.8479, "expected_cost": 1095.0},
        lifecycle_status="ACTIVE",
        trained_at=now,
    )
    db_session.add(reg)
    db_session.commit()

    assert reg.id is not None
    assert reg.lifecycle_status == "ACTIVE"

    # Duplicate version must fail
    dup_reg = ModelRegistry(
        version=version,
        architecture="Another Arch",
        artifact_path="dummy",
        hyperparameters_json={},
        metrics_json={},
        lifecycle_status="CANDIDATE",
        trained_at=now,
    )
    db_session.add(dup_reg)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # Drift report
    drift = DriftReport(
        model_version=version,
        metric_name="PSI",
        metric_value=0.0125,
        status="NORMAL",
        time_window_start=now,
        time_window_end=now,
        summary_json={"feature_shifts": {"V1": 0.002, "V2": 0.001}},
    )
    db_session.add(drift)
    db_session.commit()

    assert drift.id is not None
    assert drift.status == "NORMAL"

    # Invalid time window (end < start) must be rejected by PostgreSQL ck_drift_reports_time_window
    invalid_drift = DriftReport(
        model_version=version,
        metric_name="PSI",
        metric_value=0.05,
        status="NORMAL",
        time_window_start=now,
        time_window_end=now - timedelta(days=1),  # Invalid: end < start!
        summary_json={},
    )
    db_session.add(invalid_drift)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_prediction_ledger_immutability(db_session):
    """Verifies that predictions are strictly immutable: insert allowed, update/delete rejected."""
    tx = Transaction(
        external_id=f"TX-{uuid.uuid4().hex[:12]}",
        amount=Decimal("120.00"),
        payload_json={"Time": 2.0},
    )
    db_session.add(tx)
    db_session.commit()

    # 1. New predictions can be inserted
    pred = Prediction(
        transaction_id=tx.id,
        model_version="xgb-cost-v1",
        raw_probability=0.35,
        calibrated_probability=0.30,
        risk_level="MEDIUM",
        decision="REVIEW",
        expected_cost=7.50,
        policy_parameters_json={"threshold_review": 0.042},
        explanation_json={"top_contributions": []},
    )
    db_session.add(pred)
    db_session.commit()
    assert pred.id is not None

    # 2. Updating a prediction must be REJECTED by PostgreSQL trigger
    with pytest.raises((ProgrammingError, DBAPIError)):
        db_session.execute(
            text("UPDATE predictions SET decision = 'BLOCK' WHERE id = :id"),
            {"id": pred.id},
        )
        db_session.commit()
    db_session.rollback()

    # 3. Deleting a prediction must be REJECTED by PostgreSQL trigger
    with pytest.raises((ProgrammingError, DBAPIError)):
        db_session.execute(
            text("DELETE FROM predictions WHERE id = :id"),
            {"id": pred.id},
        )
        db_session.commit()
    db_session.rollback()

    # 4. Deleting the parent transaction must be REJECTED by ON DELETE RESTRICT
    with pytest.raises(IntegrityError):
        db_session.execute(
            text("DELETE FROM transactions WHERE id = :id"),
            {"id": tx.id},
        )
        db_session.commit()
    db_session.rollback()


def test_foreign_key_delete_restrictions(db_session):
    """Verifies that user delete is restricted by feedback, and transaction delete without predictions succeeds."""
    user = User(
        email=f"restrict_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash="hash",
        role="OPERATOR",
    )
    tx = Transaction(
        external_id=f"TX-{uuid.uuid4().hex[:12]}",
        amount=Decimal("45.00"),
        payload_json={"Time": 3.0},
    )
    db_session.add_all([user, tx])
    db_session.commit()

    fb = OperatorFeedback(
        transaction_id=tx.id,
        user_id=user.id,
        decision="CONFIRMED_GENUINE",
        is_verified=True,
        is_eligible_for_retraining=True,
    )
    db_session.add(fb)
    db_session.commit()

    # 1. Deleting user must fail due to RESTRICT on OperatorFeedback.user_id
    db_session.delete(user)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    # 2. Transaction without predictions can be deleted (cascades to feedback)
    tx_to_del = db_session.execute(select(Transaction).where(Transaction.id == tx.id)).scalar_one()
    db_session.delete(tx_to_del)
    db_session.commit()

    fb_remaining = db_session.execute(select(OperatorFeedback).where(OperatorFeedback.id == fb.id)).scalar_one_or_none()
    assert fb_remaining is None
