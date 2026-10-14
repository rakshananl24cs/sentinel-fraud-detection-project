"""Pydantic schemas for authentication and user access control."""

from __future__ import annotations

import uuid
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """Payload for user authentication."""
    email: str = Field(
        min_length=3,
        max_length=255,
        pattern=r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
        description="Registered operator or analyst email address",
    )
    password: str = Field(min_length=1, max_length=72, description="Plaintext password")


class TokenResponse(BaseModel):
    """Bearer access token response schema."""
    access_token: str = Field(description="Signed JWT access token")
    token_type: str = Field("bearer", description="Token authentication scheme")
    expires_in: int = Field(description="Token validity lifetime in seconds")


class UserResponse(BaseModel):
    """Public user identity representation, strictly omitting password hashes."""
    id: uuid.UUID = Field(description="Unique user identifier")
    email: str = Field(description="User email address")
    role: str = Field(description="Assigned role: ADMIN, OPERATOR, or ANALYST")
    is_active: bool = Field(description="Account active status")
    created_at: datetime = Field(description="User creation timestamp in UTC")

    model_config = ConfigDict(from_attributes=True)
