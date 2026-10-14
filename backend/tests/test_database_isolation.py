"""Automated verification suite for database isolation, safety interlocks, and test cleanup."""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.session import (
    clean_test_database,
    get_engine,
    get_session_factory,
    get_test_database_url,
    verify_test_database_safety,
)
from backend.app.models.transaction import Transaction


def test_safety_check_blocks_working_application_database():
    """Verifies that the safety interlock blocks execution against 'fraud_db'."""
    working_urls = [
        "postgresql+psycopg://localhost:5433/fraud_db",
        "postgresql://localhost:5433/fraud_db",
        "postgresql+psycopg://db:5432/fraud_db",
    ]
    for url in working_urls:
        with pytest.raises(RuntimeError, match="CRITICAL SAFETY INTERLOCK TRIPPED"):
            verify_test_database_safety(url)


def test_safety_check_blocks_prohibited_database_names():
    """Verifies that production, prod, and default postgres databases are rejected."""
    prohibited = ["production", "prod", "postgres", "fraud"]
    for name in prohibited:
        url = f"postgresql+psycopg://localhost:5433/{name}"
        with pytest.raises(RuntimeError, match="CRITICAL SAFETY INTERLOCK TRIPPED"):
            verify_test_database_safety(url)


def test_safety_check_requires_test_or_tmp_naming():
    """Verifies that databases without 'test' or 'tmp' in their name are rejected."""
    invalid_urls = [
        "postgresql+psycopg://localhost:5433/custom_analytics",
        "postgresql+psycopg://localhost:5433/banking_main",
    ]
    for url in invalid_urls:
        with pytest.raises(RuntimeError, match="CRITICAL SAFETY INTERLOCK TRIPPED"):
            verify_test_database_safety(url)


def test_safety_check_accepts_valid_test_databases():
    """Verifies that valid dedicated test databases are accepted without exception."""
    valid_urls = [
        "postgresql+psycopg://localhost:5433/fraud_test_db",
        "postgresql+psycopg://db:5432/fraud_test_db",
        "postgresql+psycopg://localhost:5433/test_fraud",
        "postgresql+psycopg://localhost:5433/fraud_tmp_db",
    ]
    for url in valid_urls:
        # Should not raise
        verify_test_database_safety(url)


def test_active_engine_targets_isolated_test_database():
    """Verifies that the active engine during tests targets fraud_test_db and never fraud_db."""
    engine = get_engine()
    db_name = (engine.url.database or "").strip("/").lower()
    assert db_name == "fraud_test_db", f"Expected fraud_test_db, but engine is bound to {db_name}"
    assert db_name != "fraud_db", "Active engine must not be bound to fraud_db"


def test_clean_test_database_refuses_working_database():
    """Verifies that clean_test_database refuses to execute TRUNCATE against fraud_db."""
    with pytest.raises(RuntimeError, match="CRITICAL SAFETY INTERLOCK TRIPPED"):
        clean_test_database("postgresql+psycopg://localhost:5433/fraud_db")


def test_test_database_url_missing_fails_safely(monkeypatch):
    """Verifies that get_test_database_url fails safely if TEST_DATABASE_URL is not configured."""
    monkeypatch.delenv("TEST_DATABASE_URL", raising=False)
    with pytest.raises(ValueError, match="TEST_DATABASE_URL is not set"):
        get_test_database_url()
