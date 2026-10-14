"""Idempotent seed script to provision local demonstration accounts.

Safely checks for existing user accounts before creating to prevent duplicate
key conflicts or mutating existing records.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

# Add project root to Python module search path
ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from sqlalchemy import select

from backend.app.core.security import hash_password
from backend.app.db.session import get_session_factory
from backend.app.models.user import User

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed_demo_users")

DEMO_ACCOUNTS = [
    {
        "email": "analyst@bank.internal",
        "role": "ANALYST",
    },
    {
        "email": "operator@bank.internal",
        "role": "OPERATOR",
    },
    {
        "email": "admin@bank.internal",
        "role": "ADMIN",
    },
]


def seed_demo_users(password: str) -> None:
    """Provisions missing demo accounts without overwriting or deleting records."""
    if not password:
        raise ValueError("Password cannot be empty.")

    session_factory = get_session_factory()
    with session_factory() as session:
        created_count = 0
        skipped_count = 0

        for acc in DEMO_ACCOUNTS:
            normalized_email = acc["email"].lower().strip()
            existing = session.execute(
                select(User).where(User.email == normalized_email)
            ).scalar_one_or_none()

            if existing is not None:
                logger.info(f"Account '{normalized_email}' already exists (role={existing.role}). Skipping.")
                skipped_count += 1
                continue

            pw_hash = hash_password(password)
            user = User(
                email=normalized_email,
                password_hash=pw_hash,
                role=acc["role"],
                is_active=True,
            )
            session.add(user)
            logger.info(f"Provisioned demo account '{normalized_email}' with role '{acc['role']}'.")
            created_count += 1

        session.commit()
        logger.info(f"Seed complete: {created_count} accounts created, {skipped_count} accounts already existed.")


if __name__ == "__main__":
    demo_password = os.getenv("DEMO_PASSWORD", "SecurePassword123!")
    seed_demo_users(demo_password)
