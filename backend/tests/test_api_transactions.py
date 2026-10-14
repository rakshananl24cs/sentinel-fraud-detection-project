"""Integration tests for transaction ingestion and synchronous fraud scoring API."""

from __future__ import annotations

import math
import uuid
from decimal import Decimal
from typing import Dict

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, ProgrammingError
from sqlalchemy.orm import Session

from backend.app.core.security import create_access_token, hash_password
from backend.app.db.session import get_session_factory
from backend.app.main import app
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


def make_valid_payload(external_id: str | None = None) -> Dict[str, float | str]:
    """Generates a valid 30-feature transaction payload."""
    payload: Dict[str, float | str] = {
        "Time": 1000.0,
        **{f"V{i}": 0.05 * ((-1) ** i) for i in range(1, 29)},
        "Amount": 149.99,
    }
    if external_id is not None:
        payload["external_id"] = external_id
    return payload


def test_predict_valid_authenticated_request(client, auth_headers, db_session):
    """Verifies that a valid transaction request is scored, persisted, and returns 201 Created."""
    ext_id = f"TX-VALID-{uuid.uuid4().hex[:10]}"
    payload = make_valid_payload(external_id=ext_id)

    response = client.post(
        "/api/v1/transactions/predict",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()

    # Validate response schema and fields
    assert data["transaction_id"] == ext_id
    assert data["external_id"] == ext_id
    assert data["model_version"] == "xgb-cost-v1"
    assert data["decision"] in ["APPROVE", "REVIEW", "BLOCK"]
    assert data["risk_level"] in ["LOW", "MEDIUM", "HIGH"]
    assert 0.0 <= data["fraud_probability"] <= 1.0
    assert 0.0 <= data["raw_probability"] <= 1.0
    assert data["expected_cost"] >= 0.0
    assert "policy_parameters" in data
    assert "explanation" in data
    assert "top_contributions" in data["explanation"]
    assert "prediction_id" in data

    # Verify atomic database persistence
    tx_db = db_session.execute(
        select(Transaction).where(Transaction.external_id == ext_id)
    ).scalar_one_or_none()
    assert tx_db is not None
    assert tx_db.amount == Decimal("149.99")
    assert tx_db.payload_json["Amount"] == 149.99

    pred_db = db_session.execute(
        select(Prediction).where(Prediction.transaction_id == tx_db.id)
    ).scalar_one_or_none()
    assert pred_db is not None
    assert str(pred_db.id) == data["prediction_id"]
    assert pred_db.decision == data["decision"]


def test_predict_missing_and_invalid_authentication(client):
    """Verifies that missing or invalid authentication headers return 401 Unauthorized."""
    payload = make_valid_payload()

    # 1. Missing header
    res1 = client.post("/api/v1/transactions/predict", json=payload)
    assert res1.status_code == status.HTTP_401_UNAUTHORIZED

    # 2. Invalid bearer token
    res2 = client.post(
        "/api/v1/transactions/predict",
        json=payload,
        headers={"Authorization": "Bearer invalid.malformed.token"},
    )
    assert res2.status_code == status.HTTP_401_UNAUTHORIZED


def test_predict_insufficient_role(client, db_session):
    """Verifies that an inactive user or unauthorized account returns 403 Forbidden."""
    inactive_user = User(
        email=f"inactive_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash=hash_password("Pass123!"),
        role="ANALYST",
        is_active=False,
    )
    db_session.add(inactive_user)
    db_session.commit()

    token = create_access_token(subject=inactive_user.id, claims={"role": inactive_user.role})
    response = client.post(
        "/api/v1/transactions/predict",
        json=make_valid_payload(),
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN


def test_predict_validation_rejections(client, auth_headers):
    """Verifies that missing, extra, non-finite, and invalid fields are rejected with 422."""
    valid = make_valid_payload()

    # 1. Missing required feature 'Time'
    missing_time = {k: v for k, v in valid.items() if k != "Time"}
    res_missing = client.post("/api/v1/transactions/predict", json=missing_time, headers=auth_headers)
    assert res_missing.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 2. Extra forbidden field
    extra_field = {**valid, "merchant_category": "retail"}
    res_extra = client.post("/api/v1/transactions/predict", json=extra_field, headers=auth_headers)
    assert res_extra.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 3. Non-numeric value
    bad_type = {**valid, "V1": "invalid_string"}
    res_bad_type = client.post("/api/v1/transactions/predict", json=bad_type, headers=auth_headers)
    assert res_bad_type.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    # 4. Negative amount
    negative_amt = {**valid, "Amount": -10.0}
    res_neg = client.post("/api/v1/transactions/predict", json=negative_amt, headers=auth_headers)
    assert res_neg.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_predict_explicit_rejection_of_class(client, auth_headers):
    """Verifies that any request supplying the target 'Class' label is rejected with 422."""
    payload_with_class_1 = {**make_valid_payload(), "Class": 1}
    res1 = client.post("/api/v1/transactions/predict", json=payload_with_class_1, headers=auth_headers)
    assert res1.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "class" in str(res1.json()).lower()

    payload_with_class_0 = {**make_valid_payload(), "Class": 0}
    res2 = client.post("/api/v1/transactions/predict", json=payload_with_class_0, headers=auth_headers)
    assert res2.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "class" in str(res2.json()).lower()


def test_predict_duplicate_transaction_identifier(client, auth_headers):
    """Verifies that attempting to score an existing transaction ID returns 409 Conflict."""
    dup_id = f"TX-DUP-{uuid.uuid4().hex[:10]}"
    payload = make_valid_payload(external_id=dup_id)

    # First request: 201 Created
    res1 = client.post("/api/v1/transactions/predict", json=payload, headers=auth_headers)
    assert res1.status_code == status.HTTP_201_CREATED

    # Second request with duplicate external_id: 409 Conflict
    res2 = client.post("/api/v1/transactions/predict", json=payload, headers=auth_headers)
    assert res2.status_code == status.HTTP_409_CONFLICT
    assert dup_id in res2.json()["detail"]


def test_predict_atomic_rollback_on_prediction_failure(client, auth_headers, db_session, monkeypatch):
    """Verifies atomic rollback: if prediction persistence fails, the transaction is not saved."""
    unique_ext_id = f"TX-FAIL-{uuid.uuid4().hex[:10]}"
    payload = make_valid_payload(external_id=unique_ext_id)

    # Monkeypatch Prediction __init__ to raise an exception simulating persistence failure
    original_init = Prediction.__init__

    def faulty_init(self, *args, **kwargs):
        raise RuntimeError("Simulated prediction entity failure")

    monkeypatch.setattr(Prediction, "__init__", faulty_init)

    response = client.post(
        "/api/v1/transactions/predict",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # Confirm Transaction was NOT committed (no orphaned transaction)
    tx_check = db_session.execute(
        select(Transaction).where(Transaction.external_id == unique_ext_id)
    ).scalar_one_or_none()
    assert tx_check is None


def test_predict_preserves_prediction_ledger_immutability(client, auth_headers, db_session):
    """Verifies that predictions created via the API remain strictly immutable."""
    ext_id = f"TX-IMMUTABLE-{uuid.uuid4().hex[:10]}"
    payload = make_valid_payload(external_id=ext_id)

    res = client.post("/api/v1/transactions/predict", json=payload, headers=auth_headers)
    assert res.status_code == status.HTTP_201_CREATED
    pred_id = uuid.UUID(res.json()["prediction_id"])

    # Attempt direct SQL UPDATE on the API-created prediction -> must be blocked by trigger
    with pytest.raises((ProgrammingError, DBAPIError)):
        db_session.execute(
            text("UPDATE predictions SET decision = 'BLOCK' WHERE id = :id"),
            {"id": pred_id},
        )
        db_session.commit()
    db_session.rollback()

    # Attempt direct SQL DELETE on the API-created prediction -> must be blocked by trigger
    with pytest.raises((ProgrammingError, DBAPIError)):
        db_session.execute(
            text("DELETE FROM predictions WHERE id = :id"),
            {"id": pred_id},
        )
        db_session.commit()
    db_session.rollback()


def test_predict_inference_failure_handling(client, auth_headers, db_session, monkeypatch):
    """Verifies that ML inference failures return appropriate error responses without leaving orphan records."""
    import backend.app.api.v1.transactions as tx_module
    from ml.src.models.inference import InferenceError

    # 1. Simulate InferenceError
    def failing_inference_err(payload):
        raise InferenceError("Feature matrix transformation failed")

    monkeypatch.setattr(tx_module, "predict_fraud", failing_inference_err)

    bad_id = f"TX-INF-ERR-{uuid.uuid4().hex[:8]}"
    res1 = client.post(
        "/api/v1/transactions/predict",
        json=make_valid_payload(external_id=bad_id),
        headers=auth_headers,
    )
    assert res1.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert "Inference validation error" in res1.json()["detail"]

    # 2. Simulate generic unexpected ML failure
    def failing_generic_err(payload):
        raise RuntimeError("Model binary corrupted")

    monkeypatch.setattr(tx_module, "predict_fraud", failing_generic_err)

    bad_id_2 = f"TX-GEN-ERR-{uuid.uuid4().hex[:8]}"
    res2 = client.post(
        "/api/v1/transactions/predict",
        json=make_valid_payload(external_id=bad_id_2),
        headers=auth_headers,
    )
    assert res2.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # Confirm no transaction rows were stored
    for check_id in [bad_id, bad_id_2]:
        tx_check = db_session.execute(
            select(Transaction).where(Transaction.external_id == check_id)
        ).scalar_one_or_none()
        assert tx_check is None


def test_predict_openapi_contract(client):
    """Verifies that the /transactions/predict endpoint is documented in the OpenAPI specification."""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == status.HTTP_200_OK
    schema = response.json()
    assert "/api/v1/transactions/predict" in schema["paths"]
    predict_op = schema["paths"]["/api/v1/transactions/predict"]["post"]
    assert "201" in predict_op["responses"]
    assert "409" in predict_op["responses"]
    assert "422" in predict_op["responses"]


def test_batch_predict_success(client, auth_headers, db_session):
    """Verifies batch scoring of multiple transactions, audit logging, and latest batch retrieval."""
    batch_id = f"BATCH-TEST-{uuid.uuid4().hex[:8]}"
    items = [
        make_valid_payload(external_id=f"TX-B1-{i}")
        for i in range(3)
    ]
    batch_payload = {
        "batch_id": batch_id,
        "filename": "test_batch.csv",
        "items": items,
    }

    response = client.post(
        "/api/v1/transactions/batch-predict",
        json=batch_payload,
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert "summary" in data
    assert "items" in data
    assert data["summary"]["batch_id"] == batch_id
    assert data["summary"]["total_submitted"] == 3
    assert data["summary"]["total_processed"] == 3
    assert len(data["items"]) == 3

    # Check persistence of audit log
    from backend.app.models.audit import AuditLog
    audit = db_session.execute(
        select(AuditLog).where(AuditLog.action == "BATCH_CSV_ANALYSIS", AuditLog.entity_id == batch_id)
    ).scalar_one_or_none()
    assert audit is not None
    assert audit.metadata_json["total_processed"] == 3

    # Retrieve latest batch
    latest_res = client.get("/api/v1/transactions/batches/latest", headers=auth_headers)
    assert latest_res.status_code == status.HTTP_200_OK
    latest_data = latest_res.json()
    assert latest_data["summary"]["batch_id"] == batch_id
    assert len(latest_data["items"]) == 3

    # Check operational stats
    stats_res = client.get("/api/v1/transactions/operational-stats", headers=auth_headers)
    assert stats_res.status_code == status.HTTP_200_OK
    stats = stats_res.json()
    assert stats["total_transactions"] >= 3

    # Check recent transactions
    recent_res = client.get("/api/v1/transactions/recent?limit=5", headers=auth_headers)
    assert recent_res.status_code == status.HTTP_200_OK
    recent_items = recent_res.json()["items"]
    assert len(recent_items) > 0


def test_batch_predict_with_class_column_ignored(client, auth_headers):
    """Verifies that an uploaded batch containing a ground-truth 'Class' column does not fail."""
    items = [
        {**make_valid_payload(external_id=f"TX-CLASS-{i}"), "Class": i % 2}
        for i in range(2)
    ]
    batch_payload = {
        "filename": "labeled_eval.csv",
        "items": items,
    }

    response = client.post(
        "/api/v1/transactions/batch-predict",
        json=batch_payload,
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    assert data["summary"]["total_processed"] == 2
    for item in data["items"]:
        assert item["decision"] in ("APPROVE", "REVIEW", "BLOCK")


def test_batch_predict_valid_csv_mixed_decisions(client, auth_headers, db_session):
    """Verifies batch scoring of valid transactions with distinct decision outcomes and DB persistence."""
    batch_id = f"BATCH-VALID-{uuid.uuid4().hex[:8]}"
    genuine_item = {
        "external_id": f"TX-GEN-{uuid.uuid4().hex[:6]}",
        "Time": 406.0,
        "Amount": 29.50,
        **{f"V{i}": 0.05 for i in range(1, 29)},
    }
    fraud_item = {
        "external_id": f"TX-FRD-{uuid.uuid4().hex[:6]}",
        "Time": 406.0,
        "Amount": 999.00,
        "V1": -2.31, "V2": 1.95, "V3": -1.61, "V4": 3.99, "V5": -0.52,
        "V6": -1.42, "V7": -2.54, "V8": 1.39, "V9": -2.77, "V10": -4.71,
        "V11": 3.21, "V12": -6.07, "V13": -0.27, "V14": -9.04, "V15": -0.56,
        "V16": -4.84, "V17": -8.45, "V18": -2.98, "V19": 0.42, "V20": 0.13,
        "V21": 0.52, "V22": -0.04, "V23": -0.46, "V24": 0.32, "V25": 0.04,
        "V26": 0.18, "V27": 0.26, "V28": -0.14,
    }

    batch_payload = {
        "batch_id": batch_id,
        "filename": "valid_scoring_batch.csv",
        "items": [genuine_item, fraud_item],
    }

    response = client.post(
        "/api/v1/transactions/batch-predict",
        json=batch_payload,
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    summary = data["summary"]
    items = data["items"]

    assert summary["total_submitted"] == 2
    assert summary["total_processed"] == 2
    assert summary["failed_count"] == 0
    assert len(items) == 2
    for item in items:
        assert item["status"] == "SUCCESS"
        assert item["error"] is None
        assert item["decision"] in ("APPROVE", "REVIEW", "BLOCK")
        assert item["fraud_probability"] is not None


def test_batch_predict_missing_features_validation_rejection(client, auth_headers):
    """Verifies that batch submissions with missing required feature columns are rejected with 422."""
    valid_item = make_valid_payload()
    # Missing V14
    missing_v14 = {k: v for k, v in valid_item.items() if k != "V14"}
    # Missing Time
    missing_time = {k: v for k, v in valid_item.items() if k != "Time"}

    batch_payload = {
        "filename": "missing_features.csv",
        "items": [missing_v14, missing_time],
    }

    response = client.post(
        "/api/v1/transactions/batch-predict",
        json=batch_payload,
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    err_body = str(response.json())
    assert "v14" in err_body.lower() or "time" in err_body.lower() or "missing" in err_body.lower()


def test_batch_predict_malformed_csv_input_rejection(client, auth_headers):
    """Verifies that batch submissions with non-numeric or negative values are rejected with 422."""
    valid_item = make_valid_payload()
    bad_amount = {**valid_item, "Amount": -99.99}

    batch_payload = {
        "filename": "malformed_values.csv",
        "items": [bad_amount],
    }

    response = client.post(
        "/api/v1/transactions/batch-predict",
        json=batch_payload,
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_batch_predict_all_rows_fail(client, auth_headers, monkeypatch):
    """Verifies that when all rows fail inference, the batch does not crash, reports 0 processed, and returns row errors."""
    import backend.app.api.v1.transactions as tx_module
    from ml.src.models.inference import InferenceError

    def failing_inference(scoring_input):
        raise InferenceError("Feature matrix calibration failure")

    monkeypatch.setattr(tx_module, "predict_fraud", failing_inference)

    items = [make_valid_payload(external_id=f"TX-ALLFAIL-{i}") for i in range(3)]
    batch_payload = {
        "batch_id": f"BATCH-FAIL-{uuid.uuid4().hex[:6]}",
        "filename": "all_fail.csv",
        "items": items,
    }

    response = client.post(
        "/api/v1/transactions/batch-predict",
        json=batch_payload,
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    summary = data["summary"]
    items_res = data["items"]

    assert summary["total_submitted"] == 3
    assert summary["total_processed"] == 0
    assert summary["failed_count"] == 3
    assert len(items_res) == 3

    for idx, item in enumerate(items_res):
        assert item["status"] == "ERROR"
        assert item["decision"] == "FAILED"
        assert item["risk_level"] == "UNKNOWN"
        assert item["fraud_probability"] is None
        assert f"Row {idx + 1}" in item["error"]
        assert "Feature matrix calibration failure" in item["error"]


def test_batch_predict_mixed_success_and_failure(client, auth_headers, monkeypatch, db_session):
    """Verifies that in a batch with mixed valid and failing rows, valid rows are scored and persisted while failed rows are reported."""
    import backend.app.api.v1.transactions as tx_module
    from ml.src.models.inference import InferenceError

    original_predict = tx_module.predict_fraud

    def selective_inference(scoring_input):
        tx_id = scoring_input.get("transaction_id", "")
        if "FAIL" in tx_id:
            raise InferenceError("Corrupt factor alignment")
        return original_predict(scoring_input)

    monkeypatch.setattr(tx_module, "predict_fraud", selective_inference)

    item1_id = f"TX-OK1-{uuid.uuid4().hex[:6]}"
    item2_id = f"TX-FAIL-{uuid.uuid4().hex[:6]}"
    item3_id = f"TX-OK2-{uuid.uuid4().hex[:6]}"

    batch_payload = {
        "batch_id": f"BATCH-MIXED-{uuid.uuid4().hex[:6]}",
        "filename": "mixed_batch.csv",
        "items": [
            make_valid_payload(external_id=item1_id),
            make_valid_payload(external_id=item2_id),
            make_valid_payload(external_id=item3_id),
        ],
    }

    response = client.post(
        "/api/v1/transactions/batch-predict",
        json=batch_payload,
        headers=auth_headers,
    )
    assert response.status_code == status.HTTP_201_CREATED
    data = response.json()
    summary = data["summary"]
    items_res = data["items"]

    assert summary["total_submitted"] == 3
    assert summary["total_processed"] == 2
    assert summary["failed_count"] == 1

    assert items_res[0]["status"] == "SUCCESS"
    assert items_res[0]["decision"] in ("APPROVE", "REVIEW", "BLOCK")

    assert items_res[1]["status"] == "ERROR"
    assert items_res[1]["decision"] == "FAILED"
    assert "Row 2" in items_res[1]["error"]
    assert "Corrupt factor alignment" in items_res[1]["error"]

    assert items_res[2]["status"] == "SUCCESS"
    assert items_res[2]["decision"] in ("APPROVE", "REVIEW", "BLOCK")

    # Confirm only OK1 and OK2 are in the database, FAIL is not
    tx1 = db_session.execute(select(Transaction).where(Transaction.external_id == item1_id)).scalar_one_or_none()
    assert tx1 is not None
    tx2 = db_session.execute(select(Transaction).where(Transaction.external_id == item2_id)).scalar_one_or_none()
    assert tx2 is None
    tx3 = db_session.execute(select(Transaction).where(Transaction.external_id == item3_id)).scalar_one_or_none()
    assert tx3 is not None


def test_batch_predict_duplicate_external_id_disambiguation(client, auth_headers, db_session):
    """Verifies that re-uploading transactions with existing external IDs disambiguates them and succeeds."""
    existing_id = f"TX-EXIST-{uuid.uuid4().hex[:6]}"
    # 1. First score a single transaction
    single_res = client.post(
        "/api/v1/transactions/predict",
        json=make_valid_payload(external_id=existing_id),
        headers=auth_headers,
    )
    assert single_res.status_code == status.HTTP_201_CREATED

    # 2. Upload batch containing the exact same external_id
    batch_payload = {
        "filename": "reupload.csv",
        "items": [make_valid_payload(external_id=existing_id)],
    }
    batch_res = client.post(
        "/api/v1/transactions/batch-predict",
        json=batch_payload,
        headers=auth_headers,
    )
    assert batch_res.status_code == status.HTTP_201_CREATED
    data = batch_res.json()
    assert data["summary"]["total_processed"] == 1
    scored_item = data["items"][0]
    assert scored_item["status"] == "SUCCESS"
    # The external_id should have been disambiguated to avoid collision
    assert scored_item["external_id"].startswith(existing_id)


