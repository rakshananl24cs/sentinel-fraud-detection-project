"""Cryptographic security utilities for authentication and token governance.

Uses the native C/Rust bcrypt library directly (avoiding passlib compatibility issues)
and PyJWT for HMAC-SHA256 signed bearer access tokens.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Union
from uuid import UUID

import bcrypt
import jwt

from backend.app.core.config import settings

logger = logging.getLogger(__name__)

BCRYPT_MAX_BYTES: int = 72


class SecurityError(Exception):
    """Base exception for authentication and token validation failures."""
    pass


class TokenExpiredError(SecurityError):
    """Raised when an access token has expired."""
    pass


class TokenInvalidError(SecurityError):
    """Raised when an access token signature or payload is invalid or malformed."""
    pass


def hash_password(password: str) -> str:
    """Hashes a plaintext password using native bcrypt.

    Args:
        password: The plaintext password string.

    Returns:
        The bcrypt hashed password string.

    Raises:
        ValueError: If the password is empty or its UTF-8 encoding exceeds 72 bytes.
    """
    if not isinstance(password, str) or not password:
        raise ValueError("Password cannot be empty.")

    pwd_bytes = password.encode("utf-8")
    if len(pwd_bytes) > BCRYPT_MAX_BYTES:
        raise ValueError(
            f"Password exceeds bcrypt maximum length of {BCRYPT_MAX_BYTES} bytes. "
            "Truncation is strictly prohibited."
        )

    salt = bcrypt.gensalt(rounds=settings.BCRYPT_ROUNDS)
    hashed_bytes = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_bytes.decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Safely verifies a plaintext password against a stored bcrypt hash.

    Returns False for incorrect passwords, malformed hashes, empty inputs,
    or passwords exceeding 72 bytes, without exposing internal exception details.

    Args:
        plain_password: The plaintext candidate password.
        hashed_password: The stored bcrypt hash string.

    Returns:
        True if the password matches the hash, False otherwise.
    """
    if not isinstance(plain_password, str) or not plain_password:
        return False
    if not isinstance(hashed_password, str) or not hashed_password:
        return False

    pwd_bytes = plain_password.encode("utf-8")
    if len(pwd_bytes) > BCRYPT_MAX_BYTES:
        return False

    try:
        return bcrypt.checkpw(pwd_bytes, hashed_password.encode("utf-8"))
    except (ValueError, TypeError):
        # Malformed hash string or invalid bcrypt format
        return False


def create_access_token(
    subject: Union[str, UUID],
    claims: Optional[Dict[str, Any]] = None,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """Generates a signed JWT access token.

    Args:
        subject: The primary user identifier (UUID or string).
        claims: Optional additional payload claims (e.g. role, email).
        expires_delta: Optional custom token lifetime.

    Returns:
        Signed JWT string.
    """
    now = datetime.now(timezone.utc)
    if expires_delta is not None:
        expire = now + expires_delta
    else:
        expire = now + timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)

    payload: Dict[str, Any] = {
        "sub": str(subject),
        "iat": now,
        "nbf": now,
        "exp": expire,
    }
    if claims:
        payload.update(claims)

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_access_token(token: str) -> Dict[str, Any]:
    """Decodes and validates a signed JWT access token.

    Verifies signature, expiration time, and required claims.

    Args:
        token: The encoded bearer JWT string.

    Returns:
        The decoded token claims dictionary.

    Raises:
        TokenExpiredError: If the token has expired.
        TokenInvalidError: If the token signature is invalid, claims are missing,
            or the string is malformed.
    """
    if not token or not isinstance(token, str):
        raise TokenInvalidError("Token must be a non-empty string.")

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub", "iat"]},
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise TokenExpiredError("Access token signature has expired.")
    except (jwt.InvalidTokenError, jwt.DecodeError) as e:
        raise TokenInvalidError(f"Invalid access token: {type(e).__name__}")
    except Exception as e:
        raise TokenInvalidError("Failed to decode access token.")
