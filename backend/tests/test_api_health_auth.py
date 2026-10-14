"""Integration tests for FastAPI health endpoints, authentication, and authorization."""

from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal

import pytest
from fastapi import APIRouter, Depends, status
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_user, require_role
from backend.app.core.security import create_access_token, hash_password
from backend.app.db.session import get_db, get_session_factory
from backend.app.main import app
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


def test_health_live_probe(client):
    """Verifies that liveness probes respond with 200 OK at both root and v1 paths."""
    for path in ["/health/live", "/api/v1/health/live"]:
        response = client.get(path)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"
        assert data["service"] == "fraud-detection-api"
        assert "timestamp_utc" in data


def test_health_ready_probe_success(client):
    """Verifies that readiness probe verifies database connectivity and returns 200 OK."""
    for path in ["/health/ready", "/api/v1/health/ready"]:
        response = client.get(path)
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"
        assert data["service"] == "fraud-detection-api"
        assert "timestamp_utc" in data


def test_health_ready_probe_database_failure(client):
    """Verifies that readiness probe returns 503 when database query execution fails."""
    class BrokenSession:
        def execute(self, *args, **kwargs):
            raise RuntimeError("Database connection failed")

    def broken_get_db():
        yield BrokenSession()

    app.dependency_overrides[get_db] = broken_get_db
    try:
        response = client.get("/health/ready")
        assert response.status_code == status.HTTP_503_SERVICE_UNAVAILABLE
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["database"] == "disconnected"
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_auth_login_and_current_user_profile(client, db_session):
    """Verifies full login flow and authenticated /me profile retrieval."""
    test_email = f"analyst_{uuid.uuid4().hex[:8]}@bank.internal"
    test_password = "SecurePassword123!"

    # Create active analyst user
    user = User(
        email=test_email,
        password_hash=hash_password(test_password),
        role="ANALYST",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    # 1. Successful login
    login_response = client.post(
        "/api/v1/auth/login",
        json={"email": test_email, "password": test_password},
    )
    assert login_response.status_code == status.HTTP_200_OK
    token_data = login_response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["expires_in"] > 0

    token = token_data["access_token"]

    # 2. Authenticated /me request
    me_response = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_response.status_code == status.HTTP_200_OK
    user_data = me_response.json()
    assert user_data["email"] == test_email
    assert user_data["role"] == "ANALYST"
    assert user_data["is_active"] is True
    assert "password_hash" not in user_data  # Strict credential hygiene


def test_auth_login_invalid_credentials_prevent_enumeration(client, db_session):
    """Verifies that incorrect passwords and non-existent emails return identical generic errors."""
    test_email = f"user_{uuid.uuid4().hex[:8]}@bank.internal"
    user = User(
        email=test_email,
        password_hash=hash_password("CorrectPassword123!"),
        role="OPERATOR",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    # Wrong password for existing user
    res1 = client.post(
        "/api/v1/auth/login",
        json={"email": test_email, "password": "WrongPassword123!"},
    )
    assert res1.status_code == status.HTTP_401_UNAUTHORIZED
    assert res1.json()["detail"] == "Invalid email or password."

    # Non-existent user email
    res2 = client.post(
        "/api/v1/auth/login",
        json={"email": "nonexistent_email_404@bank.internal", "password": "AnyPassword123!"},
    )
    assert res2.status_code == status.HTTP_401_UNAUTHORIZED
    assert res2.json()["detail"] == "Invalid email or password."


def test_auth_login_inactive_user_rejected(client, db_session):
    """Verifies that inactive users cannot log in even with valid credentials."""
    test_email = f"inactive_{uuid.uuid4().hex[:8]}@bank.internal"
    test_password = "Password123!"
    user = User(
        email=test_email,
        password_hash=hash_password(test_password),
        role="OPERATOR",
        is_active=False,
    )
    db_session.add(user)
    db_session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"email": test_email, "password": test_password},
    )
    assert response.status_code == status.HTTP_403_FORBIDDEN
    assert "inactive" in response.json()["detail"].lower()


def test_auth_login_password_length_validation(client):
    """Verifies that passwords > 72 bytes are rejected by schema validation."""
    long_pwd = "a" * 73
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "test@bank.internal", "password": long_pwd},
    )
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY


def test_auth_me_unauthorized_and_invalid_tokens(client):
    """Verifies that /me rejects missing, expired, and malformed tokens with 401."""
    # 1. Missing header
    res1 = client.get("/api/v1/auth/me")
    assert res1.status_code == status.HTTP_401_UNAUTHORIZED

    # 2. Malformed token
    res2 = client.get("/api/v1/auth/me", headers={"Authorization": "Bearer malformed.token.value"})
    assert res2.status_code == status.HTTP_401_UNAUTHORIZED

    # 3. Expired token
    expired_token = create_access_token(
        subject=uuid.uuid4(),
        expires_delta=timedelta(seconds=-10),
    )
    res3 = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
    assert res3.status_code == status.HTTP_401_UNAUTHORIZED
    assert "expired" in res3.json()["detail"].lower()


def test_role_based_authorization_dependency(client, db_session):
    """Verifies role-based access restrictions for ADMIN, OPERATOR, and ANALYST."""
    # Create test users with distinct roles
    admin = User(
        email=f"admin_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash=hash_password("AdminPass123!"),
        role="ADMIN",
    )
    operator = User(
        email=f"operator_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash=hash_password("OpPass123!"),
        role="OPERATOR",
    )
    analyst = User(
        email=f"analyst_{uuid.uuid4().hex[:8]}@bank.internal",
        password_hash=hash_password("AnalystPass123!"),
        role="ANALYST",
    )
    db_session.add_all([admin, operator, analyst])
    db_session.commit()

    # Define ephemeral test routes exercising require_role
    test_router = APIRouter(prefix="/test-roles")

    @test_router.get("/admin-only")
    def admin_only_endpoint(user: User = Depends(require_role(["ADMIN"]))):
        return {"status": "ok", "user": user.email}

    @test_router.get("/operator-or-admin")
    def operator_or_admin_endpoint(user: User = Depends(require_role(["ADMIN", "OPERATOR"]))):
        return {"status": "ok", "user": user.email}

    app.include_router(test_router)

    admin_token = create_access_token(subject=admin.id, claims={"role": "ADMIN"})
    op_token = create_access_token(subject=operator.id, claims={"role": "OPERATOR"})
    analyst_token = create_access_token(subject=analyst.id, claims={"role": "ANALYST"})

    # Test /admin-only: ADMIN succeeds, OPERATOR & ANALYST are forbidden
    res_admin = client.get("/test-roles/admin-only", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_admin.status_code == status.HTTP_200_OK

    res_op = client.get("/test-roles/admin-only", headers={"Authorization": f"Bearer {op_token}"})
    assert res_op.status_code == status.HTTP_403_FORBIDDEN

    res_an = client.get("/test-roles/admin-only", headers={"Authorization": f"Bearer {analyst_token}"})
    assert res_an.status_code == status.HTTP_403_FORBIDDEN

    # Test /operator-or-admin: ADMIN & OPERATOR succeed, ANALYST is forbidden
    assert client.get("/test-roles/operator-or-admin", headers={"Authorization": f"Bearer {admin_token}"}).status_code == status.HTTP_200_OK
    assert client.get("/test-roles/operator-or-admin", headers={"Authorization": f"Bearer {op_token}"}).status_code == status.HTTP_200_OK
    assert client.get("/test-roles/operator-or-admin", headers={"Authorization": f"Bearer {analyst_token}"}).status_code == status.HTTP_403_FORBIDDEN


def test_openapi_specification_schema(client):
    """Verifies that the OpenAPI 3.x document is valid and exposes expected paths."""
    response = client.get("/api/v1/openapi.json")
    assert response.status_code == status.HTTP_200_OK
    schema = response.json()
    assert "openapi" in schema
    assert "/health/live" in schema["paths"]
    assert "/health/ready" in schema["paths"]
    assert "/api/v1/auth/login" in schema["paths"]
    assert "/api/v1/auth/me" in schema["paths"]
