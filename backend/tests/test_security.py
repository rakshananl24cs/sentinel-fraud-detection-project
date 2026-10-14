"""Unit tests for cryptographic security utilities in backend/app/core/security.py.

Verifies native bcrypt hashing, 72-byte limit enforcement, malformed hash handling,
JWT token issuance, claims validation, and expiration enforcement.
"""

from __future__ import annotations

import time
from datetime import timedelta
import uuid

import pytest

from backend.app.core.security import (
    BCRYPT_MAX_BYTES,
    SecurityError,
    TokenExpiredError,
    TokenInvalidError,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)


def test_hash_and_verify_valid_password():
    """Verifies that a standard valid password hashes and verifies correctly."""
    pwd = "StandardSecurePassword#2026!"
    hashed = hash_password(pwd)

    assert isinstance(hashed, str)
    assert hashed != pwd
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")

    # Positive verification
    assert verify_password(pwd, hashed) is True

    # Negative verification
    assert verify_password("WrongPassword123", hashed) is False


def test_empty_and_invalid_type_passwords():
    """Verifies that empty passwords raise ValueError on hash and return False on verify."""
    with pytest.raises(ValueError, match="Password cannot be empty"):
        hash_password("")

    with pytest.raises(ValueError, match="Password cannot be empty"):
        hash_password(None)  # type: ignore

    # Verify handles bad inputs safely
    assert verify_password("", "some_hash") is False
    assert verify_password(None, "some_hash") is False  # type: ignore
    assert verify_password("pwd", "") is False
    assert verify_password("pwd", None) is False  # type: ignore


def test_bcrypt_72_byte_limit_enforcement():
    """Verifies that passwords <= 72 bytes are accepted and > 72 bytes are rejected without truncation."""
    # Exactly 72 ASCII bytes
    exact_72 = "a" * BCRYPT_MAX_BYTES
    assert len(exact_72.encode("utf-8")) == 72
    hashed_72 = hash_password(exact_72)
    assert verify_password(exact_72, hashed_72) is True

    # 73 ASCII bytes must raise ValueError
    too_long = "a" * (BCRYPT_MAX_BYTES + 1)
    assert len(too_long.encode("utf-8")) == 73
    with pytest.raises(ValueError, match="exceeds bcrypt maximum length of 72 bytes"):
        hash_password(too_long)

    # Verification of a too-long candidate password returns False safely
    assert verify_password(too_long, hashed_72) is False

    # Multi-byte UTF-8 testing (e.g. '€' is 3 bytes in UTF-8)
    euro_24 = "€" * 24  # 72 bytes
    assert len(euro_24.encode("utf-8")) == 72
    hashed_euro = hash_password(euro_24)
    assert verify_password(euro_24, hashed_euro) is True

    euro_25 = "€" * 25  # 75 bytes
    assert len(euro_25.encode("utf-8")) == 75
    with pytest.raises(ValueError, match="exceeds bcrypt maximum length of 72 bytes"):
        hash_password(euro_25)


def test_malformed_hashes_safe_handling():
    """Verifies that malformed, corrupted, or non-bcrypt hashes return False without crashing."""
    malformed_hashes = [
        "not_a_bcrypt_hash",
        "$2b$12$short",
        "$2b$12$invalid_characters_!!!!@@@@$$$$%%%%",
        "1234567890",
        " ",
    ]
    for bad_hash in malformed_hashes:
        assert verify_password("Password123", bad_hash) is False


def test_jwt_access_token_lifecycle():
    """Verifies token creation, claim extraction, and expiration validation."""
    user_id = uuid.uuid4()
    claims = {"email": "analyst@bank.internal", "role": "ANALYST"}

    token = create_access_token(subject=user_id, claims=claims)
    assert isinstance(token, str)

    payload = decode_access_token(token)
    assert payload["sub"] == str(user_id)
    assert payload["email"] == "analyst@bank.internal"
    assert payload["role"] == "ANALYST"
    assert "exp" in payload
    assert "iat" in payload


def test_jwt_access_token_expiration():
    """Verifies that an expired JWT raises TokenExpiredError."""
    user_id = uuid.uuid4()
    # Issue token that already expired 10 seconds ago
    expired_token = create_access_token(
        subject=user_id,
        expires_delta=timedelta(seconds=-10),
    )

    with pytest.raises(TokenExpiredError):
        decode_access_token(expired_token)


def test_jwt_tampered_and_malformed_tokens():
    """Verifies that tampered signatures and garbage strings raise TokenInvalidError."""
    user_id = uuid.uuid4()
    valid_token = create_access_token(subject=user_id)

    # Tamper with the token signature
    parts = valid_token.split(".")
    tampered_token = f"{parts[0]}.{parts[1]}.tampered_signature_bytes"

    with pytest.raises(TokenInvalidError):
        decode_access_token(tampered_token)

    # Empty and garbage tokens
    with pytest.raises(TokenInvalidError):
        decode_access_token("")

    with pytest.raises(TokenInvalidError):
        decode_access_token("completely_invalid_garbage")
