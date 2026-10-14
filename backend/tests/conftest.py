"""Pytest configuration and isolated database fixtures for backend integration tests.

Guarantees that all automated tests execute against an isolated test database (e.g. fraud_test_db),
strictly preventing data pollution, transaction leakage, or record deletion in the working
application database.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from backend.app.db.session import (
    clean_test_database,
    configure_database_for_testing,
    create_db_engine,
    get_db,
    get_engine,
    get_session_factory,
    get_test_database_url,
    reset_db_engine,
    verify_test_database_safety,
)
from backend.app.main import app


def _ensure_test_database_ready(test_url: str) -> None:
    """Verifies that the test database exists and applies Alembic migrations if needed."""
    verify_test_database_safety(test_url)
    parsed = make_url(test_url)
    test_db_name = parsed.database

    # Connect to PostgreSQL maintenance database to verify/create test database
    maint_url = parsed.set(database="postgres").render_as_string(hide_password=False)
    maint_engine = create_engine(maint_url, isolation_level="AUTOCOMMIT")
    try:
        with maint_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :dbname"),
                {"dbname": test_db_name},
            ).scalar()
            if not exists:
                conn.execute(text(f'CREATE DATABASE "{test_db_name}" OWNER "{parsed.username}";'))
    finally:
        maint_engine.dispose()

    # Verify tables and run Alembic migrations if missing
    test_engine = create_db_engine(test_url)
    try:
        inspector = inspect(test_engine)
        table_names = set(inspector.get_table_names())
    finally:
        test_engine.dispose()

    if "alembic_version" not in table_names or "transactions" not in table_names or "fraud_alerts" not in table_names:
        alembic_ini_path = Path(__file__).resolve().parents[2] / "alembic.ini"
        alembic_cfg = Config(str(alembic_ini_path))
        saved_url = os.environ.get("DATABASE_URL")
        os.environ["DATABASE_URL"] = test_url
        try:
            command.upgrade(alembic_cfg, "head")
        finally:
            if saved_url:
                os.environ["DATABASE_URL"] = saved_url


def _test_get_db() -> Generator[Session, None, None]:
    """Dependency override ensuring FastAPI endpoints use the test database session."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def pytest_sessionstart(session):
    """Initializes the dedicated test database before any tests execute."""
    test_url = get_test_database_url()

    # 1. Enforce strict safety interlock: prevent execution if target is working DB
    verify_test_database_safety(test_url)

    # 2. Ensure test database exists and migrations are current
    _ensure_test_database_ready(test_url)

    # 3. Configure global engine and session factory to test database
    configure_database_for_testing(test_url)

    # 4. Clean any existing test records before starting test suite
    clean_test_database()

    # 5. Register FastAPI dependency override
    app.dependency_overrides[get_db] = _test_get_db


def pytest_sessionfinish(session, exitstatus):
    """Safely cleans up all test fixtures and restores environment upon test suite completion."""
    try:
        # Clean up test transactions, predictions, feedback, and model registry entries
        clean_test_database()
    finally:
        app.dependency_overrides.pop(get_db, None)
        reset_db_engine()


@pytest.fixture(autouse=True)
def assert_test_database_isolation():
    """Safety assertion executing before every test function to verify isolation from working DB."""
    eng = get_engine()
    verify_test_database_safety(str(eng.url))
