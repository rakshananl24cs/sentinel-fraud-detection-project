"""Database session and engine management for SQLAlchemy 2.0.

Provides engine configuration, connection pooling, and session factories
supporting PostgreSQL via psycopg v3 and test environments.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Generator, Optional, Union

from dotenv import load_dotenv
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

# Ensure .env is loaded from workspace root if present
_env_path = Path(__file__).resolve().parents[3] / ".env"
if _env_path.exists():
    load_dotenv(_env_path)
else:
    load_dotenv()

# Initial working application database URL and name captured on startup
_INITIAL_APP_DATABASE_URL: Optional[str] = os.getenv("DATABASE_URL")
try:
    _WORKING_DATABASE_NAME: str = (
        (make_url(_INITIAL_APP_DATABASE_URL).database or "fraud_db").strip("/").lower()
        if _INITIAL_APP_DATABASE_URL
        else "fraud_db"
    )
except Exception:
    _WORKING_DATABASE_NAME: str = "fraud_db"


def get_database_url() -> str:
    """Retrieves and normalizes the database connection URL from the environment.

    Ensures that standard PostgreSQL URLs utilize the installed psycopg (v3) driver
    via the 'postgresql+psycopg://' scheme.
    """
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError(
            "DATABASE_URL is not set in the environment or .env file. "
            "Please configure the database connection string."
        )
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def get_test_database_url() -> str:
    """Retrieves and normalizes the dedicated test database connection URL from the environment.

    Strictly requires TEST_DATABASE_URL to be set in the environment or .env file.
    Tests must fail safely if TEST_DATABASE_URL is missing to ensure tests never
    silently fall back to or run against the working application database.

    Raises:
        ValueError: If TEST_DATABASE_URL is not set or empty.
    """
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        raise ValueError(
            "TEST_DATABASE_URL is not set in the environment or .env file. "
            "Automated test execution strictly requires a dedicated test database URL "
            "targeting an isolated test database (e.g. 'fraud_test_db') and will not "
            "silently fall back to the working application database."
        )

    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def verify_test_database_safety(test_url: str, working_url: Optional[str] = None) -> None:
    """Safety check preventing automated tests from running against the working application database.

    Enforces that test execution cannot target the production or working application database
    to strictly prevent data pollution, corruption, or accidental deletion.

    Raises:
        RuntimeError: If test_url targets the working application database or fails safety rules.
    """
    parsed_test = make_url(test_url)
    test_db = (parsed_test.database or "").strip("/").lower()

    # Determine working database name
    if working_url:
        work_db = (make_url(working_url).database or "").strip("/").lower()
    else:
        work_db = _WORKING_DATABASE_NAME

    # 1. Exact match with working database
    if test_db == work_db:
        raise RuntimeError(
            f"CRITICAL SAFETY INTERLOCK TRIPPED: Automated tests are configured to use working "
            f"application database '{test_db}'. Automated test execution against the working "
            f"database is strictly prohibited to prevent data loss or corruption."
        )

    # 2. Block known production/working database names
    prohibited_names = {"fraud_db", "production", "prod", "postgres", "fraud"}
    if test_db in prohibited_names:
        raise RuntimeError(
            f"CRITICAL SAFETY INTERLOCK TRIPPED: Target test database '{test_db}' is in the "
            f"prohibited databases list ({prohibited_names}). Tests must target a dedicated "
            f"test database such as 'fraud_test_db'."
        )

    # 3. Require 'test' or 'tmp' in the database name
    if "test" not in test_db and "tmp" not in test_db:
        raise RuntimeError(
            f"CRITICAL SAFETY INTERLOCK TRIPPED: Target database '{test_db}' does not contain "
            f"'test' or 'tmp' in its name. Automated tests must target a dedicated test database."
        )


def create_db_engine(database_url: Optional[str] = None) -> Engine:
    """Creates a SQLAlchemy Engine with connection health checks and pooling."""
    url = database_url or get_database_url()
    connect_args = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
        return create_engine(url, connect_args=connect_args)

    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_recycle=1800,
        connect_args=connect_args,
    )


# Lazy module-level engine and sessionmaker
_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker[Session]] = None


def get_engine() -> Engine:
    """Returns the shared database engine singleton."""
    global _engine
    if _engine is None:
        _engine = create_db_engine()
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Returns the configured sessionmaker factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(),
            autocommit=False,
            autoflush=False,
            expire_on_commit=False,
            class_=Session,
        )
    return _session_factory


def configure_database_for_testing(test_url: Optional[str] = None) -> Engine:
    """Configures the global engine and session factory to target the isolated test database.

    Enforces strict safety verification prior to binding the engine.
    """
    global _engine, _session_factory
    url = test_url or get_test_database_url()
    verify_test_database_safety(url)

    if _engine is not None:
        _engine.dispose()

    os.environ["DATABASE_URL"] = url
    _engine = create_db_engine(url)
    _session_factory = sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
        class_=Session,
    )
    return _engine


def reset_db_engine() -> None:
    """Disposes and resets the global engine and sessionmaker singletons."""
    global _engine, _session_factory
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None


def clean_test_database(engine_or_url: Optional[Union[Engine, str]] = None) -> None:
    """Safely cleans up test transactions, feedback, and model registry fixtures in the test database.

    Strictly refuses to execute against any database that fails safety checks.
    """
    if isinstance(engine_or_url, Engine):
        eng = engine_or_url
        verify_test_database_safety(eng.url.render_as_string(hide_password=True))
    elif isinstance(engine_or_url, str):
        verify_test_database_safety(engine_or_url)
        eng = create_db_engine(engine_or_url)
    else:
        eng = get_engine()
        verify_test_database_safety(eng.url.render_as_string(hide_password=True))

    with eng.connect() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE fraud_alerts, audit_logs, operator_feedback, predictions, "
                "transactions, drift_reports, model_registry, users CASCADE;"
            )
        )
        conn.commit()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a transactional database session."""
    session_factory = get_session_factory()
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
