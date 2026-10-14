"""Verification script testing authentication and role assignment for demo accounts.

Does not print passwords, hashes, tokens, or sensitive information.
"""

from __future__ import annotations

import os
import httpx

BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")
PASSWORD = os.getenv("DEMO_PASSWORD", "SecurePassword123!")

TEST_CASES = [
    ("analyst@bank.internal", "ANALYST"),
    ("operator@bank.internal", "OPERATOR"),
    ("admin@bank.internal", "ADMIN"),
]


def test_demo_logins() -> None:
    with httpx.Client(base_url=BASE_URL, timeout=10.0) as client:
        for email, expected_role in TEST_CASES:
            # 1. Test POST /api/v1/auth/login
            login_res = client.post(
                "/api/v1/auth/login",
                json={"email": email, "password": PASSWORD},
            )
            assert login_res.status_code == 200, (
                f"Login failed for {email} with status {login_res.status_code}"
            )
            data = login_res.json()
            assert "access_token" in data
            assert data["token_type"] == "bearer"
            token = data["access_token"]

            # 2. Test GET /api/v1/auth/me
            me_res = client.get(
                "/api/v1/auth/me",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert me_res.status_code == 200, (
                f"Profile lookup failed for {email} with status {me_res.status_code}"
            )
            profile = me_res.json()
            assert profile["email"] == email
            assert profile["role"] == expected_role
            assert profile["is_active"] is True
            print(f"Verified {email}: HTTP 200 OK | Role: {profile['role']} | Active: {profile['is_active']}")

    print("SUCCESS: All 3 demo accounts authenticated and verified with exact roles.")


if __name__ == "__main__":
    test_demo_logins()
